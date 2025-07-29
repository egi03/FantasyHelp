from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework import permissions, status
from django.views.decorators.cache import cache_page

from apps.core.throttling import BurstRateThrottle, SustainedRateThrottle
from ..views import (
    TeamViewSet, PlayerViewSet, UserTeamViewSet,
    TransferSuggestionViewSet, analytics_view,
    bulk_update_view, health_check_view
)


# API v2 Router Configuration
router = DefaultRouter(trailing_slash=False)

# Register viewsets with custom base names for v2
router.register('teams', TeamViewSet, basename='teams')
router.register('players', PlayerViewSet, basename='players')
router.register('user-teams', UserTeamViewSet, basename='user-teams')
router.register('suggestions', TransferSuggestionViewSet, basename='suggestions')


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
@throttle_classes([BurstRateThrottle])
@cache_page(3600)  # Cache for 1 hour
def api_v2_root(request):
    """
    API v2 root endpoint with enhanced information
    """
    return Response({
        'version': '2.0',
        'status': 'stable',
        'description': 'FPL Transfer Suggestions API v2 - Enhanced features and performance',
        'features': [
            'Advanced player analytics',
            'Machine learning transfer suggestions',
            'Real-time data synchronization',
            'Comprehensive team analysis',
            'Performance monitoring',
            'Enhanced caching'
        ],
        'endpoints': {
            # Core resources
            'teams': {
                'list': request.build_absolute_uri('teams/'),
                'detail': request.build_absolute_uri('teams/{fpl_id}/'),
                'players': request.build_absolute_uri('teams/{fpl_id}/players/'),
                'stats': request.build_absolute_uri('teams/{fpl_id}/stats/'),
            },
            'players': {
                'list': request.build_absolute_uri('players/'),
                'detail': request.build_absolute_uri('players/{fpl_id}/'),
                'search': request.build_absolute_uri('players/search/'),
                'compare': request.build_absolute_uri('players/compare/'),
                'top_performers': request.build_absolute_uri('players/top_performers/'),
                'performance_history': request.build_absolute_uri('players/{fpl_id}/performance_history/'),
            },
            'user_teams': {
                'list': request.build_absolute_uri('user-teams/'),
                'detail': request.build_absolute_uri('user-teams/{fpl_team_id}/'),
                'load_team': request.build_absolute_uri('user-teams/load_team/'),
                'analysis': request.build_absolute_uri('user-teams/{fpl_team_id}/analysis/'),
            },
            'suggestions': {
                'list': request.build_absolute_uri('suggestions/'),
                'generate': request.build_absolute_uri('suggestions/generate/'),
                'by_team': request.build_absolute_uri('suggestions/?user_team={team_id}'),
            },
            'analytics': {
                'overview': request.build_absolute_uri('analytics/'),
                'players': request.build_absolute_uri('analytics/players/'),
                'positions': request.build_absolute_uri('analytics/positions/'),
                'trends': request.build_absolute_uri('analytics/trends/'),
            },
            # Utility endpoints
            'bulk_operations': request.build_absolute_uri('bulk/'),
            'data_sync': request.build_absolute_uri('sync/'),
        },
        'parameters': {
            'pagination': {
                'page_size': 'Number of items per page (default: 20, max: 100)',
                'page': 'Page number',
                'cursor': 'Cursor-based pagination for large datasets'
            },
            'filtering': {
                'players': ['position', 'team', 'price_min', 'price_max', 'status'],
                'suggestions': ['suggestion_type', 'priority_min', 'confidence_min'],
                'teams': ['strength_min', 'position']
            },
            'ordering': {
                'players': ['total_points', 'form', 'price', 'selected_by_percent'],
                'suggestions': ['priority_score', 'confidence_score', 'created_at'],
                'teams': ['name', 'position', 'strength']
            },
            'search': {
                'players': 'Search by name, team, or position',
                'teams': 'Search by team name',
                'user_teams': 'Search by team name or manager name'
            }
        },
        'data_formats': {
            'supported': ['json'],
            'response_format': {
                'success': {'data': '...', 'meta': '...'},
                'error': {'error': 'code', 'message': 'description', 'details': '...'},
                'pagination': {'count': 0, 'next': 'url', 'previous': 'url', 'results': []}
            }
        },
        'rate_limits': {
            'anonymous': '100 requests/hour',
            'authenticated': '1000 requests/hour',
            'premium': '5000 requests/hour',
            'expensive_operations': {
                'load_team': '200 requests/hour',
                'generate_suggestions': '100 requests/hour',
                'bulk_operations': '50 requests/hour'
            }
        },
        'caching': {
            'teams': '1 hour',
            'players': '15 minutes',
            'user_teams': '10 minutes',
            'suggestions': 'Not cached (dynamic)',
            'analytics': '30 minutes'
        },
        'changelog': {
            'v2.0.0': [
                'Added advanced player analytics',
                'Improved suggestion algorithm with ML',
                'Enhanced team analysis features',
                'Better error handling and logging',
                'Optimized database queries',
                'Added comprehensive filtering options'
            ]
        },
        'deprecation_notice': None,
        'support': {
            'documentation': request.build_absolute_uri('/docs/'),
            'issues': 'https://github.com/fpl-suggestions/api/issues',
            'contact': 'api-support@fpl-suggestions.com'
        }
    })


# Advanced Analytics Endpoints
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticatedOrReadOnly])
@throttle_classes([BurstRateThrottle, SustainedRateThrottle])
def analytics_overview(request):
    """
    Get comprehensive analytics overview
    """
    from apps.analytics.services import AnalyticsService

    analytics_service = AnalyticsService()

    # Get overview statistics
    overview_data = {
        'summary': analytics_service.get_platform_summary(),
        'popular_players': analytics_service.get_popular_players(),
        'trending_transfers': analytics_service.get_trending_transfers(),
        'position_insights': analytics_service.get_position_insights(),
        'price_bands': analytics_service.get_price_band_analysis(),
    }

    return Response(overview_data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticatedOrReadOnly])
@throttle_classes([BurstRateThrottle])
def player_analytics(request):
    """
    Get detailed player analytics
    """
    from apps.analytics.services import PlayerAnalyticsService

    service = PlayerAnalyticsService()

    # Parameters
    position = request.query_params.get('position')
    team = request.query_params.get('team')
    price_range = request.query_params.get('price_range')
    timeframe = request.query_params.get('timeframe', '5')  # Last 5 gameweeks

    try:
        timeframe = int(timeframe)
    except (ValueError, TypeError):
        timeframe = 5

    analytics_data = service.get_player_analytics(
        position=position,
        team=team,
        price_range=price_range,
        timeframe=timeframe
    )

    return Response(analytics_data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticatedOrReadOnly])
@throttle_classes([BurstRateThrottle])
def position_analytics(request):
    """
    Get position-specific analytics
    """
    from apps.analytics.services import PositionAnalyticsService

    service = PositionAnalyticsService()
    position = request.query_params.get('position')

    if not position:
        return Response(
            {'error': 'position parameter is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        position = int(position)
        if position not in [1, 2, 3, 4]:
            raise ValueError("Invalid position")
    except ValueError:
        return Response(
            {'error': 'position must be 1 (GK), 2 (DEF), 3 (MID), or 4 (FWD)'},
            status=status.HTTP_400_BAD_REQUEST
        )

    analytics_data = service.get_position_analytics(position)
    return Response(analytics_data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticatedOrReadOnly])
@cache_page(1800)  # Cache for 30 minutes
def transfer_trends(request):
    """
    Get transfer trends and insights
    """
    from apps.analytics.services import TransferTrendsService

    service = TransferTrendsService()

    # Parameters
    days = request.query_params.get('days', '7')
    position = request.query_params.get('position')

    try:
        days = min(int(days), 30)  # Limit to 30 days
    except (ValueError, TypeError):
        days = 7

    trends_data = service.get_transfer_trends(days=days, position=position)
    return Response(trends_data)


# Data Synchronization Endpoints
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([BurstRateThrottle])
def sync_player_data(request):
    """
    Trigger player data synchronization
    """
    from apps.fpl.tasks import update_player_data_task

    # Check if sync is already in progress
    sync_key = 'player_data_sync_in_progress'
    if cache.get(sync_key):
        return Response({
            'message': 'Player data sync already in progress',
            'status': 'running'
        }, status=status.HTTP_409_CONFLICT)

    # Start async sync
    async_sync = request.data.get('async', True)

    if async_sync:
        task = update_player_data_task.delay()
        return Response({
            'message': 'Player data sync started',
            'task_id': task.id,
            'status': 'started'
        }, status=status.HTTP_202_ACCEPTED)
    else:
        # Synchronous sync (not recommended for production)
        from apps.fpl.services import DataSyncService

        try:
            sync_service = DataSyncService()
            result = sync_service.sync_all_data()

            return Response({
                'message': 'Player data sync completed',
                'result': result,
                'status': 'completed'
            })
        except Exception as e:
            return Response({
                'error': 'sync_failed',
                'message': f'Sync failed: {str(e)}',
                'status': 'failed'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def sync_status(request):
    """
    Get synchronization status
    """
    from celery.result import AsyncResult

    task_id = request.query_params.get('task_id')

    if not task_id:
        return Response({
            'error': 'task_id parameter is required'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = AsyncResult(task_id)

        response_data = {
            'task_id': task_id,
            'status': result.status,
            'current': getattr(result, 'current', 0),
            'total': getattr(result, 'total', 0),
        }

        if result.ready():
            if result.successful():
                response_data['result'] = result.result
            else:
                response_data['error'] = str(result.result)

        return Response(response_data)

    except Exception as e:
        return Response({
            'error': 'invalid_task_id',
            'message': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


# Enhanced Bulk Operations
@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
@throttle_classes([BurstRateThrottle])
def bulk_operations(request):
    """
    Enhanced bulk operations endpoint
    """
    operation = request.data.get('operation')
    parameters = request.data.get('parameters', {})

    operations = {
        'update_player_data': bulk_update_player_data,
        'clear_cache': bulk_clear_cache,
        'generate_suggestions': bulk_generate_suggestions,
        'cleanup_old_data': bulk_cleanup_old_data,
    }

    if operation not in operations:
        return Response({
            'error': 'invalid_operation',
            'message': f'Unknown operation: {operation}',
            'available_operations': list(operations.keys())
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = operations[operation](parameters)
        return Response({
            'operation': operation,
            'status': 'completed',
            'result': result
        })

    except Exception as e:
        return Response({
            'operation': operation,
            'status': 'failed',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def bulk_update_player_data(parameters):
    """Update player data in bulk"""
    from apps.fpl.tasks import update_player_data_task

    task = update_player_data_task.delay()
    return {'task_id': task.id, 'message': 'Player data update started'}


def bulk_clear_cache(parameters):
    """Clear application cache"""
    from django.core.cache import cache

    pattern = parameters.get('pattern', '*')

    if pattern == '*':
        cache.clear()
        return {'message': 'All cache cleared'}
    else:
        # Pattern-based cache clearing would require Redis
        return {'message': f'Pattern-based clearing not implemented: {pattern}'}


def bulk_generate_suggestions(parameters):
    """Generate suggestions for multiple teams"""
    from apps.fpl.tasks import generate_suggestions_task
    from celery import group

    team_ids = parameters.get('team_ids', [])

    if not team_ids:
        raise ValueError('team_ids parameter is required')

    # Create group of tasks
    job = group(generate_suggestions_task.s(team_id) for team_id in team_ids)
    result = job.apply_async()

    return {
        'group_id': result.id,
        'team_count': len(team_ids),
        'message': f'Suggestion generation started for {len(team_ids)} teams'
    }


def bulk_cleanup_old_data(parameters):
    """Clean up old data"""
    from django.utils import timezone
    from datetime import timedelta
    from apps.fpl.models import TransferSuggestion

    days = parameters.get('days', 30)
    cutoff_date = timezone.now() - timedelta(days=days)

    # Clean up old suggestions
    deleted_count, _ = TransferSuggestion.objects.filter(
        created_at__lt=cutoff_date
    ).delete()

    return {
        'deleted_suggestions': deleted_count,
        'cutoff_date': cutoff_date.isoformat(),
        'message': f'Cleaned up data older than {days} days'
    }


# WebSocket endpoints for real-time updates (placeholder)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def websocket_info(request):
    """
    Get WebSocket connection information
    """
    return Response({
        'websocket_url': 'ws://localhost:8000/ws/v2/',
        'channels': {
            'player_updates': 'ws://localhost:8000/ws/v2/players/',
            'team_updates': 'ws://localhost:8000/ws/v2/teams/{team_id}/',
            'suggestions': 'ws://localhost:8000/ws/v2/suggestions/{team_id}/',
        },
        'authentication': 'JWT token in query parameter: ?token=<jwt_token>',
        'note': 'WebSocket support coming in v2.1.0'
    })


# URL patterns for v2
urlpatterns = [
    # API root
    path('', api_v2_root, name='api_v2_root'),

    # Include router URLs
    path('', include(router.urls)),

    # Analytics endpoints
    path('analytics/', analytics_overview, name='analytics_overview'),
    path('analytics/players/', player_analytics, name='player_analytics'),
    path('analytics/positions/', position_analytics, name='position_analytics'),
    path('analytics/trends/', transfer_trends, name='transfer_trends'),

    # Data synchronization
    path('sync/players/', sync_player_data, name='sync_player_data'),
    path('sync/status/', sync_status, name='sync_status'),

    # Bulk operations
    path('bulk/', bulk_operations, name='bulk_operations'),

    # WebSocket info
    path('ws/info/', websocket_info, name='websocket_info'),

    # Legacy analytics endpoint (for backward compatibility)
    path('analytics', analytics_view, name='analytics_legacy'),
]


# URL names for reverse lookups
app_name = 'v2'
