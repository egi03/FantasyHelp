import os
from celery import Celery
from celery.schedules import crontab
from django.conf import settings
import ssl

# Set the default Django settings module for the 'celery' program
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

app = Celery('fpl_api')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs
app.autodiscover_tasks()


# Task routing configuration
app.conf.task_routes = {
    # Data sync tasks - high priority queue
    'apps.fpl.tasks.update_player_data_task': {'queue': 'data_sync'},
    'apps.fpl.tasks.sync_user_team_task': {'queue': 'data_sync'},

    # Suggestion tasks - medium priority queue
    'apps.fpl.tasks.generate_suggestions_task': {'queue': 'suggestions'},
    'apps.fpl.tasks.batch_generate_suggestions_task': {'queue': 'suggestions'},

    # Analytics tasks - low priority queue
    'apps.fpl.tasks.update_analytics_task': {'queue': 'analytics'},
    'apps.fpl.tasks.cleanup_old_data_task': {'queue': 'maintenance'},

    # Health checks - dedicated queue
    'apps.fpl.tasks.health_check_task': {'queue': 'monitoring'},

    # Default queue for other tasks
    '*': {'queue': 'default'},
}

# Task serialization
app.conf.task_serializer = 'json'
app.conf.accept_content = ['json']
app.conf.result_serializer = 'json'
app.conf.timezone = 'UTC'
app.conf.enable_utc = True

# Task execution configuration
app.conf.task_always_eager = False
app.conf.task_eager_propagates = True
app.conf.task_ignore_result = False
app.conf.task_store_eager_result = True

# Worker configuration
app.conf.worker_prefetch_multiplier = 1
app.conf.worker_max_tasks_per_child = 1000
app.conf.worker_disable_rate_limits = False

# Task time limits
app.conf.task_soft_time_limit = 300  # 5 minutes
app.conf.task_time_limit = 600       # 10 minutes

# Task retry configuration
app.conf.task_acks_late = True
app.conf.task_reject_on_worker_lost = True

# Result backend configuration
app.conf.result_expires = 3600  # 1 hour
app.conf.result_persistent = True

# Monitoring configuration
app.conf.worker_send_task_events = True
app.conf.task_send_sent_event = True

# Security configuration
if not settings.DEBUG:
    # SSL configuration for production
    app.conf.broker_use_ssl = {
        'keyfile': None,
        'certfile': None,
        'ca_certs': None,
        'cert_reqs': ssl.CERT_NONE
    }

    app.conf.redis_backend_use_ssl = {
        'ssl_cert_reqs': ssl.CERT_NONE,
        'ssl_ca_certs': None,
        'ssl_certfile': None,
        'ssl_keyfile': None,
    }

# Beat schedule configuration for periodic tasks
app.conf.beat_schedule = {
    # Update player data every hour
    'update-player-data': {
        'task': 'apps.fpl.tasks.update_player_data_task',
        'schedule': crontab(minute=0),  # Every hour
        'options': {
            'queue': 'data_sync',
            'priority': 9
        }
    },

    # Update analytics every 2 hours
    'update-analytics': {
        'task': 'apps.fpl.tasks.update_analytics_task',
        'schedule': crontab(minute=0, hour='*/2'),  # Every 2 hours
        'options': {
            'queue': 'analytics',
            'priority': 5
        }
    },

    # Clean up old data daily at 2 AM
    'cleanup-old-data': {
        'task': 'apps.fpl.tasks.cleanup_old_data_task',
        'schedule': crontab(hour=2, minute=0),  # 2 AM daily
        'options': {
            'queue': 'maintenance',
            'priority': 3
        }
    },

    # Health check every 15 minutes
    'health-check': {
        'task': 'apps.fpl.tasks.health_check_task',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
        'options': {
            'queue': 'monitoring',
            'priority': 7
        }
    },

    # Weekly deep analytics update (Sundays at 3 AM)
    'weekly-analytics-update': {
        'task': 'apps.analytics.tasks.weekly_analysis',
        'schedule': crontab(hour=3, minute=0, day_of_week=0),  # Sundays at 3 AM
        'options': {
            'queue': 'analytics',
            'priority': 4
        }
    },
}

# Queue configuration with priorities
app.conf.task_default_queue = 'default'
app.conf.task_default_exchange = 'default'
app.conf.task_default_exchange_type = 'direct'
app.conf.task_default_routing_key = 'default'

# Queue definitions with different priorities
app.conf.task_queues = {
    'data_sync': {
        'exchange': 'data_sync',
        'routing_key': 'data_sync',
        'priority': 9,
    },
    'suggestions': {
        'exchange': 'suggestions',
        'routing_key': 'suggestions',
        'priority': 7,
    },
    'analytics': {
        'exchange': 'analytics',
        'routing_key': 'analytics',
        'priority': 5,
    },
    'monitoring': {
        'exchange': 'monitoring',
        'routing_key': 'monitoring',
        'priority': 8,
    },
    'maintenance': {
        'exchange': 'maintenance',
        'routing_key': 'maintenance',
        'priority': 3,
    },
    'default': {
        'exchange': 'default',
        'routing_key': 'default',
        'priority': 6,
    },
}

# Error handling configuration
app.conf.task_annotations = {
    '*': {
        'rate_limit': '100/m',  # Global rate limit
        'time_limit': 600,      # 10 minutes
        'soft_time_limit': 300, # 5 minutes
    },
    'apps.fpl.tasks.update_player_data_task': {
        'rate_limit': '6/h',    # 6 times per hour max
        'time_limit': 1800,     # 30 minutes
        'soft_time_limit': 1200, # 20 minutes
        'max_retries': 3,
        'default_retry_delay': 300,  # 5 minutes
    },
    'apps.fpl.tasks.generate_suggestions_task': {
        'rate_limit': '60/m',   # 60 per minute max
        'time_limit': 300,      # 5 minutes
        'soft_time_limit': 180, # 3 minutes
        'max_retries': 2,
        'default_retry_delay': 60,   # 1 minute
    },
    'apps.fpl.tasks.sync_user_team_task': {
        'rate_limit': '120/m',  # 120 per minute max
        'time_limit': 120,      # 2 minutes
        'soft_time_limit': 60,  # 1 minute
        'max_retries': 3,
        'default_retry_delay': 30,   # 30 seconds
    },
}

# Logging configuration
app.conf.worker_log_format = '[%(asctime)s: %(levelname)s/%(processName)s] %(message)s'
app.conf.worker_task_log_format = '[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s'

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
            retval=retval,
            args=args,
            kwargs=kwargs,
        )

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Failure callback"""
        logger.error(
            'Task failed',
            task_id=task_id,
            task_name=self.name,
            exception=str(exc),
            args=args,
            kwargs=kwargs,
            traceback=einfo.traceback,
        )

        # Could integrate with error tracking services like Sentry

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Retry callback"""
        logger.warning(
            'Task retry',
            task_id=task_id,
            task_name=self.name,
            exception=str(exc),
            retry_count=self.request.retries,
            max_retries=self.max_retries,
        )

    def apply_async(self, args=None, kwargs=None, **options):
        """Override apply_async to add custom logic"""
        # Add task ID to options for tracking
        if 'task_id' not in options:
            import uuid
            options['task_id'] = str(uuid.uuid4())

        # Log task submission
        logger.info(
            'Task submitted',
            task_name=self.name,
            task_id=options.get('task_id'),
            args=args,
            kwargs=kwargs,
        )

        return super().apply_async(args, kwargs, **options)

# Set base task class
app.Task = BaseTask

# Custom signal handlers
from celery.signals import task_prerun, task_postrun, task_failure, worker_ready

@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
    """Handler called before task execution"""
    logger.info(
        'Task starting',
        task_id=task_id,
        task_name=sender.name if sender else 'unknown',
    )

@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **kwds):
    """Handler called after task execution"""
    logger.info(
        'Task finished',
        task_id=task_id,
        task_name=sender.name if sender else 'unknown',
        state=state,
    )

@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwds):
    """Handler called on task failure"""
    logger.error(
        'Task failed globally',
        task_id=task_id,
        task_name=sender.name if sender else 'unknown',
        exception=str(exception),
    )

    # Could send alerts, create incidents, etc.

@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Handler called when worker is ready"""
    logger.info(
        'Celery worker ready',
        hostname=sender.hostname,
    )

# Health check configuration
app.conf.worker_send_task_events = True

# Task result compression
app.conf.result_compression = 'gzip'
app.conf.task_compression = 'gzip'

# Security: Disable pickle for security
app.conf.task_serializer = 'json'
app.conf.result_serializer = 'json'
app.conf.accept_content = ['json']

# Error handling middleware
class TaskErrorHandlingMiddleware:
    """Middleware for task error handling"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Pre-task processing
        response = self.get_response(request)
        # Post-task processing
        return response

    def process_exception(self, request, exception):
        """Handle task exceptions"""
        logger.error(
            'Task middleware exception',
            exception=str(exception),
            request_path=getattr(request, 'path', 'unknown'),
        )

# Custom commands for Celery management
@app.task(bind=True)
def debug_task(self):
    """Debug task for testing"""
    print(f'Request: {self.request!r}')
    return {'status': 'debug_task_completed', 'request': str(self.request)}

# Flower monitoring configuration (if using Flower)
if hasattr(settings, 'FLOWER_BASIC_AUTH'):
    app.conf.flower_basic_auth = settings.FLOWER_BASIC_AUTH

# Canvas primitives for complex workflows
from celery import group, chain, chord, chunks

def create_data_sync_workflow():
    """Create a complex data sync workflow using Canvas primitives"""

    # Step 1: Update teams and positions (parallel)
    update_metadata = group(
        app.send_task('apps.fpl.tasks.update_teams_task'),
        app.send_task('apps.fpl.tasks.update_positions_task'),
    )

    # Step 2: Update players (depends on metadata)
    update_players = app.send_task('apps.fpl.tasks.update_players_task')

    # Step 3: Update analytics (depends on players)
    update_analytics = app.send_task('apps.fpl.tasks.update_analytics_task')

    # Create workflow chain
    workflow = chain(
        update_metadata,
        update_players,
        update_analytics
    )

    return workflow

def create_bulk_suggestion_workflow(team_ids):
    """Create workflow for bulk suggestion generation"""

    # Chunk team IDs for parallel processing
    team_chunks = chunks(
        app.send_task('apps.fpl.tasks.generate_suggestions_task'),
        10  # Process 10 teams at a time
    )

    # Create chord (parallel execution with callback)
    workflow = chord(
        [team_chunks(chunk) for chunk in chunks(team_ids, 10)],
        app.send_task('apps.fpl.tasks.bulk_suggestions_callback')
    )

    return workflow

# Performance monitoring
import time
from celery.signals import before_task_publish, after_task_publish

@before_task_publish.connect
def before_task_publish_handler(sender=None, headers=None, body=None, properties=None, **kwargs):
    """Track task publishing performance"""
    headers['publish_time'] = time.time()

@after_task_publish.connect
def after_task_publish_handler(sender=None, headers=None, body=None, properties=None, **kwargs):
    """Log task publishing metrics"""
    publish_time = headers.get('publish_time')
    if publish_time:
        duration = time.time() - publish_time
        logger.info(
            'Task published',
            task_name=sender,
            publish_duration_ms=round(duration * 1000, 2),
        )

# Development vs Production configuration
if settings.DEBUG:
    # Development settings
    app.conf.task_always_eager = True  # Execute tasks synchronously
    app.conf.task_eager_propagates = True
    app.conf.result_expires = 60  # Short expiration for dev
else:
    # Production settings
    app.conf.task_always_eager = False
    app.conf.worker_concurrency = 4  # Adjust based on server capacity
    app.conf.worker_max_memory_per_child = 200000  # 200MB per child process

# Export the app instance
__all__ = ['app']
