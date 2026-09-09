"""
Ensure the Celery app is loaded when Django starts, so `@shared_task`
registration and `celery -A config …` both work (docs/stage-d7-spec.md).
"""

from config.celery import app as celery_app

__all__ = ("celery_app",)
