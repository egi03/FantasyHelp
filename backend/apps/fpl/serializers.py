from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.cache import cache
from typing import Dict, Any, List, Optional
import structlog

from apps.core.serializers import BaseModelSerializer, CachedSerializerMixin
from .models import (
    Team, Position, Player, UserTeam, TeamPlayer,
    TransferSuggestion, PlayerGameweekPerformance
)

logger = structlog.get_logger(__name__)


class TeamSerializer(CachedSerializerMixin, BaseModelSerializer):
    """Optimized Team serializer with caching"""

    class Meta:
        model = Team
        fields = [
            'id', 'fpl_id', 'name', 'short_name', 'code',
            'strength', 'strength_overall_home', 'strength_overall_away',
            'strength_attack_home', 'strength_attack_away',
            'strength_defence_home', 'strength_defence_away',
            'position', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def to_representation(self, instance):
        """Add computed fields to representation"""
        data = super().to_representation(instance)

        # Add computed strength ratings
        data['overall_strength'] = (
            instance.strength_overall_home + instance.strength_overall_away
        ) / 2

        data['attack_strength'] = (
            instance.strength_attack_home + instance.strength_attack_away
        ) / 2

        data['defence_strength'] = (
            instance.strength_defence_home + instance.strength_defence_away
        ) / 2

        return data


class PositionSerializer(BaseModelSerializer):
    """Position serializer with formation constraints"""

    class Meta:
        model = Position
        fields = [
            'id', 'singular_name', 'singular_name_short',
            'plural_name', 'plural_name_short',
            'squad_select', 'squad_min_play', 'squad_max_play'
        ]
        read_only_fields = ['id']


class PlayerListSerializer(CachedSerializerMixin, BaseModelSerializer):
    """Optimized serializer for player lists"""

    team_name = serializers.CharField(source='team.name', read_only=True)
    team_short_name = serializers.CharField(source='team.short_name', read_only=True)
    position_name = serializers.CharField(source='position.singular_name', read_only=True)
    position_short = serializers.CharField(source='position.singular_name_short', read_only=True)

    # Computed fields
    value_score = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()
    injury_status = serializers.SerializerMethodField()

    class Meta:
        model = Player
        fields = [
            'id', 'fpl_id', 'web_name', 'team_name', 'team_short_name',
            'position_name', 'position_short', 'current_price', 'total_points',
            'form', 'points_per_game', 'selected_by_percent', 'value_score',
            'is_available', 'injury_status', 'status', 'minutes'
        ]

    def get_value_score(self, obj) -> float:
        """Calculate value for money score"""
        return obj.value_score

    def get_is_available(self, obj) -> bool:
        """Check if player is available"""
        return obj.is_available

    def get_injury_status(self, obj) -> Optional[str]:
        """Get human-readable injury status"""
        if obj.status == 'i':
            return 'Injured'
        elif obj.status == 'd':
            return 'Doubtful'
        elif obj.status == 's':
            return 'Suspended'
        elif obj.status == 'u':
            return 'Unavailable'
        return None


class PlayerDetailSerializer(CachedSerializerMixin, BaseModelSerializer):
    """Comprehensive player detail serializer"""

    team = TeamSerializer(read_only=True)
    position = PositionSerializer(read_only=True)

    # Computed fields
    value_score = serializers.SerializerMethodField()
    form_trend = serializers.SerializerMethodField()
    recent_performance = serializers.SerializerMethodField()

    # Stats breakdown
    attacking_stats = serializers.SerializerMethodField()
    defensive_stats = serializers.SerializerMethodField()
    disciplinary_stats = serializers.SerializerMethodField()

    class Meta:
        model = Player
        fields = [
            'id', 'fpl_id', 'first_name', 'second_name', 'web_name',
            'team', 'position', 'status', 'current_price',

            # Performance metrics
            'total_points', 'form', 'points_per_game', 'selected_by_percent',
            'value_score', 'form_trend', 'recent_performance',

            # Game statistics
            'minutes', 'attacking_stats', 'defensive_stats', 'disciplinary_stats',

            # Advanced metrics
            'influence', 'creativity', 'threat', 'ict_index',
            'expected_goals', 'expected_assists', 'expected_goal_involvements',
            'expected_goals_conceded',

            # Dream team
            'dreamteam_count', 'in_dreamteam',

            # News and availability
            'news', 'news_added', 'chance_of_playing_this_round',
            'chance_of_playing_next_round',

            # Timestamps
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_value_score(self, obj) -> float:
        return obj.value_score

    def get_form_trend(self, obj) -> str:
        """Analyze form trend over recent games"""
        from apps.fpl.services import AnalyticsService
        trend_data = AnalyticsService.get_player_performance_trend(obj.id)
        return trend_data.get('trend', 'unknown')

    def get_recent_performance(self, obj) -> Dict[str, Any]:
        """Get recent performance summary"""
        recent_performances = PlayerGameweekPerformance.objects.filter(
            player=obj
        ).order_by('-gameweek')[:5]

        if not recent_performances:
            return {'games': 0, 'average_points': 0, 'scores': []}

        scores = [p.points for p in recent_performances]
        return {
            'games': len(scores),
            'average_points': round(sum(scores) / len(scores), 2),
            'scores': scores,
            'trend': 'improving' if len(scores) >= 2 and scores[0] > scores[-1] else 'stable'
        }

    def get_attacking_stats(self, obj) -> Dict[str, int]:
        """Get attacking statistics"""
        return {
            'goals_scored': obj.goals_scored,
            'assists': obj.assists,
            'expected_goals': float(obj.expected_goals),
            'expected_assists': float(obj.expected_assists),
            'bonus': obj.bonus,
        }

    def get_defensive_stats(self, obj) -> Dict[str, int]:
        """Get defensive statistics"""
        return {
            'clean_sheets': obj.clean_sheets,
            'goals_conceded': obj.goals_conceded,
            'own_goals': obj.own_goals,
            'penalties_saved': obj.penalties_saved,
            'saves': obj.saves,
            'expected_goals_conceded': float(obj.expected_goals_conceded),
        }

    def get_disciplinary_stats(self, obj) -> Dict[str, int]:
        """Get disciplinary statistics"""
        return {
            'yellow_cards': obj.yellow_cards,
            'red_cards': obj.red_cards,
            'penalties_missed': obj.penalties_missed,
        }


class TeamPlayerSerializer(BaseModelSerializer):
    """Serializer for players in a user's team"""

    player = PlayerListSerializer(read_only=True)
    profit_loss = serializers.SerializerMethodField()
    is_starter = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    class Meta:
        model = TeamPlayer
        fields = [
            'id', 'player', 'purchase_price', 'selling_price',
            'is_captain', 'is_vice_captain', 'multiplier', 'position',
            'profit_loss', 'is_starter', 'role'
        ]

    def get_profit_loss(self, obj) -> float:
        """Calculate profit/loss on player"""
        return float(obj.profit_loss)

    def get_is_starter(self, obj) -> bool:
        """Check if player is in starting XI"""
        return obj.is_starter

    def get_role(self, obj) -> str:
        """Get player's role in team"""
        if obj.is_captain:
            return 'Captain'
        elif obj.is_vice_captain:
            return 'Vice Captain'
        elif obj.is_starter:
            return 'Starter'
        else:
            return 'Bench'


class UserTeamSerializer(CachedSerializerMixin, BaseModelSerializer):
    """Comprehensive user team serializer"""

    players = TeamPlayerSerializer(many=True, read_only=True)

    # Computed fields
    team_strength = serializers.SerializerMethodField()
    position_counts = serializers.SerializerMethodField()
    captain_info = serializers.SerializerMethodField()
    bench_value = serializers.SerializerMethodField()

    class Meta:
        model = UserTeam
        fields = [
            'id', 'fpl_team_id', 'team_name', 'manager_name',
            'current_event', 'total_points', 'overall_rank',
            'bank_balance', 'team_value', 'free_transfers',
            'total_transfers', 'transfer_cost', 'event_points', 'event_rank',
            'auto_subs_played', 'players', 'team_strength',
            'position_counts', 'captain_info', 'bench_value',
            'last_updated'
        ]
        read_only_fields = ['id', 'last_updated']

    def get_team_strength(self, obj) -> float:
        """Calculate team strength score"""
        return obj.team_strength

    def get_position_counts(self, obj) -> Dict[str, int]:
        """Get player count by position"""
        return obj.get_position_counts()

    def get_captain_info(self, obj) -> Optional[Dict[str, Any]]:
        """Get captain information"""
        captain = obj.players.filter(is_captain=True).first()
        if captain:
            return {
                'name': captain.player.web_name,
                'price': float(captain.player.current_price),
                'form': float(captain.player.form),
                'total_points': captain.player.total_points
            }
        return None

    def get_bench_value(self, obj) -> float:
        """Calculate total value of bench players"""
        bench_players = obj.players.filter(position__gt=11)
        return float(sum(tp.player.current_price for tp in bench_players))


class UserTeamCreateSerializer(serializers.Serializer):
    """Serializer for creating/loading user teams"""

    team_id = serializers.IntegerField(
        min_value=1,
        max_value=10000000,
        help_text="FPL team ID (6-7 digits)"
    )

    def validate_team_id(self, value):
        """Validate FPL team ID format"""
        if not (100000 <= value <= 9999999):
            raise serializers.ValidationError(
                "FPL team ID must be between 100000 and 9999999"
            )
        return value


class TransferSuggestionSerializer(CachedSerializerMixin, BaseModelSerializer):
    """Transfer suggestion serializer with player details"""

    player_out = PlayerListSerializer(read_only=True)
    player_in = PlayerListSerializer(read_only=True)

    # Computed fields
    expected_roi = serializers.SerializerMethodField()
    risk_level = serializers.SerializerMethodField()

    class Meta:
        model = TransferSuggestion
        fields = [
            'id', 'player_out', 'player_in', 'suggestion_type',
            'reason', 'priority_score', 'cost_change',
            'predicted_points_gain', 'confidence_score',
            'expected_roi', 'risk_level', 'is_implemented',
            'implementation_date', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_expected_roi(self, obj) -> float:
        """Calculate expected return on investment"""
        return obj.expected_roi

    def get_risk_level(self, obj) -> str:
        """Determine risk level of suggestion"""
        if obj.confidence_score >= 80:
            return 'Low'
        elif obj.confidence_score >= 60:
            return 'Medium'
        else:
            return 'High'


class TransferSuggestionCreateSerializer(serializers.Serializer):
    """Serializer for generating transfer suggestions"""

    team_id = serializers.IntegerField(
        min_value=1,
        help_text="FPL team ID"
    )
    max_suggestions = serializers.IntegerField(
        default=10,
        min_value=1,
        max_value=50,
        help_text="Maximum number of suggestions to generate"
    )
    position_filter = serializers.ChoiceField(
        choices=[(1, 'Goalkeeper'), (2, 'Defender'), (3, 'Midfielder'), (4, 'Forward')],
        required=False,
        help_text="Filter suggestions by position"
    )

    def validate_team_id(self, value):
        """Validate team exists"""
        try:
            UserTeam.objects.get(fpl_team_id=value)
        except UserTeam.DoesNotExist:
            raise serializers.ValidationError(
                "Team not found. Please load the team first."
            )
        return value


class PlayerGameweekPerformanceSerializer(BaseModelSerializer):
    """Player gameweek performance serializer"""

    player_name = serializers.CharField(source='player.web_name', read_only=True)
    team_name = serializers.CharField(source='player.team.short_name', read_only=True)

    class Meta:
        model = PlayerGameweekPerformance
        fields = [
            'id', 'player_name', 'team_name', 'gameweek', 'points',
            'minutes', 'goals_scored', 'assists', 'clean_sheets',
            'goals_conceded', 'yellow_cards', 'red_cards', 'saves',
            'bonus', 'bps', 'influence', 'creativity', 'threat',
            'ict_index', 'selected', 'transfers_in', 'transfers_out'
        ]


class PlayerComparisonSerializer(serializers.Serializer):
    """Serializer for comparing multiple players"""

    player_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=2,
        max_length=10,
        help_text="List of player IDs to compare (2-10 players)"
    )

    metrics = serializers.ListField(
        child=serializers.ChoiceField(choices=[
            'total_points', 'form', 'points_per_game', 'current_price',
            'value_score', 'selected_by_percent', 'ict_index',
            'expected_goals', 'expected_assists', 'minutes'
        ]),
        default=['total_points', 'form', 'points_per_game', 'current_price'],
        help_text="Metrics to compare"
    )

    def validate_player_ids(self, value):
        """Validate all players exist and are in same position"""
        players = Player.objects.filter(id__in=value)

        if len(players) != len(value):
            raise serializers.ValidationError("One or more players not found")

        positions = set(p.position_id for p in players)
        if len(positions) > 1:
            raise serializers.ValidationError(
                "All players must be in the same position for comparison"
            )

        return value


class PlayerSearchSerializer(serializers.Serializer):
    """Serializer for player search parameters"""

    query = serializers.CharField(
        max_length=100,
        required=False,
        help_text="Search query for player name or team"
    )
    position = serializers.ChoiceField(
        choices=[(1, 'GK'), (2, 'DEF'), (3, 'MID'), (4, 'FWD')],
        required=False,
        help_text="Filter by position"
    )
    team = serializers.CharField(
        max_length=50,
        required=False,
        help_text="Filter by team name"
    )
    min_price = serializers.DecimalField(
        max_digits=4,
        decimal_places=1,
        min_value=3.5,
        max_value=15.0,
        required=False,
        help_text="Minimum price filter"
    )
    max_price = serializers.DecimalField(
        max_digits=4,
        decimal_places=1,
        min_value=3.5,
        max_value=15.0,
        required=False,
        help_text="Maximum price filter"
    )
    min_points = serializers.IntegerField(
        min_value=0,
        required=False,
        help_text="Minimum total points"
    )
    status = serializers.ChoiceField(
        choices=[('a', 'Available'), ('d', 'Doubtful'), ('i', 'Injured'),
                ('s', 'Suspended'), ('u', 'Unavailable')],
        default='a',
        help_text="Player status filter"
    )
    sort_by = serializers.ChoiceField(
        choices=[
            'total_points', '-total_points',
            'form', '-form',
            'points_per_game', '-points_per_game',
            'current_price', '-current_price',
            'selected_by_percent', '-selected_by_percent',
            'value_score', '-value_score'
        ],
        default='-total_points',
        help_text="Sort field and direction"
    )

    def validate(self, attrs):
        """Cross-field validation"""
        min_price = attrs.get('min_price')
        max_price = attrs.get('max_price')

        if min_price and max_price and min_price > max_price:
            raise serializers.ValidationError(
                "min_price cannot be greater than max_price"
            )

        return attrs


class AnalyticsSerializer(serializers.Serializer):
    """Serializer for analytics requests"""

    metric = serializers.ChoiceField(
        choices=[
            'top_performers', 'value_picks', 'form_players',
            'price_changes', 'ownership_trends', 'position_analysis'
        ],
        help_text="Type of analytics to retrieve"
    )
    position = serializers.ChoiceField(
        choices=[(1, 'GK'), (2, 'DEF'), (3, 'MID'), (4, 'FWD')],
        required=False,
        help_text="Filter by position (if applicable)"
    )
    gameweeks = serializers.IntegerField(
        default=5,
        min_value=1,
        max_value=38,
        help_text="Number of gameweeks to analyze"
    )
    limit = serializers.IntegerField(
        default=20,
        min_value=5,
        max_value=100,
        help_text="Maximum number of results"
    )


class BulkActionSerializer(serializers.Serializer):
    """Serializer for bulk operations"""

    action = serializers.ChoiceField(
        choices=['update_prices', 'refresh_data', 'generate_suggestions'],
        help_text="Bulk action to perform"
    )

    parameters = serializers.JSONField(
        default=dict,
        help_text="Action-specific parameters"
    )

    async_execution = serializers.BooleanField(
        default=True,
        help_text="Execute action asynchronously"
    )


# Utility serializers for common responses

class SuccessResponseSerializer(serializers.Serializer):
    """Standard success response"""

    message = serializers.CharField()
    data = serializers.JSONField(required=False)
    timestamp = serializers.DateTimeField()


class ErrorResponseSerializer(serializers.Serializer):
    """Standard error response"""

    error = serializers.CharField()
    details = serializers.JSONField(required=False)
    timestamp = serializers.DateTimeField()
    request_id = serializers.CharField(required=False)


class PaginationResponseSerializer(serializers.Serializer):
    """Paginated response wrapper"""

    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = serializers.ListField()


class HealthCheckSerializer(serializers.Serializer):
    """Health check response"""

    status = serializers.ChoiceField(choices=['healthy', 'degraded', 'unhealthy'])
    timestamp = serializers.DateTimeField()
    version = serializers.CharField()
    checks = serializers.DictField()
    uptime = serializers.IntegerField(help_text="Uptime in seconds")


# Custom validation mixins

class TimestampValidationMixin:
    """Mixin for timestamp validation"""

    def validate_created_at(self, value):
        """Validate created_at is not in future"""
        from django.utils import timezone
        if value and value > timezone.now():
            raise serializers.ValidationError("Created date cannot be in the future")
        return value


class PriceValidationMixin:
    """Mixin for FPL price validation"""

    def validate_current_price(self, value):
        """Validate FPL price format"""
        if value < 3.5 or value > 15.0:
            raise serializers.ValidationError(
                "Player price must be between £3.5m and £15.0m"
            )

        # FPL prices are in 0.1 increments
        if (value * 10) % 1 != 0:
            raise serializers.ValidationError(
                "Player price must be in £0.1m increments"
            )

        return value


# Factory function for dynamic serializer creation

def create_filtered_serializer(base_serializer_class, include_fields=None, exclude_fields=None):
    """
    Factory function to create filtered versions of serializers
    Useful for different API endpoints with different field requirements
    """

    class FilteredSerializer(base_serializer_class):
        class Meta(base_serializer_class.Meta):
            if include_fields:
                fields = include_fields
            elif exclude_fields:
                exclude = exclude_fields

    return FilteredSerializer


# Example usage of factory function
PlayerMinimalSerializer = create_filtered_serializer(
    PlayerListSerializer,
    include_fields=['id', 'web_name', 'current_price', 'total_points', 'form']
)

PlayerStatsSerializer = create_filtered_serializer(
    PlayerDetailSerializer,
    exclude_fields=['news', 'news_added', 'team', 'position']
)
