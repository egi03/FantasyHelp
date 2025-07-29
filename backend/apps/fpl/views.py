from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.views import APIView
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import rest_framework as filters
from django.core.cache import cache
from django.db.models import Q, Count, Avg, Max, Min, F
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from django.http import HttpResponse
from django.utils import timezone
from typing import Dict, Any, List, Optional
import structlog
from celery import group

from apps.core.views import BaseModelViewSet, OptimizedListView
from apps.core.permissions import IsOwnerOrReadOnly, IsAuthenticatedOrReadOnlyThrottled
from apps.core.throttling import BurstRateThrottle, SustainedRateThrottle
from apps.core.filters import BaseFilterSet, RangeFilter, ChoiceFilter
from apps.core.pagination import StandardResultsSetPagination, LargeResultsSetPagination
from apps.core.exceptions import ValidationError, NotFoundError, ServiceUnavailableError
from apps.core.utils import measure_time, cache_key_generator

from .models import (
    Team, Position, Player, UserTeam, TeamPlayer,
    TransferSuggestion, PlayerGameweekPerformance
)
from .serializers import (
    TeamSerializer, PositionSerializer, PlayerListSerializer,
    PlayerDetailSerializer, UserTeamSerializer, UserTeamCreateSerializer,
    TeamPlayerSerializer, TransferSuggestionSerializer,
    TransferSuggestionCreateSerializer, PlayerGameweekPerformanceSerializer,
    PlayerComparisonSerializer, PlayerSearchSerializer, AnalyticsSerializer
)
from .services import DataSyncService, TransferSuggestionEngine, AnalyticsService
from .filters import PlayerFilter, UserTeamFilter, TransferSuggestionFilter
from .tasks import sync_user_team_task, generate_suggestions_task, update_player_data_task

logger = structlog.get_logger(__name__)


class PlayerFilter(BaseFilterSet):
    """Advanced filtering for players"""

    position = ChoiceFilter(choices=[(1, 'GK'), (2, 'DEF'), (3, 'MID'), (4, 'FWD')])
    price_range = RangeFilter(field_name='current_price')
    points_range = RangeFilter(field_name='total_points')
    form_range = RangeFilter(field_name='form')
    team_name = filters.CharFilter(field_name='team__name', lookup_expr='icontains')
    available_only = filters.BooleanFilter(method='filter_available')

    class Meta:
        model = Player
        fields = {
            'status': ['exact', 'in'],
            'current_price': ['gte', 'lte', 'exact'],
            'total_points': ['gte', 'lte'],
            'form': ['gte', 'lte'],
            'selected_by_percent': ['gte', 'lte'],
            'team__name': ['icontains'],
            'position': ['exact'],
        }

    def filter_available(self, queryset, name, value):
        """Filter for available players only"""
        if value:
            return queryset.filter(status='a', minutes__gte=300)
        return queryset


class TeamViewSet(BaseModelViewSet):
    """
    ViewSet for Premier League teams
    Provides CRUD operations with caching and optimization
    """

    queryset = Team.objects.all().order_by('name')
    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
    lookup_field = 'fpl_id'

    @method_decorator(cache_page(3600))  # Cache for 1 hour
    @method_decorator(vary_on_headers('Authorization'))
    def list(self, request, *args, **kwargs):
        """List all teams with caching"""
        return super().list(request, *args, **kwargs)

    @method_decorator(cache_page(3600))
    def retrieve(self, request, *args, **kwargs):
        """Retrieve specific team with caching"""
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=['get'])
    def players(self, request, fpl_id=None):
        """Get all players for a team"""
        team = self.get_object()
        players = Player.objects.filter(team=team).select_related('position')

        # Apply filtering
        position = request.query_params.get('position')
        if position:
            players = players.filter(position_id=position)

        serializer = PlayerListSerializer(players, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def stats(self, request, fpl_id=None):
        """Get team statistics"""
        team = self.get_object()

        # Cache key for team stats
        cache_key = f"team_stats:{team.fpl_id}"
        cached_stats = cache.get(cache_key)

        if cached_stats:
            return Response(cached_stats)

        # Calculate team statistics
        players = team.players.filter(status='a')
        stats = {
            'total_players': players.count(),
            'average_price': players.aggregate(avg_price=Avg('current_price'))['avg_price'],
            'total_points': players.aggregate(total=Sum('total_points'))['total'],
            'top_scorer': players.order_by('-total_points').first(),
            'most_expensive': players.order_by('-current_price').first(),
            'position_breakdown': players.values('position__singular_name').annotate(
                count=Count('id')
            ),
        }

        # Serialize top players
        if stats['top_scorer']:
            stats['top_scorer'] = PlayerListSerializer(stats['top_scorer']).data
        if stats['most_expensive']:
            stats['most_expensive'] = PlayerListSerializer(stats['most_expensive']).data

        # Cache for 30 minutes
        cache.set(cache_key, stats, 1800)

        return Response(stats)


class PositionViewSet(BaseModelViewSet):
    """ViewSet for player positions"""

    queryset = Position.objects.all()
    serializer_class = PositionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    throttle_classes = [BurstRateThrottle]

    @method_decorator(cache_page(7200))  # Cache for 2 hours
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class PlayerViewSet(BaseModelViewSet):
    """
    Comprehensive player viewset with advanced features
    Includes search, filtering, comparison, and analytics
    """

    queryset = Player.objects.select_related('team', 'position').all()
    serializer_class = PlayerListSerializer
    permission_classes = [IsAuthenticatedOrReadOnlyThrottled]
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PlayerFilter
    search_fields = ['web_name', 'first_name', 'second_name', 'team__name']
    ordering_fields = [
        'total_points', 'form', 'points_per_game', 'current_price',
        'selected_by_percent', 'ict_index', 'minutes'
    ]
    ordering = ['-total_points']
    pagination_class = StandardResultsSetPagination
    lookup_field = 'fpl_id'

    def get_serializer_class(self):
        """Use different serializers for list and detail views"""
        if self.action == 'retrieve':
            return PlayerDetailSerializer
        return PlayerListSerializer

    def get_queryset(self):
        """Optimize queryset based on action"""
        queryset = super().get_queryset()

        if self.action == 'list':
            # Only select necessary fields for list view
            queryset = queryset.only(
                'id', 'fpl_id', 'web_name', 'current_price', 'total_points',
                'form', 'points_per_game', 'selected_by_percent', 'status',
                'minutes', 'team__name', 'team__short_name', 'position__singular_name'
            )

        return queryset

    @measure_time
    @method_decorator(cache_page(900))  # Cache for 15 minutes
    def list(self, request, *args, **kwargs):
        """List players with caching and optimization"""
        return super().list(request, *args, **kwargs)

    @method_decorator(cache_page(1800))  # Cache for 30 minutes
    def retrieve(self, request, *args, **kwargs):
        """Retrieve player details with caching"""
        return super().retrieve(request, *args, **kwargs)

    @action(detail=False, methods=['post'])
    def search(self, request):
        """Advanced player search with multiple criteria"""
        serializer = PlayerSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        queryset = self.get_queryset()

        # Apply search filters
        if data.get('query'):
            queryset = queryset.filter(
                Q(web_name__icontains=data['query']) |
                Q(first_name__icontains=data['query']) |
                Q(second_name__icontains=data['query']) |
                Q(team__name__icontains=data['query'])
            )

        if data.get('position'):
            queryset = queryset.filter(position_id=data['position'])

        if data.get('team'):
            queryset = queryset.filter(team__name__icontains=data['team'])

        if data.get('min_price'):
            queryset = queryset.filter(current_price__gte=data['min_price'])

        if data.get('max_price'):
            queryset = queryset.filter(current_price__lte=data['max_price'])

        if data.get('min_points'):
            queryset = queryset.filter(total_points__gte=data['min_points'])

        if data.get('status'):
            queryset = queryset.filter(status=data['status'])

        # Apply sorting
        sort_by = data.get('sort_by', '-total_points')
        queryset = queryset.order_by(sort_by)

        # Paginate results
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = PlayerListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = PlayerListSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def compare(self, request):
        """Compare multiple players side by side"""
        serializer = PlayerComparisonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        player_ids = data['player_ids']
        metrics = data['metrics']

        # Get players
        players = Player.objects.filter(id__in=player_ids).select_related('team', 'position')

        if len(players) != len(player_ids):
            raise ValidationError("Some players not found")

        # Build comparison data
        comparison_data = {
            'players': [],
            'metrics': metrics,
            'summary': {}
        }

        # Collect player data
        for player in players:
            player_data = {
                'id': player.id,
                'name': player.web_name,
                'team': player.team.short_name,
                'position': player.position.singular_name_short,
                'stats': {}
            }

            # Add requested metrics
            for metric in metrics:
                if hasattr(player, metric):
                    value = getattr(player, metric)
                    if hasattr(value, '__float__'):
                        player_data['stats'][metric] = float(value)
                    else:
                        player_data['stats'][metric] = value

            comparison_data['players'].append(player_data)

        # Add summary statistics
        for metric in metrics:
            values = [p['stats'].get(metric, 0) for p in comparison_data['players']]
            if values:
                comparison_data['summary'][metric] = {
                    'min': min(values),
                    'max': max(values),
                    'avg': sum(values) / len(values),
                    'best_player': max(comparison_data['players'],
                                     key=lambda x: x['stats'].get(metric, 0))['name']
                }

        return Response(comparison_data)

    @action(detail=True, methods=['get'])
    def performance_history(self, request, fpl_id=None):
        """Get player's gameweek performance history"""
        player = self.get_object()

        # Get performance data
        performances = PlayerGameweekPerformance.objects.filter(
            player=player
        ).order_by('-gameweek')

        # Apply gameweek filter if provided
        gameweeks = request.query_params.get('gameweeks')
        if gameweeks:
            try:
                gameweeks = int(gameweeks)
                performances = performances[:gameweeks]
            except ValueError:
                pass

        serializer = PlayerGameweekPerformanceSerializer(
            performances, many=True, context={'request': request}
        )

        # Calculate trend analysis
        points = [p.points for p in performances]
        if len(points) >= 3:
            recent_form = sum(points[:3]) / 3 if len(points) >= 3 else 0
            overall_avg = sum(points) / len(points)
            trend = 'improving' if recent_form > overall_avg else 'declining'
        else:
            trend = 'insufficient_data'

        return Response({
            'performances': serializer.data,
            'analysis': {
                'games_played': len(points),
                'average_points': sum(points) / len(points) if points else 0,
                'best_performance': max(points) if points else 0,
                'worst_performance': min(points) if points else 0,
                'trend': trend,
            }
        })

    @action(detail=False, methods=['get'])
    def top_performers(self, request):
        """Get top performing players by various metrics"""
        metric = request.query_params.get('metric', 'total_points')
        position = request.query_params.get('position')
        limit = min(int(request.query_params.get('limit', 20)), 50)

        queryset = self.get_queryset().filter(status='a', minutes__gte=500)

        if position:
            queryset = queryset.filter(position_id=position)

        # Apply metric-based ordering
        valid_metrics = {
            'total_points': '-total_points',
            'form': '-form',
            'points_per_game': '-points_per_game',
            'value': '-total_points',  # Will calculate value score
            'ict_index': '-ict_index',
            'selected': '-selected_by_percent',
        }

        if metric not in valid_metrics:
            raise ValidationError(f"Invalid metric. Choose from: {list(valid_metrics.keys())}")

        if metric == 'value':
            # Calculate value score and order by it
            queryset = queryset.extra(
                select={'value_score': 'total_points / current_price'}
            ).order_by('-value_score')
        else:
            queryset = queryset.order_by(valid_metrics[metric])

        players = queryset[:limit]
        serializer = PlayerListSerializer(players, many=True, context={'request': request})

        return Response({
            'metric': metric,
            'position_filter': position,
            'count': len(players),
            'players': serializer.data
        })


class UserTeamViewSet(BaseModelViewSet):
    """
    ViewSet for user FPL teams
    Handles team loading, management, and analysis
    """

    queryset = UserTeam.objects.select_related().prefetch_related(
        'players__player__team', 'players__player__position'
    )
    serializer_class = UserTeamSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = UserTeamFilter
    search_fields = ['team_name', 'manager_name']
    ordering_fields = ['total_points', 'overall_rank', 'team_value', 'last_updated']
    ordering = ['-total_points']
    lookup_field = 'fpl_team_id'

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def load_team(self, request):
        """Load/sync a team from FPL API"""
        serializer = UserTeamCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        team_id = serializer.validated_data['team_id']

        # Check if team exists and needs update
        try:
            existing_team = UserTeam.objects.get(fpl_team_id=team_id)
            time_since_update = timezone.now() - existing_team.last_updated

            # If updated within last 10 minutes, return cached version
            if time_since_update.total_seconds() < 600:
                logger.info("Returning cached team data", team_id=team_id)
                serializer = UserTeamSerializer(existing_team)
                return Response({
                    'message': 'Team data retrieved from cache',
                    'team': serializer.data,
                    'cached': True
                })

        except UserTeam.DoesNotExist:
            existing_team = None

        # Sync team data asynchronously for better performance
        if request.query_params.get('async', '').lower() in ['true', '1']:
            task = sync_user_team_task.delay(team_id)
            return Response({
                'message': 'Team sync started',
                'task_id': task.id,
                'team_id': team_id,
            }, status=status.HTTP_202_ACCEPTED)

        # Sync team data synchronously
        try:
            sync_service = DataSyncService()
            user_team = sync_service.sync_user_team(team_id)

            serializer = UserTeamSerializer(user_team)

            logger.info("Team loaded successfully",
                       team_id=team_id,
                       manager=user_team.manager_name)

            return Response({
                'message': 'Team loaded successfully',
                'team': serializer.data,
                'cached': False
            })

        except Exception as e:
            logger.error("Failed to load team", team_id=team_id, error=str(e))
            raise ServiceUnavailableError(f"Could not load team {team_id}: {str(e)}")

    @action(detail=True, methods=['get'])
    def analysis(self, request, fpl_team_id=None):
        """Get comprehensive team analysis"""
        team = self.get_object()

        # Cache key for team analysis
        cache_key = f"team_analysis:{team.fpl_team_id}"
        cached_analysis = cache.get(cache_key)

        if cached_analysis:
            return Response(cached_analysis)

        # Calculate team analysis
        players = team.players.select_related('player__team', 'player__position')

        analysis = {
            'team_info': {
                'name': team.team_name,
                'manager': team.manager_name,
                'total_points': team.total_points,
                'team_value': float(team.team_value),
                'bank_balance': float(team.bank_balance),
            },
            'squad_analysis': self._analyze_squad(players),
            'performance_metrics': self._calculate_performance_metrics(team, players),
            'position_breakdown': self._get_position_breakdown(players),
            'recommendations': self._get_team_recommendations(team, players),
        }

        # Cache for 15 minutes
        cache.set(cache_key, analysis, 900)

        return Response(analysis)

    def _analyze_squad(self, players) -> Dict[str, Any]:
        """Analyze squad composition and value"""
        total_value = sum(float(tp.player.current_price) for tp in players)
        bench_value = sum(float(tp.player.current_price) for tp in players if not tp.is_starter)

        return {
            'total_players': players.count(),
            'starters': len([p for p in players if p.is_starter]),
            'bench_players': len([p for p in players if not p.is_starter]),
            'total_squad_value': total_value,
            'bench_value': bench_value,
            'average_player_value': total_value / players.count() if players.count() > 0 else 0,
            'most_expensive': max(players, key=lambda x: x.player.current_price).player.web_name,
            'cheapest': min(players, key=lambda x: x.player.current_price).player.web_name,
        }

    def _calculate_performance_metrics(self, team, players) -> Dict[str, Any]:
        """Calculate team performance metrics"""
        total_points = sum(tp.player.total_points for tp in players)
        total_form = sum(float(tp.player.form) for tp in players)

        return {
            'squad_total_points': total_points,
            'average_player_points': total_points / players.count() if players.count() > 0 else 0,
            'squad_average_form': total_form / players.count() if players.count() > 0 else 0,
            'captain_performance': self._get_captain_performance(players),
            'bench_strength': self._calculate_bench_strength(players),
        }

    def _get_position_breakdown(self, players) -> Dict[str, Any]:
        """Get breakdown by position"""
        breakdown = {}

        for tp in players:
            pos_name = tp.player.position.singular_name
            if pos_name not in breakdown:
                breakdown[pos_name] = {
                    'count': 0,
                    'total_value': 0,
                    'total_points': 0,
                    'players': []
                }

            breakdown[pos_name]['count'] += 1
            breakdown[pos_name]['total_value'] += float(tp.player.current_price)
            breakdown[pos_name]['total_points'] += tp.player.total_points
            breakdown[pos_name]['players'].append({
                'name': tp.player.web_name,
                'price': float(tp.player.current_price),
                'points': tp.player.total_points,
                'form': float(tp.player.form),
            })

        return breakdown

    def _get_team_recommendations(self, team, players) -> List[Dict[str, Any]]:
        """Get quick team recommendations"""
        recommendations = []

        # Check for injured players
        injured_players = [tp for tp in players if tp.player.status != 'a']
        if injured_players:
            recommendations.append({
                'type': 'injury_concern',
                'message': f"You have {len(injured_players)} player(s) with injury concerns",
                'players': [tp.player.web_name for tp in injured_players]
            })

        # Check for low-performing players
        poor_form_players = [tp for tp in players if float(tp.player.form) < 2.0 and tp.is_starter]
        if poor_form_players:
            recommendations.append({
                'type': 'poor_form',
                'message': f"{len(poor_form_players)} starter(s) in poor form",
                'players': [tp.player.web_name for tp in poor_form_players]
            })

        # Check bench value
        bench_value = sum(float(tp.player.current_price) for tp in players if not tp.is_starter)
        if bench_value > 20.0:
            recommendations.append({
                'type': 'expensive_bench',
                'message': f"Bench value is high (£{bench_value}m) - consider downgrading",
            })

        return recommendations

    def _get_captain_performance(self, players) -> Dict[str, Any]:
        """Analyze captain performance"""
        captain = next((tp for tp in players if tp.is_captain), None)

        if captain:
            return {
                'name': captain.player.web_name,
                'total_points': captain.player.total_points,
                'form': float(captain.player.form),
                'selected_by_percent': float(captain.player.selected_by_percent),
            }

        return {}

    def _calculate_bench_strength(self, players) -> float:
        """Calculate bench strength score"""
        bench_players = [tp for tp in players if not tp.is_starter]
        if not bench_players:
            return 0.0

        total_points = sum(tp.player.total_points for tp in bench_players)
        return total_points / len(bench_players)


class TransferSuggestionViewSet(BaseModelViewSet):
    """
    ViewSet for transfer suggestions
    Provides AI-powered transfer recommendations
    """

    queryset = TransferSuggestion.objects.select_related(
        'user_team', 'player_out__team', 'player_out__position',
        'player_in__team', 'player_in__position'
    )
    serializer_class = TransferSuggestionSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = TransferSuggestionFilter
    ordering_fields = ['priority_score', 'confidence_score', 'cost_change', 'created_at']
    ordering = ['-priority_score']

    def get_queryset(self):
        """Filter suggestions by user's teams"""
        if self.request.user.is_authenticated:
            user_teams = UserTeam.objects.filter(
                # Add user relationship when implementing user auth
                # user=self.request.user
            )
            return super().get_queryset().filter(user_team__in=user_teams)
        return super().get_queryset().none()

    @action(detail=False, methods=['post'])
    def generate(self, request):
        """Generate new transfer suggestions for a team"""
        serializer = TransferSuggestionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        team_id = data['team_id']
        max_suggestions = data['max_suggestions']
        position_filter = data.get('position_filter')

        # Get user team
        try:
            user_team = UserTeam.objects.get(fpl_team_id=team_id)
        except UserTeam.DoesNotExist:
            raise NotFoundError(f"Team {team_id} not found. Please load the team first.")

        # Generate suggestions asynchronously for better performance
        if request.query_params.get('async', '').lower() in ['true', '1']:
            task = generate_suggestions_task.delay(
                team_id, max_suggestions, position_filter
            )
            return Response({
                'message': 'Suggestion generation started',
                'task_id': task.id,
                'team_id': team_id,
            }, status=status.HTTP_202_ACCEPTED)

        # Generate suggestions synchronously
        try:
            suggestion_engine = TransferSuggestionEngine()
            suggestions = suggestion_engine.generate_suggestions(
                user_team, max_suggestions
            )

            # Get saved suggestions from database
            saved_suggestions = TransferSuggestion.objects.filter(
                user_team=user_team
            ).select_related(
                'player_out__team', 'player_out__position',
                'player_in__team', 'player_in__position'
            ).order_by('-priority_score')

            if position_filter:
                saved_suggestions = saved_suggestions.filter(
                    player_out__position_id=position_filter
                )

            serializer = TransferSuggestionSerializer(
                saved_suggestions, many=True, context={'request': request}
            )

            logger.info("Transfer suggestions generated",
                       team_id=team_id,
                       suggestions_count=len(saved_suggestions))

            return Response({
                'message': 'Transfer suggestions generated successfully',
                'team_id': team_id,
                'count': len(saved_suggestions),
                'suggestions': serializer.data
            })

        except Exception as e:
            logger.error("Failed to generate suggestions",
                        team_id=team_id, error=str(e))
            raise ServiceUnavailableError(f"Could not generate suggestions: {str(e)}")

    @action(detail=True, methods=['post'])
    def mark_implemented(self, request, pk=None):
        """Mark a suggestion as implemented by the user"""
        suggestion = self.get_object()
        suggestion.mark_as_implemented()

        return Response({
            'message': 'Suggestion marked as implemented',
            'implemented_at': suggestion.implementation_date.isoformat()
        })


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
@throttle_classes([AnonRateThrottle])
@cache_page(1800)  # Cache for 30 minutes
def analytics_view(request):
    """Get FPL analytics and insights"""
    serializer = AnalyticsSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)

    data = serializer.validated_data
    metric = data['metric']
    position = data.get('position')
    gameweeks = data['gameweeks']
    limit = data['limit']

    analytics_service = AnalyticsService()

    try:
        if metric == 'top_performers':
            results = Player.objects.filter(
                status='a', minutes__gte=500
            ).select_related('team', 'position')

            if position:
                results = results.filter(position_id=position)

            results = results.order_by('-total_points')[:limit]

            data = {
                'metric': metric,
                'results': PlayerListSerializer(results, many=True).data
            }

        elif metric == 'position_analysis':
            if not position:
                raise ValidationError("Position is required for position analysis")

            data = analytics_service.get_position_analysis(position)

        else:
            raise ValidationError(f"Unsupported metric: {metric}")

        return Response(data)

    except Exception as e:
        logger.error("Analytics request failed", metric=metric, error=str(e))
        raise ServiceUnavailableError(f"Analytics unavailable: {str(e)}")


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
@throttle_classes([UserRateThrottle])
def bulk_update_view(request):
    """Bulk update operations for admin users"""
    action = request.data.get('action')

    if action == 'update_player_data':
        # Trigger player data update
        task = update_player_data_task.delay()
        return Response({
            'message': 'Player data update started',
            'task_id': task.id
        }, status=status.HTTP_202_ACCEPTED)

    elif action == 'clear_cache':
        # Clear application cache
        cache.clear()
        return Response({'message': 'Cache cleared successfully'})

    else:
        raise ValidationError(f"Unknown action: {action}")


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
@throttle_classes([AnonRateThrottle])
def health_check_view(request):
    """Health check endpoint for monitoring"""
    from django.db import connection
    from django.core.cache import cache
    import time

    start_time = time.time()
    health_status = {'status': 'healthy', 'checks': {}}

    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        health_status['checks']['database'] = 'healthy'
    except Exception as e:
        health_status['checks']['database'] = f'unhealthy: {str(e)}'
        health_status['status'] = 'unhealthy'

    # Cache check
    try:
        cache.set('health_check', 'ok', 30)
        cache.get('health_check')
        health_status['checks']['cache'] = 'healthy'
    except Exception as e:
        health_status['checks']['cache'] = f'unhealthy: {str(e)}'
        health_status['status'] = 'degraded'

    # FPL API check (simplified)
    try:
        # This would check FPL API connectivity
        health_status['checks']['fpl_api'] = 'healthy'
    except Exception as e:
        health_status['checks']['fpl_api'] = f'degraded: {str(e)}'
        if health_status['status'] == 'healthy':
            health_status['status'] = 'degraded'

    health_status['response_time'] = round((time.time() - start_time) * 1000, 2)
    health_status['timestamp'] = timezone.now().isoformat()

    # Return appropriate status code
    if health_status['status'] == 'healthy':
        return Response(health_status)
    elif health_status['status'] == 'degraded':
        return Response(health_status, status=status.HTTP_200_OK)
    else:
        return Response(health_status, status=status.HTTP_503_SERVICE_UNAVAILABLE)
