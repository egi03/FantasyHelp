from rest_framework import permissions
from rest_framework.permissions import BasePermission
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.utils import timezone
from typing import Any, Optional
import structlog

from apps.core.utils import get_client_ip

logger = structlog.get_logger(__name__)


class BasePermission(BasePermission):
    """
    Enhanced base permission class with logging and caching
    """

    def has_permission(self, request, view):
        """
        Enhanced permission check with logging
        """
        result = self._check_permission(request, view)

        # Log permission checks for audit
        if not result:
            logger.warning(
                "Permission denied",
                user_id=getattr(request.user, 'id', None) if hasattr(request, 'user') else None,
                user_type='anonymous' if isinstance(request.user, AnonymousUser) else 'authenticated',
                permission_class=self.__class__.__name__,
                view_class=view.__class__.__name__ if view else None,
                method=request.method,
                path=request.path,
                ip_address=get_client_ip(request),
            )

        return result

    def _check_permission(self, request, view):
        """
        Override this method instead of has_permission for permission logic
        """
        return True

    def has_object_permission(self, request, view, obj):
        """
        Enhanced object-level permission check
        """
        result = self._check_object_permission(request, view, obj)

        if not result:
            logger.warning(
                "Object permission denied",
                user_id=getattr(request.user, 'id', None) if hasattr(request, 'user') else None,
                permission_class=self.__class__.__name__,
                object_type=obj.__class__.__name__,
                object_id=getattr(obj, 'id', None),
                method=request.method,
            )

        return result

    def _check_object_permission(self, request, view, obj):
        """
        Override this method for object-level permission logic
        """
        return True


class IsOwnerOrReadOnly(BasePermission):
    """
    Permission that only allows owners of an object to edit it
    """

    def _check_permission(self, request, view):
        # Read permissions for any request
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions only for authenticated users
        return request.user and request.user.is_authenticated

    def _check_object_permission(self, request, view, obj):
        # Read permissions for any request
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions only to the owner of the object
        return hasattr(obj, 'user') and obj.user == request.user


class IsAuthenticatedOrReadOnlyThrottled(BasePermission):
    """
    Permission that allows read access to everyone but throttles anonymous users
    """

    def _check_permission(self, request, view):
        # Write permissions only for authenticated users
        if request.method not in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        # Read permissions for everyone (throttling handled separately)
        return True


class IsPremiumUser(BasePermission):
    """
    Permission that only allows premium users
    """

    def _check_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Check if user has premium status
        return getattr(request.user, 'is_premium', False)


class IsTeamOwner(BasePermission):
    """
    Permission that checks if user owns the FPL team
    """

    def _check_object_permission(self, request, view, obj):
        # For UserTeam objects, check ownership through user relationship
        if hasattr(obj, 'user'):
            return obj.user == request.user

        # For objects related to UserTeam, traverse the relationship
        if hasattr(obj, 'user_team') and hasattr(obj.user_team, 'user'):
            return obj.user_team.user == request.user

        return False


class IsAdminOrReadOnly(BasePermission):
    """
    Permission that allows read access to everyone and write access to admins only
    """

    def _check_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True

        return request.user and request.user.is_staff


class HasAPIKey(BasePermission):
    """
    Permission that checks for valid API key in headers
    """

    def _check_permission(self, request, view):
        api_key = request.META.get('HTTP_X_API_KEY')

        if not api_key:
            return False

        # Check if API key is valid (implement your own logic)
        return self._validate_api_key(api_key, request)

    def _validate_api_key(self, api_key: str, request) -> bool:
        """
        Validate API key against database or cache
        """
        # Check cache first
        cache_key = f"api_key:{api_key}"
        cached_result = cache.get(cache_key)

        if cached_result is not None:
            return cached_result

        # Implement your API key validation logic here
        # This could check against a database table of API keys
        valid = self._check_api_key_in_database(api_key)

        # Cache result for performance
        cache.set(cache_key, valid, 300)  # Cache for 5 minutes

        return valid

    def _check_api_key_in_database(self, api_key: str) -> bool:
        """
        Check API key in database - implement based on your model
        """
        # Example implementation:
        # from apps.auth.models import APIKey
        # try:
        #     api_key_obj = APIKey.objects.get(key=api_key, is_active=True)
        #     return True
        # except APIKey.DoesNotExist:
        #     return False

        return False  # Placeholder


class IsWhitelistedIP(BasePermission):
    """
    Permission that only allows requests from whitelisted IP addresses
    """

    def __init__(self, allowed_ips=None):
        self.allowed_ips = allowed_ips or []

    def _check_permission(self, request, view):
        client_ip = get_client_ip(request)

        # Allow if no whitelist is configured
        if not self.allowed_ips:
            return True

        is_allowed = client_ip in self.allowed_ips

        if not is_allowed:
            logger.warning(
                "IP not whitelisted",
                ip_address=client_ip,
                allowed_ips=self.allowed_ips,
                path=request.path,
            )

        return is_allowed


class TimeBasedPermission(BasePermission):
    """
    Permission that only allows access during certain time periods
    """

    def __init__(self, allowed_hours=None):
        # Default: allow during business hours (9 AM - 5 PM UTC)
        self.allowed_hours = allowed_hours or list(range(9, 17))

    def _check_permission(self, request, view):
        current_hour = timezone.now().hour

        is_allowed = current_hour in self.allowed_hours

        if not is_allowed:
            logger.info(
                "Access denied due to time restriction",
                current_hour=current_hour,
                allowed_hours=self.allowed_hours,
                user_id=getattr(request.user, 'id', None) if hasattr(request, 'user') else None,
            )

        return is_allowed


class RateLimitedPermission(BasePermission):
    """
    Permission that implements rate limiting at the permission level
    """

    def __init__(self, requests_per_hour=100):
        self.requests_per_hour = requests_per_hour

    def _check_permission(self, request, view):
        # Generate rate limit key
        if request.user and request.user.is_authenticated:
            rate_key = f"rate_limit_user:{request.user.id}"
        else:
            rate_key = f"rate_limit_ip:{get_client_ip(request)}"

        # Check current request count
        current_requests = cache.get(rate_key, 0)

        if current_requests >= self.requests_per_hour:
            logger.warning(
                "Rate limit exceeded in permission check",
                rate_key=rate_key,
                current_requests=current_requests,
                limit=self.requests_per_hour,
            )
            return False

        # Increment counter
        cache.set(rate_key, current_requests + 1, 3600)  # 1 hour TTL

        return True


class FeaturePermission(BasePermission):
    """
    Permission that checks if a feature is enabled for the user
    """

    def __init__(self, feature_name):
        self.feature_name = feature_name

    def _check_permission(self, request, view):
        # Check feature flags
        return self._is_feature_enabled(request.user, self.feature_name)

    def _is_feature_enabled(self, user, feature_name: str) -> bool:
        """
        Check if feature is enabled for user
        """
        # Check cache first
        cache_key = f"feature:{feature_name}:user:{getattr(user, 'id', 'anonymous')}"
        cached_result = cache.get(cache_key)

        if cached_result is not None:
            return cached_result

        # Implement your feature flag logic here
        # This could check against a feature flags service or database
        enabled = self._check_feature_flag(user, feature_name)

        # Cache result
        cache.set(cache_key, enabled, 900)  # Cache for 15 minutes

        return enabled

    def _check_feature_flag(self, user, feature_name: str) -> bool:
        """
        Check feature flag - implement based on your feature flag system
        """
        # Example implementation with Django settings
        from django.conf import settings

        feature_flags = getattr(settings, 'FEATURE_FLAGS', {})

        # Default feature state
        default_enabled = feature_flags.get(feature_name, True)

        # User-specific overrides could be implemented here
        # For example, check user groups, premium status, etc.

        return default_enabled


class DynamicPermission(BasePermission):
    """
    Permission that can be configured dynamically based on request context
    """

    def __init__(self, permission_func=None):
        self.permission_func = permission_func or self._default_permission

    def _check_permission(self, request, view):
        return self.permission_func(request, view)

    def _check_object_permission(self, request, view, obj):
        if hasattr(self.permission_func, 'check_object'):
            return self.permission_func.check_object(request, view, obj)
        return True

    def _default_permission(self, request, view):
        """Default permission logic"""
        return request.user and request.user.is_authenticated


class CompositePermission(BasePermission):
    """
    Permission that combines multiple permission classes with AND/OR logic
    """

    def __init__(self, permissions, operator='AND'):
        self.permissions = [perm() if isinstance(perm, type) else perm for perm in permissions]
        self.operator = operator.upper()

    def _check_permission(self, request, view):
        results = [perm.has_permission(request, view) for perm in self.permissions]

        if self.operator == 'AND':
            return all(results)
        elif self.operator == 'OR':
            return any(results)
        else:
            raise ValueError(f"Unknown operator: {self.operator}")

    def _check_object_permission(self, request, view, obj):
        results = [
            perm.has_object_permission(request, view, obj)
            for perm in self.permissions
        ]

        if self.operator == 'AND':
            return all(results)
        elif self.operator == 'OR':
            return any(results)
        else:
            raise ValueError(f"Unknown operator: {self.operator}")


class ResourceQuotaPermission(BasePermission):
    """
    Permission that enforces resource quotas (e.g., number of teams, suggestions)
    """

    def __init__(self, resource_type, quota_limit):
        self.resource_type = resource_type
        self.quota_limit = quota_limit

    def _check_permission(self, request, view):
        if request.method not in ['POST', 'PUT', 'PATCH']:
            return True  # No quota check for read operations

        if not request.user or not request.user.is_authenticated:
            return False

        # Check current resource usage
        current_usage = self._get_current_usage(request.user)

        if current_usage >= self.quota_limit:
            logger.warning(
                "Resource quota exceeded",
                user_id=request.user.id,
                resource_type=self.resource_type,
                current_usage=current_usage,
                quota_limit=self.quota_limit,
            )
            return False

        return True

    def _get_current_usage(self, user) -> int:
        """
        Get current resource usage for user
        """
        # Implement based on your resource type
        if self.resource_type == 'teams':
            from apps.fpl.models import UserTeam
            return UserTeam.objects.filter(user=user).count()
        elif self.resource_type == 'suggestions':
            from apps.fpl.models import TransferSuggestion
            # Count suggestions generated today
            today = timezone.now().date()
            return TransferSuggestion.objects.filter(
                user_team__user=user,
                created_at__date=today
            ).count()

        return 0


# Permission factory for creating custom permissions
class PermissionFactory:
    """
    Factory for creating permission instances with custom parameters
    """

    @staticmethod
    def create_ip_whitelist(allowed_ips):
        """Create IP whitelist permission"""
        return IsWhitelistedIP(allowed_ips=allowed_ips)

    @staticmethod
    def create_time_based(allowed_hours):
        """Create time-based permission"""
        return TimeBasedPermission(allowed_hours=allowed_hours)

    @staticmethod
    def create_rate_limited(requests_per_hour):
        """Create rate-limited permission"""
        return RateLimitedPermission(requests_per_hour=requests_per_hour)

    @staticmethod
    def create_feature_gated(feature_name):
        """Create feature-gated permission"""
        return FeaturePermission(feature_name=feature_name)

    @staticmethod
    def create_composite(permissions, operator='AND'):
        """Create composite permission"""
        return CompositePermission(permissions=permissions, operator=operator)

    @staticmethod
    def create_quota_based(resource_type, quota_limit):
        """Create quota-based permission"""
        return ResourceQuotaPermission(resource_type=resource_type, quota_limit=quota_limit)


# Utility functions for permission checking
def check_user_permissions(user, permission_classes, request=None, view=None, obj=None):
    """
    Utility function to check multiple permissions for a user
    """
    for permission_class in permission_classes:
        permission = permission_class()

        # Check view-level permission
        if request and view:
            if not permission.has_permission(request, view):
                return False

        # Check object-level permission
        if obj and request and view:
            if not permission.has_object_permission(request, view, obj):
                return False

    return True


def get_user_permission_context(user):
    """
    Get permission context for a user (roles, groups, etc.)
    """
    if not user or user.is_anonymous:
        return {
            'is_authenticated': False,
            'is_staff': False,
            'is_premium': False,
            'groups': [],
            'permissions': [],
        }

    return {
        'is_authenticated': True,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'is_premium': getattr(user, 'is_premium', False),
        'groups': list(user.groups.values_list('name', flat=True)),
        'permissions': list(user.get_all_permissions()),
        'date_joined': user.date_joined,
        'last_login': user.last_login,
    }


# Decorators for view-level permission checking
def require_permission(*permission_classes):
    """
    Decorator to require specific permissions for a view
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            for permission_class in permission_classes:
                permission = permission_class()
                if not permission.has_permission(request, None):
                    from django.http import HttpResponseForbidden
                    return HttpResponseForbidden("Permission denied")

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def require_feature(feature_name):
    """
    Decorator to require a feature flag to be enabled
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            permission = FeaturePermission(feature_name)
            if not permission.has_permission(request, None):
                from django.http import HttpResponseForbidden
                return HttpResponseForbidden(f"Feature '{feature_name}' is not enabled")

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator
