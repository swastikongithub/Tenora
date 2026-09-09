from django.contrib import admin
from apps.billing.models import (
    Plan,
    ProrationRecord,
    ReconciliationDiscrepancy,
    Subscription,
    SubscriptionCheckout,
    UsageRecord,
    WebhookEvent,
)

admin.site.register(Plan)
admin.site.register(Subscription)
admin.site.register(SubscriptionCheckout)
admin.site.register(WebhookEvent)
admin.site.register(UsageRecord)
admin.site.register(ProrationRecord)
admin.site.register(ReconciliationDiscrepancy)