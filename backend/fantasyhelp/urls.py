from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.views.generic import RedirectView
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView
)

from apps.core.views import HealthCheckView


@require_http_methods(["GET"])
@cache_page(3600)  # Cache for 1 hour
def api_root_view(request):
    """
    API root endpoint with service information
    """
    return JsonResponse({
        'service': 'FPL Transfer Suggestions API',
        'version': '2.0.0',
        'description': 'API for Fantasy Premier League transfer suggestions',
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
            }
        },
        'status': {
            'health': request.build_absolute_uri('/health/'),
        },
        'rate_limits': {
            'anonymous': '100 requests/hour',
            'authenticated': '1000 requests/hour',
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
            ],
            'documentation': request.build_absolute_uri('/docs/')
        }, status=404)

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
        }, status=500)

    return JsonResponse({'error': 'Internal Server Error'}, status=500)


# Main URL patterns
urlpatterns = [
    # API Root
    path('', RedirectView.as_view(url='/api/', permanent=False)),
    path('api/', api_root_view, name='api_root'),

    # Admin Interface
    path(getattr(settings, 'ADMIN_URL', 'admin/'), admin.site.urls),

    # Health and Monitoring
    path('health/', HealthCheckView.as_view(), name='health_check'),

    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # API Version 2 (main)
    path('api/v2/', include('apps.fpl.urls.v2')),
]


# Development-specific URLs
if settings.DEBUG:
    from django.views import defaults as default_views

    urlpatterns += [
        # Development error pages
        path('400/', default_views.bad_request, kwargs={'exception': Exception('Bad Request!')}),
        path('403/', default_views.permission_denied, kwargs={'exception': Exception('Permission Denied')}),
        path('404/', custom_404_view, kwargs={'exception': Exception('Page not Found!')}),
        path('500/', custom_500_view),
    ]

    # Serve media files in development
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


# Custom error handlers
handler404 = 'fantasyhelp.urls.custom_404_view'
handler500 = 'fantasyhelp.urls.custom_500_view'

# Custom admin configuration
admin.site.site_header = 'FPL Suggestions API Administration'
admin.site.site_title = 'FPL API Admin'
admin.site.index_title = 'Welcome to FPL Suggestions API Administration'
