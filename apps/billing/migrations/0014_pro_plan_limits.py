"""
Property-billing plan §17: Pro = 20 workspaces per owner, 20 active residents per
workspace. Every plan got Basic's numbers (2 / 10) as the column default in
0013; this sets the Pro tier's numbers on an existing `PRO` plan, if one exists.
Data-only and reversible (reverse restores the Basic defaults on that row).
"""

from django.db import migrations


def set_pro_limits(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(code="PRO").update(max_workspaces=20, max_members_per_workspace=20)


def unset_pro_limits(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(code="PRO").update(max_workspaces=2, max_members_per_workspace=10)


class Migration(migrations.Migration):
    dependencies = [("billing", "0013_plan_limits")]

    operations = [migrations.RunPython(set_pro_limits, unset_pro_limits)]
