from rest_framework.pagination import PageNumberPagination, CursorPagination
from rest_framework.response import Response
from django.core.paginator import Paginator
from django.utils.functional import cached_property
from collections import OrderedDict
from typing import Optional, Dict, Any
import structlog
from urllib.parse import urlencode

logger = structlog.get_logger(__name__)


class OptimizedPaginator(Paginator):
    """
    Optimized paginator that avoids expensive COUNT queries for large datasets
    """

    @cached_property
    def count(self):
        """
        Return the total number of objects, using cached count when possible
        """
        # Try to get count from cache first
        from django.core.cache import cache

        cache_key = f"paginator_count:{hash(str(self.object_list.query))}"
        cached_count = cache.get(cache_key)

        if cached_count is not None:
            return cached_count

        # Get actual count
        try:
            count = self.object_list.count()
        except (AttributeError, TypeError):
            # Fallback for non-QuerySet objects
            count = len(self.object_list)

        # Cache count for fast pagination
        cache.set(cache_key, count, 300)  # Cache for 5 minutes

        return count


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard pagination for most API endpoints
    Provides consistent pagination with metadata
    """

    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    django_paginator_class = OptimizedPaginator

    def get_paginated_response(self, data):
        """
        Enhanced paginated response with additional metadata
        """
        page_info = {
            'current_page': self.page.number,
            'total_pages': self.page.paginator.num_pages,
            'page_size': self.get_page_size(self.request),
            'has_next': self.page.has_next(),
            'has_previous': self.page.has_previous(),
        }

        # Add next/previous page numbers
        if self.page.has_next():
            page_info['next_page'] = self.page.next_page_number()

        if self.page.has_previous():
            page_info['previous_page'] = self.page.previous_page_number()

        # Calculate result range
        start_index = self.page.start_index()
        end_index = self.page.end_index()

        response_data = OrderedDict([
            ('count', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('page_info', page_info),
            ('results', data),
            ('range', {
                'start': start_index,
                'end': end_index,
                'total': self.page.paginator.count
            })
        ])

        return Response(response_data)

    def get_page_size(self, request):
        """
        Get page size with validation and logging
        """
        if self.page_size_query_param:
            try:
                page_size = int(request.query_params[self.page_size_query_param])

                if page_size > 0:
                    # Log large page size requests
                    if page_size > 50:
                        logger.info(
                            "Large page size requested",
                            page_size=page_size,
                            user_id=getattr(request.user, 'id', None),
                            path=request.path
                        )

                    return min(page_size, self.max_page_size)

            except (KeyError, ValueError):
                pass

        return self.page_size

    def paginate_queryset(self, queryset, request, view=None):
        """
        Enhanced pagination with performance monitoring
        """
        import time
        start_time = time.time()

        result = super().paginate_queryset(queryset, request, view)

        # Log slow pagination
        duration = time.time() - start_time
        if duration > 1.0:  # Log queries taking more than 1 second
            logger.warning(
                "Slow pagination query",
                duration_ms=round(duration * 1000, 2),
                page=getattr(self.page, 'number', None),
                page_size=self.get_page_size(request),
                total_count=getattr(self.page.paginator, 'count', None),
                view=view.__class__.__name__ if view else None,
            )

        return result


class LargeResultsSetPagination(PageNumberPagination):
    """
    Pagination for large datasets with cursor-based fallback
    """

    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200
    django_paginator_class = OptimizedPaginator

    def get_paginated_response(self, data):
        """
        Response optimized for large datasets
        """
        # Don't calculate total count for very large datasets to avoid slow queries
        count = None
        if self.page.paginator.count <= 10000:  # Only show count for smaller datasets
            count = self.page.paginator.count

        response_data = OrderedDict([
            ('count', count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('page_info', {
                'current_page': self.page.number,
                'page_size': self.get_page_size(self.request),
                'has_next': self.page.has_next(),
                'has_previous': self.page.has_previous(),
            }),
            ('results', data)
        ])

        return Response(response_data)


class CursorBasedPagination(CursorPagination):
    """
    Cursor-based pagination for real-time data and large datasets
    Provides consistent performance regardless of offset
    """

    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    ordering = '-created_at'  # Default ordering
    cursor_query_param = 'cursor'
    cursor_query_description = 'The pagination cursor value'

    def get_paginated_response(self, data):
        """
        Enhanced cursor response with metadata
        """
        response_data = OrderedDict([
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('page_info', {
                'page_size': self.get_page_size(self.request),
                'has_next': self.has_next,
                'has_previous': self.has_previous,
                'ordering': self.ordering,
            }),
            ('results', data)
        ])

        return Response(response_data)

    def get_page_size(self, request):
        """Get validated page size"""
        if self.page_size_query_param:
            try:
                return min(
                    int(request.query_params[self.page_size_query_param]),
                    self.max_page_size
                )
            except (KeyError, ValueError):
                pass

        return self.page_size


class SearchResultsPagination(StandardResultsSetPagination):
    """
    Specialized pagination for search results
    """

    page_size = 15
    max_page_size = 50

    def get_paginated_response(self, data):
        """
        Search-specific response with query metadata
        """
        response = super().get_paginated_response(data)

        # Add search metadata
        search_query = self.request.query_params.get('search', '')
        if search_query:
            response.data['search_info'] = {
                'query': search_query,
                'results_count': response.data['count'],
                'has_results': response.data['count'] > 0,
            }

        return response


class AnalyticsPagination(PageNumberPagination):
    """
    Pagination for analytics endpoints with aggregation support
    """

    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        """
        Analytics response with aggregation metadata
        """
        response_data = OrderedDict([
            ('count', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('page_info', {
                'current_page': self.page.number,
                'total_pages': self.page.paginator.num_pages,
                'page_size': self.get_page_size(self.request),
            }),
            ('results', data)
        ])

        # Add aggregation data if available
        if hasattr(self, 'aggregation_data'):
            response_data['aggregations'] = self.aggregation_data

        return Response(response_data)


class InfinitePagination(CursorPagination):
    """
    Infinite scroll pagination for mobile/frontend applications
    """

    page_size = 10
    page_size_query_param = 'limit'
    max_page_size = 50
    ordering = '-id'

    def get_paginated_response(self, data):
        """
        Simplified response for infinite scroll
        """
        return Response({
            'next_cursor': self.get_next_link(),
            'has_more': self.has_next,
            'results': data,
            'count': len(data)
        })


class AdminPagination(PageNumberPagination):
    """
    Pagination for Django admin interface
    """

    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 200

    def get_paginated_response(self, data):
        """
        Admin-friendly pagination response
        """
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('page_info', {
                'current_page': self.page.number,
                'total_pages': self.page.paginator.num_pages,
                'start_index': self.page.start_index(),
                'end_index': self.page.end_index(),
            }),
            ('results', data)
        ]))


class CustomLimitOffsetPagination(PageNumberPagination):
    """
    Custom limit/offset pagination for compatibility with external systems
    """

    page_size = 20
    page_size_query_param = 'limit'
    page_query_param = 'offset'
    max_page_size = 100

    def get_page_number(self, request, paginator):
        """
        Convert offset to page number
        """
        try:
            offset = int(request.query_params.get(self.page_query_param, 0))
            limit = self.get_page_size(request)

            if offset < 0:
                offset = 0

            page_number = (offset // limit) + 1
            return page_number

        except (KeyError, ValueError):
            return 1

    def get_next_link(self):
        """
        Generate next link with offset parameter
        """
        if not self.page.has_next():
            return None

        url = self.request.build_absolute_uri()
        page_size = self.get_page_size(self.request)
        offset = (self.page.number * page_size)

        return self._replace_query_param(url, 'offset', offset)

    def get_previous_link(self):
        """
        Generate previous link with offset parameter
        """
        if not self.page.has_previous():
            return None

        url = self.request.build_absolute_uri()
        page_size = self.get_page_size(self.request)
        offset = ((self.page.number - 2) * page_size)

        if offset <= 0:
            return self._remove_query_param(url, 'offset')

        return self._replace_query_param(url, 'offset', offset)

    def _replace_query_param(self, url, key, val):
        """
        Replace query parameter in URL
        """
        from urllib.parse import urlparse, parse_qs, urlunparse

        parsed = urlparse(url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        query_params[key] = [str(val)]

        new_query = urlencode(query_params, doseq=True)
        return urlunparse((
            parsed.scheme, parsed.netloc, parsed.path,
            parsed.params, new_query, parsed.fragment
        ))

    def _remove_query_param(self, url, key):
        """
        Remove query parameter from URL
        """
        from urllib.parse import urlparse, parse_qs, urlunparse

        parsed = urlparse(url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        query_params.pop(key, None)

        new_query = urlencode(query_params, doseq=True)
        return urlunparse((
            parsed.scheme, parsed.netloc, parsed.path,
            parsed.params, new_query, parsed.fragment
        ))


# Pagination factory for dynamic pagination selection
class PaginationFactory:
    """
    Factory for selecting appropriate pagination class based on context
    """

    PAGINATION_CLASSES = {
        'standard': StandardResultsSetPagination,
        'large': LargeResultsSetPagination,
        'cursor': CursorBasedPagination,
        'search': SearchResultsPagination,
        'analytics': AnalyticsPagination,
        'infinite': InfinitePagination,
        'admin': AdminPagination,
        'offset': CustomLimitOffsetPagination,
    }

    @classmethod
    def get_pagination_class(cls, pagination_type: str = 'standard'):
        """
        Get pagination class by type
        """
        return cls.PAGINATION_CLASSES.get(pagination_type, StandardResultsSetPagination)

    @classmethod
    def create_paginator(cls, pagination_type: str = 'standard', **kwargs):
        """
        Create paginator instance with custom parameters
        """
        pagination_class = cls.get_pagination_class(pagination_type)
        paginator = pagination_class()

        # Apply custom parameters
        for key, value in kwargs.items():
            if hasattr(paginator, key):
                setattr(paginator, key, value)

        return paginator


# Utility functions for pagination
def get_pagination_info(request, queryset, pagination_class=None):
    """
    Get pagination information without actually paginating
    """
    if pagination_class is None:
        pagination_class = StandardResultsSetPagination

    paginator = pagination_class()

    # Get basic pagination info
    page_size = paginator.get_page_size(request)
    total_count = queryset.count()
    total_pages = (total_count + page_size - 1) // page_size

    try:
        current_page = int(request.query_params.get('page', 1))
    except ValueError:
        current_page = 1

    return {
        'total_count': total_count,
        'total_pages': total_pages,
        'current_page': current_page,
        'page_size': page_size,
        'has_next': current_page < total_pages,
        'has_previous': current_page > 1,
    }


def build_pagination_urls(request, page_info: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """
    Build pagination URLs for custom responses
    """
    base_url = request.build_absolute_uri().split('?')[0]
    query_params = dict(request.query_params)

    urls = {'next': None, 'previous': None}

    # Build next URL
    if page_info['has_next']:
        query_params['page'] = page_info['current_page'] + 1
        urls['next'] = f"{base_url}?{urlencode(query_params)}"

    # Build previous URL
    if page_info['has_previous']:
        if page_info['current_page'] == 2:
            # Remove page parameter for first page
            query_params.pop('page', None)
            query_string = urlencode(query_params)
            urls['previous'] = f"{base_url}?{query_string}" if query_string else base_url
        else:
            query_params['page'] = page_info['current_page'] - 1
            urls['previous'] = f"{base_url}?{urlencode(query_params)}"

    return urls


# Performance monitoring decorator for pagination
def monitor_pagination_performance(func):
    """
    Decorator to monitor pagination performance
    """
    def wrapper(*args, **kwargs):
        import time
        start_time = time.time()

        result = func(*args, **kwargs)

        duration = time.time() - start_time
        if duration > 0.5:  # Log slow pagination
            logger.warning(
                "Slow pagination detected",
                function=func.__name__,
                duration_ms=round(duration * 1000, 2),
            )

        return result

    return wrapper
