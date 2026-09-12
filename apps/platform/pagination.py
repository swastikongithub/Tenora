from rest_framework.pagination import PageNumberPagination


class PlatformPageNumberPagination(PageNumberPagination):
    """
    docs/operator-control-plane-spec.md §C — the first pagination class in this
    codebase (no existing endpoint paginates). Deliberately NOT
    settings.REST_FRAMEWORK's DEFAULT_PAGINATION_CLASS — attached explicitly, per
    view, only to the new platform list endpoints that call for it, so no
    existing unpaginated endpoint (tenant-facing or the pre-existing
    /api/platform/stats/) changes shape by accident.
    """

    page_size = 25
