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
    Input for POST /api/subscriptions/current/confirm-checkout/ — the three
    values Razorpay Checkout hands back on success. All required; the view
    verifies the signature and never trusts them for state changes.
    """

    razorpay_payment_id = serializers.CharField()
    razorpay_subscription_id = serializers.CharField()
    razorpay_signature = serializers.CharField()


class SubscriptionCheckoutSerializer(serializers.ModelSerializer):
    """
    Output for the checkout-start response — what the frontend needs to open
    Razorpay Checkout. The public key id is added by the view (it's a setting,
    not a model field); the API secret NEVER crosses this boundary.

    The model field is now `external_subscription_id`, but the JSON key stays
    `razorpay_subscription_id` — the frontend (and Razorpay Checkout's
    `subscription_id` option) depends on it; the adapter refactor must not
    change this external contract (payment-gateway-adapter-spec.md §3).
    """

    razorpay_subscription_id = serializers.CharField(
        source="external_subscription_id", read_only=True
    )
    plan = PlanSerializer(read_only=True)

    class Meta:
        model = SubscriptionCheckout
        fields = ["razorpay_subscription_id", "plan", "status"]


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
