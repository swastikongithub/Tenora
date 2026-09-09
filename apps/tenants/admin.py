from django.contrib import admin
from apps.tenants.models import Tenant, Membership

admin.site.register(Tenant)
admin.site.register(Membership)