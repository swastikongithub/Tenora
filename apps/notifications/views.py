"""
Notification endpoints. All four are GLOBAL paths (see
apps.tenants.authentication.GLOBAL_PATHS): a notification belongs to a user,
not to a workspace, so there is no X-Tenant-ID. Every query filters on
`request.user` — an id belonging to someone else simply matches nothing.
"""

from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.services import NotificationService


class NotificationSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenant.name", default=None, read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "kind",
            "title",
            "body",
            "data",
            "tenant_id",
            "tenant_name",
            "read_at",
            "created_at",
        ]


class MarkReadSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=200)
    all = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not attrs.get("all") and not attrs.get("ids"):
            raise serializers.ValidationError("Provide `ids` or `all: true`.")
        return attrs


class PreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = ["billing", "payments", "membership", "email_enabled"]


class NotificationPagination(PageNumberPagination):
    page_size = 30


class NotificationListView(APIView):
    """GET /api/notifications/?unread=1 — the caller's own notifications."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = NotificationService.for_user(request.user).select_related("tenant")
        if request.query_params.get("unread") in ("1", "true"):
            qs = qs.filter(read_at__isnull=True)
        paginator = NotificationPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(NotificationSerializer(page, many=True).data)


class NotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = NotificationService.for_user(request.user).filter(read_at__isnull=True).count()
        return Response({"unread": count})


class NotificationMarkReadView(APIView):
    """POST /api/notifications/read/ — {ids: [...]} or {all: true}."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = NotificationService.mark_read(
            user=request.user,
            ids=serializer.validated_data.get("ids"),
            all_unread=serializer.validated_data["all"],
        )
        return Response({"updated": updated}, status=status.HTTP_200_OK)


class NotificationPreferenceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(PreferenceSerializer(NotificationService.preferences_for(request.user)).data)

    def patch(self, request):
        serializer = PreferenceSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        prefs = NotificationService.update_preferences(
            user=request.user, changes=serializer.validated_data
        )
        return Response(PreferenceSerializer(prefs).data)
