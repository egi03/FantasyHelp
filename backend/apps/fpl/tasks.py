from celery import shared_task, group, chord
from celery.exceptions import Retry
from django.core.cache import cache
from django.utils import timezone
from django.db import transaction
from typing import Dict, Any, List, Optional
import structlog
import time
from datetime import timedelta

from apps.core.exceptions import (
    FPLAPIError, DataSyncError, AsyncTaskError,
    ExceptionContext, handle_external_service_error
)
from apps.core.utils import measure_time, PerformanceTimer
from .models import Player, Team, UserTeam, TransferSuggestion
from .services import DataSyncService, TransferSuggestionEngine, AnalyticsService

logger = structlog.get_logger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
@measure_time
def update_player_data_task(self):
    """
    Update all player data from FPL API
    Runs periodically to keep data fresh
    """
    task_id = self.request.id

    # Set lock to prevent concurrent executions
    lock_key = 'update_player_data_lock'
    if cache.get(lock_key):
        logger.warning("Player data update already in progress", task_id=task_id)
        return {'status': 'skipped', 'reason': 'already_running'}

    try:
        # Set lock with 1 hour expiration
        cache.set(lock_key, task_id, 3600)

        # Update task state
        self.update_state(
            state='PROGRESS',
            meta={'current': 0, 'total': 100, 'status': 'Starting data sync...'}
        )

        with ExceptionContext('update_player_data', task_id=task_id):
            sync_service = DataSyncService()

            # Update progress: Starting teams sync
            self.update_state(
                state='PROGRESS',
                meta={'current': 10, 'total': 100, 'status': 'Syncing teams...'}
            )

            # Sync all data
            result = sync_service.sync_all_data()

            # Update progress: Data sync complete
            self.update_state(
                state='PROGRESS',
                meta={'current': 90, 'total': 100, 'status': 'Finalizing...'}
            )

            # Clear related caches
            _clear_player_caches()

            # Log success
            logger.info(
                "Player data update completed successfully",
                task_id=task_id,
                result=result,
                duration=time.time() - self.request.called_directly
            )

            return {
                'status': 'completed',
                'result': result,
                'timestamp': timezone.now().isoformat(),
                'task_id': task_id
            }

    except FPLAPIError as e:
        logger.error("FPL API error during data update", task_id=task_id, error=str(e))

        # Retry on API errors
        try:
            raise self.retry(countdown=60 * (self.request.retries + 1))
        except self.MaxRetriesExceededError:
            return {
                'status': 'failed',
                'error': 'FPL API unavailable after retries',
                'details': str(e)
            }

    except Exception as e:
        logger.error("Unexpected error during data update", task_id=task_id, error=str(e))

        return {
            'status': 'failed',
            'error': 'Data sync failed',
            'details': str(e),
            'task_id': task_id
        }

    finally:
        # Always clear the lock
        cache.delete(lock_key)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def sync_user_team_task(self, team_id: int):
    """
    Sync specific user team data from FPL API
    """
    task_id = self.request.id

    try:
        self.update_state(
            state='PROGRESS',
            meta={'current': 0, 'total': 100, 'status': f'Loading team {team_id}...'}
        )

        with ExceptionContext('sync_user_team', task_id=task_id, team_id=team_id):
            sync_service = DataSyncService()

            # Sync team data
            self.update_state(
                state='PROGRESS',
                meta={'current': 50, 'total': 100, 'status': 'Syncing team data...'}
            )

            user_team = sync_service.sync_user_team(team_id)

            self.update_state(
                state='PROGRESS',
                meta={'current': 90, 'total': 100, 'status': 'Finalizing...'}
            )

            # Clear team-specific caches
            _clear_team_caches(team_id)

            logger.info(
                "User team sync completed",
                task_id=task_id,
                team_id=team_id,
                team_name=user_team.team_name
            )

            return {
                'status': 'completed',
                'team_id': team_id,
                'team_name': user_team.team_name,
                'manager_name': user_team.manager_name,
                'total_points': user_team.total_points,
                'timestamp': timezone.now().isoformat()
            }

    except Exception as e:
        logger.error(
            "User team sync failed",
            task_id=task_id,
            team_id=team_id,
            error=str(e)
        )

        # Retry on failure
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=30 * (self.request.retries + 1))

        return {
            'status': 'failed',
            'team_id': team_id,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True, max_retries=2, default_retry_delay=15)
def generate_suggestions_task(self, team_id: int, max_suggestions: int = 10,
                            position_filter: Optional[int] = None):
    """
    Generate transfer suggestions for a team
    """
    task_id = self.request.id

    try:
        self.update_state(
            state='PROGRESS',
            meta={'current': 0, 'total': 100, 'status': f'Analyzing team {team_id}...'}
        )

        # Get user team
        try:
            user_team = UserTeam.objects.get(fpl_team_id=team_id)
        except UserTeam.DoesNotExist:
            raise AsyncTaskError(f"Team {team_id} not found. Load team first.")

        with ExceptionContext('generate_suggestions', task_id=task_id, team_id=team_id):
            suggestion_engine = TransferSuggestionEngine()

            self.update_state(
                state='PROGRESS',
                meta={'current': 30, 'total': 100, 'status': 'Analyzing players...'}
            )

            # Generate suggestions
            suggestions = suggestion_engine.generate_suggestions(
                user_team, max_suggestions
            )

            self.update_state(
                state='PROGRESS',
                meta={'current': 80, 'total': 100, 'status': 'Saving suggestions...'}
            )

            # Filter by position if specified
            if position_filter:
                suggestions = [
                    s for s in suggestions
                    if s.player_out.position_id == position_filter
                ]

            # Clear suggestion caches
            _clear_suggestion_caches(team_id)

            logger.info(
                "Transfer suggestions generated",
                task_id=task_id,
                team_id=team_id,
                suggestions_count=len(suggestions)
            )

            return {
                'status': 'completed',
                'team_id': team_id,
                'suggestions_count': len(suggestions),
                'suggestions': [
                    {
                        'player_out': s.player_out.web_name,
                        'player_in': s.player_in.web_name,
                        'priority_score': float(s.priority_score),
                        'cost_change': float(s.cost_change),
                        'reason': s.reason[:100] + '...' if len(s.reason) > 100 else s.reason
                    }
                    for s in suggestions[:5]  # Return top 5 in summary
                ],
                'timestamp': timezone.now().isoformat()
            }

    except Exception as e:
        logger.error(
            "Suggestion generation failed",
            task_id=task_id,
            team_id=team_id,
            error=str(e)
        )

        if self.request.retries < self.max_retries:
            raise self.retry(countdown=15 * (self.request.retries + 1))

        return {
            'status': 'failed',
            'team_id': team_id,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True)
def batch_generate_suggestions_task(self, team_ids: List[int]):
    """
    Generate suggestions for multiple teams in parallel
    """
    task_id = self.request.id

    try:
        # Create subtasks for each team
        subtasks = group(
            generate_suggestions_task.s(team_id)
            for team_id in team_ids
        )

        # Execute subtasks
        job = subtasks.apply_async()

        # Wait for completion and collect results
        results = []
        completed = 0
        total = len(team_ids)

        for result in job.get():
            completed += 1
            results.append(result)

            # Update progress
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': completed,
                    'total': total,
                    'status': f'Completed {completed}/{total} teams'
                }
            )

        successful = len([r for r in results if r.get('status') == 'completed'])
        failed = total - successful

        logger.info(
            "Batch suggestion generation completed",
            task_id=task_id,
            total_teams=total,
            successful=successful,
            failed=failed
        )

        return {
            'status': 'completed',
            'total_teams': total,
            'successful': successful,
            'failed': failed,
            'results': results,
            'timestamp': timezone.now().isoformat()
        }

    except Exception as e:
        logger.error(
            "Batch suggestion generation failed",
            task_id=task_id,
            error=str(e)
        )

        return {
            'status': 'failed',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True)
def cleanup_old_data_task(self):
    """
    Clean up old data and suggestions
    Runs daily to maintain database performance
    """
    task_id = self.request.id

    try:
        with PerformanceTimer('cleanup_old_data'):
            cleanup_stats = {
                'suggestions_deleted': 0,
                'analytics_deleted': 0,
                'cache_cleared': False
            }

            # Clean up old suggestions (older than 7 days)
            cutoff_date = timezone.now() - timedelta(days=7)

            self.update_state(
                state='PROGRESS',
                meta={'current': 20, 'total': 100, 'status': 'Cleaning suggestions...'}
            )

            deleted_suggestions, _ = TransferSuggestion.objects.filter(
                created_at__lt=cutoff_date
            ).delete()
            cleanup_stats['suggestions_deleted'] = deleted_suggestions

            # Clean up old analytics data (older than 30 days)
            analytics_cutoff = timezone.now() - timedelta(days=30)

            self.update_state(
                state='PROGRESS',
                meta={'current': 60, 'total': 100, 'status': 'Cleaning analytics...'}
            )

            # Clean up old performance data, logs, etc.
            # (Implementation depends on your analytics models)

            self.update_state(
                state='PROGRESS',
                meta={'current': 80, 'total': 100, 'status': 'Clearing caches...'}
            )

            # Clear stale caches
            _clear_expired_caches()
            cleanup_stats['cache_cleared'] = True

            logger.info(
                "Data cleanup completed",
                task_id=task_id,
                stats=cleanup_stats
            )

            return {
                'status': 'completed',
                'stats': cleanup_stats,
                'timestamp': timezone.now().isoformat()
            }

    except Exception as e:
        logger.error("Data cleanup failed", task_id=task_id, error=str(e))

        return {
            'status': 'failed',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True)
def update_analytics_task(self):
    """
    Update analytics and insights
    Runs hourly to provide fresh analytics data
    """
    task_id = self.request.id

    try:
        with ExceptionContext('update_analytics', task_id=task_id):
            analytics_service = AnalyticsService()

            # Update various analytics
            self.update_state(
                state='PROGRESS',
                meta={'current': 0, 'total': 100, 'status': 'Updating player trends...'}
            )

            # Update player performance trends
            analytics_service.update_player_trends()

            self.update_state(
                state='PROGRESS',
                meta={'current': 33, 'total': 100, 'status': 'Updating transfer trends...'}
            )

            # Update transfer trends
            analytics_service.update_transfer_trends()

            self.update_state(
                state='PROGRESS',
                meta={'current': 66, 'total': 100, 'status': 'Updating position analysis...'}
            )

            # Update position analysis
            analytics_service.update_position_analysis()

            self.update_state(
                state='PROGRESS',
                meta={'current': 90, 'total': 100, 'status': 'Finalizing...'}
            )

            # Clear analytics caches
            _clear_analytics_caches()

            logger.info("Analytics update completed", task_id=task_id)

            return {
                'status': 'completed',
                'timestamp': timezone.now().isoformat()
            }

    except Exception as e:
        logger.error("Analytics update failed", task_id=task_id, error=str(e))

        return {
            'status': 'failed',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True, max_retries=1)
def health_check_task(self):
    """
    Periodic health check of external services
    """
    task_id = self.request.id

    try:
        health_status = {
            'fpl_api': False,
            'database': False,
            'cache': False,
            'timestamp': timezone.now().isoformat()
        }

        # Check FPL API
        try:
            from .services import FPLAPIClient
            api_client = FPLAPIClient()
            api_client.get_bootstrap_data()  # Simple API call
            health_status['fpl_api'] = True
        except Exception as e:
            logger.warning("FPL API health check failed", error=str(e))

        # Check database
        try:
            Player.objects.count()
            health_status['database'] = True
        except Exception as e:
            logger.warning("Database health check failed", error=str(e))

        # Check cache
        try:
            cache.set('health_check', 'ok', 10)
            health_status['cache'] = cache.get('health_check') == 'ok'
        except Exception as e:
            logger.warning("Cache health check failed", error=str(e))

        # Overall health
        overall_healthy = all(health_status[k] for k in ['fpl_api', 'database', 'cache'])

        if not overall_healthy:
            logger.warning("System health check failed", status=health_status)

        return {
            'status': 'completed',
            'healthy': overall_healthy,
            'details': health_status
        }

    except Exception as e:
        logger.error("Health check task failed", task_id=task_id, error=str(e))

        return {
            'status': 'failed',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


# Periodic task configuration
@shared_task
def schedule_periodic_tasks():
    """
    Schedule periodic tasks based on current time and conditions
    """
    from celery import current_app

    now = timezone.now()

    # Schedule data updates every hour
    if now.minute == 0:  # On the hour
        update_player_data_task.delay()

    # Schedule analytics updates every 2 hours
    if now.minute == 0 and now.hour % 2 == 0:
        update_analytics_task.delay()

    # Schedule cleanup daily at 2 AM
    if now.hour == 2 and now.minute == 0:
        cleanup_old_data_task.delay()

    # Schedule health checks every 15 minutes
    if now.minute % 15 == 0:
        health_check_task.delay()

    return f"Scheduled tasks for {now.isoformat()}"


# Cache management utilities
def _clear_player_caches():
    """Clear player-related caches"""
    cache_patterns = [
        'player:*',
        'top_players:*',
        'player_search:*',
        'player_comparison:*'
    ]

    for pattern in cache_patterns:
        try:
            if hasattr(cache, 'delete_pattern'):
                cache.delete_pattern(pattern)
        except Exception as e:
            logger.warning(f"Failed to clear cache pattern {pattern}: {e}")


def _clear_team_caches(team_id: int):
    """Clear team-specific caches"""
    cache_keys = [
        f'team:{team_id}',
        f'team_analysis:{team_id}',
        f'team_picks:{team_id}:*'
    ]

    for key in cache_keys:
        try:
            if '*' in key:
                if hasattr(cache, 'delete_pattern'):
                    cache.delete_pattern(key)
            else:
                cache.delete(key)
        except Exception as e:
            logger.warning(f"Failed to clear cache key {key}: {e}")


def _clear_suggestion_caches(team_id: int):
    """Clear suggestion-related caches"""
    cache_keys = [
        f'suggestions:{team_id}',
        f'suggestion_analysis:{team_id}'
    ]

    for key in cache_keys:
        try:
            cache.delete(key)
        except Exception as e:
            logger.warning(f"Failed to clear cache key {key}: {e}")


def _clear_analytics_caches():
    """Clear analytics-related caches"""
    cache_patterns = [
        'analytics:*',
        'trends:*',
        'position_analysis:*'
    ]

    for pattern in cache_patterns:
        try:
            if hasattr(cache, 'delete_pattern'):
                cache.delete_pattern(pattern)
        except Exception as e:
            logger.warning(f"Failed to clear cache pattern {pattern}: {e}")


def _clear_expired_caches():
    """Clear expired and stale caches"""
    # This would be implementation-specific based on cache backend
    # For Redis, you could use SCAN and TTL commands
    try:
        # Example implementation for Redis
        if hasattr(cache, '_cache') and hasattr(cache._cache, 'get_client'):
            client = cache._cache.get_client()
            # Scan for keys and check TTL
            # Implementation depends on Redis client
        else:
            logger.info("Cache expiration cleanup not implemented for current backend")
    except Exception as e:
        logger.warning(f"Failed to clear expired caches: {e}")


# Task monitoring utilities
@shared_task
def get_task_status(task_id: str):
    """
    Get detailed status of a task
    """
    from celery.result import AsyncResult

    try:
        result = AsyncResult(task_id)

        status_info = {
            'task_id': task_id,
            'status': result.status,
            'successful': result.successful(),
            'failed': result.failed(),
            'ready': result.ready(),
            'timestamp': timezone.now().isoformat()
        }

        if result.ready():
            if result.successful():
                status_info['result'] = result.result
            else:
                status_info['error'] = str(result.result)
                status_info['traceback'] = result.traceback
        else:
            # Get progress info if available
            if hasattr(result, 'info') and result.info:
                status_info['progress'] = result.info

        return status_info

    except Exception as e:
        return {
            'task_id': task_id,
            'status': 'ERROR',
            'error': f'Failed to get task status: {str(e)}',
            'timestamp': timezone.now().isoformat()
        }


# Error handling and retry policies
def should_retry_task(exc):
    """
    Determine if a task should be retried based on exception type
    """
    retry_exceptions = (
        FPLAPIError,
        DataSyncError,
        ConnectionError,
        TimeoutError
    )

    return isinstance(exc, retry_exceptions)


# Task result callbacks
@shared_task
def task_success_callback(task_id: str, result: Dict[str, Any]):
    """
    Callback for successful task completion
    """
    logger.info(
        "Task completed successfully",
        task_id=task_id,
        result_status=result.get('status'),
        timestamp=timezone.now().isoformat()
    )

    # Could integrate with monitoring systems, send notifications, etc.


@shared_task
def task_failure_callback(task_id: str, error: str, traceback: str):
    """
    Callback for task failure
    """
    logger.error(
        "Task failed",
        task_id=task_id,
        error=error,
        traceback=traceback,
        timestamp=timezone.now().isoformat()
    )

    # Could send alerts, create support tickets, etc.
