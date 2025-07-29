import os
from celery import Celery
from celery.schedules import crontab
from django.conf import settings

# Set the default Django settings module for the 'celery' program
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fantasyhelp.settings')

app = Celery('fantasyhelp')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs
app.autodiscover_tasks()

# Basic configuration for development
app.conf.task_serializer = 'json'
app.conf.accept_content = ['json']
app.conf.result_serializer = 'json'
app.conf.timezone = 'UTC'
app.conf.enable_utc = True

# Development settings - tasks run synchronously
app.conf.task_always_eager = True
app.conf.task_eager_propagates = True

# Task time limits
app.conf.task_soft_time_limit = 300  # 5 minutes
app.conf.task_time_limit = 600       # 10 minutes

# Simple beat schedule for development
app.conf.beat_schedule = {
    # Update player data every hour
    'update-player-data': {
        'task': 'apps.fpl.tasks.update_player_data_task',
        'schedule': crontab(minute=0),  # Every hour
    },

    # Clean up old data daily at 2 AM
    'cleanup-old-data': {
        'task': 'apps.fpl.tasks.cleanup_old_data_task',
        'schedule': crontab(hour=2, minute=0),  # 2 AM daily
    },
}

# Custom task base class
from celery import Task
import structlog

logger = structlog.get_logger(__name__)

class BaseTask(Task):
    """
    Base task class with enhanced error handling and logging
    """

    def on_success(self, retval, task_id, args, kwargs):
        """Success callback"""
        logger.info(
            'Task succeeded',
            task_id=task_id,
            task_name=self.name,
        )

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Failure callback"""
        logger.error(
            'Task failed',
            task_id=task_id,
            task_name=self.name,
            exception=str(exc),
        )

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Retry callback"""
        logger.warning(
            'Task retry',
            task_id=task_id,
            task_name=self.name,
            exception=str(exc),
            retry_count=self.request.retries,
        )

# Set base task class
app.Task = BaseTask


@app.task(bind=True)
def debug_task(self):
    """Debug task for testing"""
    print(f'Request: {self.request!r}')
    return {'status': 'debug_task_completed', 'request': str(self.request)}


# For production with Redis, uncomment and configure:
"""
# Production configuration
if not settings.DEBUG:
    app.conf.task_always_eager = False
    app.conf.broker_url = 'redis://localhost:6379/0'
    app.conf.result_backend = 'redis://localhost:6379/0'

    # Task routing
    app.conf.task_routes = {
        'apps.fpl.tasks.update_player_data_task': {'queue': 'data_sync'},
        'apps.fpl.tasks.sync_user_team_task': {'queue': 'data_sync'},
        'apps.fpl.tasks.generate_suggestions_task': {'queue': 'suggestions'},
    }

    # Worker configuration
    app.conf.worker_prefetch_multiplier = 1
    app.conf.worker_max_tasks_per_child = 1000
"""
