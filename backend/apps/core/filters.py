import django_filters
from django_filters import rest_framework as filters
from django.db.models import Q, Count, Avg, Max, Min
from django.utils import timezone
from datetime import timedelta
from typing import Any, List, Optional, Dict
import structlog

logger = structlog.get_logger(__name__)


class BaseFilterSet(filters.FilterSet):
    """
    Enhanced base filter set with common functionality
    """

    @property
    def qs(self):
        """Enhanced queryset with performance optimizations"""
        parent = super().qs

        # Apply select_related if defined
        if hasattr(self, 'select_related_fields'):
            parent = parent.select_related(*self.select_related_fields)

        # Apply prefetch_related if defined
        if hasattr(self, 'prefetch_related_fields'):
            parent = parent.prefetch_related(*self.prefetch_related_fields)

        # Apply distinct if needed
        if hasattr(self, 'apply_distinct') and self.apply_distinct:
            parent = parent.distinct()

        return parent

    def filter_queryset(self, queryset):
        """Enhanced filter with logging for complex queries"""
        import time
        start_time = time.time()

        result = super().filter_queryset(queryset)

        # Log slow filters
        duration = time.time() - start_time
        if duration > 1.0:  # Log filters taking more than 1 second
            logger.warning(
                "Slow filter operation",
                filter_class=self.__class__.__name__,
                duration_ms=round(duration * 1000, 2),
                filter_data=dict(self.data),
            )

        return result


class RangeFilter(filters.BaseRangeFilter, filters.NumberFilter):
    """
    Enhanced range filter for numeric fields
    """
    pass


class MultipleChoiceFilter(filters.MultipleChoiceFilter):
    """
    Enhanced multiple choice filter with better performance
    """

    def filter(self, qs, value):
        if not value:
            return qs

        # Use __in lookup for better performance with multiple values
        return qs.filter(**{f"{self.field_name}__in": value})


class ChoiceFilter(filters.ChoiceFilter):
    """
    Enhanced choice filter with validation
    """

    def filter(self, qs, value):
        if value is None:
            return qs

        # Validate choice
        if self.extra.get('choices') and value not in dict(self.extra['choices']):
            logger.warning(
                "Invalid choice in filter",
                field_name=self.field_name,
                value=value,
                valid_choices=list(dict(self.extra['choices']).keys()),
            )
            return qs.none()  # Return empty queryset for invalid choices

        return super().filter(qs, value)


class DateRangeFilter(filters.DateFromToRangeFilter):
    """
    Enhanced date range filter with preset options
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add preset date ranges
        self.extra['help_text'] = (
            'Date range filter. Accepts dates in YYYY-MM-DD format. '
            'Use "today", "yesterday", "last_week", "last_month" for presets.'
        )

    def filter(self, qs, value):
        if not value:
            return qs

        # Handle preset values
        if isinstance(value, str):
            preset_value = self._get_preset_range(value)
            if preset_value:
                value = preset_value

        return super().filter(qs, value)

    def _get_preset_range(self, preset: str) -> Optional[Dict[str, Any]]:
        """Get date range for preset values"""
        now = timezone.now().date()

        presets = {
            'today': {'after': now, 'before': now},
            'yesterday': {
                'after': now - timedelta(days=1),
                'before': now - timedelta(days=1)
            },
            'last_week': {
                'after': now - timedelta(days=7),
                'before': now
            },
            'last_month': {
                'after': now - timedelta(days=30),
                'before': now
            },
            'last_3_months': {
                'after': now - timedelta(days=90),
                'before': now
            },
        }

        return presets.get(preset.lower())


class SearchFilter(filters.CharFilter):
    """
    Enhanced search filter with full-text search capabilities
    """

    def __init__(self, search_fields=None, *args, **kwargs):
        self.search_fields = search_fields or []
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if not value or not self.search_fields:
            return qs

        # Build search query
        search_query = Q()
        search_terms = value.split()

        for term in search_terms:
            term_query = Q()
            for field in self.search_fields:
                term_query |= Q(**{f"{field}__icontains": term})
            search_query &= term_query

        return qs.filter(search_query)


class BooleanFilter(filters.BooleanFilter):
    """
    Enhanced boolean filter with string value support
    """

    def filter(self, qs, value):
        if value is None:
            return qs

        # Handle string values
        if isinstance(value, str):
            value = value.lower() in ('true', '1', 'yes', 'on')

        return super().filter(qs, value)


class OrderingFilter(filters.OrderingFilter):
    """
    Enhanced ordering filter with validation and security
    """

    def __init__(self, *args, **kwargs):
        # Define allowed ordering fields to prevent injection
        self.allowed_fields = kwargs.pop('allowed_fields', [])
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if not value:
            return qs

        # Validate ordering fields
        if self.allowed_fields:
            validated_ordering = []
            for field in value:
                # Remove the '-' prefix for validation
                field_name = field.lstrip('-')
                if field_name in self.allowed_fields:
                    validated_ordering.append(field)
                else:
                    logger.warning(
                        "Invalid ordering field",
                        field=field,
                        allowed_fields=self.allowed_fields,
                    )

            if not validated_ordering:
                return qs

            value = validated_ordering

        return super().filter(qs, value)


class DynamicChoiceFilter(filters.ChoiceFilter):
    """
    Choice filter with dynamically generated choices from database
    """

    def __init__(self, choice_queryset=None, choice_field='name', *args, **kwargs):
        self.choice_queryset = choice_queryset
        self.choice_field = choice_field
        super().__init__(*args, **kwargs)

    @property
    def field(self):
        if not hasattr(self, '_field'):
            choices = self._get_dynamic_choices()
            self.extra['choices'] = choices
            self._field = super().field
        return self._field

    def _get_dynamic_choices(self) -> List[tuple]:
        """Generate choices from database"""
        if not self.choice_queryset:
            return []

        try:
            return list(
                self.choice_queryset.values_list('id', self.choice_field)
            )
        except Exception as e:
            logger.error("Error generating dynamic choices", error=str(e))
            return []


class NumericStatsFilter(filters.Filter):
    """
    Filter for numeric statistics with aggregation support
    """

    def __init__(self, stat_type='avg', *args, **kwargs):
        """
        Initialize with aggregation type

        Args:
            stat_type: 'avg', 'min', 'max', 'sum', 'count'
        """
        self.stat_type = stat_type
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if value is None:
            return qs

        # Build aggregation based on stat_type
        aggregation_map = {
            'avg': Avg,
            'min': Min,
            'max': Max,
            'sum': Sum,
            'count': Count,
        }

        aggregation_func = aggregation_map.get(self.stat_type, Avg)

        # Apply filter based on aggregated value
        # This is a simplified example - you'd implement based on your needs
        return qs.annotate(
            stat_value=aggregation_func(self.field_name)
        ).filter(stat_value=value)


class FacetedFilter(filters.Filter):
    """
    Filter that provides faceted search capabilities
    """

    def __init__(self, facet_fields=None, *args, **kwargs):
        self.facet_fields = facet_fields or []
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if not value or not self.facet_fields:
            return qs

        # Parse faceted value (format: "field1:value1,field2:value2")
        facet_filters = Q()

        for facet in value.split(','):
            if ':' in facet:
                field, facet_value = facet.split(':', 1)
                if field in self.facet_fields:
                    facet_filters &= Q(**{field: facet_value})

        return qs.filter(facet_filters)

    def get_facet_counts(self, qs) -> Dict[str, Dict[str, int]]:
        """Get facet counts for frontend display"""
        facet_counts = {}

        for field in self.facet_fields:
            try:
                counts = qs.values(field).annotate(
                    count=Count('id')
                ).order_by('-count')

                facet_counts[field] = {
                    item[field]: item['count'] for item in counts
                }
            except Exception as e:
                logger.error(f"Error calculating facet counts for {field}", error=str(e))
                facet_counts[field] = {}

        return facet_counts


class RelatedFieldFilter(filters.Filter):
    """
    Filter for related fields with optimization
    """

    def __init__(self, related_field, lookup_type='exact', *args, **kwargs):
        self.related_field = related_field
        self.lookup_type = lookup_type
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if value is None:
            return qs

        # Build lookup for related field
        lookup = f"{self.related_field}__{self.lookup_type}"
        return qs.filter(**{lookup: value})


class GeolocationFilter(filters.Filter):
    """
    Filter for geographic location-based queries
    """

    def __init__(self, lat_field='latitude', lng_field='longitude', *args, **kwargs):
        self.lat_field = lat_field
        self.lng_field = lng_field
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if not value:
            return qs

        # Parse location string (format: "lat,lng,radius")
        try:
            parts = value.split(',')
            if len(parts) >= 2:
                lat = float(parts[0])
                lng = float(parts[1])
                radius = float(parts[2]) if len(parts) > 2 else 10  # Default 10km

                # This would require GeoDjango for proper implementation
                # Simplified version using bounding box
                lat_delta = radius / 111.0  # Approximate km per degree
                lng_delta = radius / (111.0 * abs(lat))

                return qs.filter(
                    **{
                        f"{self.lat_field}__gte": lat - lat_delta,
                        f"{self.lat_field}__lte": lat + lat_delta,
                        f"{self.lng_field}__gte": lng - lng_delta,
                        f"{self.lng_field}__lte": lng + lng_delta,
                    }
                )
        except (ValueError, IndexError) as e:
            logger.warning("Invalid geolocation filter", value=value, error=str(e))

        return qs


class CachedChoiceFilter(filters.ChoiceFilter):
    """
    Choice filter with cached choices for performance
    """

    def __init__(self, cache_key=None, cache_timeout=3600, *args, **kwargs):
        self.cache_key = cache_key
        self.cache_timeout = cache_timeout
        super().__init__(*args, **kwargs)

    @property
    def field(self):
        if not hasattr(self, '_field'):
            if self.cache_key:
                from django.core.cache import cache
                choices = cache.get(self.cache_key)
                if choices is None:
                    choices = self._generate_choices()
                    cache.set(self.cache_key, choices, self.cache_timeout)
                self.extra['choices'] = choices

            self._field = super().field
        return self._field

    def _generate_choices(self) -> List[tuple]:
        """Override this method to generate choices"""
        return []


class ConditionalFilter(filters.Filter):
    """
    Filter that applies different logic based on conditions
    """

    def __init__(self, conditions=None, *args, **kwargs):
        """
        Initialize with conditions dictionary

        Args:
            conditions: Dict mapping condition values to filter logic
        """
        self.conditions = conditions or {}
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if value is None or value not in self.conditions:
            return qs

        condition_func = self.conditions[value]

        if callable(condition_func):
            return condition_func(qs)
        elif isinstance(condition_func, dict):
            return qs.filter(**condition_func)
        elif isinstance(condition_func, Q):
            return qs.filter(condition_func)

        return qs


class AggregationFilter(filters.Filter):
    """
    Filter that works with aggregated data
    """

    def __init__(self, aggregation_field, aggregation_func=Count, *args, **kwargs):
        self.aggregation_field = aggregation_field
        self.aggregation_func = aggregation_func
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if value is None:
            return qs

        # Apply aggregation and filter
        annotation_name = f"{self.field_name}_agg"

        return qs.annotate(
            **{annotation_name: self.aggregation_func(self.aggregation_field)}
        ).filter(**{annotation_name: value})


# Custom filter backend for advanced filtering
class AdvancedFilterBackend:
    """
    Advanced filter backend with additional features
    """

    def filter_queryset(self, request, queryset, view):
        """
        Apply advanced filtering logic
        """
        # Add performance monitoring
        import time
        start_time = time.time()

        # Apply standard filtering
        filter_class = getattr(view, 'filterset_class', None)
        if filter_class:
            filterset = filter_class(request.query_params, queryset=queryset)
            queryset = filterset.qs

        # Apply custom filters
        queryset = self._apply_custom_filters(request, queryset, view)

        # Log performance
        duration = time.time() - start_time
        if duration > 0.5:
            logger.warning(
                "Slow filtering operation",
                view=view.__class__.__name__,
                duration_ms=round(duration * 1000, 2),
                filter_params=dict(request.query_params),
            )

        return queryset

    def _apply_custom_filters(self, request, queryset, view):
        """Apply view-specific custom filters"""

        # Example: Apply user-specific filters
        if hasattr(view, 'get_user_specific_filters'):
            user_filters = view.get_user_specific_filters(request.user)
            if user_filters:
                queryset = queryset.filter(user_filters)

        # Example: Apply permission-based filters
        if hasattr(view, 'get_permission_filters'):
            permission_filters = view.get_permission_filters(request)
            if permission_filters:
                queryset = queryset.filter(permission_filters)

        return queryset


# Filter utilities
class FilterUtils:
    """
    Utility functions for filtering operations
    """

    @staticmethod
    def build_search_query(search_term: str, search_fields: List[str]) -> Q:
        """
        Build a search query across multiple fields
        """
        query = Q()
        terms = search_term.split()

        for term in terms:
            term_query = Q()
            for field in search_fields:
                term_query |= Q(**{f"{field}__icontains": term})
            query &= term_query

        return query

    @staticmethod
    def apply_date_filters(queryset, date_field: str, date_params: Dict[str, Any]):
        """
        Apply date-based filters to queryset
        """
        filters = {}

        if 'date_from' in date_params:
            filters[f"{date_field}__gte"] = date_params['date_from']

        if 'date_to' in date_params:
            filters[f"{date_field}__lte"] = date_params['date_to']

        if 'date_exact' in date_params:
            filters[f"{date_field}__date"] = date_params['date_exact']

        return queryset.filter(**filters) if filters else queryset

    @staticmethod
    def apply_numeric_filters(queryset, field: str, numeric_params: Dict[str, Any]):
        """
        Apply numeric range filters to queryset
        """
        filters = {}

        if 'min' in numeric_params:
            filters[f"{field}__gte"] = numeric_params['min']

        if 'max' in numeric_params:
            filters[f"{field}__lte"] = numeric_params['max']

        if 'exact' in numeric_params:
            filters[field] = numeric_params['exact']

        return queryset.filter(**filters) if filters else queryset

    @staticmethod
    def get_filter_summary(filterset) -> Dict[str, Any]:
        """
        Get summary of applied filters for debugging/logging
        """
        summary = {
            'filter_class': filterset.__class__.__name__,
            'total_filters': len(filterset.filters),
            'applied_filters': {},
            'filter_count': 0,
        }

        for name, filter_instance in filterset.filters.items():
            if name in filterset.data:
                summary['applied_filters'][name] = {
                    'value': filterset.data[name],
                    'filter_type': filter_instance.__class__.__name__,
                }
                summary['filter_count'] += 1

        return summary

    @staticmethod
    def validate_filter_params(params: Dict[str, Any], allowed_params: List[str]) -> Dict[str, Any]:
        """
        Validate and sanitize filter parameters
        """
        validated = {}

        for key, value in params.items():
            if key in allowed_params:
                # Basic sanitization
                if isinstance(value, str):
                    value = value.strip()
                    if len(value) > 1000:  # Prevent extremely long values
                        value = value[:1000]

                validated[key] = value
            else:
                logger.warning(
                    "Invalid filter parameter",
                    parameter=key,
                    value=value,
                    allowed_params=allowed_params,
                )

        return validated


# Performance monitoring decorator for filters
def monitor_filter_performance(func):
    """
    Decorator to monitor filter performance
    """
    def wrapper(*args, **kwargs):
        import time
        start_time = time.time()

        result = func(*args, **kwargs)

        duration = time.time() - start_time
        if duration > 0.5:
            logger.warning(
                "Slow filter operation",
                function=func.__name__,
                duration_ms=round(duration * 1000, 2),
            )

        return result

    return wrapper


# Filter factory for creating filter instances
class FilterFactory:
    """
    Factory for creating filter instances with common configurations
    """

    @staticmethod
    def create_search_filter(search_fields: List[str]):
        """Create search filter for multiple fields"""
        return SearchFilter(search_fields=search_fields)

    @staticmethod
    def create_date_range_filter(field_name: str):
        """Create date range filter"""
        return DateRangeFilter(field_name=field_name)

    @staticmethod
    def create_numeric_range_filter(field_name: str):
        """Create numeric range filter"""
        return RangeFilter(field_name=field_name)

    @staticmethod
    def create_choice_filter(field_name: str, choices: List[tuple]):
        """Create choice filter with validation"""
        return ChoiceFilter(field_name=field_name, choices=choices)

    @staticmethod
    def create_boolean_filter(field_name: str):
        """Create boolean filter with string support"""
        return BooleanFilter(field_name=field_name)
