from rest_framework import serializers

from apps.billing.models import Plan, Subscription, SubscriptionCheckout


class PlanSerializer(serializers.ModelSerializer):
    """Output only. `is_active` omitted — the list endpoint only ever
    returns active plans, so exposing it would always read True."""

    class Meta:
        model = Plan
        fields = ["id", "name", "code", "price_cents", "currency", "interval"]


class SubscriptionSerializer(serializers.ModelSerializer):
    """
    Output only. Nests the plan. No `tenant` field — the caller already
    identified the tenant via X-Tenant-ID; echoing it back would just
    invite clients to treat it as settable.
    """

    plan = PlanSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan",
            "status",
            "current_period_start",
            "current_period_end",
            "created_at",
            "updated_at",
        ]


class CheckoutStartSerializer(serializers.Serializer):
    """
    Input for POST /api/subscriptions/current/checkout/ — the plan an OWNER
    wants to subscribe to. Plain Serializer, so a body carrying `tenant_id`
    binds to nothing (tenant comes only from X-Tenant-ID).
    """

    plan_id = serializers.UUIDField()


class CheckoutConfirmSerializer(serializers.Serializer):
    """
    Input for POST /api/subscriptions/current/confirm-checkout/ — what the
    browser reports when a provider's checkout finishes.

    Only the subscription id is required, and even that is checked against OUR
    stored checkout rather than believed. Razorpay's two signature fields stay
    optional because Cashfree's subscription return carries no signed payload
    at all — the adapter decides what, if anything, in this report is worth
    reading. Nothing here ever drives a state change.
    """

    subscription_id = serializers.CharField(required=False, allow_blank=True)
    razorpay_subscription_id = serializers.CharField(required=False, allow_blank=True)
    razorpay_payment_id = serializers.CharField(required=False, allow_blank=True)
    razorpay_signature = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not (attrs.get("subscription_id") or attrs.get("razorpay_subscription_id")):
            raise serializers.ValidationError(
                {"subscription_id": ["This field is required."]}
            )
        return attrs


class SubscriptionCheckoutSerializer(serializers.ModelSerializer):
    """
    Output for the checkout-start response — what the frontend needs to open
    the active provider's checkout. The publishable key id is added by the view
    (it's a setting, not a model field); no API secret EVER crosses this
    boundary, for either provider.

    The model field is now `external_subscription_id`, but the JSON key stays
    `razorpay_subscription_id` — the frontend (and Razorpay Checkout's
    `subscription_id` option) depends on it; the adapter refactor must not
    change this external contract (payment-gateway-adapter-spec.md §3).
    """

    razorpay_subscription_id = serializers.CharField(
        source="external_subscription_id", read_only=True
    )
    #: Provider-neutral names — what a non-Razorpay frontend reads. The
    #: razorpay_* key above is kept alongside them so the existing contract
    #: (and Razorpay Checkout's own `subscription_id` option) is unbroken.
    subscription_id = serializers.CharField(
        source="external_subscription_id", read_only=True
    )
    plan = PlanSerializer(read_only=True)

    class Meta:
        model = SubscriptionCheckout
        fields = [
            "razorpay_subscription_id",
            "subscription_id",
            "provider",
            "session_token",
            "plan",
            "status",
        ]


class SubscriptionUpdateSerializer(serializers.Serializer):
    """
    Input shape only. Exactly one of `plan_id` / `status` per request:
    a plan change goes through SubscriptionService.change_plan, a status
    change through SubscriptionService.transition_status. Both present
    is ambiguous, neither is a no-op — both rejected as 400 rather than
    left to depend on dict ordering.
    """

    plan_id = serializers.UUIDField(required=False)
    status = serializers.ChoiceField(
        choices=Subscription.Status.choices, required=False
    )

    def validate(self, attrs):
        if len(attrs) != 1:
            raise serializers.ValidationError(
                "Provide exactly one of 'plan_id' or 'status'."
            )
        return attrs
