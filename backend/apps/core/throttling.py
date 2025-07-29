from rest_framework.throttling import BaseThrottle, UserRateThrottle, AnonRateThrottle
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
from typing import Optional, Dict, Any, List
import time
import structlog

from apps.core.utils import get_client_ip
from apps.core.exceptions import RateLimitExceededError

logger = structlog.get_logger(__name__)


class BaseRateThrottle(BaseThrottle):
    """
    Enhanced base rate throttle with advanced features
    """

    cache_format = 'throttle_%(scope)s_%(ident)s'
    timer = time.time

    def __init__(self):
        self.history = []
        self.now = None

    def allow_request(self, request, view):
        """
        Implement the check to see if the request should be throttled
        """
        if self.rate is None:
            return True

        self.key = self.get_cache_key(request, view)
        if self.key is None:
            return True

        self.history = self.cache.get(self.key, [])
        self.now = self.timer()

        # Drop any requests from the history which have now passed the throttle duration
        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()

        if len(self.history) >= self.num_requests:
            # Log rate limit hit
            logger.warning(
                "Rate limit exceeded",
                key=self.key,
                num_requests=self.num_requests,
                duration=self.duration,
                history_count=len(self.history),
                user_id=getattr(request.user, 'id', None) if hasattr(request, 'user') else None,
                ip_address=get_client_ip(request),
                path=request.path,
                method=request.method,
            )
            return self.throttle_failure()

        return self.throttle_success()

    def throttle_success(self):
        """
        Inserts the current request's timestamp along with the key
        into the cache.
        """
        self.history.insert(0, self.now)
        self.cache.set(self.key, self.history, self.duration)
        return True

    def throttle_failure(self):
        """
        Called when a request to the API has failed due to throttling.
        """
        return False

    def wait(self):
        """
        Returns the recommended next request time in seconds.
        """
        if self.history:
            remaining_duration = self.duration - (self.now - self.history[-1])
        else:
            remaining_duration = self.duration

        available_requests = self.num_requests - len(self.history) + 1
        if available_requests <= 0:
            return None

        return remaining_duration / float(available_requests)

    def get_cache_key(self, request, view):
        """
        Generate cache key for throttling
        """
        if not hasattr(self, 'scope'):
            msg = ('You must set either `.scope` or `.rate` for '
                   '\'%s\' throttle' % self.__class__.__name__)
            raise ImproperlyConfigured(msg)

        ident = self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }

    def get_ident(self, request):
        """
        Identify a unique cache key to use for throttling.
        """
        return get_client_ip(request)

    def parse_rate(self, rate):
        """
        Given the request rate string, return a two tuple of:
        <allowed number of requests>, <period of time in seconds>
        """
        if rate is None:
            return (None, None)

        num, period = rate.split('/')
        num_requests = int(num)
        duration = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[period[0]]
        return (num_requests, duration)


class BurstRateThrottle(BaseRateThrottle):
    """
    Throttle for handling burst requests (short-term high frequency)
    """

    scope = 'burst'

    def __init__(self):
        super().__init__()
        self.rate = getattr(settings, 'BURST_RATE_THROTTLE', '60/min')
        self.num_requests, self.duration = self.parse_rate(self.rate)
        self.cache = cache

    def get_cache_key(self, request, view):
        """Generate cache key with view-specific scope"""
        ident = self.get_ident(request)
        view_name = view.__class__.__name__ if view else 'unknown'

        return f'throttle_burst_{view_name}_{ident}'


class SustainedRateThrottle(BaseRateThrottle):
    """
    Throttle for sustained usage (long-term moderate frequency)
    """

    scope = 'sustained'

    def __init__(self):
        super().__init__()
        self.rate = getattr(settings, 'SUSTAINED_RATE_THROTTLE', '1000/hour')
        self.num_requests, self.duration = self.parse_rate(self.rate)
        self.cache = cache

    def get_cache_key(self, request, view):
        """Generate cache key for sustained throttling"""
        ident = self.get_ident(request)
        return f'throttle_sustained_{ident}'


class UserRateThrottle(BaseRateThrottle):
    """
    Enhanced user-based rate throttling with premium user support
    """

    scope = 'user'

    def __init__(self):
        super().__init__()
        self.cache = cache

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)

        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }

    def get_rate(self, request, view):
        """
        Determine the string representation of the allowed request rate.
        """
        if not request.user or not request.user.is_authenticated:
            return getattr(settings, 'ANON_RATE_THROTTLE', '100/hour')

        # Check for premium users
        if hasattr(request.user, 'is_premium') and request.user.is_premium:
            return getattr(settings, 'PREMIUM_RATE_THROTTLE', '5000/hour')

        return getattr(settings, 'USER_RATE_THROTTLE', '1000/hour')

    def allow_request(self, request, view):
        """
        Override to set rate dynamically
        """
        self.rate = self.get_rate(request, view)
        self.num_requests, self.duration = self.parse_rate(self.rate)

        return super().allow_request(request, view)


class AnonRateThrottle(BaseRateThrottle):
    """
    Enhanced anonymous user rate throttling
    """

    scope = 'anon'

    def __init__(self):
        super().__init__()
        self.rate = getattr(settings, 'ANON_RATE_THROTTLE', '100/hour')
        self.num_requests, self.duration = self.parse_rate(self.rate)
        self.cache = cache

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return None  # Only throttle unauthenticated requests

        ident = self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }


class EndpointSpecificThrottle(BaseRateThrottle):
    """
    Throttle that applies different rates to different endpoints
    """

    endpoint_rates = {
        # Expensive operations
        'generate_suggestions': '20/hour',
        'load_team': '100/hour',
        'bulk_update': '10/hour',

        # Analytics endpoints
        'analytics': '200/hour',
        'player_search': '500/hour',

        # Default for other endpoints
        'default': '1000/hour',
    }

    def __init__(self):
        super().__init__()
        self.cache = cache

    def get_rate_for_endpoint(self, request, view):
        """
        Get rate limit for specific endpoint
        """
        if hasattr(view, 'action'):
            # DRF ViewSet action
            endpoint_key = view.action
        elif hasattr(view, 'get_view_name'):
            # DRF view name
            endpoint_key = view.get_view_name().lower().replace(' ', '_')
        else:
            # Fallback to view class name
            endpoint_key = view.__class__.__name__.lower()

        return self.endpoint_rates.get(endpoint_key, self.endpoint_rates['default'])

    def allow_request(self, request, view):
        """
        Check rate limit for specific endpoint
        """
        self.rate = self.get_rate_for_endpoint(request, view)
        self.num_requests, self.duration = self.parse_rate(self.rate)

        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        """
        Generate endpoint-specific cache key
        """
        ident = self.get_ident(request)
        endpoint = getattr(view, 'action', view.__class__.__name__)

        return f'throttle_endpoint_{endpoint}_{ident}'


class IPBasedThrottle(BaseRateThrottle):
    """
    Throttle based on IP address with whitelist support
    """

    scope = 'ip'

    def __init__(self):
        super().__init__()
        self.rate = getattr(settings, 'IP_RATE_THROTTLE', '200/hour')
        self.num_requests, self.duration = self.parse_rate(self.rate)
        self.cache = cache
        self.whitelisted_ips = getattr(settings, 'THROTTLE_WHITELIST_IPS', [])

    def allow_request(self, request, view):
        """
        Check if IP is whitelisted before applying throttle
        """
        client_ip = get_client_ip(request)

        # Skip throttling for whitelisted IPs
        if client_ip in self.whitelisted_ips:
            logger.debug("IP whitelisted, skipping throttle", ip=client_ip)
            return True

        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        """
        Generate IP-based cache key
        """
        ident = get_client_ip(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }


class DatabaseThrottle(BaseRateThrottle):
    """
    Throttle that stores rate limit data in database for persistence
    """

    def __init__(self):
        super().__init__()
        self.rate = getattr(settings, 'DB_RATE_THROTTLE', '500/hour')
        self.num_requests, self.duration = self.parse_rate(self.rate)

    def allow_request(self, request, view):
        """
        Check rate limit using database storage
        """
        if self.rate is None:
            return True

        key = self.get_cache_key(request, view)
        if key is None:
            return True

        # Use database-backed throttling
        return self._check_database_throttle(key, request, view)

    def _check_database_throttle(self, key: str, request, view) -> bool:
        """
        Check throttle using database (implement based on your needs)
        """
        from apps.core.models import ThrottleRecord  # You'd need to create this model

        try:
            # Clean up old records
            cutoff_time = timezone.now() - timezone.timedelta(seconds=self.duration)
            ThrottleRecord.objects.filter(
                key=key,
                timestamp__lt=cutoff_time
            ).delete()

            # Count current requests
            current_count = ThrottleRecord.objects.filter(key=key).count()

            if current_count >= self.num_requests:
                return False

            # Record this request
            ThrottleRecord.objects.create(
                key=key,
                timestamp=timezone.now(),
                user_id=getattr(request.user, 'id', None) if hasattr(request, 'user') else None,
                ip_address=get_client_ip(request),
                path=request.path,
                method=request.method,
            )

            return True

        except Exception as e:
            logger.error("Database throttle error", error=str(e))
            # Fallback to allowing request if database fails
            return True


class DynamicRateThrottle(BaseRateThrottle):
    """
    Throttle with dynamic rate adjustment based on system load
    """

    def __init__(self):
        super().__init__()
        self.base_rate = getattr(settings, 'DYNAMIC_BASE_RATE', '1000/hour')
        self.cache = cache

    def get_current_rate(self, request, view):
        """
        Calculate current rate based on system load
        """
        # Get system load metrics
        load_factor = self._get_system_load_factor()

        base_num, base_duration = self.parse_rate(self.base_rate)

        # Adjust rate based on load (higher load = lower rate)
        adjusted_num = max(int(base_num * (1 - load_factor)), base_num // 4)

        return f"{adjusted_num}/{base_duration}s" if base_duration < 60 else f"{adjusted_num}/{base_duration//60}m"

    def _get_system_load_factor(self) -> float:
        """
        Get system load factor (0.0 = no load, 1.0 = high load)
        """
        try:
            # Check cache hit rate
            cache_stats = cache.get('cache_stats', {})
            cache_hit_rate = cache_stats.get('hit_rate', 0.9)

            # Check database query count
            db_load = cache.get('db_query_count', 0)

            # Simple load calculation (can be made more sophisticated)
            load_factor = max(0.0, min(1.0, (1 - cache_hit_rate) + (db_load / 1000)))

            return load_factor

        except Exception:
            return 0.0  # Default to no load adjustment if metrics unavailable

    def allow_request(self, request, view):
        """
        Check rate limit with dynamic adjustment
        """
        self.rate = self.get_current_rate(request, view)
        self.num_requests, self.duration = self.parse_rate(self.rate)

        return super().allow_request(request, view)


class TimeWindowThrottle(BaseRateThrottle):
    """
    Throttle that uses sliding time windows for more accurate rate limiting
    """

    def __init__(self, window_size=60):
        super().__init__()
        self.window_size = window_size  # Size of each time window in seconds
        self.rate = getattr(settings, 'WINDOW_RATE_THROTTLE', '100/hour')
        self.num_requests, self.duration = self.parse_rate(self.rate)
        self.cache = cache

    def allow_request(self, request, view):
        """
        Check rate limit using sliding time windows
        """
        if self.rate is None:
            return True

        key = self.get_cache_key(request, view)
        if key is None:
            return True

        now = int(time.time())

        # Calculate number of windows to check
        num_windows = self.duration // self.window_size

        # Count requests across all windows
        total_requests = 0
        for i in range(num_windows):
            window_start = now - (i * self.window_size)
            window_key = f"{key}:window:{window_start}"
            window_count = cache.get(window_key, 0)
            total_requests += window_count

        if total_requests >= self.num_requests:
            logger.warning(
                "Time window throttle exceeded",
                key=key,
                total_requests=total_requests,
                limit=self.num_requests,
                windows_checked=num_windows,
            )
            return False

        # Increment current window
        current_window = now - (now % self.window_size)
        current_window_key = f"{key}:window:{current_window}"

        try:
            cache.add(current_window_key, 0, self.window_size)
            cache.incr(current_window_key)
        except ValueError:
            # Key expired, reset
            cache.set(current_window_key, 1, self.window_size)

        return True


class CompositeThrottle(BaseThrottle):
    """
    Throttle that combines multiple throttling strategies
    """

    def __init__(self, throttles, mode='all'):
        """
        Initialize composite throttle

        Args:
            throttles: List of throttle classes or instances
            mode: 'all' (all must pass) or 'any' (any can pass)
        """
        self.throttles = [
            throttle() if isinstance(throttle, type) else throttle
            for throttle in throttles
        ]
        self.mode = mode

    def allow_request(self, request, view):
        """
        Check all throttles based on mode
        """
        results = []

        for throttle in self.throttles:
            result = throttle.allow_request(request, view)
            results.append(result)

            # Short-circuit for 'all' mode if any throttle fails
            if self.mode == 'all' and not result:
                return False

            # Short-circuit for 'any' mode if any throttle passes
            if self.mode == 'any' and result:
                return True

        if self.mode == 'all':
            return all(results)
        else:  # mode == 'any'
            return any(results)

    def wait(self):
        """
        Return the maximum wait time from all throttles
        """
        wait_times = []

        for throttle in self.throttles:
            wait_time = throttle.wait()
            if wait_time is not None:
                wait_times.append(wait_time)

        return max(wait_times) if wait_times else None


# Throttle factory for creating throttle instances
class ThrottleFactory:
    """
    Factory for creating throttle instances with custom parameters
    """

    @staticmethod
    def create_burst_throttle(rate='60/min'):
        """Create burst throttle with custom rate"""
        throttle = BurstRateThrottle()
        throttle.rate = rate
        throttle.num_requests, throttle.duration = throttle.parse_rate(rate)
        return throttle

    @staticmethod
    def create_sustained_throttle(rate='1000/hour'):
        """Create sustained throttle with custom rate"""
        throttle = SustainedRateThrottle()
        throttle.rate = rate
        throttle.num_requests, throttle.duration = throttle.parse_rate(rate)
        return throttle

    @staticmethod
    def create_endpoint_throttle(endpoint_rates=None):
        """Create endpoint-specific throttle"""
        throttle = EndpointSpecificThrottle()
        if endpoint_rates:
            throttle.endpoint_rates.update(endpoint_rates)
        return throttle

    @staticmethod
    def create_composite_throttle(throttles, mode='all'):
        """Create composite throttle"""
        return CompositeThrottle(throttles=throttles, mode=mode)


# Throttle monitoring and metrics
class ThrottleMonitor:
    """
    Monitor throttling metrics for analysis and alerting
    """

    @staticmethod
    def record_throttle_hit(key: str, request, view=None):
        """Record a throttle hit for monitoring"""
        metric_data = {
            'timestamp': timezone.now().isoformat(),
            'key': key,
            'user_id': getattr(request.user, 'id', None) if hasattr(request, 'user') else None,
            'ip_address': get_client_ip(request),
            'path': request.path,
            'method': request.method,
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'view': view.__class__.__name__ if view else None,
        }

        # Store in cache for monitoring dashboard
        monitor_key = f"throttle_hits:{timezone.now().strftime('%Y%m%d%H')}"
        hits = cache.get(monitor_key, [])
        hits.append(metric_data)
        cache.set(monitor_key, hits[-1000:], 3600)  # Keep last 1000 hits for 1 hour

        logger.info("Throttle hit recorded", **metric_data)

    @staticmethod
    def get_throttle_stats(hours_back=24):
        """Get throttle statistics for monitoring"""
        stats = {
            'total_hits': 0,
            'hits_by_hour': {},
            'top_ips': {},
            'top_paths': {},
            'top_users': {},
        }

        # Collect data from last N hours
        for hour_offset in range(hours_back):
            hour_key = (timezone.now() - timezone.timedelta(hours=hour_offset)).strftime('%Y%m%d%H')
            monitor_key = f"throttle_hits:{hour_key}"

            hits = cache.get(monitor_key, [])
            stats['total_hits'] += len(hits)
            stats['hits_by_hour'][hour_key] = len(hits)

            # Aggregate by IP, path, and user
            for hit in hits:
                ip = hit.get('ip_address', 'unknown')
                path = hit.get('path', 'unknown')
                user_id = hit.get('user_id')

                stats['top_ips'][ip] = stats['top_ips'].get(ip, 0) + 1
                stats['top_paths'][path] = stats['top_paths'].get(path, 0) + 1

                if user_id:
                    stats['top_users'][user_id] = stats['top_users'].get(user_id, 0) + 1

        return stats


# Utility functions
def get_remaining_requests(request, throttle_class):
    """
    Get remaining requests for a user/IP with a specific throttle
    """
    throttle = throttle_class()

    if hasattr(throttle, 'rate'):
        throttle.num_requests, throttle.duration = throttle.parse_rate(throttle.rate)

    key = throttle.get_cache_key(request, None)
    if not key:
        return throttle.num_requests

    history = cache.get(key, [])
    now = time.time()

    # Filter recent requests
    recent_requests = [req_time for req_time in history if req_time > now - throttle.duration]

    return max(0, throttle.num_requests - len(recent_requests))


def reset_throttle_for_user(user_id=None, ip_address=None):
    """
    Reset throttle counts for a specific user or IP (admin function)
    """
    patterns = []

    if user_id:
        patterns.extend([
            f'throttle_user_{user_id}',
            f'throttle_burst_*_{user_id}',
            f'throttle_sustained_{user_id}',
        ])

    if ip_address:
        patterns.extend([
            f'throttle_anon_{ip_address}',
            f'throttle_ip_{ip_address}',
            f'throttle_burst_*_{ip_address}',
        ])

    cleared_count = 0
    for pattern in patterns:
        if '*' in pattern:
            # Pattern matching would require Redis SCAN
            logger.info(f"Pattern reset not implemented: {pattern}")
        else:
            if cache.delete(pattern):
                cleared_count += 1

    logger.info(
        "Throttle reset completed",
        user_id=user_id,
        ip_address=ip_address,
        cleared_count=cleared_count,
    )

    return cleared_count
