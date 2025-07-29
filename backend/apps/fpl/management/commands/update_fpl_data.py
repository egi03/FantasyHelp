
"""
Usage: python manage.py update_fpl_data [--force] [--async]
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.core.cache import cache
from typing import Any, Dict
import structlog

from apps.fpl.services import DataSyncService
from apps.fpl.tasks import update_player_data_task

logger = structlog.get_logger(__name__)


class Command(BaseCommand):
    help = 'Update FPL data from the official API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update even if recently updated',
        )
        parser.add_argument(
            '--async',
            action='store_true',
            help='Run update asynchronously using Celery',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        """Execute the command"""

        verbosity = int(options.get('verbosity', 1))
        verbose = options['verbose'] or verbosity > 1
        force = options['force']
        async_update = options['async']
        dry_run = options['dry_run']

        if verbose:
            self.stdout.write(
                self.style.HTTP_INFO('Starting FPL data update...')
            )

        # Check if update is needed
        if not force and not self._should_update():
            self.stdout.write(
                self.style.WARNING('Data was recently updated. Use --force to override.')
            )
            return

        if dry_run:
            self._dry_run_update(verbose)
            return

        if async_update:
            self._async_update(verbose)
        else:
            self._sync_update(verbose)

    def _should_update(self) -> bool:
        """Check if update should proceed based on last update time"""
        last_update = cache.get('last_fpl_data_update')
        if not last_update:
            return True

        # Don't update if last update was within the last hour
        return (timezone.now() - last_update).total_seconds() > 3600

    def _dry_run_update(self, verbose: bool):
        """Show what would be updated without making changes"""
        self.stdout.write(
            self.style.HTTP_INFO('DRY RUN - No changes will be made')
        )

        try:
            sync_service = DataSyncService()

            # Get current counts
            from apps.fpl.models import Player, Team
            current_players = Player.objects.count()
            current_teams = Team.objects.count()

            self.stdout.write(f'Current players in database: {current_players}')
            self.stdout.write(f'Current teams in database: {current_teams}')

            # Get data from API (without saving)
            bootstrap_data = sync_service.api_client.get_bootstrap_data()
            if bootstrap_data:
                api_players = len(bootstrap_data['elements'])
                api_teams = len(bootstrap_data['teams'])

                self.stdout.write(f'Players available from API: {api_players}')
                self.stdout.write(f'Teams available from API: {api_teams}')

                self.stdout.write(
                    self.style.SUCCESS('Dry run completed successfully')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('Failed to fetch data from FPL API')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Dry run failed: {str(e)}')
            )

    def _async_update(self, verbose: bool):
        """Run update asynchronously"""
        try:
            task = update_player_data_task.delay()

            self.stdout.write(
                self.style.SUCCESS(f'Async update started with task ID: {task.id}')
            )

            if verbose:
                self.stdout.write('Use the following command to check status:')
                self.stdout.write(f'python manage.py check_task_status {task.id}')

        except Exception as e:
            raise CommandError(f'Failed to start async update: {str(e)}')

    def _sync_update(self, verbose: bool):
        """Run update synchronously"""
        try:
            sync_service = DataSyncService()

            if verbose:
                self.stdout.write('Fetching data from FPL API...')

            result = sync_service.sync_all_data()

            # Record successful update
            cache.set('last_fpl_data_update', timezone.now(), 86400)  # 24 hours

            # Display results
            self.stdout.write(
                self.style.SUCCESS('FPL data update completed successfully!')
            )

            if verbose:
                self.stdout.write(f"Teams updated: {result.get('teams', 0)}")
                self.stdout.write(f"Positions updated: {result.get('positions', 0)}")
                self.stdout.write(f"Players updated: {result.get('players', 0)}")

                if result.get('errors'):
                    self.stdout.write(
                        self.style.WARNING(f"Errors encountered: {len(result['errors'])}")
                    )
                    for error in result['errors'][:5]:  # Show first 5 errors
                        self.stdout.write(f"  - {error}")

        except Exception as e:
            raise CommandError(f'Failed to update FPL data: {str(e)}')


# ================================
# apps/fpl/management/commands/load_team.py
# ================================

"""
Management command to load a specific FPL team
Usage: python manage.py load_team <team_id> [--generate-suggestions]
"""

from django.core.management.base import BaseCommand, CommandError
from apps.fpl.services import DataSyncService, TransferSuggestionEngine
from apps.fpl.models import UserTeam


class Command(BaseCommand):
    help = 'Load a specific FPL team by ID'

    def add_arguments(self, parser):
        parser.add_argument(
            'team_id',
            type=int,
            help='FPL team ID to load'
        )
        parser.add_argument(
            '--generate-suggestions',
            action='store_true',
            help='Generate transfer suggestions after loading team',
        )
        parser.add_argument(
            '--update-data',
            action='store_true',
            help='Update player data before loading team',
        )

    def handle(self, *args, **options):
        team_id = options['team_id']
        generate_suggestions = options['generate_suggestions']
        update_data = options['update_data']

        # Validate team ID
        if not (100000 <= team_id <= 9999999):
            raise CommandError('Invalid team ID. Must be 6-7 digits.')

        try:
            sync_service = DataSyncService()

            # Update player data if requested
            if update_data:
                self.stdout.write('Updating player data first...')
                sync_service.sync_all_data()
                self.stdout.write(
                    self.style.SUCCESS('Player data updated.')
                )

            # Load team
            self.stdout.write(f'Loading team {team_id}...')
            user_team = sync_service.sync_user_team(team_id)

            self.stdout.write(
                self.style.SUCCESS(f'Team loaded successfully!')
            )
            self.stdout.write(f'Team: {user_team.team_name}')
            self.stdout.write(f'Manager: {user_team.manager_name}')
            self.stdout.write(f'Total Points: {user_team.total_points}')
            self.stdout.write(f'Team Value: £{user_team.team_value}m')
            self.stdout.write(f'Bank Balance: £{user_team.bank_balance}m')

            # Generate suggestions if requested
            if generate_suggestions:
                self.stdout.write('Generating transfer suggestions...')

                suggestion_engine = TransferSuggestionEngine()
                suggestions = suggestion_engine.generate_suggestions(user_team)

                self.stdout.write(
                    self.style.SUCCESS(f'Generated {len(suggestions)} suggestions:')
                )

                for i, suggestion in enumerate(suggestions[:5], 1):
                    self.stdout.write(
                        f'{i}. {suggestion.player_out.web_name} → '
                        f'{suggestion.player_in.web_name} '
                        f'(Score: {suggestion.priority_score}, '
                        f'Cost: £{suggestion.cost_change}m)'
                    )

        except Exception as e:
            raise CommandError(f'Failed to load team: {str(e)}')


# ================================
# apps/fpl/management/commands/generate_suggestions.py
# ================================

"""
Management command to generate transfer suggestions for teams
Usage: python manage.py generate_suggestions [--team-id <id>] [--all-teams]
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from apps.fpl.models import UserTeam, TransferSuggestion
from apps.fpl.services import TransferSuggestionEngine


class Command(BaseCommand):
    help = 'Generate transfer suggestions for FPL teams'

    def add_arguments(self, parser):
        parser.add_argument(
            '--team-id',
            type=int,
            help='Generate suggestions for specific team ID'
        )
        parser.add_argument(
            '--all-teams',
            action='store_true',
            help='Generate suggestions for all teams in database'
        )
        parser.add_argument(
            '--max-suggestions',
            type=int,
            default=10,
            help='Maximum number of suggestions per team (default: 10)'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=10,
            help='Number of teams to process in each batch (default: 10)'
        )

    def handle(self, *args, **options):
        team_id = options.get('team_id')
        all_teams = options['all_teams']
        max_suggestions = options['max_suggestions']
        batch_size = options['batch_size']

        if not team_id and not all_teams:
            raise CommandError('Must specify either --team-id or --all-teams')

        if team_id and all_teams:
            raise CommandError('Cannot specify both --team-id and --all-teams')

        suggestion_engine = TransferSuggestionEngine()

        if team_id:
            self._generate_for_team(suggestion_engine, team_id, max_suggestions)
        else:
            self._generate_for_all_teams(suggestion_engine, max_suggestions, batch_size)

    def _generate_for_team(self, engine, team_id: int, max_suggestions: int):
        """Generate suggestions for a single team"""
        try:
            user_team = UserTeam.objects.get(fpl_team_id=team_id)

            self.stdout.write(f'Generating suggestions for team {team_id}...')

            suggestions = engine.generate_suggestions(user_team, max_suggestions)

            self.stdout.write(
                self.style.SUCCESS(
                    f'Generated {len(suggestions)} suggestions for {user_team.team_name}'
                )
            )

            # Display top suggestions
            for i, suggestion in enumerate(suggestions[:3], 1):
                self.stdout.write(
                    f'{i}. {suggestion.player_out.web_name} → '
                    f'{suggestion.player_in.web_name} '
                    f'(Priority: {suggestion.priority_score})'
                )

        except UserTeam.DoesNotExist:
            raise CommandError(f'Team {team_id} not found in database')
        except Exception as e:
            raise CommandError(f'Failed to generate suggestions: {str(e)}')

    def _generate_for_all_teams(self, engine, max_suggestions: int, batch_size: int):
        """Generate suggestions for all teams"""
        teams = UserTeam.objects.all()
        total_teams = teams.count()

        if total_teams == 0:
            self.stdout.write(
                self.style.WARNING('No teams found in database')
            )
            return

        self.stdout.write(f'Generating suggestions for {total_teams} teams...')

        processed = 0
        errors = 0

        # Process in batches
        for start in range(0, total_teams, batch_size):
            end = min(start + batch_size, total_teams)
            batch_teams = teams[start:end]

            self.stdout.write(f'Processing batch {start//batch_size + 1}...')

            for team in batch_teams:
                try:
                    suggestions = engine.generate_suggestions(team, max_suggestions)
                    processed += 1

                    if processed % 10 == 0:  # Progress update every 10 teams
                        self.stdout.write(f'Processed {processed}/{total_teams} teams')

                except Exception as e:
                    errors += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f'Failed to generate suggestions for team {team.fpl_team_id}: {str(e)}'
                        )
                    )

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed! Processed {processed} teams, {errors} errors'
            )
        )

        # Show total suggestions generated
        total_suggestions = TransferSuggestion.objects.count()
        self.stdout.write(f'Total suggestions in database: {total_suggestions}')


# ================================
# apps/fpl/management/commands/cleanup_data.py
# ================================

"""
Management command to clean up old data
Usage: python manage.py cleanup_data [--days <days>] [--dry-run]
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.fpl.models import TransferSuggestion, PlayerGameweekPerformance


class Command(BaseCommand):
    help = 'Clean up old data from the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Delete data older than this many days (default: 30)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        parser.add_argument(
            '--suggestions-only',
            action='store_true',
            help='Only clean up transfer suggestions'
        )
        parser.add_argument(
            '--performance-only',
            action='store_true',
            help='Only clean up performance data'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        suggestions_only = options['suggestions_only']
        performance_only = options['performance_only']

        cutoff_date = timezone.now() - timedelta(days=days)

        self.stdout.write(
            f'Cleaning up data older than {cutoff_date.strftime("%Y-%m-%d %H:%M:%S")}'
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN - No data will be deleted')
            )

        total_deleted = 0

        # Clean up transfer suggestions
        if not performance_only:
            deleted_suggestions = self._cleanup_suggestions(cutoff_date, dry_run)
            total_deleted += deleted_suggestions

        # Clean up performance data
        if not suggestions_only:
            deleted_performance = self._cleanup_performance_data(cutoff_date, dry_run)
            total_deleted += deleted_performance

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'Would delete {total_deleted} total records')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Deleted {total_deleted} total records')
            )

    def _cleanup_suggestions(self, cutoff_date, dry_run: bool) -> int:
        """Clean up old transfer suggestions"""
        suggestions_query = TransferSuggestion.objects.filter(
            created_at__lt=cutoff_date
        )

        count = suggestions_query.count()

        if count > 0:
            if dry_run:
                self.stdout.write(f'Would delete {count} transfer suggestions')
            else:
                suggestions_query.delete()
                self.stdout.write(f'Deleted {count} transfer suggestions')
        else:
            self.stdout.write('No old transfer suggestions to delete')

        return count

    def _cleanup_performance_data(self, cutoff_date, dry_run: bool) -> int:
        """Clean up old performance data"""
        # Keep performance data for longer (90 days default)
        performance_cutoff = timezone.now() - timedelta(days=90)

        performance_query = PlayerGameweekPerformance.objects.filter(
            created_at__lt=performance_cutoff
        )

        count = performance_query.count()

        if count > 0:
            if dry_run:
                self.stdout.write(f'Would delete {count} performance records')
            else:
                performance_query.delete()
                self.stdout.write(f'Deleted {count} performance records')
        else:
            self.stdout.write('No old performance data to delete')

        return count


# ================================
# apps/fpl/management/commands/check_task_status.py
# ================================

"""
Management command to check Celery task status
Usage: python manage.py check_task_status <task_id>
"""

from django.core.management.base import BaseCommand, CommandError
from celery.result import AsyncResult
import json


class Command(BaseCommand):
    help = 'Check the status of a Celery task'

    def add_arguments(self, parser):
        parser.add_argument(
            'task_id',
            type=str,
            help='Celery task ID to check'
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Output result in JSON format'
        )

    def handle(self, *args, **options):
        task_id = options['task_id']
        json_output = options['json']

        try:
            result = AsyncResult(task_id)

            status_info = {
                'task_id': task_id,
                'status': result.status,
                'ready': result.ready(),
                'successful': result.successful() if result.ready() else None,
                'failed': result.failed() if result.ready() else None,
            }

            if result.ready():
                if result.successful():
                    status_info['result'] = result.result
                else:
                    status_info['error'] = str(result.result)
                    if hasattr(result, 'traceback'):
                        status_info['traceback'] = result.traceback
            elif hasattr(result, 'info') and result.info:
                status_info['progress'] = result.info

            if json_output:
                self.stdout.write(
                    json.dumps(status_info, indent=2, default=str)
                )
            else:
                self._display_status(status_info)

        except Exception as e:
            if json_output:
                self.stdout.write(
                    json.dumps({'error': str(e)}, indent=2)
                )
            else:
                raise CommandError(f'Failed to check task status: {str(e)}')

    def _display_status(self, status_info):
        """Display status in human-readable format"""
        self.stdout.write(f"Task ID: {status_info['task_id']}")
        self.stdout.write(f"Status: {status_info['status']}")

        if status_info['ready']:
            if status_info['successful']:
                self.stdout.write(
                    self.style.SUCCESS('Task completed successfully!')
                )
                if 'result' in status_info:
                    self.stdout.write('Result:')
                    self.stdout.write(json.dumps(status_info['result'], indent=2, default=str))
            else:
                self.stdout.write(
                    self.style.ERROR('Task failed!')
                )
                if 'error' in status_info:
                    self.stdout.write(f"Error: {status_info['error']}")
        else:
            self.stdout.write('Task is still running...')
            if 'progress' in status_info:
                self.stdout.write('Progress:')
                self.stdout.write(json.dumps(status_info['progress'], indent=2, default=str))


# ================================
# apps/fpl/management/commands/export_data.py
# ================================

"""
Management command to export FPL data
Usage: python manage.py export_data --type <type> --format <format> --output <file>
"""

from django.core.management.base import BaseCommand, CommandError
from django.core import serializers
from apps.fpl.models import Player, Team, UserTeam, TransferSuggestion
import csv
import json


class Command(BaseCommand):
    help = 'Export FPL data to various formats'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            choices=['players', 'teams', 'user_teams', 'suggestions', 'all'],
            required=True,
            help='Type of data to export'
        )
        parser.add_argument(
            '--format',
            choices=['json', 'csv', 'xml'],
            default='json',
            help='Export format (default: json)'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Output file path (if not specified, prints to stdout)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of records to export'
        )
        parser.add_argument(
            '--filter',
            type=str,
            help='JSON string of filters to apply'
        )

    def handle(self, *args, **options):
        data_type = options['type']
        format_type = options['format']
        output_file = options.get('output')
        limit = options.get('limit')
        filter_json = options.get('filter')

        # Parse filters
        filters = {}
        if filter_json:
            try:
                filters = json.loads(filter_json)
            except json.JSONDecodeError:
                raise CommandError('Invalid JSON in --filter argument')

        # Export data
        if data_type == 'all':
            self._export_all_data(format_type, output_file, limit, filters)
        else:
            self._export_single_type(data_type, format_type, output_file, limit, filters)

    def _export_single_type(self, data_type: str, format_type: str,
                           output_file: str, limit: int, filters: dict):
        """Export single data type"""
        # Get queryset based on type
        model_map = {
            'players': Player,
            'teams': Team,
            'user_teams': UserTeam,
            'suggestions': TransferSuggestion,
        }

        model = model_map[data_type]
        queryset = model.objects.filter(**filters)

        if limit:
            queryset = queryset[:limit]

        # Export based on format
        if format_type == 'json':
            data = serializers.serialize('json', queryset, indent=2)
        elif format_type == 'xml':
            data = serializers.serialize('xml', queryset)
        elif format_type == 'csv':
            data = self._export_csv(queryset)

        # Output data
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(data)
            self.stdout.write(
                self.style.SUCCESS(f'Data exported to {output_file}')
            )
        else:
            self.stdout.write(data)

    def _export_all_data(self, format_type: str, output_file: str,
                        limit: int, filters: dict):
        """Export all data types"""
        all_data = {}

        model_map = {
            'teams': Team,
            'players': Player,
            'user_teams': UserTeam,
            'suggestions': TransferSuggestion,
        }

        for name, model in model_map.items():
            queryset = model.objects.filter(**filters)
            if limit:
                queryset = queryset[:limit]

            if format_type == 'json':
                # Convert to list of dictionaries for JSON
                data = []
                for obj in queryset:
                    if hasattr(obj, 'to_dict'):
                        data.append(obj.to_dict())
                    else:
                        # Fallback serialization
                        serialized = serializers.serialize('python', [obj])
                        data.append(serialized[0]['fields'])

                all_data[name] = data

        # Output
        if format_type == 'json':
            output = json.dumps(all_data, indent=2, default=str)
        else:
            raise CommandError('All data export only supports JSON format')

        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output)
            self.stdout.write(
                self.style.SUCCESS(f'All data exported to {output_file}')
            )
        else:
            self.stdout.write(output)

    def _export_csv(self, queryset) -> str:
        """Export queryset to CSV format"""
        if not queryset:
            return ''

        import io
        output = io.StringIO()

        # Get field names from first object
        first_obj = queryset.first()
        if hasattr(first_obj, 'to_dict'):
            field_names = list(first_obj.to_dict().keys())
        else:
            field_names = [f.name for f in first_obj._meta.fields]

        writer = csv.DictWriter(output, fieldnames=field_names)
        writer.writeheader()

        for obj in queryset:
            if hasattr(obj, 'to_dict'):
                row_data = obj.to_dict()
            else:
                row_data = {f.name: getattr(obj, f.name) for f in obj._meta.fields}

            # Convert non-string values
            for key, value in row_data.items():
                if value is None:
                    row_data[key] = ''
                else:
                    row_data[key] = str(value)

            writer.writerow(row_data)

        return output.getvalue()
