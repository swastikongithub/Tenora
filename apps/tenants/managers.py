from django.db import models


class TenantScopedManager(models.Manager):
    """
    Used only by tenant-owned models (Subscription now; UsageRecord,
    Invoice, Payment in later phases). Global models like Plan use
    the default manager instead — that distinction matters when you
    write the isolation tests: every model with this manager is a
    model that MUST be checked for cross-tenant leakage.

    Deliberately requires an explicit `tenant` argument rather than
    inferring it from thread-local state. Thread-local tenant context
    is a common pattern in multi-tenant Django apps, but it makes bugs
    invisible — a query silently uses the wrong tenant instead of
    raising an error when the context wasn't set correctly. Passing
    tenant explicitly forces every call site to be honest about which
    tenant it's operating for, and makes the isolation tests trivial
    to reason about.
    """

    def for_tenant(self, tenant):
        return self.get_queryset().filter(tenant=tenant)
