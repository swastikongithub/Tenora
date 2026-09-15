"""
Online resident payments for property bills (P9).

Resident -> provider (Cashfree) -> workspace owner -> Bill -> Receipt. Nothing here
touches the Tenora subscription (apps.billing): a different gateway, different
credentials, a different webhook route, and a property payment is never
evidence of a subscription payment.

The browser is never authoritative. It can only ask to START a checkout for a
bill it can already see; the amount, the bill's ownership, whether money
arrived and what the bill now says are all decided here:

  start()          lock the bill, compute the FULL amount due, reuse or create an
                   OnlinePaymentAttempt, create the provider order with a stable
                   idempotency key (outside the DB lock), return checkout data.
  apply_payment()  a verified provider payment (webhook or status query) settles
                   the bill through PaymentService.record — the same path an owner's
                   offline payment takes — under row locks; or, if the capture no
                   longer fits the bill, marks the attempt UNAPPLIED for refund.
  reconcile()      read the provider's payments for an open attempt and apply /
                   expire it. Used on the return page, before a new checkout, and
                   by the scheduled sweep.
  refund()         owner-initiated refund of an UNAPPLIED capture.

Double settlement is prevented by the database, not by a pre-check: the attempt's
one-to-one `payment`, the Payment `idempotency_key` ("online:<attempt>") and
`reference` ("cashfree:<payment id>") are each unique, and the bill row is locked
while the amount is applied.
"""

import logging
import re
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from apps.properties.aging import server_today
from apps.properties.gateway import get_property_gateway
from apps.properties.gateway.base import (
    CustomerDetails,
    GatewayRejected,
    GatewayUnavailable,
    IdempotencyConflict,
    OrderAlreadyExists,
    ProviderPayment,
    ProviderPaymentStatus,
)
from apps.properties.models import Bill, OnlinePaymentAttempt, Payment
from apps.properties.services import (
    OPEN_BILL_STATUSES,
    DomainError,
    PaymentService,
    _audit,
    _month_label,
    _owners,
)

logger = logging.getLogger(__name__)

S = OnlinePaymentAttempt.Status
OPEN = (S.CREATED, S.ACTIVE)
SUPPORTED_CURRENCY = "INR"
#: Don't hand out a checkout that expires almost immediately; start a new one.
MIN_REMAINING = timedelta(minutes=3)
#: Status reads on the return page query the provider at most this often.
RECHECK_INTERVAL = timedelta(seconds=10)
#: A CREATED checkout whose provider order still can't be confirmed after this
#: long is replaced rather than retried with the same idempotency key forever.
STUCK_CREATE_AFTER = timedelta(seconds=60)
FAILED_PAYMENT_STATUSES = {
    ProviderPaymentStatus.FAILED,
    ProviderPaymentStatus.USER_DROPPED,
    ProviderPaymentStatus.CANCELLED,
}
REFUND_NAMESPACE = uuid.UUID("5f0a8f0e-8c0e-4c39-9f2e-7b8c7c1d5a11")


def webhook_path():
    return "/api/webhooks/cashfree/property-payments/"


def _customer_phone(resident):
    """Cashfree requires a 10-digit customer phone. Taken from the resident
    profile, then the account; a +91/91 prefix is accepted."""
    for raw in (resident.phone, getattr(resident.user, "phone", "")):
        digits = re.sub(r"\D", "", raw or "")
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        if len(digits) == 10:
            return digits
    return ""


def display_state(attempt):
    """What the resident should be told — derived only from server state."""
    if attempt.status == S.SUCCEEDED:
        return "succeeded"
    if attempt.status in OPEN:
        return "failed" if attempt.last_payment_status in FAILED_PAYMENT_STATUSES else "processing"
    if attempt.status == S.EXPIRED:
        return "expired"
    if attempt.status == S.FAILED:
        return "failed"
    if attempt.unapplied_reason in ("BILL_NOT_PAYABLE", "OVERPAYMENT", "BILL_ALREADY_SETTLED"):
        return "already_paid"
    return "needs_review"


def eligibility(*, user, bill, is_manager):
    """The `online_payment` block on a bill: can THIS viewer pay THIS bill now?"""
    open_attempt = (
        OnlinePaymentAttempt.objects.for_tenant(bill.tenant).filter(bill=bill, status__in=OPEN).first()
    )
    due = max(bill.total_cents - bill.amount_paid_cents, 0) if bill.status in OPEN_BILL_STATUSES else 0
    reason = None
    if not settings.PROPERTY_ONLINE_PAYMENTS_ENABLED:
        reason = "DISABLED"
    elif is_manager or bill.resident.user_id != user.id:
        reason = "NOT_RESIDENT"
    elif bill.status not in OPEN_BILL_STATUSES or due <= 0:
        reason = "NOTHING_DUE"
    elif bill.currency != SUPPORTED_CURRENCY:
        reason = "CURRENCY_NOT_SUPPORTED"
    elif not _customer_phone(bill.resident):
        reason = "PHONE_REQUIRED"
    return {
        "available": reason is None,
        "reason": reason,
        "amount_cents": due,
        "currency": bill.currency,
        "open_attempt": attempt_payload(open_attempt) if open_attempt and reason != "NOT_RESIDENT" else None,
    }


def attempt_payload(attempt, *, include_session=False):
    """The only representation of an attempt that leaves the server. No raw
    provider payloads, no secrets."""
    data = {
        "id": str(attempt.id),
        "bill_id": str(attempt.bill_id),
        "status": attempt.status,
        "display_state": display_state(attempt),
        "amount_cents": attempt.amount_cents,
        "currency": attempt.currency,
        "order_id": attempt.provider_order_id,
        "expires_at": attempt.expires_at,
        "failure_message": attempt.failure_message,
        "unapplied_reason": attempt.unapplied_reason,
        "refund_status": attempt.refund_status,
        "receipt_id": None,
        "created_at": attempt.created_at,
        "finalized_at": attempt.finalized_at,
    }
    if attempt.payment_id:
        receipt = getattr(attempt.payment, "receipt", None)
        data["receipt_id"] = str(receipt.id) if receipt else None
    if include_session:
        data["payment_session_id"] = attempt.payment_session_id
        data["checkout_mode"] = get_property_gateway().checkout_mode
    return data


class OnlinePaymentService:
    # --- start ----------------------------------------------------------------

    @staticmethod
    def start(*, user, tenant, bill):
        if not settings.PROPERTY_ONLINE_PAYMENTS_ENABLED:
            raise DomainError("ONLINE_PAYMENTS_DISABLED", "Online payments aren’t available for this workspace.", status_code=409)
        if bill.tenant_id != tenant.id or bill.resident.user_id != user.id:
            raise DomainError("NOT_FOUND", "Bill not found.", status_code=404)
        phone = _customer_phone(bill.resident)
        if not phone:
            raise DomainError(
                "PHONE_REQUIRED",
                "Add a 10-digit mobile number in Settings to pay online.",
                field="phone",
                status_code=409,
            )

        # A checkout may already be open. Ask the provider first: it may have
        # been paid a moment ago, in which case there is nothing to start.
        existing = OnlinePaymentAttempt.objects.for_tenant(tenant).filter(bill=bill, status__in=OPEN).first()
        if existing and existing.status == S.ACTIVE:
            OnlinePaymentService.reconcile(existing, force=True)

        now = timezone.now()
        ttl = timedelta(minutes=settings.PROPERTY_ONLINE_PAYMENT_TTL_MINUTES)
        gateway = get_property_gateway()
        try:
            with transaction.atomic():
                bill = Bill.objects.select_for_update(of=("self",)).select_related("resident__user").get(pk=bill.pk)
                if bill.status not in OPEN_BILL_STATUSES:
                    raise DomainError("BILL_NOT_PAYABLE", "This bill has nothing left to pay.", status_code=409)
                if bill.currency != SUPPORTED_CURRENCY:
                    raise DomainError("CURRENCY_NOT_SUPPORTED", "Online payment is available for INR bills only.", status_code=409)
                due = bill.total_cents - bill.amount_paid_cents
                if due <= 0:
                    raise DomainError("BILL_NOT_PAYABLE", "This bill has nothing left to pay.", status_code=409)

                attempt = (
                    OnlinePaymentAttempt.objects.for_tenant(tenant)
                    .select_for_update()
                    .filter(bill=bill, status__in=OPEN)
                    .first()
                )
                if attempt and (attempt.amount_cents != due or attempt.expires_at - now < MIN_REMAINING):
                    # The bill changed or the checkout is about to lapse. Close it
                    # locally; a late capture on it is still applied if it fits,
                    # otherwise it becomes UNAPPLIED (refund), never a second credit.
                    attempt.status = S.EXPIRED
                    attempt.failure_message = "Replaced by a new checkout."
                    attempt.finalized_at = now
                    attempt.save(update_fields=["status", "failure_message", "finalized_at", "updated_at"])
                    attempt = None
                if attempt is None:
                    attempt_id = uuid.uuid4()
                    attempt = OnlinePaymentAttempt.objects.create(
                        id=attempt_id,
                        tenant=tenant,
                        bill=bill,
                        resident=bill.resident,
                        initiated_by=user,
                        provider=gateway.name,
                        provider_order_id=f"TNR{attempt_id.hex}",
                        amount_cents=due,
                        currency=bill.currency,
                        expires_at=now + ttl,
                    )
                    _audit(
                        actor=user,
                        tenant=tenant,
                        action="online_payment.started",
                        target_type="OnlinePaymentAttempt",
                        target_id=attempt.id,
                        summary=f"Online checkout of {due} {bill.currency} for {bill.bill_number}",
                        metadata={"bill_id": str(bill.id), "amount_cents": due, "order_id": attempt.provider_order_id},
                    )
        except IntegrityError:
            # A concurrent start won the one-open-attempt constraint; use its row.
            attempt = OnlinePaymentAttempt.objects.for_tenant(tenant).filter(bill=bill, status__in=OPEN).first()
            if attempt is None:
                raise DomainError("PAYMENT_IN_PROGRESS", "A payment is already being started. Try again.", status_code=409)

        return OnlinePaymentService._ensure_provider_order(attempt, gateway=gateway, phone=phone)

    @staticmethod
    def _ensure_provider_order(attempt, *, gateway, phone):
        if attempt.status == S.ACTIVE and attempt.payment_session_id:
            return attempt
        bill = attempt.bill
        resident = attempt.resident
        notify_url = ""
        if settings.BACKEND_PUBLIC_URL.startswith("https://"):
            notify_url = settings.BACKEND_PUBLIC_URL.rstrip("/") + webhook_path()
        return_url = f"{settings.FRONTEND_URL.rstrip('/')}/bills/{bill.id}?online_payment={attempt.id}"
        try:
            created = gateway.create_payment_order(
                order_id=attempt.provider_order_id,
                amount_cents=attempt.amount_cents,
                currency=attempt.currency,
                customer=CustomerDetails(
                    customer_id=resident.id.hex,
                    phone=phone,
                    name=resident.display_name,
                    email=resident.user.email if not resident.user.email.endswith(".invalid") else "",
                ),
                expires_at=attempt.expires_at,
                return_url=return_url,
                notify_url=notify_url,
                note=f"Tenora bill {bill.bill_number}"[:200],
                tags={"tenora_attempt": str(attempt.id), "bill_number": bill.bill_number},
                idempotency_key=str(attempt.idempotency_key),
            )
            session_id, order_ref = created.payment_session_id, created.provider_order_ref
        except (OrderAlreadyExists, IdempotencyConflict) as exc:
            # Another request for this same checkout created (or is creating) the
            # order. Read it back; if it isn't readable yet, report "in progress"
            # WITHOUT failing the attempt — the concurrent request will finish it.
            in_progress = isinstance(exc, IdempotencyConflict)
            try:
                state = gateway.get_order(attempt.provider_order_id)
            except GatewayUnavailable:
                state = None
            if state is None or not state.payment_session_id:
                if in_progress:
                    if timezone.now() - attempt.created_at > STUCK_CREATE_AFTER:
                        # Still unconfirmed long after the first try: stop reusing
                        # this key so the next click starts a fresh checkout.
                        with transaction.atomic():
                            locked = OnlinePaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
                            if locked.status == S.CREATED:
                                locked.status = S.EXPIRED
                                locked.failure_message = "The checkout couldn’t be confirmed and was replaced."
                                locked.finalized_at = timezone.now()
                                locked.save(update_fields=["status", "failure_message", "finalized_at", "updated_at"])
                    raise DomainError(
                        "PAYMENT_IN_PROGRESS",
                        "This payment is already being started. Try again in a moment.",
                        status_code=409,
                    )
                raise DomainError("PAYMENT_PROVIDER_UNAVAILABLE", "Couldn’t reach the payment provider. Try again.", status_code=503)
            session_id, order_ref = state.payment_session_id, ""
        except GatewayRejected as exc:
            with transaction.atomic():
                locked = OnlinePaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
                if locked.status == S.CREATED:
                    locked.status = S.FAILED
                    locked.failure_message = (exc.message or "Rejected by the payment provider.")[:255]
                    locked.finalized_at = timezone.now()
                    locked.save(update_fields=["status", "failure_message", "finalized_at", "updated_at"])
            raise DomainError(
                "PAYMENT_PROVIDER_REJECTED",
                "The payment provider couldn’t start this payment. Try again later.",
                status_code=502,
            )
        except GatewayUnavailable:
            # Outcome unknown: keep the CREATED row. A retry reuses the same
            # order id and idempotency key, so it can never create a second order.
            raise DomainError("PAYMENT_PROVIDER_UNAVAILABLE", "Couldn’t reach the payment provider. Try again.", status_code=503)

        with transaction.atomic():
            locked = OnlinePaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
            if locked.status == S.CREATED:
                locked.status = S.ACTIVE
                locked.payment_session_id = session_id
                locked.provider_order_ref = order_ref or locked.provider_order_ref
                locked.save(update_fields=["status", "payment_session_id", "provider_order_ref", "updated_at"])
        attempt = OnlinePaymentAttempt.objects.select_related("bill", "payment").get(pk=attempt.pk)
        if attempt.status != S.ACTIVE or not attempt.payment_session_id:
            # Never hand the browser a checkout that isn't payable.
            raise DomainError("PAYMENT_IN_PROGRESS", "This payment couldn’t be started. Try again.", status_code=409)
        return attempt

    # --- settlement ---------------------------------------------------------------

    @staticmethod
    def apply_payment(*, order_id, payment: ProviderPayment):
        """
        Apply one provider payment for `order_id`. Returns a short outcome code.
        Idempotent: re-delivering the same event, or the webhook and a status
        query racing each other, settles the bill at most once.

        Cross-tenant lookup by provider order id is intentional (like the
        subscription webhook's correlation id): the provider calls with no tenant
        context, and the attempt row carries the tenant from here on.
        """
        try:
            with transaction.atomic():
                attempt = (
                    OnlinePaymentAttempt.objects.select_for_update(of=("self",))
                    .select_related("tenant", "bill", "resident__user")
                    .filter(provider_order_id=order_id)
                    .first()
                )
                if attempt is None:
                    return "unknown_order"
                now = timezone.now()
                attempt.last_checked_at = now

                if payment.status != ProviderPaymentStatus.SUCCESS:
                    if attempt.status in OPEN:
                        attempt.last_payment_status = payment.status
                        if payment.status in FAILED_PAYMENT_STATUSES:
                            attempt.failure_message = (payment.message or "The payment didn’t go through.")[:255]
                    attempt.save(update_fields=["last_checked_at", "last_payment_status", "failure_message", "updated_at"])
                    return "status_recorded"

                if attempt.status == S.SUCCEEDED:
                    if attempt.provider_payment_id == payment.provider_payment_id:
                        attempt.save(update_fields=["last_checked_at", "updated_at"])
                        return "already_settled"
                    _audit(
                        actor=None,
                        tenant=attempt.tenant,
                        action="online_payment.duplicate_capture",
                        target_type="OnlinePaymentAttempt",
                        target_id=attempt.id,
                        summary=f"Second successful provider payment on settled order {order_id}",
                        metadata={"provider_payment_id": payment.provider_payment_id, "amount_cents": payment.amount_cents},
                    )
                    return "duplicate_capture"
                if attempt.status in (S.UNAPPLIED, S.REFUND_PENDING, S.REFUNDED):
                    return "already_unapplied"

                attempt.provider_payment_id = payment.provider_payment_id
                attempt.last_payment_status = payment.status
                if payment.currency != attempt.currency or payment.amount_cents != attempt.amount_cents:
                    return OnlinePaymentService._unapply(attempt, "AMOUNT_MISMATCH", payment)

                try:
                    with transaction.atomic():
                        recorded, _ = PaymentService.record(
                            actor=None,
                            tenant=attempt.tenant,
                            bill=attempt.bill,
                            amount_cents=attempt.amount_cents,
                            payment_date=server_today(),
                            method=Payment.Method.ONLINE,
                            reference=f"cashfree:{payment.provider_payment_id}"[:128],
                            notes=f"Online payment, order {order_id}",
                            idempotency_key=f"online:{attempt.id}",
                        )
                except DomainError as exc:
                    reason = "BILL_ALREADY_SETTLED" if exc.code == "BILL_NOT_PAYABLE" else exc.code
                    return OnlinePaymentService._unapply(attempt, reason, payment)

                attempt.status = S.SUCCEEDED
                attempt.payment = recorded
                attempt.finalized_at = now
                attempt.failure_message = ""
                attempt.save()
                _audit(
                    actor=None,
                    tenant=attempt.tenant,
                    action="online_payment.settled",
                    target_type="OnlinePaymentAttempt",
                    target_id=attempt.id,
                    summary=f"Online payment {payment.provider_payment_id} settled {attempt.amount_cents} on {attempt.bill.bill_number}",
                    metadata={
                        "payment_id": str(recorded.id),
                        "bill_id": str(attempt.bill_id),
                        "provider_payment_id": payment.provider_payment_id,
                    },
                )
                return "settled"
        except IntegrityError:
            # The same provider payment id is already attached to another attempt.
            logger.warning("online payment %s for order %s already recorded elsewhere", payment.provider_payment_id, order_id)
            return "duplicate_provider_payment"

    @staticmethod
    def _unapply(attempt, reason, payment):
        attempt.status = S.UNAPPLIED
        attempt.unapplied_reason = reason[:40]
        attempt.finalized_at = timezone.now()
        attempt.failure_message = "Payment received but not applied to the bill; it will be refunded."
        attempt.save()
        _audit(
            actor=None,
            tenant=attempt.tenant,
            action="online_payment.unapplied",
            target_type="OnlinePaymentAttempt",
            target_id=attempt.id,
            summary=f"Captured online payment not applied to {attempt.bill.bill_number}: {reason}",
            metadata={
                "reason": reason,
                "provider_payment_id": payment.provider_payment_id,
                "captured_amount_cents": payment.amount_cents,
                "captured_currency": payment.currency,
                "expected_amount_cents": attempt.amount_cents,
            },
        )
        bill = attempt.bill
        NotificationService.notify(
            recipient=attempt.resident.user,
            kind=Notification.Kind.ONLINE_PAYMENT_UNAPPLIED,
            tenant=attempt.tenant,
            title=f"Your online payment for the {_month_label(bill.period_start)} bill couldn’t be applied",
            body="The bill was already settled or changed. Your property owner will refund it.",
            data={"bill_id": str(bill.id), "online_payment_id": str(attempt.id)},
            dedupe_key=f"online-unapplied:{attempt.id}",
        )
        for owner in _owners(attempt.tenant):
            NotificationService.notify(
                recipient=owner,
                kind=Notification.Kind.ONLINE_PAYMENT_UNAPPLIED,
                tenant=attempt.tenant,
                title=f"Online payment from {bill.resident_name} needs a refund",
                body=f"Bill {bill.bill_number}: {reason.replace('_', ' ').lower()}.",
                data={"bill_id": str(bill.id), "online_payment_id": str(attempt.id)},
                dedupe_key=f"online-unapplied:{attempt.id}",
            )
        return "unapplied"

    # --- reconciliation -------------------------------------------------------------

    @staticmethod
    def reconcile(attempt, *, force=False):
        """Bring an open attempt in line with the provider. Never raises for a
        provider outage — the attempt simply stays as it was."""
        attempt = OnlinePaymentAttempt.objects.get(pk=attempt.pk)
        if attempt.status not in OPEN:
            return attempt
        now = timezone.now()
        if not force and attempt.last_checked_at and now - attempt.last_checked_at < RECHECK_INTERVAL:
            return attempt
        gateway = get_property_gateway()
        try:
            payments = gateway.get_payment_status(attempt.provider_order_id) if attempt.status == S.ACTIVE else []
        except (GatewayUnavailable, GatewayRejected):
            OnlinePaymentAttempt.objects.filter(pk=attempt.pk).update(last_checked_at=now)
            return OnlinePaymentAttempt.objects.get(pk=attempt.pk)

        successes = [p for p in payments if p.status == ProviderPaymentStatus.SUCCESS]
        for success in successes:
            OnlinePaymentService.apply_payment(order_id=attempt.provider_order_id, payment=success)
        if not successes:
            pending = any(p.status == ProviderPaymentStatus.PENDING for p in payments)
            with transaction.atomic():
                locked = OnlinePaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
                if locked.status in OPEN:
                    locked.last_checked_at = now
                    if payments:
                        latest = payments[-1]
                        locked.last_payment_status = latest.status
                        if latest.status in FAILED_PAYMENT_STATUSES:
                            locked.failure_message = (latest.message or "The payment didn’t go through.")[:255]
                    if not pending and now >= locked.expires_at:
                        locked.status = S.EXPIRED
                        locked.finalized_at = now
                        if not locked.failure_message:
                            locked.failure_message = "The checkout expired before payment."
                    locked.save()
        return OnlinePaymentAttempt.objects.get(pk=attempt.pk)

    @staticmethod
    def reconcile_open(*, now=None, limit=200):
        """Scheduled sweep: every open attempt that is past expiry, or old enough
        that its webhook should have arrived, and not checked recently."""
        now = now or timezone.now()
        stale = (
            OnlinePaymentAttempt.objects.filter(status__in=OPEN, created_at__lte=now - timedelta(minutes=2))
            .exclude(last_checked_at__gt=now - timedelta(minutes=5))
            .order_by("created_at")[:limit]
        )
        counts = {"checked": 0, "settled": 0, "expired": 0}
        for attempt in stale:
            before = attempt.status
            after = OnlinePaymentService.reconcile(attempt, force=True).status
            counts["checked"] += 1
            if after == S.SUCCEEDED:
                counts["settled"] += 1
            elif after == S.EXPIRED and before != S.EXPIRED:
                counts["expired"] += 1
        return counts

    # --- refunds ----------------------------------------------------------------------

    @staticmethod
    def refund(*, actor, tenant, attempt):
        """Refund a capture that could not be applied to its bill. Applied
        payments are not refunded here: reversing a settled bill is outside P9."""
        if attempt.tenant_id != tenant.id:
            raise DomainError("NOT_FOUND", "Online payment not found.", status_code=404)
        refund_id = f"RF{attempt.id.hex}"
        with transaction.atomic():
            locked = OnlinePaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
            if locked.status == S.REFUNDED:
                return locked
            if locked.status not in (S.UNAPPLIED, S.REFUND_PENDING):
                raise DomainError(
                    "REFUND_NOT_ALLOWED",
                    "Only an online payment that couldn’t be applied to its bill can be refunded here.",
                    status_code=409,
                )
            locked.status = S.REFUND_PENDING
            locked.refund_id = refund_id
            locked.save(update_fields=["status", "refund_id", "updated_at"])
            _audit(
                actor=actor,
                tenant=tenant,
                action="online_payment.refund_requested",
                target_type="OnlinePaymentAttempt",
                target_id=locked.id,
                summary=f"Refund requested for online payment {locked.provider_payment_id}",
                metadata={"refund_id": refund_id, "amount_cents": locked.amount_cents},
            )
        try:
            result = get_property_gateway().refund_payment(
                order_id=attempt.provider_order_id,
                refund_id=refund_id,
                amount_cents=attempt.amount_cents,
                note="Tenora online payment not applied",
                idempotency_key=str(uuid.uuid5(REFUND_NAMESPACE, refund_id)),
            )
        except GatewayUnavailable:
            raise DomainError("PAYMENT_PROVIDER_UNAVAILABLE", "Couldn’t reach the payment provider. Try again.", status_code=503)
        except GatewayRejected as exc:
            raise DomainError("REFUND_REJECTED", f"The payment provider refused the refund: {exc.message}"[:255], status_code=502)
        with transaction.atomic():
            locked = OnlinePaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
            locked.refund_status = result.status
            if result.status == "SUCCESS" and locked.status != S.REFUNDED:
                locked.status = S.REFUNDED
                locked.refunded_at = timezone.now()
                _audit(
                    actor=actor,
                    tenant=tenant,
                    action="online_payment.refunded",
                    target_type="OnlinePaymentAttempt",
                    target_id=locked.id,
                    summary=f"Refunded online payment {locked.provider_payment_id}",
                    metadata={"refund_id": refund_id, "amount_cents": result.amount_cents},
                )
            locked.save()
        return locked
