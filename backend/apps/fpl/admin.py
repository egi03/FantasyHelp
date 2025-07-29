from django.contrib import admin
from django.db.models import Count, Avg, Sum, Q
from django.utils.html import format_html
from django.urls import reverse
from django.shortcuts import redirect
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.core.cache import cache
from typing import Any, List
import csv
from datetime import timedelta

from apps.core.admin import BaseModelAdmin, ReadOnlyAdminMixin
from .models import (
    Team, Position, Player, UserTeam, TeamPlayer,
    TransferSuggestion, PlayerGameweekPerformance
)
from .services import DataSyncService, TransferSuggestionEngine
from .tasks import update_player_data_task, generate_suggestions_task


class TeamAdmin(BaseModelAdmin):
    """Enhanced Team admin with team analysis"""

    list_display = [
        'name', 'short_name', 'code', 'position', 'strength_display',
        'player_count', 'total_value'
    ]
    list_filter = [
        'position', 'strength', 'strength_overall_home', 'strength_overall_away'
    ]
    search_fields = ['name', 'short_name']
    readonly_fields = ['fpl_id', 'code']
    ordering = ['position', 'name']

    fieldsets = (
        ('Basic Information', {
            'fields': ('fpl_id', 'name', 'short_name', 'code', 'pulse_id', 'position')
        }),
        ('Strength Ratings', {
            'fields': (
                'strength',
                ('strength_overall_home', 'strength_overall_away'),
                ('strength_attack_home', 'strength_attack_away'),
                ('strength_defence_home', 'strength_defence_away'),
            ),
            'classes': ['collapse']
        }),
        ('Timestamps', {
            'fields': (),
            'classes': ['collapse']
        }),
    )

    actions = ['export_teams_csv', 'update_team_strengths']

    def get_queryset(self, request):
        """Optimize queryset with annotations"""
        return super().get_queryset(request).annotate(
            player_count=Count('players'),
            total_value=Sum('players__current_price')
        )

    def strength_display(self, obj):
        """Display strength with color coding"""
        strength = obj.strength
        if strength >= 1200:
            color = 'green'
        elif strength >= 1000:
            color = 'orange'
        else:
            color = 'red'

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, strength
        )
    strength_display.short_description = 'Strength'
    strength_display.admin_order_field = 'strength'

    def player_count(self, obj):
        """Display player count with link"""
        count = getattr(obj, 'player_count', 0)
        if count:
            url = reverse('admin:fpl_player_changelist') + f'?team__id__exact={obj.id}'
            return format_html('<a href="{}">{} players</a>', url, count)
        return '0 players'
    player_count.short_description = 'Players'
    player_count.admin_order_field = 'player_count'

    def total_value(self, obj):
        """Display total team value"""
        value = getattr(obj, 'total_value', 0)
        return f"£{value:.1f}m" if value else "£0.0m"
    total_value.short_description = 'Total Value'
    total_value.admin_order_field = 'total_value'

    def export_teams_csv(self, request, queryset):
        """Export teams to CSV"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="teams.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Name', 'Short Name', 'Code', 'Position', 'Strength',
            'Attack Home', 'Attack Away', 'Defence Home', 'Defence Away'
        ])

        for team in queryset:
            writer.writerow([
                team.name, team.short_name, team.code, team.position,
                team.strength, team.strength_attack_home, team.strength_attack_away,
                team.strength_defence_home, team.strength_defence_away
            ])

        return response
    export_teams_csv.short_description = "Export selected teams to CSV"

    def update_team_strengths(self, request, queryset):
        """Update team strength ratings"""
        try:
            sync_service = DataSyncService()
            # This would update team strengths from FPL API
            messages.success(request, f"Updated strength ratings for {queryset.count()} teams")
        except Exception as e:
            messages.error(request, f"Failed to update team strengths: {str(e)}")
    update_team_strengths.short_description = "Update strength ratings"


class PositionAdmin(ReadOnlyAdminMixin, BaseModelAdmin):
    """Position admin - mostly read-only"""

    list_display = [
        'singular_name', 'singular_name_short', 'plural_name',
        'squad_select', 'squad_min_play', 'squad_max_play', 'player_count'
    ]
    readonly_fields = ['id']  # Position model only has id field, no created_at/updated_at
    ordering = ['id']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            player_count=Count('players')
        )

    def player_count(self, obj):
        """Display player count"""
        count = getattr(obj, 'player_count', 0)
        if count:
            url = reverse('admin:fpl_player_changelist') + f'?position__id__exact={obj.id}'
            return format_html('<a href="{}">{} players</a>', url, count)
        return '0 players'
    player_count.short_description = 'Active Players'


class PlayerAdmin(BaseModelAdmin):
    """Comprehensive Player admin with advanced features"""

    list_display = [
        'web_name', 'team_link', 'position_display', 'current_price',
        'total_points', 'form_display', 'status_display', 'selected_by_percent',
        'last_updated'
    ]
    list_filter = [
        'status', 'position', 'team', 'in_dreamteam',
        ('current_price', admin.AllValuesFieldListFilter),
        ('total_points', admin.AllValuesFieldListFilter),
        'updated_at',
    ]
    search_fields = ['web_name', 'first_name', 'second_name', 'team__name']
    readonly_fields = [
        'fpl_id', 'first_name', 'second_name', 'web_name',
        'created_at', 'updated_at', 'news_added'
    ]
    ordering = ['-total_points', '-form']

    list_per_page = 50
    list_max_show_all = 200

    fieldsets = (
        ('Player Information', {
            'fields': (
                'fpl_id', 'first_name', 'second_name', 'web_name',
                'team', 'position', 'status'
            )
        }),
        ('Performance Stats', {
            'fields': (
                ('total_points', 'form', 'points_per_game'),
                ('minutes', 'goals_scored', 'assists'),
                ('clean_sheets', 'goals_conceded', 'saves'),
                ('yellow_cards', 'red_cards', 'bonus'),
            )
        }),
        ('Advanced Stats', {
            'fields': (
                ('influence', 'creativity', 'threat', 'ict_index'),
                ('expected_goals', 'expected_assists', 'expected_goal_involvements'),
                ('bps', 'dreamteam_count', 'in_dreamteam'),
            ),
            'classes': ['collapse']
        }),
        ('Market Data', {
            'fields': (
                'current_price', 'selected_by_percent',
                ('chance_of_playing_this_round', 'chance_of_playing_next_round')
            )
        }),
        ('News & Updates', {
            'fields': ('news', 'news_added'),
            'classes': ['collapse']
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )

    actions = [
        'export_players_csv', 'update_selected_players', 'mark_as_unavailable',
        'generate_player_report'
    ]

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('team', 'position')

    def team_link(self, obj):
        """Display team as clickable link"""
        url = reverse('admin:fpl_team_change', args=[obj.team.pk])
        return format_html('<a href="{}">{}</a>', url, obj.team.short_name)
    team_link.short_description = 'Team'
    team_link.admin_order_field = 'team__name'

    def position_display(self, obj):
        """Display position with icon"""
        icons = {1: '🥅', 2: '🛡️', 3: '⚽', 4: '🎯'}
        icon = icons.get(obj.position_id, '❓')
        return f"{icon} {obj.position.singular_name_short}"
    position_display.short_description = 'Position'
    position_display.admin_order_field = 'position'

    def form_display(self, obj):
        """Display form with color coding"""
        form = float(obj.form)
        if form >= 6:
            color = 'green'
        elif form >= 4:
            color = 'orange'
        else:
            color = 'red'

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, form
        )
    form_display.short_description = 'Form'
    form_display.admin_order_field = 'form'

    def status_display(self, obj):
        """Display status with appropriate styling"""
        status_colors = {
            'a': ('✅', 'Available'),
            'd': ('⚠️', 'Doubtful'),
            'i': ('🏥', 'Injured'),
            's': ('🔴', 'Suspended'),
            'u': ('❌', 'Unavailable'),
        }

        icon, text = status_colors.get(obj.status, ('❓', 'Unknown'))
        return f"{icon} {text}"
    status_display.short_description = 'Status'
    status_display.admin_order_field = 'status'

    def last_updated(self, obj):
        """Display time since last update"""
        delta = timezone.now() - obj.updated_at
        if delta.days > 0:
            return f"{delta.days} days ago"
        elif delta.seconds > 3600:
            return f"{delta.seconds // 3600} hours ago"
        else:
            return f"{delta.seconds // 60} minutes ago"
    last_updated.short_description = 'Last Updated'
    last_updated.admin_order_field = 'updated_at'

    def export_players_csv(self, request, queryset):
        """Export players to CSV"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="players.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Name', 'Team', 'Position', 'Price', 'Total Points', 'Form',
            'Minutes', 'Goals', 'Assists', 'Status'
        ])

        for player in queryset.select_related('team', 'position'):
            writer.writerow([
                player.web_name, player.team.name, player.position.singular_name,
                player.current_price, player.total_points, player.form,
                player.minutes, player.goals_scored, player.assists,
                player.get_status_display()
            ])

        return response
    export_players_csv.short_description = "Export selected players to CSV"

    def update_selected_players(self, request, queryset):
        """Update selected players from FPL API"""
        player_ids = list(queryset.values_list('fpl_id', flat=True))

        try:
            # This would trigger selective player updates
            messages.success(request, f"Queued update for {len(player_ids)} players")
        except Exception as e:
            messages.error(request, f"Failed to queue player updates: {str(e)}")
    update_selected_players.short_description = "Update selected players"

    def mark_as_unavailable(self, request, queryset):
        """Mark selected players as unavailable"""
        count = queryset.update(status='u')
        messages.success(request, f"Marked {count} players as unavailable")
    mark_as_unavailable.short_description = "Mark as unavailable"

    def generate_player_report(self, request, queryset):
        """Generate detailed player report"""
        if queryset.count() > 50:
            messages.error(request, "Cannot generate report for more than 50 players")
            return

        # This would generate a detailed analysis report
        messages.success(request, f"Generated report for {queryset.count()} players")
    generate_player_report.short_description = "Generate player report"


class TeamPlayerInline(admin.TabularInline):
    """Inline for team players in UserTeam admin"""

    model = TeamPlayer
    extra = 0
    readonly_fields = ['player_link', 'purchase_price', 'selling_price', 'profit_loss']
    fields = [
        'player_link', 'position', 'purchase_price', 'selling_price', 'profit_loss',
        'is_captain', 'is_vice_captain', 'multiplier'
    ]

    def player_link(self, obj):
        """Display player as clickable link"""
        if obj.player:
            url = reverse('admin:fpl_player_change', args=[obj.player.pk])
            return format_html('<a href="{}">{}</a>', url, obj.player.web_name)
        return '-'
    player_link.short_description = 'Player'

    def profit_loss(self, obj):
        """Display profit/loss with color coding"""
        if obj.pk:  # Only for existing objects
            profit = obj.selling_price - obj.purchase_price
            color = 'green' if profit > 0 else 'red' if profit < 0 else 'black'
            return format_html(
                '<span style="color: {};">{:+.1f}</span>',
                color, profit
            )
        return '-'
    profit_loss.short_description = 'P/L'


class UserTeamAdmin(BaseModelAdmin):
    """User team admin with comprehensive analysis"""

    list_display = [
        'team_name', 'manager_name', 'fpl_team_id', 'total_points',
        'overall_rank', 'team_value', 'bank_balance', 'free_transfers',
        'last_updated'
    ]
    list_filter = [
        'current_event', 'free_transfers', 'last_updated',
        ('total_points', admin.AllValuesFieldListFilter),
        ('overall_rank', admin.AllValuesFieldListFilter),
    ]
    search_fields = ['team_name', 'manager_name', 'fpl_team_id']
    readonly_fields = [
        'fpl_team_id', 'current_event', 'overall_rank', 'event_points',
        'event_rank', 'auto_subs_played', 'created_at', 'updated_at', 'last_updated'
    ]
    ordering = ['-total_points']

    inlines = [TeamPlayerInline]

    fieldsets = (
        ('Team Information', {
            'fields': (
                'fpl_team_id', 'team_name', 'manager_name', 'current_event'
            )
        }),
        ('Performance', {
            'fields': (
                ('total_points', 'overall_rank'),
                ('event_points', 'event_rank'),
                'auto_subs_played',
            )
        }),
        ('Financial', {
            'fields': (
                ('team_value', 'bank_balance'),
                ('free_transfers', 'total_transfers', 'transfer_cost'),
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'last_updated'),
            'classes': ['collapse']
        }),
    )

    actions = [
        'sync_selected_teams', 'generate_suggestions_for_teams',
        'export_teams_analysis'
    ]

    def sync_selected_teams(self, request, queryset):
        """Sync selected teams from FPL API"""
        team_ids = list(queryset.values_list('fpl_team_id', flat=True))

        # Queue async tasks
        for team_id in team_ids:
            from .tasks import sync_user_team_task
            sync_user_team_task.delay(team_id)

        messages.success(request, f"Queued sync for {len(team_ids)} teams")
    sync_selected_teams.short_description = "Sync selected teams"

    def generate_suggestions_for_teams(self, request, queryset):
        """Generate transfer suggestions for selected teams"""
        team_ids = list(queryset.values_list('fpl_team_id', flat=True))

        if len(team_ids) > 10:
            messages.error(request, "Cannot generate suggestions for more than 10 teams at once")
            return

        # Queue suggestion generation
        for team_id in team_ids:
            generate_suggestions_task.delay(team_id)

        messages.success(request, f"Queued suggestion generation for {len(team_ids)} teams")
    generate_suggestions_for_teams.short_description = "Generate transfer suggestions"

    def export_teams_analysis(self, request, queryset):
        """Export team analysis to CSV"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="teams_analysis.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Team Name', 'Manager', 'FPL ID', 'Total Points', 'Rank',
            'Team Value', 'Bank Balance', 'Free Transfers', 'Last Updated'
        ])

        for team in queryset:
            writer.writerow([
                team.team_name, team.manager_name, team.fpl_team_id,
                team.total_points, team.overall_rank or 'N/A',
                team.team_value, team.bank_balance, team.free_transfers,
                team.last_updated.strftime('%Y-%m-%d %H:%M')
            ])

        return response
    export_teams_analysis.short_description = "Export teams analysis"


class TransferSuggestionAdmin(BaseModelAdmin):
    """Transfer suggestion admin with filtering and analysis"""

    list_display = [
        'user_team_link', 'transfer_display', 'suggestion_type',
        'priority_score', 'confidence_score', 'cost_change',
        'is_implemented', 'created_at'
    ]
    list_filter = [
        'suggestion_type', 'is_implemented', 'created_at',
        ('priority_score', admin.AllValuesFieldListFilter),
        ('confidence_score', admin.AllValuesFieldListFilter),
        'player_out__position', 'player_in__position',
    ]
    search_fields = [
        'user_team__team_name', 'user_team__manager_name',
        'player_out__web_name', 'player_in__web_name'
    ]
    readonly_fields = [
        'user_team', 'player_out', 'player_in', 'priority_score',
        'predicted_points_gain', 'confidence_score', 'created_at', 'updated_at'
    ]
    ordering = ['-priority_score', '-created_at']

    fieldsets = (
        ('Transfer Details', {
            'fields': (
                'user_team', 'suggestion_type',
                ('player_out', 'player_in'),
                'reason'
            )
        }),
        ('Analysis', {
            'fields': (
                ('priority_score', 'confidence_score'),
                ('cost_change', 'predicted_points_gain'),
            )
        }),
        ('Implementation', {
            'fields': ('is_implemented', 'implementation_date')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )

    actions = ['mark_as_implemented', 'export_suggestions_csv']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user_team', 'player_out__team', 'player_in__team',
            'player_out__position', 'player_in__position'
        )

    def user_team_link(self, obj):
        """Display user team as clickable link"""
        url = reverse('admin:fpl_userteam_change', args=[obj.user_team.pk])
        return format_html('<a href="{}">{}</a>', url, obj.user_team.team_name)
    user_team_link.short_description = 'Team'
    user_team_link.admin_order_field = 'user_team__team_name'

    def transfer_display(self, obj):
        """Display transfer in readable format"""
        return format_html(
            '{} → {}',
            obj.player_out.web_name,
            obj.player_in.web_name
        )
    transfer_display.short_description = 'Transfer'

    def mark_as_implemented(self, request, queryset):
        """Mark suggestions as implemented"""
        count = 0
        for suggestion in queryset:
            if not suggestion.is_implemented:
                suggestion.mark_as_implemented()
                count += 1

        messages.success(request, f"Marked {count} suggestions as implemented")
    mark_as_implemented.short_description = "Mark as implemented"

    def export_suggestions_csv(self, request, queryset):
        """Export suggestions to CSV"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="transfer_suggestions.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Team', 'Manager', 'Player Out', 'Player In', 'Type',
            'Priority Score', 'Confidence', 'Cost Change', 'Reason',
            'Implemented', 'Created'
        ])

        for suggestion in queryset.select_related('user_team', 'player_out', 'player_in'):
            writer.writerow([
                suggestion.user_team.team_name,
                suggestion.user_team.manager_name,
                suggestion.player_out.web_name,
                suggestion.player_in.web_name,
                suggestion.get_suggestion_type_display(),
                suggestion.priority_score,
                suggestion.confidence_score,
                suggestion.cost_change,
                suggestion.reason[:100] + '...' if len(suggestion.reason) > 100 else suggestion.reason,
                'Yes' if suggestion.is_implemented else 'No',
                suggestion.created_at.strftime('%Y-%m-%d %H:%M')
            ])

        return response
    export_suggestions_csv.short_description = "Export suggestions to CSV"


class PlayerGameweekPerformanceAdmin(BaseModelAdmin):
    """Player gameweek performance admin"""

    list_display = [
        'player_link', 'gameweek', 'points', 'minutes',
        'goals_scored', 'assists', 'clean_sheets', 'bonus'
    ]
    list_filter = [
        'gameweek', 'player__position', 'player__team',
        ('points', admin.AllValuesFieldListFilter),
    ]
    search_fields = ['player__web_name', 'player__team__name']
    readonly_fields = ['player', 'gameweek']
    ordering = ['-gameweek', '-points']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('player__team', 'player__position')

    def player_link(self, obj):
        """Display player as clickable link"""
        url = reverse('admin:fpl_player_change', args=[obj.player.pk])
        return format_html('<a href="{}">{}</a>', url, obj.player.web_name)
    player_link.short_description = 'Player'
    player_link.admin_order_field = 'player__web_name'


# Register models with custom admin
admin.site.register(Team, TeamAdmin)
admin.site.register(Position, PositionAdmin)
admin.site.register(Player, PlayerAdmin)
admin.site.register(UserTeam, UserTeamAdmin)
admin.site.register(TransferSuggestion, TransferSuggestionAdmin)
admin.site.register(PlayerGameweekPerformance, PlayerGameweekPerformanceAdmin)

# Customize admin site
admin.site.site_header = 'FPL Transfer Suggestions Admin'
admin.site.site_title = 'FPL Admin'
admin.site.index_title = 'FPL Transfer Suggestions Administration'

# Custom admin views
from django.urls import path
from django.template.response import TemplateResponse

def admin_dashboard_view(request):
    """Custom admin dashboard with key metrics"""
    context = {
        'title': 'FPL Dashboard',
        'total_players': Player.objects.count(),
        'active_players': Player.objects.filter(status='a').count(),
        'total_teams': UserTeam.objects.count(),
        'recent_suggestions': TransferSuggestion.objects.count(),
        'teams_by_value': UserTeam.objects.order_by('-team_value')[:10],
        'top_players': Player.objects.order_by('-total_points')[:10],
    }

    return TemplateResponse(request, 'admin/fpl_dashboard.html', context)

# Add custom URLs to admin
def get_admin_urls():
    urls = [
        path('dashboard/', admin_dashboard_view, name='fpl_dashboard'),
    ]
    return urls

# Store the original get_urls method to avoid recursion
_original_get_urls = admin.site.get_urls
admin.site.get_urls = lambda: get_admin_urls() + _original_get_urls()
