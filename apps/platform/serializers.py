import re

from rest_framework import serializers

from apps.billing.models import Plan, ReconciliationDiscrepancy, Subscription, WebhookEvent
from apps.platform.models import AuditEvent
from apps.tenants.models import Tenant
from apps.users.models import User


class PlatformTenantSerializer(serializers.ModelSerializer):
    """
    Output only. One row per tenant for the platform-admin tenant list —
    deliberately NOT scoped to any tenant (docs/platform-admin-spec.md §4.3).

    `member_count` is read straight off an annotation the view attaches
    (`Count("memberships")`), never a Python-side loop over related rows.

    `subscription` is a small {plan_name, status} summary, or null for a
    tenant with none — using the same `except Subscription.DoesNotExist`
    idiom CurrentSubscriptionView already relies on, not a hasattr shortcut
    that would swallow the real exception class.
    """

    member_count = serializers.IntegerField(read_only=True)
    subscription = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "created_at", "member_count", "subscription"]

    def get_subscription(self, tenant):
        try:
            sub = tenant.subscription
        except Subscription.DoesNotExist:
            return None
        return {"plan_name": sub.plan.name, "status": sub.status}


class PlatformPlanSerializer(serializers.ModelSerializer):
    """
    Output only. Unlike the tenant-facing PlanSerializer (apps.billing.serializers),
    this is deliberately a SEPARATE serializer, not a shared/extended one — it
    exposes exactly the fields the tenant-facing one omits on purpose
    (`is_active`, `external_plan_id`), for an audience (platform staff) that
    needs to see inactive/unsynced plans too.

    `subscriber_count` is a real annotation the view attaches
    (`Count("subscriptions")`), matching PlatformTenantSerializer's
    `member_count` convention above.
    """

    subscriber_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Plan
        fields = [
            "id",
            "name",
            "code",
            "price_cents",
            "currency",
            "interval",
            "is_active",
            "external_plan_id",
            "subscriber_count",
        ]


class PlatformWebhookEventSerializer(serializers.ModelSerializer):
    """
    Output only. SANITIZED — docs/operator-control-plane-spec.md §B: exactly
    Tenora's own normalized fields, never `raw_payload`. A gateway's raw event
    payload can embed customer contact and payment-instrument metadata; Phase 1
    exposes only this fixed, normalized field set on both the list and detail
    read, with no exception.

    `tenant` is resolved by the view (apps.platform.services
    .resolve_tenants_for_external_subscription_ids) and handed in via
    `context["tenant_map"]` — a batch lookup, not a per-row query here.
    """

    tenant = serializers.SerializerMethodField()

    class Meta:
        model = WebhookEvent
        fields = [
            "id",
            "external_event_id",
            "event_type",
            "external_subscription_id",
            "tenant",
            "period_start",
            "period_end",
            "event_created_at",
            "received_at",
            "processed",
        ]

    def get_tenant(self, obj):
        return self.context.get("tenant_map", {}).get(obj.external_subscription_id)


class PlatformReconciliationDiscrepancySerializer(serializers.ModelSerializer):
    """Output only. `tenant` is a small {id, name, slug} summary, read off the
    view's `select_related("tenant")` — no extra query per row."""

    tenant = serializers.SerializerMethodField()

    class Meta:
        model = ReconciliationDiscrepancy
        fields = [
            "id",
            "tenant",
            "subscription_id",
            "external_subscription_id",
            "category",
            "local_status",
            "provider_status",
            "detail",
            "detected_at",
        ]

    def get_tenant(self, obj):
        return {
            "id": str(obj.tenant_id),
            "name": obj.tenant.name,
            "slug": obj.tenant.slug,
        }


class PlatformUserSerializer(serializers.ModelSerializer):
    """
    Output only. Never the password hash. Deliberately a separate serializer
    from apps.users.serializers.UserSerializer/MeSerializer — this audience
    (platform staff, about ANY user) needs the platform-relevant flags those
    serializers don't expose (is_superuser, is_active, email_verified,
    date_joined); RegisterView/MeView's response shapes are untouched.
    """

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "is_staff",
            "is_superuser",
            "is_active",
            "email_verified",
            "date_joined",
        ]


class PlatformUserDetailSerializer(PlatformUserSerializer):
    """
    GET /api/platform/users/detail/?id= only. Adds `memberships` — which
    tenants this user belongs to and with what role — built by the view the
    same way MyTenantsView already flattens {**TenantSerializer(tenant).data,
    "role": ...} for "tenants I belong to" (apps.tenants.views), reused here
    for "tenants THIS user belongs to". Not apps.tenants.serializers
    .MembershipSerializer — that serializer answers the opposite direction
    ("members of one fixed tenant, with each row's own email"), not this one.
    """

    memberships = serializers.SerializerMethodField()

    class Meta(PlatformUserSerializer.Meta):
        fields = PlatformUserSerializer.Meta.fields + ["memberships"]

    def get_memberships(self, obj):
        # Precomputed by the view (one query) and handed in via context —
        # same batch-then-serialize shape as PlatformWebhookEventSerializer's
        # tenant_map above, not a per-instance query.
        return self.context.get("memberships", [])


class PlatformAuditEventSerializer(serializers.ModelSerializer):
    """
    Output only — GET /api/platform/audit-log/. `actor` is shaped as a small
    {id, email} summary (or null once the account is gone — AuditEvent.actor
    is SET_NULL), the same nested-summary convention every other FK on this
    surface already uses (compare `tenant` on
    PlatformReconciliationDiscrepancySerializer). `metadata` is returned
    verbatim — the write-time discipline (never a password/secret/raw
    payload) lives in AuditService, not here; this serializer adds no
    redaction of its own because none should ever be needed.
    """

    actor = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "actor",
            "action",
            "target_type",
            "target_id",
            "summary",
            "metadata",
            "is_critical",
            "created_at",
        ]

    def get_actor(self, obj):
        if not obj.actor_id or obj.actor is None:
            return None
        return {"id": str(obj.actor_id), "email": obj.actor.email}


# Operator-supplied plan identity/currency shapes. Format rules only — they
# say nothing about what a plan may cost or how often it bills, which is the
# operator's business decision, not this layer's.
_PLAN_CODE_RE = re.compile(r"[A-Z0-9][A-Z0-9_-]*")
_CURRENCY_RE = re.compile(r"[A-Z]{3}")


def _clean_name(value):
    name = value.strip()
    if not name:
        raise serializers.ValidationError("This field may not be blank.")
    return name


def _clean_code(value):
    code = value.strip().upper()
    if not _PLAN_CODE_RE.fullmatch(code):
        raise serializers.ValidationError(
            "Use letters, digits, underscores and hyphens only (e.g. PRO_ANNUAL)."
        )
    return code


def _clean_currency(value):
    currency = value.strip().upper()
    if not _CURRENCY_RE.fullmatch(currency):
        raise serializers.ValidationError(
            "Use a three-letter ISO 4217 currency code (e.g. USD)."
        )
    return currency


class PlatformPlanCreateSerializer(serializers.Serializer):
    """
    Input only — POST /api/platform/plans/ (Phase 3).

    A plain `Serializer`, not a `ModelSerializer`, for the same reason
    `RegisterSerializer` is (apps.users.serializers): unknown body keys are
    silently dropped rather than bound, so a client cannot reach a field this
    endpoint does not offer. That matters concretely here — `external_plan_id`
    and `is_active` are NOT accepted at creation. A plan is always created
    unsynced (provisioning it at the gateway is a separate, explicit operator
    action, so creating a plan never has an external side effect) and always
    created active.

    `code` uniqueness is checked against the database so a duplicate reads as a
    clean field error instead of an IntegrityError; the UNIQUE constraint on
    the column remains the real guarantee under concurrency, and the view
    catches that collision too (CLAUDE.md: "the DB constraint — not a
    pre-check — is the real concurrency guarantee").
    """

    name = serializers.CharField(max_length=100)
    code = serializers.CharField(max_length=50)
    price_cents = serializers.IntegerField(min_value=0)
    currency = serializers.CharField(min_length=3, max_length=3)
    interval = serializers.ChoiceField(choices=Plan.Interval.choices)

    def validate_name(self, value):
        return _clean_name(value)

    def validate_currency(self, value):
        return _clean_currency(value)

    def validate_code(self, value):
        code = _clean_code(value)
        if Plan.objects.filter(code=code).exists():
            raise serializers.ValidationError("A plan with this code already exists.")
        return code


class PlatformPlanUpdateSerializer(serializers.Serializer):
    """
    Input only — PATCH /api/platform/plans/detail/?id= (Phase 3).

    Deliberately accepts the money/identity fields (`price_cents`, `currency`,
    `interval`, `code`) even though a synced plan forbids changing them.
    Dropping them here instead would make an attempt to change a locked plan's
    price look like it succeeded; accepting them lets
    `PlanManagementService.update_plan` answer the real question — is THIS plan
    locked — and reject naming the offending fields. On an unsynced plan they
    are legitimately editable, which is exactly the spec's rule: "before
    `external_plan_id` is set, every field on a `Plan` may be edited freely".

    `external_plan_id` itself is not a field here, on any plan, in any state:
    the platform sets it exactly once, from a gateway sync, and nothing else
    may ever assign or replace it.

    Takes the plan being edited as `instance` so the `code` uniqueness check
    can exclude that row. An empty body is a client mistake, not a silent
    no-op, so it is rejected.
    """

    name = serializers.CharField(max_length=100, required=False)
    code = serializers.CharField(max_length=50, required=False)
    price_cents = serializers.IntegerField(min_value=0, required=False)
    currency = serializers.CharField(min_length=3, max_length=3, required=False)
    interval = serializers.ChoiceField(choices=Plan.Interval.choices, required=False)
    is_active = serializers.BooleanField(required=False)

    def validate_name(self, value):
        return _clean_name(value)

    def validate_currency(self, value):
        return _clean_currency(value)

    def validate_code(self, value):
        code = _clean_code(value)
        clashes = Plan.objects.filter(code=code)
        if self.instance is not None:
            clashes = clashes.exclude(pk=self.instance.pk)
        if clashes.exists():
            raise serializers.ValidationError("A plan with this code already exists.")
        return code

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to change.")
        return attrs
