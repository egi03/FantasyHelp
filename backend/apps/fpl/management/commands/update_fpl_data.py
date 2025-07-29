from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.core.cache import cache
from typing import Any, Dict
import structlog

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

        try:
            from apps.fpl.services import DataSyncService

            sync_service = DataSyncService()
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
            from apps.fpl.services import DataSyncService
            from apps.fpl.models import Player, Team

            # Get current counts
            current_players = Player.objects.count()
            current_teams = Team.objects.count()

            self.stdout.write(f'Current players in database: {current_players}')
            self.stdout.write(f'Current teams in database: {current_teams}')

            # This would check API data in a real implementation
            self.stdout.write('API check would be performed here...')

            self.stdout.write(
                self.style.SUCCESS('Dry run completed successfully')
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Dry run failed: {str(e)}')
            )
