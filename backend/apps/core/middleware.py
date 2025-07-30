import time
import uuid
import json
from typing import Optional, Dict, Any
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from django.urls import resolve
from django.contrib.auth.models import AnonymousUser
from rest_framework import status
import structlog

from .exceptions import RateLimitExceededError, SecurityError
from .utils import get_client_ip, is_valid_json

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Comprehensive request/response logging middleware
    Logs all API requests with timing and user information
    """

    def process_request(self, request: HttpRequest) -> None:
        """Log incoming request details"""
        # Add unique request ID
        request.id = str(uuid.uuid4())
        request.start_time = time.time()

        # Extract request information
        user_id = None
        if hasattr(request, 'user') and not isinstance(request.user, AnonymousUser):
            user_id = request.user.id

        # Log request start
        logger.info(
            "Request started",
            request_id=request.id,
            method=request.method,
            path=request.path,
            query_params=dict(request.GET),
            user_id=user_id,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            content_type=request.content_type,
            content_length=request.META.get('CONTENT_LENGTH', 0),
        )

        # Log request body for POST/PUT/PATCH (excluding sensitive data)
        if request.method in ['POST', 'PUT', 'PATCH'] and request.content_type == 'application/json':
            try:
                body = json.loads(request.body.decode('utf-8'))
                # Remove sensitive fields
                sensitive_fields = ['password', 'token', 'secret', 'key']
                filtered_body = {
                    k: '***REDACTED***' if any(sensitive in k.lower() for sensitive in sensitive_fields) else v
                    for k, v in body.items()
                }

                logger.info(
                    "Request body",
                    request_id=request.id,
                    body=filtered_body
                )
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Log response details and performance metrics"""
        if not hasattr(request, 'id'):
            return response

        # Calculate request duration
        duration = time.time() - getattr(request, 'start_time', time.time())

        # Get resolved URL name
        url_name = None
        try:
            resolved = resolve(request.path)
            url_name = resolved.url_name
        except Exception:
            pass

        # Log response
        logger.info(
            "Request completed",
            request_id=request.id,
            status_code=response.status_code,
            duration_ms=round(duration * 1000, 2),
            url_name=url_name,
            response_size=len(response.content) if hasattr(response, 'content') else 0,
        )

        # Add performance headers
        response['X-Request-ID'] = request.id
        response['X-Response-Time'] = f"{duration:.3f}s"

        # Log slow requests
        if duration > 2.0:  # Log requests taking more than 2 seconds
            logger.warning(
                "Slow request detected",
                request_id=request.id,
                duration_ms=round(duration * 1000, 2),
                path=request.path,
                method=request.method,
            )

        return response


class RateLimitMiddleware(MiddlewareMixin):
    """
    Advanced rate limiting middleware
    Supports different limits for different endpoints and user types
    """

    def __init__(self, get_response):
        super().__init__(get_response)
        self.rate_limits = getattr(settings, 'RATE_LIMITS', {
            'default': {'requests': 100, 'window': 3600},  # 100 requests per hour
            'auth': {'requests': 1000, 'window': 3600},     # 1000 requests per hour for authenticated users
            'premium': {'requests': 5000, 'window': 3600},  # 5000 requests per hour for premium users
        })

    def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        """Check rate limits before processing request"""
        if settings.DEBUG:
            return None
        
        if not getattr(settings, 'RATELIMIT_ENABLE', True):
            return None

        # Skip rate limiting for certain paths
        skip_paths = ['/health/', '/metrics/', '/admin/']
        if any(request.path.startswith(path) for path in skip_paths):
            return None

        # Determine rate limit category
        limit_key = self.get_rate_limit_key(request)
        if not limit_key:
            return None

        # Get rate limit configuration
        limit_config = self.get_rate_limit_config(request)
        max_requests = limit_config['requests']
        window_seconds = limit_config['window']

        # Check current usage
        cache_key = f"rate_limit:{limit_key}"
        current_requests = cache.get(cache_key, 0)

        if current_requests >= max_requests:
            logger.warning(
                "Rate limit exceeded",
                limit_key=limit_key,
                current_requests=current_requests,
                max_requests=max_requests,
                ip_address=get_client_ip(request),
                user_id=getattr(request.user, 'id', None) if hasattr(request, 'user') else None,
            )

            return JsonResponse({
                'error': 'Rate limit exceeded',
                'detail': f'Maximum {max_requests} requests per {window_seconds} seconds',
                'retry_after': self.get_retry_after(cache_key, window_seconds),
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        # Increment counter
        cache.set(cache_key, current_requests + 1, window_seconds)

        return None

    def get_rate_limit_key(self, request: HttpRequest) -> str:
        """Generate rate limit key for the request"""
        if hasattr(request, 'user') and request.user.is_authenticated:
            return f"user:{request.user.id}"
        else:
            return f"ip:{get_client_ip(request)}"

    def get_rate_limit_config(self, request: HttpRequest) -> Dict[str, int]:
        """Get rate limit configuration for the request"""
        # Check if user has premium status
        if hasattr(request, 'user') and request.user.is_authenticated:
            if hasattr(request.user, 'is_premium') and request.user.is_premium:
                return self.rate_limits['premium']
            return self.rate_limits['auth']

        return self.rate_limits['default']

    def get_retry_after(self, cache_key: str, window_seconds: int) -> int:
        """Calculate retry-after seconds"""
        # Get TTL of the cache key to determine when limit resets
        try:
            ttl = cache.ttl(cache_key)
            return max(ttl, 60)  # Minimum 60 seconds
        except AttributeError:
            return window_seconds


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Add security headers to all responses
    Implements OWASP security recommendations
    """

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Add security headers to response"""

        # Content Security Policy
        if not response.get('Content-Security-Policy'):
            csp_directives = [
                "default-src 'self'",
                "script-src 'self' 'unsafe-inline'",
                "style-src 'self' 'unsafe-inline'",
                "img-src 'self' data: https:",
                "connect-src 'self'",
                "font-src 'self'",
                "object-src 'none'",
                "media-src 'self'",
                "frame-ancestors 'none'",
            ]
            response['Content-Security-Policy'] = '; '.join(csp_directives)

        # Security headers
        security_headers = {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains' if request.is_secure() else None,
        }

        for header, value in security_headers.items():
            if value and not response.get(header):
                response[header] = value

        # Remove server information
        if 'Server' in response:
            del response['Server']

        return response


class IPWhitelistMiddleware(MiddlewareMixin):
    """
    IP whitelist middleware for admin and sensitive endpoints
    """

    def __init__(self, get_response):
        super().__init__(get_response)
        self.whitelisted_ips = getattr(settings, 'WHITELISTED_IPS', [])
        self.protected_paths = getattr(settings, 'IP_PROTECTED_PATHS', ['/admin/', '/api/admin/'])

    def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        """Check IP whitelist for protected paths"""
        if not self.whitelisted_ips:
            return None

        # Check if path is protected
        is_protected = any(request.path.startswith(path) for path in self.protected_paths)
        if not is_protected:
            return None

        # Get client IP
        client_ip = get_client_ip(request)

        # Check whitelist
        if client_ip not in self.whitelisted_ips:
            logger.warning(
                "IP access denied",
                ip_address=client_ip,
                path=request.path,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )

            return JsonResponse({
                'error': 'Access denied',
                'detail': 'Your IP address is not authorized to access this resource',
            }, status=status.HTTP_403_FORBIDDEN)

        return None


class CorsMiddleware(MiddlewareMixin):
    """
    Custom CORS middleware with advanced features
    """

    def __init__(self, get_response):
        super().__init__(get_response)
        self.allowed_origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
        self.allowed_methods = getattr(settings, 'CORS_ALLOWED_METHODS', [
            'DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT'
        ])
        self.allowed_headers = getattr(settings, 'CORS_ALLOWED_HEADERS', [
            'accept', 'accept-encoding', 'authorization', 'content-type',
            'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
        ])
        self.expose_headers = getattr(settings, 'CORS_EXPOSE_HEADERS', [
            'X-Request-ID', 'X-Response-Time'
        ])
        self.max_age = getattr(settings, 'CORS_PREFLIGHT_MAX_AGE', 86400)

    def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        """Handle CORS preflight requests"""
        if request.method == 'OPTIONS':
            origin = request.META.get('HTTP_ORIGIN')

            if self.is_origin_allowed(origin):
                response = HttpResponse()
                self.add_cors_headers(response, origin)
                response['Access-Control-Allow-Methods'] = ', '.join(self.allowed_methods)
                response['Access-Control-Allow-Headers'] = ', '.join(self.allowed_headers)
                response['Access-Control-Max-Age'] = str(self.max_age)
                return response

        return None

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Add CORS headers to response"""
        origin = request.META.get('HTTP_ORIGIN')

        if self.is_origin_allowed(origin):
            self.add_cors_headers(response, origin)

        return response

    def is_origin_allowed(self, origin: str) -> bool:
        """Check if origin is allowed"""
        if not origin:
            return False

        if getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', False):
            return True

        return origin in self.allowed_origins

    def add_cors_headers(self, response: HttpResponse, origin: str) -> None:
        """Add CORS headers to response"""
        response['Access-Control-Allow-Origin'] = origin
        response['Access-Control-Allow-Credentials'] = 'true'

        if self.expose_headers:
            response['Access-Control-Expose-Headers'] = ', '.join(self.expose_headers)


class ExceptionHandlingMiddleware(MiddlewareMixin):
    """
    Global exception handling middleware
    Provides consistent error responses and logging
    """

    def process_exception(self, request: HttpRequest, exception: Exception) -> Optional[HttpResponse]:
        """Handle uncaught exceptions"""
        request_id = getattr(request, 'id', 'unknown')

        # Log the exception
        logger.error(
            "Unhandled exception in middleware",
            request_id=request_id,
            exception=str(exception),
            exception_type=exception.__class__.__name__,
            path=request.path,
            method=request.method,
            user_id=getattr(request.user, 'id', None) if hasattr(request, 'user') else None,
        )

        # Don't handle exceptions in debug mode
        if settings.DEBUG:
            return None

        # Return JSON error response for API requests
        if request.path.startswith('/api/'):
            error_response = {
                'error': 'Internal server error',
                'message': 'An unexpected error occurred',
                'request_id': request_id,
                'timestamp': timezone.now().isoformat(),
            }

            return JsonResponse(
                error_response,
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return None


class MaintenanceMiddleware(MiddlewareMixin):
    """
    Maintenance mode middleware
    Returns maintenance response when system is under maintenance
    """

    def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        """Check if system is in maintenance mode"""
        maintenance_mode = cache.get('maintenance_mode', False)

        if not maintenance_mode:
            return None

        # Allow admin users to bypass maintenance mode
        if hasattr(request, 'user') and request.user.is_staff:
            return None

        # Allow health check endpoints
        if request.path in ['/health/', '/metrics/']:
            return None

        # Return maintenance response
        maintenance_message = cache.get('maintenance_message', 'System is currently under maintenance')

        if request.path.startswith('/api/'):
            return JsonResponse({
                'error': 'Service unavailable',
                'message': maintenance_message,
                'timestamp': timezone.now().isoformat(),
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # Return HTML maintenance page for web requests
        return HttpResponse(
            f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Maintenance</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; margin-top: 100px; }}
                    .maintenance {{ background: #f8f9fa; padding: 50px; border-radius: 10px; display: inline-block; }}
                </style>
            </head>
            <body>
                <div class="maintenance">
                    <h1>🔧 Under Maintenance</h1>
                    <p>{maintenance_message}</p>
                    <p>We'll be back shortly!</p>
                </div>
            </body>
            </html>
            """,
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
            content_type='text/html'
        )


class DatabaseRoutingMiddleware(MiddlewareMixin):
    """
    Database routing middleware for read/write splitting
    Routes read queries to read replicas when available
    """

    def process_request(self, request: HttpRequest) -> None:
        """Set database routing hints based on request"""
        # Use read database for GET requests
        if request.method == 'GET':
            request.db_hint = 'read'
        else:
            request.db_hint = 'write'

        # Store in thread local for database router
        from django.db import connections
        connections._hints = getattr(connections, '_hints', {})
        connections._hints['request'] = request


class PerformanceMonitoringMiddleware(MiddlewareMixin):
    """
    Performance monitoring middleware
    Tracks response times and identifies slow endpoints
    """

    def process_request(self, request: HttpRequest) -> None:
        """Initialize performance tracking"""
        request.perf_start = time.time()
        request.perf_queries_start = len(connections.queries) if settings.DEBUG else 0

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Track performance metrics"""
        if not hasattr(request, 'perf_start'):
            return response

        # Calculate metrics
        duration = time.time() - request.perf_start
        query_count = (len(connections.queries) - request.perf_queries_start) if settings.DEBUG else 0

        # Add performance headers
        response['X-DB-Queries'] = str(query_count)

        # Log performance metrics
        if duration > 1.0 or query_count > 50:  # Log slow requests or high query count
            logger.warning(
                "Performance issue detected",
                path=request.path,
                method=request.method,
                duration_ms=round(duration * 1000, 2),
                query_count=query_count,
                status_code=response.status_code,
            )

        # Store metrics for monitoring systems
        self.store_performance_metrics(request, response, duration, query_count)

        return response

    def store_performance_metrics(self, request: HttpRequest, response: HttpResponse,
                                duration: float, query_count: int) -> None:
        """Store performance metrics for monitoring"""
        # This could integrate with monitoring systems like Prometheus, Datadog, etc.
        metrics_key = f"performance:{request.path}:{request.method}"

        # Store in cache for aggregation
        cache.set(f"{metrics_key}:last_duration", duration, 3600)
        cache.set(f"{metrics_key}:last_queries", query_count, 3600)

        # Increment counters
        counter_key = f"{metrics_key}:count"
        current_count = cache.get(counter_key, 0)
        cache.set(counter_key, current_count + 1, 3600)


# Utility function to enable/disable maintenance mode
def set_maintenance_mode(enabled: bool, message: str = None) -> None:
    """Enable or disable maintenance mode"""
    cache.set('maintenance_mode', enabled, 3600 * 24)  # 24 hours

    if message:
        cache.set('maintenance_message', message, 3600 * 24)

    logger.info(
        "Maintenance mode changed",
        enabled=enabled,
        message=message
    )
