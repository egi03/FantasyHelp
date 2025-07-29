import asyncio
import aiohttp
import requests
import structlog
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.db.models import Q, F, Count, Avg, Max, Min

from apps.core.exceptions import (
    FPLAPIError,
    RateLimitExceededError,
    PlayerNotFoundError,
    TeamNotFoundError,
    ValidationError
)
from apps.core.utils import retry_with_backoff, measure_time
from .models import (
    Player, Team, Position, UserTeam, TeamPlayer,
    TransferSuggestion, PlayerGameweekPerformance
)

logger = structlog.get_logger(__name__)


class SuggestionType(Enum):
    """Types of transfer suggestions"""
    UPGRADE = "upgrade"
    SIDEWAYS = "sideways"
    DOWNGRADE = "downgrade"
    INJURY = "injury"
    ROTATION = "rotation"
    FIXTURE = "fixture"
    FORM = "form"
    VALUE = "value"


@dataclass
class PlayerStats:
    """Data class for player statistics"""
    total_points: int
    form: float
    points_per_game: float
    selected_by_percent: float
    value_score: float
    ict_index: float
    expected_goals: float
    expected_assists: float
    minutes: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_points': self.total_points,
            'form': self.form,
            'points_per_game': self.points_per_game,
            'selected_by_percent': self.selected_by_percent,
            'value_score': self.value_score,
            'ict_index': self.ict_index,
            'expected_goals': self.expected_goals,
            'expected_assists': self.expected_assists,
            'minutes': self.minutes,
        }


@dataclass
class TransferAnalysis:
    """Data class for transfer analysis results"""
    player_out_id: int
    player_in_id: int
    suggestion_type: SuggestionType
    priority_score: float
    cost_change: Decimal
    predicted_points_gain: float
    confidence_score: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            'player_out_id': self.player_out_id,
            'player_in_id': self.player_in_id,
            'suggestion_type': self.suggestion_type.value,
            'priority_score': self.priority_score,
            'cost_change': float(self.cost_change),
            'predicted_points_gain': self.predicted_points_gain,
            'confidence_score': self.confidence_score,
            'reason': self.reason,
        }


class FPLAPIClient:
    """
    High-performance FPL API client with advanced features
    Includes rate limiting, caching, retries, and error handling
    """

    def __init__(self):
        self.base_url = settings.FPL_API_SETTINGS['BASE_URL']
        self.timeout = settings.FPL_API_SETTINGS['TIMEOUT']
        self.retry_attempts = settings.FPL_API_SETTINGS['RETRY_ATTEMPTS']
        self.rate_limit = settings.FPL_API_SETTINGS['RATE_LIMIT']
        self.cache_ttl = settings.FPL_API_SETTINGS['CACHE_TTL']

        # Session setup with optimizations
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'FPL-Suggestions-API/2.0 (Enterprise)',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })

        # Rate limiting
        self._last_request_time = {}
        self._request_count = 0
        self._rate_limit_reset = timezone.now()

    def _check_rate_limit(self) -> None:
        """Check and enforce rate limiting"""
        now = timezone.now()

        # Reset counter every hour
        if now - self._rate_limit_reset > timedelta(hours=1):
            self._request_count = 0
            self._rate_limit_reset = now

        if self._request_count >= self.rate_limit:
            logger.warning("Rate limit exceeded", requests_count=self._request_count)
            raise RateLimitExceededError("FPL API rate limit exceeded")

        # Add small delay between requests
        if hasattr(self, '_last_request'):
            time_since_last = (now - self._last_request).total_seconds()
            if time_since_last < 0.1:  # 100ms minimum between requests
                import time
                time.sleep(0.1 - time_since_last)

        self._last_request = now
        self._request_count += 1

    @retry_with_backoff(max_retries=3)
    @measure_time
    def _make_request(self, endpoint: str, cache_key: Optional[str] = None) -> Dict[str, Any]:
        """Make HTTP request with caching and error handling"""
        # Check cache first
        if cache_key:
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                logger.debug("Cache hit", endpoint=endpoint, cache_key=cache_key)
                return cached_data

        # Check rate limit
        self._check_rate_limit()

        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            logger.info("Making FPL API request", url=url)
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()

            # Cache successful response
            if cache_key:
                cache.set(cache_key, data, self.cache_ttl)
                logger.debug("Cached response", cache_key=cache_key, ttl=self.cache_ttl)

            return data

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                raise RateLimitExceededError("FPL API rate limit exceeded")
            elif e.response.status_code == 404:
                raise PlayerNotFoundError(f"Endpoint not found: {endpoint}")
            else:
                raise FPLAPIError(f"HTTP error {e.response.status_code}: {e}")

        except requests.exceptions.RequestException as e:
            raise FPLAPIError(f"Request failed: {e}")

        except ValueError as e:
            raise FPLAPIError(f"Invalid JSON response: {e}")

    def get_bootstrap_data(self) -> Dict[str, Any]:
        """Get bootstrap data with caching"""
        cache_key = "fpl:bootstrap_data"
        return self._make_request("bootstrap-static/", cache_key)

    def get_team_data(self, team_id: int) -> Dict[str, Any]:
        """Get team data with caching"""
        cache_key = f"fpl:team:{team_id}"
        return self._make_request(f"entry/{team_id}/", cache_key)

    def get_team_picks(self, team_id: int, gameweek: Optional[int] = None) -> Dict[str, Any]:
        """Get team picks for gameweek"""
        if gameweek is None:
            # Get current gameweek from team data
            team_data = self.get_team_data(team_id)
            gameweek = team_data.get('current_event', 1)

        cache_key = f"fpl:picks:{team_id}:{gameweek}"
        return self._make_request(f"entry/{team_id}/event/{gameweek}/picks/", cache_key)

    def get_player_gameweek_data(self, player_id: int, gameweek: int) -> Dict[str, Any]:
        """Get player performance data for specific gameweek"""
        cache_key = f"fpl:player:{player_id}:gw:{gameweek}"
        return self._make_request(f"element-summary/{player_id}/", cache_key)

    def get_fixtures(self, gameweek: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get fixture data"""
        endpoint = "fixtures/"
        if gameweek:
            endpoint += f"?event={gameweek}"

        cache_key = f"fpl:fixtures:{gameweek if gameweek else 'all'}"
        return self._make_request(endpoint, cache_key)

    async def get_multiple_player_data(self, player_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """Get data for multiple players concurrently"""
        async with aiohttp.ClientSession() as session:
            tasks = []
            for player_id in player_ids:
                task = self._async_get_player_data(session, player_id)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            player_data = {}
            for player_id, result in zip(player_ids, results):
                if not isinstance(result, Exception):
                    player_data[player_id] = result
                else:
                    logger.warning("Failed to get player data",
                                 player_id=player_id, error=str(result))

            return player_data

    async def _async_get_player_data(self, session: aiohttp.ClientSession,
                                   player_id: int) -> Dict[str, Any]:
        """Async helper for getting player data"""
        url = f"{self.base_url}/element-summary/{player_id}/"

        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            else:
                raise FPLAPIError(f"Failed to get player {player_id}: {response.status}")


class DataSyncService:
    """
    Service for syncing FPL data with database
    Handles bulk updates and maintains data consistency
    """

    def __init__(self):
        self.api_client = FPLAPIClient()
        self.batch_size = settings.DATA_UPDATE_SETTINGS['BATCH_SIZE']

    @transaction.atomic
    @measure_time
    def sync_all_data(self) -> Dict[str, Any]:
        """Sync all FPL data (teams, positions, players)"""
        logger.info("Starting full data sync")

        results = {
            'teams': 0,
            'positions': 0,
            'players': 0,
            'errors': []
        }

        try:
            bootstrap_data = self.api_client.get_bootstrap_data()

            # Sync teams
            results['teams'] = self._sync_teams(bootstrap_data['teams'])

            # Sync positions
            results['positions'] = self._sync_positions(bootstrap_data['element_types'])

            # Sync players
            results['players'] = self._sync_players(bootstrap_data['elements'])

            logger.info("Data sync completed successfully", results=results)

        except Exception as e:
            logger.error("Data sync failed", error=str(e))
            results['errors'].append(str(e))
            raise

        return results

    def _sync_teams(self, teams_data: List[Dict[str, Any]]) -> int:
        """Sync team data"""
        team_objects = []

        for team_data in teams_data:
            team_objects.append({
                'fpl_id': team_data['id'],
                'name': team_data['name'],
                'short_name': team_data['short_name'],
                'code': team_data['code'],
                'pulse_id': team_data.get('pulse_id'),
                'strength': team_data.get('strength', 1000),
                'strength_overall_home': team_data.get('strength_overall_home', 1000),
                'strength_overall_away': team_data.get('strength_overall_away', 1000),
                'strength_attack_home': team_data.get('strength_attack_home', 1000),
                'strength_attack_away': team_data.get('strength_attack_away', 1000),
                'strength_defence_home': team_data.get('strength_defence_home', 1000),
                'strength_defence_away': team_data.get('strength_defence_away', 1000),
                'position': team_data.get('position'),
            })

        result = Team.objects.bulk_create_or_update(
            team_objects, ['fpl_id'], self.batch_size
        )

        logger.info("Teams synced", created=result['created'], updated=result['updated'])
        return result['created'] + result['updated']

    def _sync_positions(self, positions_data: List[Dict[str, Any]]) -> int:
        """Sync position data"""
        position_objects = []

        for pos_data in positions_data:
            position_objects.append({
                'id': pos_data['id'],
                'singular_name': pos_data['singular_name'],
                'singular_name_short': pos_data['singular_name_short'],
                'plural_name': pos_data['plural_name'],
                'plural_name_short': pos_data['plural_name_short'],
                'squad_select': pos_data['squad_select'],
                'squad_min_play': pos_data['squad_min_play'],
                'squad_max_play': pos_data['squad_max_play'],
            })

        result = Position.objects.bulk_create_or_update(
            position_objects, ['id'], self.batch_size
        )

        logger.info("Positions synced", created=result['created'], updated=result['updated'])
        return result['created'] + result['updated']

    def _sync_players(self, players_data: List[Dict[str, Any]]) -> int:
        """Sync player data with optimizations"""
        player_objects = []

        # Get team and position mappings for efficiency
        team_mapping = {team.fpl_id: team for team in Team.objects.all()}
        position_mapping = {pos.id: pos for pos in Position.objects.all()}

        for player_data in players_data:
            team = team_mapping.get(player_data['team'])
            position = position_mapping.get(player_data['element_type'])

            if not team or not position:
                logger.warning("Missing team or position",
                             player_id=player_data['id'],
                             team_id=player_data['team'],
                             position_id=player_data['element_type'])
                continue

            player_objects.append({
                'fpl_id': player_data['id'],
                'first_name': player_data['first_name'],
                'second_name': player_data['second_name'],
                'web_name': player_data['web_name'],
                'team_id': team.id,
                'position_id': position.id,
                'status': player_data.get('status', 'a'),
                'current_price': Decimal(str(player_data['now_cost'] / 10)),
                'total_points': player_data['total_points'],
                'form': Decimal(str(player_data.get('form', 0) or 0)),
                'points_per_game': Decimal(str(player_data.get('points_per_game', 0) or 0)),
                'selected_by_percent': Decimal(str(player_data.get('selected_by_percent', 0) or 0)),
                'minutes': player_data.get('minutes', 0),
                'goals_scored': player_data.get('goals_scored', 0),
                'assists': player_data.get('assists', 0),
                'clean_sheets': player_data.get('clean_sheets', 0),
                'goals_conceded': player_data.get('goals_conceded', 0),
                'own_goals': player_data.get('own_goals', 0),
                'penalties_saved': player_data.get('penalties_saved', 0),
                'penalties_missed': player_data.get('penalties_missed', 0),
                'yellow_cards': player_data.get('yellow_cards', 0),
                'red_cards': player_data.get('red_cards', 0),
                'saves': player_data.get('saves', 0),
                'bonus': player_data.get('bonus', 0),
                'bps': player_data.get('bps', 0),
                'influence': Decimal(str(player_data.get('influence', 0) or 0)),
                'creativity': Decimal(str(player_data.get('creativity', 0) or 0)),
                'threat': Decimal(str(player_data.get('threat', 0) or 0)),
                'ict_index': Decimal(str(player_data.get('ict_index', 0) or 0)),
                'expected_goals': Decimal(str(player_data.get('expected_goals', 0) or 0)),
                'expected_assists': Decimal(str(player_data.get('expected_assists', 0) or 0)),
                'expected_goal_involvements': Decimal(str(player_data.get('expected_goal_involvements', 0) or 0)),
                'expected_goals_conceded': Decimal(str(player_data.get('expected_goals_conceded', 0) or 0)),
                'dreamteam_count': player_data.get('dreamteam_count', 0),
                'in_dreamteam': player_data.get('in_dreamteam', False),
                'news': player_data.get('news', ''),
                'news_added': self._parse_date(player_data.get('news_added')),
                'chance_of_playing_this_round': player_data.get('chance_of_playing_this_round'),
                'chance_of_playing_next_round': player_data.get('chance_of_playing_next_round'),
            })

        result = Player.objects.bulk_create_or_update(
            player_objects, ['fpl_id'], self.batch_size
        )

        logger.info("Players synced", created=result['created'], updated=result['updated'])
        return result['created'] + result['updated']

    def _parse_date(self, date_string: Optional[str]) -> Optional[datetime]:
        """Parse FPL date string to datetime"""
        if not date_string:
            return None

        try:
            # FPL uses ISO format
            return datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None

    @transaction.atomic
    def sync_user_team(self, team_id: int) -> UserTeam:
        """Sync specific user team data"""
        logger.info("Syncing user team", team_id=team_id)

        try:
            # Get team data and picks
            team_data = self.api_client.get_team_data(team_id)
            picks_data = self.api_client.get_team_picks(team_id)

            # Update or create user team
            user_team, created = UserTeam.objects.update_or_create(
                fpl_team_id=team_id,
                defaults={
                    'team_name': team_data['name'],
                    'manager_name': f"{team_data['player_first_name']} {team_data['player_last_name']}",
                    'current_event': team_data['current_event'],
                    'total_points': team_data['summary_overall_points'],
                    'overall_rank': team_data.get('summary_overall_rank'),
                    'bank_balance': Decimal(str(picks_data['entry_history']['bank'] / 10)),
                    'team_value': Decimal(str(picks_data['entry_history']['value'] / 10)),
                    'free_transfers': picks_data['entry_history']['event_transfers'],
                    'total_transfers': team_data.get('total_transfers', 0),
                    'transfer_cost': picks_data['entry_history']['event_transfers_cost'],
                    'event_points': picks_data['entry_history']['points'],
                    'event_rank': picks_data['entry_history'].get('rank'),
                    'auto_subs_played': picks_data.get('automatic_subs', []) and len(picks_data['automatic_subs']),
                }
            )

            # Clear existing team players
            TeamPlayer.objects.filter(user_team=user_team).delete()

            # Add current team players
            team_players = []
            for pick in picks_data['picks']:
                try:
                    player = Player.objects.get(fpl_id=pick['element'])
                    team_players.append(TeamPlayer(
                        user_team=user_team,
                        player=player,
                        purchase_price=Decimal(str(pick['purchase_price'] / 10)),
                        selling_price=Decimal(str(pick['selling_price'] / 10)),
                        is_captain=pick['is_captain'],
                        is_vice_captain=pick['is_vice_captain'],
                        multiplier=pick['multiplier'],
                        position=pick['position'],
                    ))
                except Player.DoesNotExist:
                    logger.warning("Player not found in database",
                                 fpl_id=pick['element'])

            if team_players:
                TeamPlayer.objects.bulk_create(team_players)

            logger.info("User team synced successfully",
                       team_id=team_id,
                       created=created,
                       players_count=len(team_players))

            return user_team

        except Exception as e:
            logger.error("Failed to sync user team", team_id=team_id, error=str(e))
            raise TeamNotFoundError(f"Could not sync team {team_id}: {e}")


class TransferSuggestionEngine:
    """
    Advanced transfer suggestion engine with machine learning capabilities
    Analyzes player performance, fixtures, and team needs
    """

    def __init__(self):
        self.data_sync = DataSyncService()

        # Scoring weights for different factors
        self.weights = {
            'form': 0.25,
            'points_per_game': 0.20,
            'value': 0.15,
            'fixtures': 0.15,
            'ownership': 0.10,
            'ict': 0.10,
            'expected_stats': 0.05,
        }

    @measure_time
    def generate_suggestions(self, user_team: UserTeam,
                           max_suggestions: int = 10) -> List[TransferAnalysis]:
        """Generate comprehensive transfer suggestions"""
        logger.info("Generating transfer suggestions", team_id=user_team.fpl_team_id)

        # Get current team players
        current_players = list(
            user_team.players.select_related('player__team', 'player__position')
        )

        if len(current_players) != 15:
            logger.warning("Team doesn't have 15 players",
                         team_id=user_team.fpl_team_id,
                         player_count=len(current_players))

        suggestions = []

        # Analyze each position
        for position_id in [1, 2, 3, 4]:  # GK, DEF, MID, FWD
            position_players = [tp for tp in current_players
                              if tp.player.position_id == position_id]

            if position_players:
                position_suggestions = self._analyze_position_transfers(
                    user_team, position_players, position_id
                )
                suggestions.extend(position_suggestions)

        # Sort by priority score and limit results
        suggestions.sort(key=lambda x: x.priority_score, reverse=True)
        top_suggestions = suggestions[:max_suggestions]

        # Save to database
        self._save_suggestions(user_team, top_suggestions)

        logger.info("Transfer suggestions generated",
                   team_id=user_team.fpl_team_id,
                   suggestions_count=len(top_suggestions))

        return top_suggestions

    def _analyze_position_transfers(self, user_team: UserTeam,
                                  current_players: List[TeamPlayer],
                                  position_id: int) -> List[TransferAnalysis]:
        """Analyze transfer options for a specific position"""
        suggestions = []

        # Get available players in this position
        available_players = self._get_available_players(position_id, current_players)

        for current_player in current_players:
            # Skip if player is performing very well
            if self._is_essential_player(current_player.player):
                continue

            player_suggestions = self._find_replacements(
                user_team, current_player, available_players
            )
            suggestions.extend(player_suggestions)

        return suggestions

    def _get_available_players(self, position_id: int,
                             current_players: List[TeamPlayer]) -> List[Player]:
        """Get available players for transfer in position"""
        current_player_ids = [tp.player.id for tp in current_players]

        return list(
            Player.objects.filter(
                position_id=position_id,
                status='a',  # Available
                minutes__gte=300,  # Played at least 300 minutes
            )
            .exclude(id__in=current_player_ids)
            .select_related('team', 'position')
            .order_by('-total_points', '-form')[:50]  # Top 50 candidates
        )

    def _find_replacements(self, user_team: UserTeam,
                          current_player: TeamPlayer,
                          available_players: List[Player]) -> List[TransferAnalysis]:
        """Find suitable replacements for current player"""
        suggestions = []

        for replacement in available_players:
            # Check if transfer is financially viable
            cost_change = replacement.current_price - current_player.selling_price

            if cost_change <= user_team.bank_balance:
                analysis = self._analyze_transfer(
                    current_player.player, replacement, cost_change
                )

                if analysis.priority_score > 0:
                    suggestions.append(analysis)

        # Return top 3 suggestions for this player
        suggestions.sort(key=lambda x: x.priority_score, reverse=True)
        return suggestions[:3]

    def _analyze_transfer(self, player_out: Player, player_in: Player,
                         cost_change: Decimal) -> TransferAnalysis:
        """Analyze a specific transfer option"""

        # Calculate individual scores
        form_score = self._calculate_form_score(player_out, player_in)
        ppg_score = self._calculate_ppg_score(player_out, player_in)
        value_score = self._calculate_value_score(player_out, player_in)
        fixture_score = self._calculate_fixture_score(player_out, player_in)
        ownership_score = self._calculate_ownership_score(player_out, player_in)
        ict_score = self._calculate_ict_score(player_out, player_in)
        expected_score = self._calculate_expected_score(player_out, player_in)

        # Calculate weighted priority score
        priority_score = (
            form_score * self.weights['form'] +
            ppg_score * self.weights['points_per_game'] +
            value_score * self.weights['value'] +
            fixture_score * self.weights['fixtures'] +
            ownership_score * self.weights['ownership'] +
            ict_score * self.weights['ict'] +
            expected_score * self.weights['expected_stats']
        )

        # Determine suggestion type
        suggestion_type = self._determine_suggestion_type(
            player_out, player_in, cost_change
        )

        # Calculate predicted points gain
        predicted_points_gain = self._predict_points_gain(
            player_out, player_in, priority_score
        )

        # Calculate confidence score
        confidence_score = self._calculate_confidence(
            player_out, player_in, priority_score
        )

        # Generate reason
        reason = self._generate_transfer_reason(
            player_out, player_in, suggestion_type,
            form_score, ppg_score, value_score
        )

        return TransferAnalysis(
            player_out_id=player_out.id,
            player_in_id=player_in.id,
            suggestion_type=suggestion_type,
            priority_score=round(priority_score, 2),
            cost_change=cost_change,
            predicted_points_gain=round(predicted_points_gain, 2),
            confidence_score=round(confidence_score, 2),
            reason=reason
        )

    def _calculate_form_score(self, player_out: Player, player_in: Player) -> float:
        """Calculate form comparison score"""
        form_diff = float(player_in.form - player_out.form)
        return max(0, min(10, form_diff * 2))  # Scale to 0-10

    def _calculate_ppg_score(self, player_out: Player, player_in: Player) -> float:
        """Calculate points per game comparison score"""
        ppg_diff = float(player_in.points_per_game - player_out.points_per_game)
        return max(0, min(10, ppg_diff))  # Scale to 0-10

    def _calculate_value_score(self, player_out: Player, player_in: Player) -> float:
        """Calculate value for money score"""
        out_value = player_out.value_score
        in_value = player_in.value_score

        if out_value == 0:
            return 5.0  # Neutral score

        value_ratio = in_value / out_value
        return max(0, min(10, (value_ratio - 1) * 10))

    def _calculate_fixture_score(self, player_out: Player, player_in: Player) -> float:
        """Calculate fixture difficulty score (simplified)"""
        # This would analyze upcoming fixtures - simplified for now
        out_strength = (player_out.team.strength_attack_home +
                       player_out.team.strength_attack_away) / 2
        in_strength = (player_in.team.strength_attack_home +
                      player_in.team.strength_attack_away) / 2

        strength_diff = (in_strength - out_strength) / 100
        return max(0, min(10, strength_diff))

    def _calculate_ownership_score(self, player_out: Player, player_in: Player) -> float:
        """Calculate ownership differential score"""
        ownership_diff = float(player_in.selected_by_percent - player_out.selected_by_percent)

        # Reward lower ownership (differential picks)
        if ownership_diff < 0:
            return min(10, abs(ownership_diff) / 2)
        else:
            return max(0, 5 - ownership_diff / 4)

    def _calculate_ict_score(self, player_out: Player, player_in: Player) -> float:
        """Calculate ICT index comparison score"""
        ict_diff = float(player_in.ict_index - player_out.ict_index)
        return max(0, min(10, ict_diff / 5))

    def _calculate_expected_score(self, player_out: Player, player_in: Player) -> float:
        """Calculate expected stats comparison score"""
        out_expected = float(player_out.expected_goals + player_out.expected_assists)
        in_expected = float(player_in.expected_goals + player_in.expected_assists)

        expected_diff = in_expected - out_expected
        return max(0, min(10, expected_diff * 2))

    def _determine_suggestion_type(self, player_out: Player, player_in: Player,
                                 cost_change: Decimal) -> SuggestionType:
        """Determine the type of transfer suggestion"""
        if cost_change > 0.5:
            return SuggestionType.UPGRADE
        elif cost_change < -0.5:
            return SuggestionType.DOWNGRADE
        elif player_out.status != 'a':
            return SuggestionType.INJURY
        elif float(player_in.form) > float(player_out.form) + 1:
            return SuggestionType.FORM
        else:
            return SuggestionType.SIDEWAYS

    def _predict_points_gain(self, player_out: Player, player_in: Player,
                           priority_score: float) -> float:
        """Predict expected points gain over next 5 gameweeks"""
        base_prediction = float(player_in.points_per_game - player_out.points_per_game) * 5

        # Adjust based on priority score
        confidence_multiplier = priority_score / 10
        return base_prediction * confidence_multiplier

    def _calculate_confidence(self, player_out: Player, player_in: Player,
                            priority_score: float) -> float:
        """Calculate confidence in the suggestion"""
        base_confidence = 50.0  # Base 50%

        # Factors that increase confidence
        if player_in.minutes > player_out.minutes:
            base_confidence += 10

        if float(player_in.form) > float(player_out.form):
            base_confidence += 15

        if player_in.total_points > player_out.total_points:
            base_confidence += 10

        # Priority score influence
        priority_influence = (priority_score / 10) * 15

        final_confidence = base_confidence + priority_influence
        return max(20, min(95, final_confidence))  # Clamp between 20-95%

    def _generate_transfer_reason(self, player_out: Player, player_in: Player,
                                suggestion_type: SuggestionType,
                                form_score: float, ppg_score: float,
                                value_score: float) -> str:
        """Generate human-readable transfer reason"""
        reasons = []

        if form_score > 2:
            reasons.append(f"Better recent form ({player_in.form} vs {player_out.form})")

        if ppg_score > 1:
            reasons.append(f"Higher points per game ({player_in.points_per_game} vs {player_out.points_per_game})")

        if value_score > 2:
            reasons.append("Better value for money")

        if player_in.minutes > player_out.minutes + 200:
            reasons.append("More game time")

        if player_out.status != 'a':
            reasons.append(f"Current player is {player_out.get_status_display().lower()}")

        if not reasons:
            reasons.append("Potential upgrade based on overall statistics")

        return "; ".join(reasons[:3])  # Limit to top 3 reasons

    def _is_essential_player(self, player: Player) -> bool:
        """Check if player should be considered essential (unlikely to transfer)"""
        return (
            player.total_points > 150 and  # High season points
            float(player.form) > 6.0 and   # Good recent form
            float(player.selected_by_percent) > 30.0  # High ownership
        )

    def _save_suggestions(self, user_team: UserTeam,
                         suggestions: List[TransferAnalysis]) -> None:
        """Save suggestions to database"""
        # Clear existing suggestions
        TransferSuggestion.objects.filter(user_team=user_team).delete()

        # Create new suggestions
        suggestion_objects = []
        for suggestion in suggestions:
            suggestion_objects.append(TransferSuggestion(
                user_team=user_team,
                player_out_id=suggestion.player_out_id,
                player_in_id=suggestion.player_in_id,
                suggestion_type=suggestion.suggestion_type.value,
                reason=suggestion.reason,
                priority_score=Decimal(str(suggestion.priority_score)),
                cost_change=suggestion.cost_change,
                predicted_points_gain=Decimal(str(suggestion.predicted_points_gain)),
                confidence_score=Decimal(str(suggestion.confidence_score)),
            ))

        if suggestion_objects:
            TransferSuggestion.objects.bulk_create(suggestion_objects)


class AnalyticsService:
    """Service for advanced analytics and insights"""

    @staticmethod
    def get_player_performance_trend(player_id: int, gameweeks: int = 5) -> Dict[str, Any]:
        """Get player performance trend over recent gameweeks"""
        performances = PlayerGameweekPerformance.objects.filter(
            player_id=player_id
        ).order_by('-gameweek')[:gameweeks]

        if not performances:
            return {'trend': 'no_data', 'average_points': 0, 'games': 0}

        points = [p.points for p in performances]
        average_points = sum(points) / len(points)

        # Calculate trend
        if len(points) >= 3:
            recent_avg = sum(points[:3]) / 3
            older_avg = sum(points[3:]) / len(points[3:]) if len(points) > 3 else recent_avg

            if recent_avg > older_avg + 1:
                trend = 'improving'
            elif recent_avg < older_avg - 1:
                trend = 'declining'
            else:
                trend = 'stable'
        else:
            trend = 'insufficient_data'

        return {
            'trend': trend,
            'average_points': round(average_points, 2),
            'games': len(points),
            'recent_scores': points
        }

    @staticmethod
    def get_position_analysis(position_id: int) -> Dict[str, Any]:
        """Get comprehensive analysis for a position"""
        players = Player.objects.filter(
            position_id=position_id,
            status='a',
            minutes__gte=500
        ).select_related('team')

        if not players:
            return {'error': 'No players found'}

        # Calculate statistics
        stats = players.aggregate(
            avg_points=Avg('total_points'),
            avg_price=Avg('current_price'),
            avg_form=Avg('form'),
            max_points=Max('total_points'),
            min_price=Min('current_price')
        )

        # Top performers
        top_points = list(players.order_by('-total_points')[:5])
        best_value = list(
            players.extra(select={'value_score': 'total_points / current_price'})
            .order_by('-value_score')[:5]
        )

        return {
            'statistics': stats,
            'top_performers': [p.web_name for p in top_points],
            'best_value': [p.web_name for p in best_value],
            'total_players': len(players)
        }
