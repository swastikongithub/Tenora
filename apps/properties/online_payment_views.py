"""
P9 online resident payment endpoints.

Tenant-scoped (X-Tenant-ID + ACTIVE membership, like every property endpoint):
  POST /api/bills/<id>/online-payment/       resident starts checkout of own bill
  GET  /api/online-payments/                  owner: attempts (filter ?status=)
  GET  /api/online-payments/<id>/             resident (own) / owner: server status
  POST /api/online-payments/<id>/refund/      owner: refund an UNAPPLIED capture

Provider-facing (no user, no tenant; the signature is the authentication):
  POST /api/webhooks/cashfree/property-payments/

Request bodies are never read on the start endpoint: amount, bill, resident and
workspace all come from the URL id resolved inside the caller's own scope and
from server state. Responses carry `attempt_payload` only — never a raw
provider object.
"""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.properties.gateway import get_property_gateway
from apps.properties.gateway.base import WebhookEventKind, WebhookRejected
from apps.properties.models import OnlinePaymentAttempt, PropertyPaymentWebhookEvent
from apps.properties.online_payments import OnlinePaymentService, attempt_payload
from apps.properties.views import PropertyPagination, WorkspaceAPIView, visible_bills

logger = logging.getLogger(__name__)


def visible_attempts(view):
    qs = OnlinePaymentAttempt.objects.for_tenant(view.request.tenant).select_related("bill", "payment__receipt")
    if view.is_manager("payments.manage"):
        return qs
    return qs.filter(resident__user=view.request.user)


class BillOnlinePaymentView(WorkspaceAPIView):
    def post(self, request, pk):
        bill = self.get_scoped(visible_bills(request).select_related("resident__user", "tenant"), pk)
        attempt = OnlinePaymentService.start(user=request.user, tenant=request.tenant, bill=bill)
        return Response(attempt_payload(attempt, include_session=True), status=status.HTTP_201_CREATED)


class OnlinePaymentListView(WorkspaceAPIView):
    capabilities = {"GET": "payments.manage"}

    def get(self, request):
        qs = visible_attempts(self).order_by("-created_at")
        wanted = request.query_params.get("status")
        if wanted:
            qs = qs.filter(status__in=[s for s in wanted.split(",") if s in OnlinePaymentAttempt.Status.values])
        paginator = PropertyPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        rows = []
        for attempt in page:
            row = attempt_payload(attempt)
            row.update(
                bill_number=attempt.bill.bill_number,
                resident_name=attempt.bill.resident_name,
                unit_identifier=attempt.bill.unit_identifier,
                period_start=attempt.bill.period_start,
            )
            rows.append(row)
        return paginator.get_paginated_response(rows)


class OnlinePaymentDetailView(WorkspaceAPIView):
    def get(self, request, pk):
        attempt = self.get_scoped(visible_attempts(self), pk)
        # The browser's return from checkout proves nothing. Ask the provider
        # (rate-limited inside reconcile) and report only what the server holds.
        attempt = OnlinePaymentService.reconcile(attempt)
        attempt = OnlinePaymentAttempt.objects.select_related("bill", "payment__receipt").get(pk=attempt.pk)
        return Response(attempt_payload(attempt))


class OnlinePaymentRefundView(WorkspaceAPIView):
    capabilities = {"POST": "payments.manage"}

    def post(self, request, pk):
        attempt = self.get_scoped(visible_attempts(self), pk)
        attempt = OnlinePaymentService.refund(actor=request.user, tenant=request.tenant, attempt=attempt)
        attempt = OnlinePaymentAttempt.objects.select_related("bill", "payment__receipt").get(pk=attempt.pk)
        return Response(attempt_payload(attempt))


class CashfreePropertyPaymentWebhookView(APIView):
    """
    Cashfree payment webhooks for property-bill checkouts.

    Unauthenticated by design (authentication_classes = []), so
    TenantJWTAuthentication never runs and the route needs no GLOBAL_PATHS entry
    — the same arrangement as the subscription webhook, on a separate URL with
    separate verification. Order:
      1. read the RAW body bytes before anything parses them;
      2. verify x-webhook-signature over timestamp + raw body, and the timestamp
         window — failure is 400 and nothing is stored;
      3. parse; store the delivery under a unique dedupe key (a redelivery
         collides and is acknowledged without being processed again);
      4. apply the payment idempotently; a processing failure is recorded on the
         event row and still answered 200 (the reconciliation sweep, which asks
         Cashfree directly, finishes the job — retrying the webhook would not).
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw_body = request.body
        gateway = get_property_gateway()
        try:
            gateway.verify_webhook(request.headers, raw_body)
        except WebhookRejected as exc:
            logger.warning("property payment webhook rejected: %s", exc.reason)
            return Response({"detail": "Invalid webhook."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            event = gateway.parse_webhook(request.headers, raw_body)
        except ValueError:
            return Response({"detail": "Invalid webhook."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                stored = PropertyPaymentWebhookEvent.objects.create(
                    provider=gateway.name,
                    dedupe_key=event.dedupe_key,
                    event_type=event.raw_type,
                    provider_order_id=event.order_id[:64],
                    provider_payment_id=(event.payment.provider_payment_id if event.payment else "")[:64],
                    payload=event.payload,
                )
        except IntegrityError:
            return Response({"status": "duplicate"}, status=status.HTTP_200_OK)

        outcome = "ignored"
        error = ""
        try:
            if event.kind != WebhookEventKind.OTHER and event.payment is not None and event.order_id:
                outcome = OnlinePaymentService.apply_payment(order_id=event.order_id, payment=event.payment)
        except Exception as exc:  # noqa: BLE001 — never let processing change the ack
            logger.exception("property payment webhook processing failed for order %s", event.order_id)
            outcome, error = "error", exc.__class__.__name__
        PropertyPaymentWebhookEvent.objects.filter(pk=stored.pk).update(
            processed_at=timezone.now(), outcome=outcome[:40], processing_error=error[:120]
        )
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


__all__ = [
    "BillOnlinePaymentView",
    "CashfreePropertyPaymentWebhookView",
    "OnlinePaymentDetailView",
    "OnlinePaymentListView",
    "OnlinePaymentRefundView",
]
