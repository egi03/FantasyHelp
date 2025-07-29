from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse, HttpResponse
from django.views.generic import RedirectView
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods
from rest_framework import permissions
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView
)

from apps.core.views import HealthCheckView
from apps.core.exceptions import NotFoundError


# API Version Configuration
API_VERSION_V1 = 'v1'
API_VERSION_V2 = 'v2'
DEFAULT_API_VERSION = API_VERSION_V2


@require_http_methods(["GET"])
@cache_page(3600)  # Cache for 1 hour
def api_root_view(request):
    """
    API root endpoint with service information
    """
    return JsonResponse({
        'service': 'FPL Transfer Suggestions API',
        'version': '2.0.0',
        'description': 'Enterprise-grade API for Fantasy Premier League transfer suggestions',
        'author': 'FPL Suggestions Team',
        'documentation': {
            'swagger': request.build_absolute_uri('/docs/'),
            'redoc': request.build_absolute_uri('/redoc/'),
            'openapi_schema': request.build_absolute_uri('/api/schema/')
        },
        'endpoints': {
            'v2': {
                'base_url': request.build_absolute_uri('/api/v2/'),
                'players': request.build_absolute_uri('/api/v2/players/'),
                'teams': request.build_absolute_uri('/api/v2/teams/'),
                'user_teams': request.build_absolute_uri('/api/v2/user-teams/'),
                'suggestions': request.build_absolute_uri('/api/v2/suggestions/'),
                'analytics': request.build_absolute_uri('/api/v2/analytics/'),
            },
            'v1': {
                'base_url': request.build_absolute_uri('/api/v1/'),
                'note': 'Legacy API version - consider upgrading to v2'
            }
        },
        'status': {
            'health': request.build_absolute_uri('/health/'),
            'metrics': request.build_absolute_uri('/metrics/') if not settings.DEBUG else None,
        },
        'authentication': {
            'methods': ['JWT', 'Session'],
            'jwt_endpoints': {
                'obtain': request.build_absolute_uri('/api/auth/jwt/create/'),
                'refresh': request.build_absolute_uri('/api/auth/jwt/refresh/'),
                'verify': request.build_absolute_uri('/api/auth/jwt/verify/'),
            }
        },
        'rate_limits': {
            'anonymous': '100 requests/hour',
            'authenticated': '1000 requests/hour',
            'premium': '5000 requests/hour'
        },
        'support': {
            'documentation': 'https://docs.fpl-suggestions.com',
            'issues': 'https://github.com/fpl-suggestions/api/issues',
            'contact': 'support@fpl-suggestions.com'
        }
    })


def custom_404_view(request, exception=None):
    """
    Custom 404 handler for API endpoints
    """
    if request.path.startswith('/api/'):
        return JsonResponse({
            'error': 'not_found',
            'message': 'The requested endpoint was not found',
            'path': request.path,
            'method': request.method,
            'available_endpoints': [
                '/api/v2/players/',
                '/api/v2/teams/',
                '/api/v2/user-teams/',
                '/api/v2/suggestions/',
                '/api/v2/analytics/',
            ],
            'documentation': request.build_absolute_uri('/docs/')
        }, status=404)

    # For non-API requests, redirect to API root
    return RedirectView.as_view(url='/api/', permanent=False)(request)


def custom_500_view(request):
    """
    Custom 500 handler for API endpoints
    """
    if request.path.startswith('/api/'):
        return JsonResponse({
            'error': 'internal_server_error',
            'message': 'An internal server error occurred',
            'request_id': getattr(request, 'id', 'unknown'),
            'support': 'Please contact support with the request ID'
        }, status=500)

    return HttpResponse(
        '<h1>Internal Server Error</h1><p>Something went wrong. Please try again later.</p>',
        status=500,
        content_type='text/html'
    )


# Main URL patterns
urlpatterns = [
    # API Root
    path('', RedirectView.as_view(url='/api/', permanent=False)),
    path('api/', api_root_view, name='api_root'),

    # Admin Interface (secured with custom URL)
    path(settings.ADMIN_URL, admin.site.urls),

    # Health and Monitoring
    path('health/', HealthCheckView.as_view(), name='health_check'),

    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Authentication
    path('api/auth/', include('apps.authentication.urls')),

    # API Versions
    path('api/v1/', include('apps.fpl.urls.v1'), name='api_v1'),
    path('api/v2/', include('apps.fpl.urls.v2'), name='api_v2'),

    # Default API version (currently v2)
    path('api/', include('apps.fpl.urls.v2')),

    # Analytics and Reporting
    path('api/analytics/', include('apps.analytics.urls')),

    # Webhook endpoints
    path('webhooks/', include('apps.webhooks.urls')),

    # Internal tools and utilities
    path('internal/', include('apps.internal.urls')),
]


# Development-specific URLs
if settings.DEBUG:
    import debug_toolbar
    from django.views import defaults as default_views

    urlpatterns += [
        # Debug toolbar
        path('__debug__/', include(debug_toolbar.urls)),

        # Django admin docs
        path('admin/doc/', include('django.contrib.admindocs.urls')),

        # Development error pages
        path('400/', default_views.bad_request, kwargs={'exception': Exception('Bad Request!')}),
        path('403/', default_views.permission_denied, kwargs={'exception': Exception('Permission Denied')}),
        path('404/', custom_404_view, kwargs={'exception': Exception('Page not Found!')}),
        path('500/', custom_500_view),

        # Test endpoints for development
        path('api/dev/', include('apps.dev.urls')),
    ]

    # Serve media files in development
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


# Production monitoring and metrics
if not settings.DEBUG:
    urlpatterns += [
        # Prometheus metrics
        path('metrics/', include('django_prometheus.urls')),

        # Sentry health check
        path('_health/', HealthCheckView.as_view(), name='internal_health'),
    ]


# API versioning middleware setup
class APIVersionMiddleware:
    """
    Middleware to handle API versioning
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Extract version from URL or headers
        self.set_api_version(request)

        response = self.get_response(request)

        # Add version info to response headers
        if hasattr(request, 'api_version'):
            response['API-Version'] = request.api_version
            response['API-Version-Supported'] = f"{API_VERSION_V1}, {API_VERSION_V2}"
            response['API-Version-Latest'] = DEFAULT_API_VERSION

        return response

    def set_api_version(self, request):
        """Set API version on request object"""
        version = None

        # Try to get version from URL
        if request.path.startswith('/api/v1/'):
            version = API_VERSION_V1
        elif request.path.startswith('/api/v2/'):
            version = API_VERSION_V2

        # Try to get version from header
        if not version:
            version = request.META.get('HTTP_API_VERSION')

        # Try to get version from query parameter
        if not version:
            version = request.GET.get('version')

        # Default to latest version
        if not version:
            version = DEFAULT_API_VERSION

        request.api_version = version


# Custom error handlers
handler404 = 'config.urls.custom_404_view'
handler500 = 'config.urls.custom_500_view'


# URL pattern for API documentation based on environment
if settings.DEBUG:
    # Full documentation access in development
    documentation_patterns = [
        path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
        path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    ]
else:
    # Restricted documentation access in production
    from rest_framework.permissions import IsAdminUser

    documentation_patterns = [
        path('docs/',
             SpectacularSwaggerView.as_view(
                 url_name='schema',
                 permission_classes=[IsAdminUser]
             ),
             name='swagger-ui'),
        path('redoc/',
             SpectacularRedocView.as_view(
                 url_name='schema',
                 permission_classes=[IsAdminUser]
             ),
             name='redoc'),
        path('api/schema/',
             SpectacularAPIView.as_view(permission_classes=[IsAdminUser]),
             name='schema'),
    ]

# Add documentation patterns to main urlpatterns
urlpatterns.extend(documentation_patterns)


# Custom admin configuration
admin.site.site_header = 'FPL Suggestions API Administration'
admin.site.site_title = 'FPL API Admin'
admin.site.index_title = 'Welcome to FPL Suggestions API Administration'

# Admin site customization
class AdminConfig:
    """Enhanced admin configuration"""

    def __init__(self):
        self.customize_admin()

    def customize_admin(self):
        """Customize Django admin interface"""
        # Only allow admin access to staff users
        admin.site.login_required = True

        # Custom admin URLs based on environment
        if not settings.DEBUG:
            # Additional security for production admin
            from django.contrib.admin.views.decorators import staff_member_required
            from django.contrib.auth.decorators import login_required

            # Wrap admin views with additional security
            admin.site.admin_view = staff_member_required(admin.site.admin_view)


# Initialize admin configuration
admin_config = AdminConfig()


# API rate limiting configuration
RATE_LIMIT_PATTERNS = {
    # More restrictive limits for expensive endpoints
    r'^/api/v[12]/suggestions/generate/': {
        'anonymous': '10/hour',
        'authenticated': '100/hour',
        'premium': '500/hour'
    },
    r'^/api/v[12]/user-teams/load-team/': {
        'anonymous': '20/hour',
        'authenticated': '200/hour',
        'premium': '1000/hour'
    },
    r'^/api/v[12]/analytics/': {
        'anonymous': '50/hour',
        'authenticated': '500/hour',
        'premium': '2000/hour'
    },
    # Default limits for other endpoints
    r'^/api/': {
        'anonymous': '100/hour',
        'authenticated': '1000/hour',
        'premium': '5000/hour'
    }
}


# URL naming conventions
URL_NAMES = {
    'api_root': 'api_root',
    'health_check': 'health_check',
    'schema': 'schema',
    'swagger_ui': 'swagger-ui',
    'redoc': 'redoc',

    # API v1 names
    'v1_players': 'v1:players-list',
    'v1_teams': 'v1:teams-list',
    'v1_suggestions': 'v1:suggestions-list',

    # API v2 names
    'v2_players': 'v2:players-list',
    'v2_teams': 'v2:teams-list',
    'v2_user_teams': 'v2:user-teams-list',
    'v2_suggestions': 'v2:suggestions-list',
    'v2_analytics': 'v2:analytics-list',
}


# Security headers for specific endpoints
SECURITY_HEADERS = {
    '/api/': {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
    },
    '/admin/': {
        'X-Frame-Options': 'SAMEORIGIN',  # Allow iframe for admin
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
    }
}


# URL validation patterns
URL_VALIDATION_PATTERNS = {
    'fpl_team_id': r'(?P<fpl_team_id>[1-9]\d{5,6})',  # 6-7 digit team IDs
    'player_id': r'(?P<player_id>\d+)',
    'gameweek': r'(?P<gameweek>[1-3]?\d)',  # 1-38
    'uuid': r'(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})',
}


# CORS configuration for different endpoints
CORS_ENDPOINT_CONFIG = {
    '/api/v2/': {
        'allow_credentials': True,
        'allow_headers': ['accept', 'authorization', 'content-type', 'x-api-key'],
        'expose_headers': ['x-request-id', 'x-response-time', 'api-version'],
    },
    '/api/v1/': {
        'allow_credentials': False,  # Legacy API, less secure
        'allow_headers': ['accept', 'content-type'],
    }
}
