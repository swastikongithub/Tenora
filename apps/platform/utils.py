import uuid


def parse_uuid_or_none(value):
    """
    A malformed id must never 500 — it must read the same as "not found" (a
    detail lookup) or "no matches" (a filter), matching how this codebase
    already collapses "missing" and "malformed" into one clean outcome
    elsewhere (apps.tenants.authentication.TenantJWTAuthentication's
    TenantHeaderRequired handling of both cases). Returns None for a missing,
    empty, or non-UUID-shaped value; never raises.
    """
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None
