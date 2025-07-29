# Create apps/fpl/filters.py

import django_filters
from django_filters import rest_framework as filters
from django.db.models import Q
from typing import Any

from .models import Player, UserTeam, TransferSuggestion


class PlayerFilter(filters.FilterSet):
    """Advanced filtering for players"""

    position = filters.ChoiceFilter(choices=[(1, 'GK'), (2, 'DEF'), (3, 'MID'), (4, 'FWD')])
    price_min = filters.NumberFilter(field_name='current_price', lookup_expr='gte')
    price_max = filters.NumberFilter(field_name='current_price', lookup_expr='lte')
    points_min = filters.NumberFilter(field_name='total_points', lookup_expr='gte')
    points_max = filters.NumberFilter(field_name='total_points', lookup_expr='lte')
    form_min = filters.NumberFilter(field_name='form', lookup_expr='gte')
    form_max = filters.NumberFilter(field_name='form', lookup_expr='lte')
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


class UserTeamFilter(filters.FilterSet):
    """Filtering for user teams"""

    total_points_min = filters.NumberFilter(field_name='total_points', lookup_expr='gte')
    total_points_max = filters.NumberFilter(field_name='total_points', lookup_expr='lte')
    team_value_min = filters.NumberFilter(field_name='team_value', lookup_expr='gte')
    team_value_max = filters.NumberFilter(field_name='team_value', lookup_expr='lte')

    class Meta:
        model = UserTeam
        fields = {
            'team_name': ['icontains'],
            'manager_name': ['icontains'],
            'total_points': ['gte', 'lte'],
            'team_value': ['gte', 'lte'],
            'free_transfers': ['exact', 'gte', 'lte'],
        }


class TransferSuggestionFilter(filters.FilterSet):
    """Filtering for transfer suggestions"""

    priority_min = filters.NumberFilter(field_name='priority_score', lookup_expr='gte')
    priority_max = filters.NumberFilter(field_name='priority_score', lookup_expr='lte')
    confidence_min = filters.NumberFilter(field_name='confidence_score', lookup_expr='gte')
    confidence_max = filters.NumberFilter(field_name='confidence_score', lookup_expr='lte')

    class Meta:
        model = TransferSuggestion
        fields = {
            'suggestion_type': ['exact', 'in'],
            'priority_score': ['gte', 'lte'],
            'confidence_score': ['gte', 'lte'],
            'is_implemented': ['exact'],
            'user_team': ['exact'],
        }
