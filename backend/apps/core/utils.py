import time
import json
import hashlib
import random
import string
from functools import wraps
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Callable, Union, Tuple
from datetime import datetime, timedelta
from django.http import HttpRequest
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
import structlog

logger = structlog.get_logger(__name__)


def get_client_ip(request: HttpRequest) -> str:
    """
    Get client IP address from request, handling proxies and load balancers
    """
    # Check for IP in headers set by proxies
    ip_headers = [
        'HTTP_X_FORWARDED_FOR',
        'HTTP_X_REAL_IP',
        'HTTP_X_FORWARDED',
        'HTTP_X_CLUSTER_CLIENT_IP',
        'HTTP_FORWARDED_FOR',
        'HTTP_FORWARDED',
        'REMOTE_ADDR',
    ]

    for header in ip_headers:
        ip = request.META.get(header)
        if ip:
            # Handle comma-separated IPs (X-Forwarded-For can contain multiple IPs)
            if ',' in ip:
                ip = ip.split(',')[0].strip()

            # Validate IP format
            if is_valid_ip(ip):
                return ip

    return '127.0.0.1'  # Fallback


def is_valid_ip(ip: str) -> bool:
    """
    Validate IP address format
    """
    import socket

    try:
        socket.inet_aton(ip)
        return True
    except socket.error:
        pass

    try:
        socket.inet_pton(socket.AF_INET6, ip)
        return True
    except socket.error:
        pass

    return False


def generate_random_string(length: int = 32, include_digits: bool = True,
                          include_special: bool = False) -> str:
    """
    Generate a random string for tokens, passwords, etc.
    """
    chars = string.ascii_letters

    if include_digits:
        chars += string.digits

    if include_special:
        chars += '!@#$%^&*'

    return ''.join(random.choice(chars) for _ in range(length))


def hash_string(value: str, salt: str = None) -> str:
    """
    Hash a string using SHA-256 with optional salt
    """
    if salt:
        value = f"{value}{salt}"

    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def is_valid_json(value: str) -> bool:
    """
    Check if string is valid JSON
    """
    try:
        json.loads(value)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


def safe_json_loads(value: str, default: Any = None) -> Any:
    """
    Safely parse JSON string, returning default on error
    """
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def format_currency(amount: Union[int, float, Decimal], currency: str = '£') -> str:
    """
    Format currency amount for display
    """
    if isinstance(amount, (int, float)):
        amount = Decimal(str(amount))

    # Round to 2 decimal places
    amount = amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    return f"{currency}{amount:,.2f}"


def format_large_number(number: Union[int, float]) -> str:
    """
    Format large numbers with K, M, B suffixes
    """
    if number < 1000:
        return str(int(number))
    elif number < 1000000:
        return f"{number/1000:.1f}K"
    elif number < 1000000000:
        return f"{number/1000000:.1f}M"
    else:
        return f"{number/1000000000:.1f}B"


def calculate_percentage_change(old_value: float, new_value: float) -> float:
    """
    Calculate percentage change between two values
    """
    if old_value == 0:
        return 100.0 if new_value > 0 else 0.0

    return ((new_value - old_value) / old_value) * 100


def truncate_string(text: str, length: int = 100, suffix: str = '...') -> str:
    """
    Truncate string to specified length with suffix
    """
    if len(text) <= length:
        return text

    return text[:length - len(suffix)] + suffix


def slugify_string(text: str) -> str:
    """
    Convert string to URL-friendly slug
    """
    import re

    # Convert to lowercase and replace spaces/special chars with hyphens
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    slug = re.sub(r'[-\s]+', '-', slug)

    return slug.strip('-')


def parse_date_string(date_string: str, format_str: str = '%Y-%m-%d') -> Optional[datetime]:
    """
    Parse date string to datetime object
    """
    try:
        return datetime.strptime(date_string, format_str)
    except (ValueError, TypeError):
        return None


def format_duration(seconds: float) -> str:
    """
    Format duration in seconds to human-readable format
    """
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        seconds = seconds % 60
        return f"{minutes}m {seconds:.0f}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    Split list into chunks of specified size
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def deep_merge_dicts(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dictionaries
    """
    result = dict1.copy()

    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def flatten_dict(data: Dict[str, Any], separator: str = '.') -> Dict[str, Any]:
    """
    Flatten nested dictionary
    """
    def _flatten(obj: Any, parent_key: str = '') -> Dict[str, Any]:
        items = []

        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{parent_key}{separator}{key}" if parent_key else key
                items.extend(_flatten(value, new_key).items())
        else:
            return {parent_key: obj}

        return dict(items)

    return _flatten(data)


# Decorators

def measure_time(func: Callable) -> Callable:
    """
    Decorator to measure and log function execution time
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()

        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time

            logger.info(
                "Function execution completed",
                function=func.__name__,
                module=func.__module__,
                duration_ms=round(duration * 1000, 2),
                args_count=len(args),
                kwargs_count=len(kwargs),
            )

            return result

        except Exception as e:
            duration = time.time() - start_time

            logger.error(
                "Function execution failed",
                function=func.__name__,
                module=func.__module__,
                duration_ms=round(duration * 1000, 2),
                exception=str(e),
                exception_type=e.__class__.__name__,
            )

            raise

    return wrapper


def retry_with_backoff(max_retries: int = 3, backoff_factor: float = 2.0,
                      initial_delay: float = 1.0) -> Callable:
    """
    Decorator to retry function with exponential backoff
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            "Function failed after all retries",
                            function=func.__name__,
                            attempts=attempt + 1,
                            exception=str(e),
                        )
                        raise

                    logger.warning(
                        "Function failed, retrying",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay=delay,
                        exception=str(e),
                    )

                    time.sleep(delay)
                    delay *= backoff_factor

            raise last_exception

        return wrapper
    return decorator


def cache_result(timeout: int = 3600, key_prefix: str = None) -> Callable:
    """
    Decorator to cache function results
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = generate_cache_key(func, args, kwargs, key_prefix)

            # Try to get from cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                logger.debug(
                    "Cache hit for function",
                    function=func.__name__,
                    cache_key=cache_key,
                )
                return cached_result

            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, timeout)

            logger.debug(
                "Function result cached",
                function=func.__name__,
                cache_key=cache_key,
                timeout=timeout,
            )

            return result

        return wrapper
    return decorator


def rate_limit(calls: int, period: int) -> Callable:
    """
    Decorator to rate limit function calls per period (in seconds)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate rate limit key
            key = f"rate_limit:{func.__module__}.{func.__name__}"

            # Get current call count
            current_calls = cache.get(key, 0)

            if current_calls >= calls:
                from .exceptions import RateLimitExceededError
                raise RateLimitExceededError(
                    f"Rate limit exceeded: {calls} calls per {period} seconds"
                )

            # Increment counter
            cache.set(key, current_calls + 1, period)

            return func(*args, **kwargs)

        return wrapper
    return decorator


# Cache utilities

def generate_cache_key(func: Callable, args: tuple, kwargs: dict,
                      prefix: str = None) -> str:
    """
    Generate cache key for function call
    """
    # Create key components
    key_parts = [
        prefix or f"{func.__module__}.{func.__name__}",
        str(hash(args)),
        str(hash(tuple(sorted(kwargs.items())))),
    ]

    return ":".join(key_parts)


def cache_key_generator(model_name: str, **params) -> str:
    """
    Generate cache key for model queries
    """
    key_parts = [model_name]

    for key, value in sorted(params.items()):
        key_parts.append(f"{key}:{value}")

    return ":".join(key_parts)


def invalidate_cache_pattern(pattern: str) -> int:
    """
    Invalidate cache keys matching pattern
    Returns number of keys invalidated
    """
    # This would require Redis for pattern matching
    # For now, implement basic version
    try:
        if hasattr(cache, 'delete_pattern'):
            return cache.delete_pattern(pattern)
        else:
            # Fallback: log the pattern for manual cleanup
            logger.warning(
                "Cache pattern invalidation not supported",
                pattern=pattern,
                cache_backend=cache.__class__.__name__,
            )
            return 0
    except Exception as e:
        logger.error(
            "Cache invalidation failed",
            pattern=pattern,
            error=str(e),
        )
        return 0


# Data validation utilities

def validate_email(email: str) -> bool:
    """
    Validate email address format
    """
    import re

    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_phone(phone: str) -> bool:
    """
    Validate phone number format
    """
    import re

    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)

    # Check if it's a valid length (7-15 digits)
    return 7 <= len(digits) <= 15


def validate_fpl_team_id(team_id: Union[str, int]) -> bool:
    """
    Validate FPL team ID format
    """
    try:
        team_id = int(team_id)
        return 100000 <= team_id <= 9999999
    except (ValueError, TypeError):
        return False


def sanitize_input(value: str, max_length: int = 1000,
                  allowed_chars: str = None) -> str:
    """
    Sanitize user input
    """
    if not isinstance(value, str):
        value = str(value)

    # Truncate to max length
    value = value[:max_length]

    # Remove control characters
    value = ''.join(char for char in value if ord(char) >= 32 or char in '\t\n\r')

    # Filter allowed characters if specified
    if allowed_chars:
        value = ''.join(char for char in value if char in allowed_chars)

    return value.strip()


# Performance utilities

class PerformanceTimer:
    """
    Context manager for timing operations
    """

    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration = self.end_time - self.start_time

        logger.info(
            "Operation completed",
            operation=self.operation_name,
            duration_ms=round(duration * 1000, 2),
            success=exc_type is None,
        )

    @property
    def duration(self) -> float:
        """Get duration in seconds"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0


class BatchProcessor:
    """
    Utility for processing items in batches
    """

    def __init__(self, batch_size: int = 100, delay_between_batches: float = 0):
        self.batch_size = batch_size
        self.delay_between_batches = delay_between_batches

    def process(self, items: List[Any], process_func: Callable) -> List[Any]:
        """
        Process items in batches
        """
        results = []
        batches = chunk_list(items, self.batch_size)

        for i, batch in enumerate(batches):
            logger.info(
                "Processing batch",
                batch_number=i + 1,
                total_batches=len(batches),
                batch_size=len(batch),
            )

            batch_results = process_func(batch)
            results.extend(batch_results)

            # Add delay between batches if specified
            if self.delay_between_batches > 0 and i < len(batches) - 1:
                time.sleep(self.delay_between_batches)

        return results


# File utilities

def safe_file_name(filename: str) -> str:
    """
    Create safe filename by removing/replacing unsafe characters
    """
    import re

    # Remove path components
    filename = filename.split('/')[-1].split('\\')[-1]

    # Replace unsafe characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)

    # Remove control characters
    filename = ''.join(char for char in filename if ord(char) >= 32)

    # Truncate if too long
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = f"{name[:255-len(ext)-1]}.{ext}" if ext else name[:255]

    return filename or 'unnamed_file'


def get_file_extension(filename: str) -> str:
    """
    Get file extension from filename
    """
    return filename.split('.')[-1].lower() if '.' in filename else ''


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.1f} GB"


# URL utilities

def build_url(base_url: str, path: str = '', params: Dict[str, Any] = None) -> str:
    """
    Build URL with path and query parameters
    """
    from urllib.parse import urljoin, urlencode

    # Join base URL and path
    url = urljoin(base_url.rstrip('/') + '/', path.lstrip('/'))

    # Add query parameters
    if params:
        # Filter out None values
        params = {k: v for k, v in params.items() if v is not None}
        if params:
            url += '?' + urlencode(params)

    return url


# Environment utilities

def get_environment() -> str:
    """
    Get current environment (development, staging, production)
    """
    return getattr(settings, 'ENVIRONMENT', 'development')


def is_development() -> bool:
    """
    Check if running in development environment
    """
    return get_environment() == 'development' or settings.DEBUG


def is_production() -> bool:
    """
    Check if running in production environment
    """
    return get_environment() == 'production'


# Custom JSON encoder
class ExtendedJSONEncoder(DjangoJSONEncoder):
    """
    Extended JSON encoder that handles additional types
    """

    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, set):
            return list(obj)
        elif hasattr(obj, 'isoformat'):
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            return obj.__dict__

        return super().default(obj)


# Configuration helper
class ConfigHelper:
    """
    Helper for accessing configuration values with defaults and type conversion
    """

    @staticmethod
    def get_int(key: str, default: int = 0) -> int:
        """Get integer configuration value"""
        try:
            return int(getattr(settings, key, default))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def get_float(key: str, default: float = 0.0) -> float:
        """Get float configuration value"""
        try:
            return float(getattr(settings, key, default))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def get_bool(key: str, default: bool = False) -> bool:
        """Get boolean configuration value"""
        value = getattr(settings, key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        return bool(value)

    @staticmethod
    def get_list(key: str, default: List[str] = None) -> List[str]:
        """Get list configuration value"""
        default = default or []
        value = getattr(settings, key, default)

        if isinstance(value, (list, tuple)):
            return list(value)
        elif isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]

        return default
