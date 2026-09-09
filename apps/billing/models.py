import uuid

from django.db import models

from apps.billing.gateway.base import EventType
from apps.tenants.managers import TenantScopedManager
from apps.tenants.models import Tenant


class Plan(models.Model):
    """
    Global/platform data — not tenant-owned, so it deliberately does
    NOT use TenantScopedManager. Any tenant can read any active plan.
    """

    class Interval(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        ANNUAL = "ANNUAL", "Annual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    price_cents = models.IntegerField()  # never floats for money
    currency = models.CharField(max_length=3, default="USD")
    # Billing period length. Nothing consumes this in Phase 1 — it exists
    # so Phase 2 proration has a period to work against and the pricing UI
    # has a real field to toggle. No proration logic here yet.
    interval = models.CharField(
        max_length=10, choices=Interval.choices, default=Interval.MONTHLY
    )
    is_active = models.BooleanField(default=True)
    # The corresponding gateway-side plan ID, populated by
    # `manage.py sync_razorpay_plans` via the active adapter. Provider-neutral
    # name (payment-gateway-adapter-spec.md §4.5). Nullable so existing rows and
    # freshly-created local Plans are valid before a sync; unique so a local
    # Plan maps to exactly one gateway plan (Postgres allows multiple NULLs
    # under a unique constraint, which is what we want).
    external_plan_id = models.CharField(
        max_length=255, null=True, blank=True, unique=True
    )

    def __str__(self):
        return f"{self.name} ({self.price_cents / 100:.2f} {self.currency})"


class Subscription(models.Model):
    """
    Tenant-owned. Uses OneToOneField, not ForeignKey + a separate
    unique constraint — the domain rule is "one tenant has exactly
    one subscription" in Phase 1, so the field type should say that
    directly rather than a FK that merely happens to be constrained
    to one-per-tenant.

    State machine is enforced in services.py, not here — this class
    stays a plain data model. Don't assign `.status = "..."` directly
    from views/serializers; go through SubscriptionService so illegal
    transitions (e.g. CANCELED -> ACTIVE) can't slip in from a random
    call site.
    """

    class Status(models.TextChoices):
        TRIALING = "TRIALING", "Trialing"
        ACTIVE = "ACTIVE", "Active"
        PAST_DUE = "PAST_DUE", "Past due"
        CANCELED = "CANCELED", "Canceled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(
        Tenant, on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=10, choices=Status.choices)
    # The gateway-side subscription id, set when D3 first creates this row from a
    # verified ACTIVATED webhook. Provider-neutral name, matching the sibling
    # fields (payment-gateway-adapter-spec.md §4.5). Nullable so pre-D3 rows and
    # the seed/demo path stay valid; unique-when-set so every later event
    # (CHARGED, CANCELLED, …) correlates to exactly one local row. Postgres
    # allows multiple NULLs under a unique constraint.
    external_subscription_id = models.CharField(
        max_length=255, null=True, blank=True, unique=True
    )
    # D4 out-of-order guard: the `event_created_at` (provider generation time) of
    # the most recent webhook event whose effect was applied to this
    # subscription. Processing refuses to apply an event older than this, so a
    # late-arriving stale event can't move state backward. Nullable — set the
    # first time a post-creation event applies (the creating ACTIVATED is the
    # baseline, not a "later" event). Not exposed by SubscriptionSerializer.
    last_event_at = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager()

    class Meta:
        indexes = [models.Index(fields=["tenant"])]

    def __str__(self):
        return f"{self.tenant} — {self.plan.code} ({self.status})"


class SubscriptionCheckout(models.Model):
    """
    A Razorpay Subscription creation that is in flight for a tenant — created
    when an OWNER starts checkout (stage-d2-spec.md §2), before any local
    `Subscription` row exists.

    Deliberately a SEPARATE model, not a new `Subscription.Status`: a checkout
    attempt is a different concept from a subscription, and extending the
    state machine that's been locked since B2 would ripple through nine call
    sites. Same instinct as splitting `WebhookEvent` from `Subscription` and
    `EmailVerificationToken` from `User.email_verified`.

    OneToOne on tenant: one in-flight checkout per tenant. A second "subscribe"
    click reuses this row's `external_subscription_id` rather than creating a
    second gateway subscription — the `select_for_update()` in
    `CheckoutService.create_checkout` is what serialises that.

    `status` is NOT a subscription state:
      - CREATED   — Razorpay Subscription made, Checkout not yet completed.
      - CONFIRMED — the Checkout success callback's signature verified. This is
                    "the client's success report was authentic", for UI feedback
                    and audit only. It does NOT mean the subscription is active —
                    that waits for D3 processing the real gateway
                    `ACTIVATED` webhook. D3 owns turning a CONFIRMED checkout
                    into a `Subscription` row.

    Tenant-owned data, so `TenantScopedManager` (CLAUDE.md) — `for_tenant()` is
    used by the checkout/confirm views; D3's webhook handler, which has no tenant
    context, still looks it up directly by `external_subscription_id`.
    """

    class Status(models.TextChoices):
        CREATED = "CREATED", "Created"
        CONFIRMED = "CONFIRMED", "Confirmed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(
        Tenant, on_delete=models.CASCADE, related_name="checkout"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="+")
    # Null until the gateway subscription is actually created; unique so a row
    # maps to exactly one gateway subscription (Postgres allows multiple NULLs).
    external_subscription_id = models.CharField(
        max_length=255, null=True, blank=True, unique=True
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.CREATED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager()

    def __str__(self):
        return f"checkout: {self.tenant} → {self.plan.code} ({self.status})"


class WebhookEvent(models.Model):
    """
    A verified, deduplicated payment-gateway webhook event (stage-d1-spec.md
    §4.3), normalized through the active adapter.

    NOT tenant-owned — the gateway calls the webhook with no tenant context, and
    the event references gateway-side IDs a later stage maps back to a tenant.
    So this uses the plain manager, like Plan, never TenantScopedManager.

    `external_event_id` (the gateway's unique per-delivery id) is `unique`, and
    that constraint IS the entire idempotency guarantee: gateways deliver
    at-least-once, and a redelivery is absorbed by a unique-constraint collision,
    not by a non-atomic check-then-insert. Same philosophy as OutstandingToken /
    EmailVerificationToken.

    `event_type` stores the project's own `EventType` vocabulary (the adapter's
    `parse_webhook_event` maps the provider's specific names into it); the raw
    provider event name is retained inside `raw_payload` for audit.

    `external_subscription_id` is the normalized correlation key
    (`NormalizedEvent.external_subscription_id`), copied out at storage time so
    D3 processing — inline AND the `process_webhook_events` backfill command,
    which has no headers and no live adapter context — matches events to a
    `Subscription`/`SubscriptionCheckout` by reading a plain column, never by
    re-parsing `raw_payload`. Indexed, NOT unique: many events share one
    subscription.

    D3 turns these rows into `SubscriptionService` state changes:
    `WebhookProcessingService.process_event` sets `processed=True` in the same
    transaction as the state change it applies. A row with `processed=False` is
    one whose effect has not (yet) been applied — the retry command's queue.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_event_id = models.CharField(max_length=255, unique=True)
    external_subscription_id = models.CharField(
        max_length=255, null=True, blank=True, db_index=True
    )
    event_type = models.CharField(
        max_length=32, choices=[(e.value, e.value) for e in EventType]
    )
    # The billing period the event reports (a `subscription.charged` renewal
    # carries one; most events don't). Copied off `NormalizedEvent` at storage
    # time — same write-time-normalization rule as `external_subscription_id`,
    # so the `process_webhook_events` backfill command consumes a plain column
    # and never re-parses `raw_payload` or needs a live adapter.
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    # When the PROVIDER generated the event (Razorpay's top-level envelope
    # `created_at`), distinct from `received_at` (our receipt time). D4's
    # cross-event-type ordering signal — see `Subscription.last_event_at`.
    # Nullable: a payload that carried no such timestamp bypasses the guard.
    event_created_at = models.DateTimeField(null=True, blank=True)
    # Parsed JSON, not raw bytes: the signature was already verified against the
    # exact raw body before parsing, so there is nothing left to re-verify, and
    # JSON keeps the payload queryable for the processing stage.
    raw_payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["processed"])]

    def __str__(self):
        return f"{self.external_event_id} ({self.event_type})"


class UsageRecord(models.Model):
    """
    An immutable snapshot of one metered quantity for one tenant over one
    billing period (docs/stage-d5-spec.md).

    D5's only metric is `active_members` — a count of the tenant's real
    `Membership` rows. No usage is fabricated: this counts a resource the domain
    already tracks. `metric` is a field, not a hardcoded assumption, so a second
    *real* metric could be added later without a migration — not because one
    exists now.

    `UNIQUE(tenant, metric, period_start, period_end)` is the idempotency
    guarantee: re-running a snapshot for an already-recorded period collides on
    the constraint and is a safe no-op, exactly like
    `WebhookEvent.external_event_id` — but keyed on a natural business key rather
    than an external id. (There is no external ingestion in this design; the
    master spec's older `idempotency_key`/ingestion `UsageRecord` is superseded
    — see docs/stage-d5-spec.md §1.)

    Immutable in practice: the recording service never updates an existing row,
    so the quantity captured is the count at first-snapshot time for that
    period. A fresh count means a fresh period (driven by a CHARGED webhook),
    not an overwrite.
    """

    class Metric(models.TextChoices):
        ACTIVE_MEMBERS = "active_members", "Active members"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="usage_records"
    )
    metric = models.CharField(max_length=50, choices=Metric.choices)
    quantity = models.PositiveIntegerField()
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    objects = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "metric", "period_start", "period_end"],
                name="unique_usage_snapshot",
            )
        ]
        indexes = [models.Index(fields=["tenant", "metric"])]

    def __str__(self):
        return (
            f"{self.tenant} — {self.metric}={self.quantity} "
            f"[{self.period_start:%Y-%m-%d}…{self.period_end:%Y-%m-%d}]"
        )


class ProrationRecord(models.Model):
    """
    An AUDIT record of a proration CALCULATION performed at the moment of a
    mid-cycle plan change (docs/stage-d6-spec.md) — NOT a record of money moving.
    Nothing is charged, refunded, or sent to any payment gateway because this row
    exists.

    Tenora's `SubscriptionService.change_plan` swaps `Subscription.plan` locally
    with no gateway call at all. A real Razorpay integration would instead call
    the Update Subscription API (`plan_id`, `schedule_change_at="now"`) and
    Razorpay itself would own the proration collection — the invoice on an
    upgrade, the credit note + refund on a downgrade (stage-d6-spec.md §1). This
    row is an independent honest calculation / audit trail; if a real mid-cycle
    collection path is ever built, that is separate later work.

    `amount_cents` is SIGNED (integer cents, never floats): positive = the extra
    the customer would owe for an upgrade; negative = the credit they would be
    owed for a downgrade; zero = a real plan change between two same-priced
    plans. Same data category as `UsageRecord` — a real calculation at a real
    moment, recorded honestly. No uniqueness constraint: several plan changes in
    one period each get their own record.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="proration_records"
    )
    subscription = models.ForeignKey(
        "Subscription", on_delete=models.CASCADE, related_name="proration_records"
    )
    from_plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="+")
    to_plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="+")
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    # The exact "now" the calculation used — an explicit field, NOT auto_now_add,
    # so the row provably carries the instant the math was performed against.
    calculated_at = models.DateTimeField()
    amount_cents = models.IntegerField()  # signed; never floats
    currency = models.CharField(max_length=3)

    objects = TenantScopedManager()

    class Meta:
        indexes = [models.Index(fields=["tenant", "subscription"])]

    def __str__(self):
        return (
            f"{self.tenant} — {self.from_plan.code}→{self.to_plan.code} "
            f"{self.currency} {self.amount_cents:+d} @ {self.calculated_at:%Y-%m-%d}"
        )


class ReconciliationDiscrepancy(models.Model):
    """
    An IMMUTABLE record that a reconciliation sweep found local `Subscription`
    state diverging from the payment provider's reported state
    (docs/stage-d8-spec.md).

    DETECTION ONLY. Writing this row changes nothing — no local state is
    corrected, nothing is written back to the provider. Same audit-record
    category as `UsageRecord` / `ProrationRecord`: a real thing that was found,
    recorded honestly. Acting on drift is a human / future-stage decision
    (spec §1).

    No open/resolved workflow. Each sweep that STILL sees the divergence writes
    a fresh row (`detected_at` moves forward); the sequence of rows for a
    subscription IS the "how long has this been drifting" record. A row is
    never mutated or deleted by the application.

    Only the subscription STATUS is reconciled (spec §6): period dates are a
    synthesized local placeholder for much of a subscription's life, and the
    provider plan id diverges by design because `change_plan` is local-only.
    """

    class Category(models.TextChoices):
        #: Local status and provider status disagree, neither side terminal.
        STATUS_MISMATCH = "STATUS_MISMATCH", "Status mismatch"
        #: Local status is terminal (CANCELED) but the provider still reports a
        #: NON-terminal subscription — i.e. the provider may still be charging a
        #: customer Tenora considers gone. Tenora's cancellation flow is
        #: local-only, so D8 cannot correct this; it is still the most
        #: financially significant drift D8 can surface, so it gets its own
        #: category instead of being folded into STATUS_MISMATCH or skipped.
        LOCAL_CANCELED_PROVIDER_ACTIVE = (
            "LOCAL_CANCELED_PROVIDER_ACTIVE",
            "Locally canceled, still live at provider",
        )
        #: The provider explicitly reports no such subscription for an id a
        #: local row still points at.
        PROVIDER_NOT_FOUND = "PROVIDER_NOT_FOUND", "Provider has no record"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="reconciliation_discrepancies",
    )
    subscription = models.ForeignKey(
        "Subscription",
        on_delete=models.CASCADE,
        related_name="reconciliation_discrepancies",
    )
    # A snapshot of the id at detection time — the value you would paste into
    # the provider's dashboard. Denormalized (the FK already gives it) so a
    # reader needs no join, and so it survives even if the Subscription's field
    # is later cleared.
    external_subscription_id = models.CharField(max_length=255)
    category = models.CharField(max_length=40, choices=Category.choices)
    # First-class columns, NOT prose: a status discrepancy is queryable and
    # auditable without parsing `detail`. Plain CharFields — a snapshot of the
    # values as they were, not FKs into vocabularies that may later change.
    local_status = models.CharField(max_length=20)
    provider_status = models.CharField(max_length=20, blank=True)  # "" for PROVIDER_NOT_FOUND
    detail = models.CharField(max_length=255, blank=True)  # human prose; never parsed
    # The sweep instant this was detected — explicit, like
    # ProrationRecord.calculated_at, not auto_now_add.
    detected_at = models.DateTimeField()

    objects = TenantScopedManager()

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "subscription"]),
            models.Index(fields=["detected_at"]),
        ]
        verbose_name_plural = "reconciliation discrepancies"

    def __str__(self):
        return (
            f"{self.tenant} — {self.category} "
            f"({self.local_status} vs {self.provider_status or '—'}) "
            f"@ {self.detected_at:%Y-%m-%d %H:%M}"
        )
