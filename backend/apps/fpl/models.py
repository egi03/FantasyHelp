from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.cache import cache
from django.utils import timezone
from decimal import Decimal
import uuid
from typing import Optional, Dict, Any, List

from apps.core.models import BaseModel, TimestampedModel, OptimizedManager


class Team(BaseModel):
    """Premier League teams with caching and optimization"""

    class Meta:
        db_table = 'fpl_teams'
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['name']),
        ]
        ordering = ['name']

    fpl_id = models.PositiveIntegerField(
        unique=True,
        help_text="FPL API team ID"
    )
    name = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Team name"
    )
    short_name = models.CharField(
        max_length=3,
        help_text="Three letter team code"
    )
    code = models.PositiveIntegerField(
        unique=True,
        db_index=True,
        help_text="Team code for assets"
    )
    pulse_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Pulse ID for news"
    )

    # Performance metrics
    strength = models.PositiveSmallIntegerField(
        default=1000,
        validators=[MinValueValidator(0), MaxValueValidator(5000)]
    )
    strength_overall_home = models.PositiveSmallIntegerField(default=1000)
    strength_overall_away = models.PositiveSmallIntegerField(default=1000)
    strength_attack_home = models.PositiveSmallIntegerField(default=1000)
    strength_attack_away = models.PositiveSmallIntegerField(default=1000)
    strength_defence_home = models.PositiveSmallIntegerField(default=1000)
    strength_defence_away = models.PositiveSmallIntegerField(default=1000)

    # Metadata
    position = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Current league position"
    )

    objects = OptimizedManager()

    def __str__(self) -> str:
        return self.name

    @classmethod
    def get_cached(cls, fpl_id: int) -> Optional['Team']:
        """Get team with caching"""
        cache_key = f"team:{fpl_id}"
        team = cache.get(cache_key)

        if team is None:
            try:
                team = cls.objects.get(fpl_id=fpl_id)
                cache.set(cache_key, team, 3600)  # Cache for 1 hour
            except cls.DoesNotExist:
                return None

        return team


class Position(BaseModel):
    """Player positions with caching"""

    class Meta:
        db_table = 'fpl_positions'
        ordering = ['id']

    GOALKEEPER = 1
    DEFENDER = 2
    MIDFIELDER = 3
    FORWARD = 4

    POSITION_CHOICES = [
        (GOALKEEPER, 'Goalkeeper'),
        (DEFENDER, 'Defender'),
        (MIDFIELDER, 'Midfielder'),
        (FORWARD, 'Forward'),
    ]

    singular_name = models.CharField(max_length=20)
    singular_name_short = models.CharField(max_length=3)
    plural_name = models.CharField(max_length=20)
    plural_name_short = models.CharField(max_length=3)

    # Formation constraints
    squad_select = models.PositiveSmallIntegerField(help_text="Number in full squad")
    squad_min_play = models.PositiveSmallIntegerField(help_text="Minimum playing")
    squad_max_play = models.PositiveSmallIntegerField(help_text="Maximum playing")

    def __str__(self) -> str:
        return self.singular_name


class Player(TimestampedModel):
    """
    Player model with comprehensive stats and optimizations
    Designed for high-performance queries and caching
    """

    class Meta:
        db_table = 'fpl_players'
        indexes = [
            models.Index(fields=['fpl_id']),
            models.Index(fields=['position', '-total_points']),
            models.Index(fields=['team', 'position']),
            models.Index(fields=['-form', '-points_per_game']),
            models.Index(fields=['current_price', 'position']),
            models.Index(fields=['-selected_by_percent']),
            models.Index(fields=['status']),
            models.Index(fields=['updated_at']),
        ]
        ordering = ['-total_points', '-form']

    # Core Information
    fpl_id = models.PositiveIntegerField(
        unique=True,
        db_index=True,
        help_text="FPL API player ID"
    )

    # Personal Details
    first_name = models.CharField(max_length=50)
    second_name = models.CharField(max_length=50, db_index=True)
    web_name = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Display name"
    )

    # Relationships
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='players'
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name='players'
    )

    # Status and Availability
    STATUS_CHOICES = [
        ('a', 'Available'),
        ('d', 'Doubtful'),
        ('i', 'Injured'),
        ('n', 'Not available'),
        ('s', 'Suspended'),
        ('u', 'Unavailable'),
    ]

    status = models.CharField(
        max_length=1,
        choices=STATUS_CHOICES,
        default='a',
        db_index=True
    )

    # Pricing
    current_price = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        db_index=True,
        help_text="Current price in millions"
    )

    # Performance Metrics
    total_points = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Season total points"
    )

    form = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=0.0,
        db_index=True,
        help_text="Average points last 5 games"
    )

    points_per_game = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0.0,
        db_index=True,
        help_text="Points per game played"
    )

    selected_by_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.0,
        db_index=True,
        help_text="Percentage of teams that own this player"
    )

    # Game Statistics
    minutes = models.PositiveIntegerField(default=0)
    goals_scored = models.PositiveIntegerField(default=0)
    assists = models.PositiveIntegerField(default=0)
    clean_sheets = models.PositiveIntegerField(default=0)
    goals_conceded = models.PositiveIntegerField(default=0)
    own_goals = models.PositiveIntegerField(default=0)
    penalties_saved = models.PositiveIntegerField(default=0)
    penalties_missed = models.PositiveIntegerField(default=0)
    yellow_cards = models.PositiveIntegerField(default=0)
    red_cards = models.PositiveIntegerField(default=0)
    saves = models.PositiveIntegerField(default=0)
    bonus = models.PositiveIntegerField(default=0)
    bps = models.PositiveIntegerField(
        default=0,
        help_text="Bonus Point System score"
    )

    # Influence, Creativity, Threat
    influence = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=0.0,
        help_text="Player's impact on team performance"
    )
    creativity = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=0.0,
        help_text="Player's creativity in final third"
    )
    threat = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=0.0,
        help_text="Player's threat in opposition box"
    )
    ict_index = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=0.0,
        help_text="Combined ICT score"
    )

    # Expected Stats (xG, xA)
    expected_goals = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.0,
        help_text="Expected goals"
    )
    expected_assists = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.0,
        help_text="Expected assists"
    )
    expected_goal_involvements = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.0,
        help_text="Expected goal involvements"
    )
    expected_goals_conceded = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.0,
        help_text="Expected goals conceded"
    )

    # Dream Team
    dreamteam_count = models.PositiveIntegerField(
        default=0,
        help_text="Times in dream team"
    )
    in_dreamteam = models.BooleanField(
        default=False,
        help_text="Currently in dream team"
    )

    # News and Updates
    news = models.TextField(
        blank=True,
        help_text="Latest news about player"
    )
    news_added = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When news was added"
    )

    # Constraints
    chance_of_playing_this_round = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Chance of playing percentage"
    )
    chance_of_playing_next_round = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    objects = OptimizedManager()

    def __str__(self) -> str:
        return f"{self.web_name} ({self.team.short_name})"

    @property
    def full_name(self) -> str:
        """Get player's full name"""
        return f"{self.first_name} {self.second_name}"

    @property
    def is_available(self) -> bool:
        """Check if player is available for selection"""
        return self.status == 'a'

    @property
    def value_score(self) -> float:
        """Calculate value for money score"""
        if self.current_price == 0:
            return 0
        return float(self.total_points) / float(self.current_price)

    @property
    def form_score(self) -> float:
        """Get form as float for calculations"""
        return float(self.form)

    def get_stats_dict(self) -> Dict[str, Any]:
        """Get comprehensive stats dictionary"""
        return {
            'total_points': self.total_points,
            'form': float(self.form),
            'points_per_game': float(self.points_per_game),
            'selected_by_percent': float(self.selected_by_percent),
            'value_score': self.value_score,
            'minutes': self.minutes,
            'goals_scored': self.goals_scored,
            'assists': self.assists,
            'clean_sheets': self.clean_sheets,
            'bonus': self.bonus,
            'ict_index': float(self.ict_index),
            'expected_goals': float(self.expected_goals),
            'expected_assists': float(self.expected_assists),
        }

    @classmethod
    def get_top_players(cls, position_id: int, limit: int = 20) -> List['Player']:
        """Get top players by position with caching"""
        cache_key = f"top_players:{position_id}:{limit}"
        players = cache.get(cache_key)

        if players is None:
            players = list(
                cls.objects.filter(position_id=position_id, status='a')
                .select_related('team', 'position')
                .order_by('-total_points', '-form')[:limit]
            )
            cache.set(cache_key, players, 1800)  # Cache for 30 minutes

        return players

    @classmethod
    def get_value_picks(cls, position_id: int, max_price: Decimal, limit: int = 10) -> List['Player']:
        """Get best value players under price threshold"""
        return list(
            cls.objects.filter(
                position_id=position_id,
                status='a',
                current_price__lte=max_price,
                minutes__gte=500  # Played at least 500 minutes
            )
            .select_related('team', 'position')
            .extra(select={'value_score': 'total_points / current_price'})
            .order_by('-value_score', '-form')[:limit]
        )


class UserTeam(TimestampedModel):
    """User's FPL team with comprehensive tracking"""

    class Meta:
        db_table = 'fpl_user_teams'
        indexes = [
            models.Index(fields=['fpl_team_id']),
            models.Index(fields=['manager_name']),
            models.Index(fields=['-total_points']),
            models.Index(fields=['last_updated']),
        ]
        ordering = ['-total_points']

    # Core Team Info
    fpl_team_id = models.PositiveIntegerField(
        unique=True,
        db_index=True,
        help_text="FPL team ID"
    )
    team_name = models.CharField(max_length=100)
    manager_name = models.CharField(max_length=100, db_index=True)

    # Performance Tracking
    current_event = models.PositiveSmallIntegerField(default=1)
    total_points = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Total points this season"
    )
    overall_rank = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Overall rank"
    )

    # Financial Information
    bank_balance = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=0.0,
        help_text="Money in bank (millions)"
    )
    team_value = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=100.0,
        help_text="Total team value (millions)"
    )

    # Transfer Information
    free_transfers = models.PositiveSmallIntegerField(default=1)
    total_transfers = models.PositiveIntegerField(default=0)
    transfer_cost = models.PositiveIntegerField(
        default=0,
        help_text="Points deducted for transfers"
    )

    # Gameweek Performance
    event_points = models.IntegerField(
        default=0,
        help_text="Points scored this gameweek"
    )
    event_rank = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Rank for current gameweek"
    )

    # Metadata
    last_updated = models.DateTimeField(auto_now=True, db_index=True)
    auto_subs_played = models.PositiveSmallIntegerField(default=0)

    objects = OptimizedManager()

    def __str__(self) -> str:
        return f"{self.team_name} - {self.manager_name}"

    @property
    def available_budget(self) -> Decimal:
        """Calculate total available budget for transfers"""
        return self.bank_balance

    @property
    def team_strength(self) -> float:
        """Calculate overall team strength score"""
        players = self.players.select_related('player')
        if not players:
            return 0.0

        total_points = sum(tp.player.total_points for tp in players)
        return total_points / len(players)

    def get_position_counts(self) -> Dict[str, int]:
        """Get count of players by position"""
        from django.db.models import Count

        return dict(
            self.players.values('player__position__singular_name')
            .annotate(count=Count('id'))
            .values_list('player__position__singular_name', 'count')
        )

    def can_afford_transfer(self, player_out_price: Decimal, player_in_price: Decimal) -> bool:
        """Check if team can afford a specific transfer"""
        cost_difference = player_in_price - player_out_price
        return cost_difference <= self.bank_balance


class TeamPlayer(BaseModel):
    """Players in a user's team with purchase details"""

    class Meta:
        db_table = 'fpl_team_players'
        unique_together = ['user_team', 'player']
        indexes = [
            models.Index(fields=['user_team', 'player']),
            models.Index(fields=['is_captain']),
            models.Index(fields=['is_vice_captain']),
            models.Index(fields=['multiplier']),
        ]
        ordering = ['user_team', '-multiplier', '-player__total_points']

    user_team = models.ForeignKey(
        UserTeam,
        on_delete=models.CASCADE,
        related_name='players'
    )
    player = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name='team_selections'
    )

    # Purchase Information
    purchase_price = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        help_text="Price when purchased"
    )
    selling_price = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        help_text="Current selling price"
    )

    # Team Selection
    is_captain = models.BooleanField(default=False, db_index=True)
    is_vice_captain = models.BooleanField(default=False, db_index=True)
    multiplier = models.PositiveSmallIntegerField(
        default=1,
        db_index=True,
        help_text="Points multiplier (1 for bench, 2 for captain)"
    )

    # Position in team
    position = models.PositiveSmallIntegerField(
        help_text="Position in team (1-15)"
    )

    def __str__(self) -> str:
        return f"{self.user_team.team_name} - {self.player.web_name}"

    @property
    def profit_loss(self) -> Decimal:
        """Calculate profit/loss on this player"""
        return self.selling_price - self.purchase_price

    @property
    def is_starter(self) -> bool:
        """Check if player is in starting XI"""
        return self.position <= 11

    @property
    def is_bench(self) -> bool:
        """Check if player is on bench"""
        return self.position > 11


class TransferSuggestion(TimestampedModel):
    """AI-generated transfer suggestions with scoring"""

    class Meta:
        db_table = 'fpl_transfer_suggestions'
        indexes = [
            models.Index(fields=['user_team', '-priority_score']),
            models.Index(fields=['player_out']),
            models.Index(fields=['player_in']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['suggestion_type']),
        ]
        ordering = ['-priority_score', '-created_at']

    SUGGESTION_TYPES = [
        ('upgrade', 'Upgrade Player'),
        ('sideways', 'Sideways Move'),
        ('downgrade', 'Downgrade for Funds'),
        ('injury', 'Injury Replacement'),
        ('rotation', 'Rotation Risk'),
        ('fixture', 'Fixture-based'),
        ('form', 'Form-based'),
        ('value', 'Value Play'),
    ]

    # Core Suggestion
    user_team = models.ForeignKey(
        UserTeam,
        on_delete=models.CASCADE,
        related_name='transfer_suggestions'
    )
    player_out = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name='suggestions_out'
    )
    player_in = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name='suggestions_in'
    )

    # Suggestion Details
    suggestion_type = models.CharField(
        max_length=20,
        choices=SUGGESTION_TYPES,
        default='upgrade',
        db_index=True
    )
    reason = models.TextField(help_text="Detailed reasoning for transfer")
    priority_score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        db_index=True,
        help_text="AI-calculated priority score"
    )

    # Financial Impact
    cost_change = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        help_text="Cost difference (negative = saves money)"
    )

    # Performance Predictions
    predicted_points_gain = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.0,
        help_text="Expected points improvement over 5 GWs"
    )
    confidence_score = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=50.0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Confidence in suggestion (0-100%)"
    )

    # Tracking
    is_implemented = models.BooleanField(
        default=False,
        help_text="Whether user made this transfer"
    )
    implementation_date = models.DateTimeField(
        null=True,
        blank=True
    )

    objects = OptimizedManager()

    def __str__(self) -> str:
        return f"{self.user_team.team_name}: {self.player_out.web_name} → {self.player_in.web_name}"

    @property
    def expected_roi(self) -> float:
        """Calculate expected return on investment"""
        if self.cost_change == 0:
            return float(self.predicted_points_gain)
        return float(self.predicted_points_gain) / abs(float(self.cost_change))

    def mark_as_implemented(self):
        """Mark suggestion as implemented by user"""
        self.is_implemented = True
        self.implementation_date = timezone.now()
        self.save(update_fields=['is_implemented', 'implementation_date'])


class PlayerGameweekPerformance(BaseModel):
    """Track player performance by gameweek for historical analysis"""

    class Meta:
        db_table = 'fpl_player_gameweek_performance'
        unique_together = ['player', 'gameweek']
        indexes = [
            models.Index(fields=['player', 'gameweek']),
            models.Index(fields=['gameweek', '-points']),
            models.Index(fields=['-points']),
        ]
        ordering = ['gameweek', '-points']

    player = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name='gameweek_performances'
    )
    gameweek = models.PositiveSmallIntegerField()

    # Performance Data
    points = models.IntegerField(default=0)
    minutes = models.PositiveSmallIntegerField(default=0)
    goals_scored = models.PositiveSmallIntegerField(default=0)
    assists = models.PositiveSmallIntegerField(default=0)
    clean_sheets = models.PositiveSmallIntegerField(default=0)
    goals_conceded = models.PositiveSmallIntegerField(default=0)
    yellow_cards = models.PositiveSmallIntegerField(default=0)
    red_cards = models.PositiveSmallIntegerField(default=0)
    saves = models.PositiveSmallIntegerField(default=0)
    bonus = models.PositiveSmallIntegerField(default=0)
    bps = models.PositiveSmallIntegerField(default=0)

    # Advanced Stats
    influence = models.DecimalField(max_digits=5, decimal_places=1, default=0.0)
    creativity = models.DecimalField(max_digits=5, decimal_places=1, default=0.0)
    threat = models.DecimalField(max_digits=5, decimal_places=1, default=0.0)
    ict_index = models.DecimalField(max_digits=5, decimal_places=1, default=0.0)

    # Selection Stats
    selected = models.PositiveIntegerField(
        default=0,
        help_text="Number of teams that selected this player"
    )
    transfers_in = models.PositiveIntegerField(default=0)
    transfers_out = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.player.web_name} - GW{self.gameweek}: {self.points}pts"
