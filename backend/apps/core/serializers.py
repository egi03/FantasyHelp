from rest_framework import serializers
from rest_framework.fields import empty
from django.core.cache import cache
from django.utils import timezone
from typing import Dict, Any, Optional, List
import hashlib
import json
import structlog

logger = structlog.get_logger(__name__)


class BaseModelSerializer(serializers.ModelSerializer):
    """
    Enhanced base model serializer with common functionality
    Provides standardized field handling and validation
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add request context if available
        self.request = self.context.get('request')
        self.user = getattr(self.request, 'user', None) if self.request else None

    def to_representation(self, instance):
        """Enhanced representation with performance optimization"""
        data = super().to_representation(instance)

        # Add metadata if requested
        if self.should_include_metadata():
            data['_metadata'] = self.get_metadata(instance)

        # Transform fields based on context
        data = self.transform_fields(data, instance)

        return data

    def should_include_metadata(self) -> bool:
        """Check if metadata should be included"""
        if not self.request:
            return False

        return self.request.query_params.get('include_metadata', '').lower() in ['true', '1', 'yes']

    def get_metadata(self, instance) -> Dict[str, Any]:
        """Get metadata for instance"""
        metadata = {
            'model': instance.__class__.__name__.lower(),
            'pk': str(instance.pk),
        }

        # Add timestamps if available
        if hasattr(instance, 'created_at'):
            metadata['created_at'] = instance.created_at.isoformat()

        if hasattr(instance, 'updated_at'):
            metadata['updated_at'] = instance.updated_at.isoformat()

        return metadata

    def transform_fields(self, data: Dict[str, Any], instance) -> Dict[str, Any]:
        """Transform fields based on context - override in subclasses"""
        return data

    def validate(self, attrs):
        """Enhanced validation with logging"""
        attrs = super().validate(attrs)

        # Log validation if in debug mode
        if logger.isEnabledFor('DEBUG'):
            logger.debug(
                "Serializer validation completed",
                serializer=self.__class__.__name__,
                fields=list(attrs.keys())
            )

        return attrs

    def create(self, validated_data):
        """Enhanced create with audit logging"""
        instance = super().create(validated_data)

        logger.info(
            "Object created via serializer",
            model=instance.__class__.__name__,
            pk=str(instance.pk),
            user_id=self.user.id if self.user else None
        )

        return instance

    def update(self, instance, validated_data):
        """Enhanced update with audit logging"""
        # Store original values for comparison
        original_data = {}
        for field in validated_data.keys():
            if hasattr(instance, field):
                original_data[field] = getattr(instance, field)

        updated_instance = super().update(instance, validated_data)

        # Log changes
        changes = {}
        for field, new_value in validated_data.items():
            old_value = original_data.get(field)
            if old_value != new_value:
                changes[field] = {'old': old_value, 'new': new_value}

        if changes:
            logger.info(
                "Object updated via serializer",
                model=instance.__class__.__name__,
                pk=str(instance.pk),
                changes=changes,
                user_id=self.user.id if self.user else None
            )

        return updated_instance


class CachedSerializerMixin:
    """
    Mixin for adding caching capabilities to serializers
    Caches serialized representations for improved performance
    """

    # Cache timeout in seconds (1 hour default)
    CACHE_TIMEOUT = 3600

    # Whether to use caching for this serializer
    USE_CACHE = True

    def get_cache_key(self, instance) -> str:
        """Generate cache key for instance"""
        model_name = instance.__class__.__name__.lower()
        instance_id = str(instance.pk)
        serializer_name = self.__class__.__name__.lower()

        # Include context-sensitive data in cache key
        context_hash = self.get_context_hash()

        return f"serializer:{model_name}:{instance_id}:{serializer_name}:{context_hash}"

    def get_context_hash(self) -> str:
        """Generate hash of context-sensitive data"""
        context_data = {}

        # Include request parameters that affect serialization
        if self.context.get('request'):
            request = self.context['request']
            context_data.update({
                'include_metadata': request.query_params.get('include_metadata', ''),
                'fields': request.query_params.get('fields', ''),
                'expand': request.query_params.get('expand', ''),
            })

        # Include user-specific data if relevant
        if hasattr(self, 'user') and self.user:
            context_data['user_id'] = self.user.id

        # Create hash of context data
        context_str = json.dumps(context_data, sort_keys=True)
        return hashlib.md5(context_str.encode()).hexdigest()[:8]

    def to_representation(self, instance):
        """Use cached representation if available"""
        if not self.USE_CACHE:
            return super().to_representation(instance)

        cache_key = self.get_cache_key(instance)
        cached_data = cache.get(cache_key)

        if cached_data is not None:
            logger.debug("Serializer cache hit", cache_key=cache_key)
            return cached_data

        # Generate representation and cache it
        data = super().to_representation(instance)

        # Cache with timeout
        cache.set(cache_key, data, self.CACHE_TIMEOUT)
        logger.debug("Serializer cached", cache_key=cache_key)

        return data

    def invalidate_cache(self, instance):
        """Invalidate cache for instance"""
        cache_key = self.get_cache_key(instance)
        cache.delete(cache_key)
        logger.debug("Serializer cache invalidated", cache_key=cache_key)


class DynamicFieldsSerializerMixin:
    """
    Mixin for dynamic field inclusion/exclusion
    Allows clients to specify which fields they want
    """

    def __init__(self, *args, **kwargs):
        # Extract fields parameter
        fields = kwargs.pop('fields', None)
        exclude = kwargs.pop('exclude', None)

        super().__init__(*args, **kwargs)

        # Handle fields from query parameters
        if self.context.get('request'):
            request = self.context['request']
            query_fields = request.query_params.get('fields')
            query_exclude = request.query_params.get('exclude')

            if query_fields:
                fields = query_fields.split(',')
            if query_exclude:
                exclude = query_exclude.split(',')

        if fields is not None:
            # Remove fields not in the specified list
            allowed = set(fields)
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name, None)

        if exclude is not None:
            # Remove excluded fields
            for field_name in exclude:
                self.fields.pop(field_name, None)


class TimestampedSerializerMixin:
    """
    Mixin for handling timestamped models
    Provides consistent timestamp field handling
    """

    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # Format timestamps consistently
        if 'created_at' in data and data['created_at']:
            data['created_at'] = self.format_timestamp(instance.created_at)

        if 'updated_at' in data and data['updated_at']:
            data['updated_at'] = self.format_timestamp(instance.updated_at)

        return data

    def format_timestamp(self, timestamp) -> str:
        """Format timestamp for API response"""
        return timestamp.isoformat()

    def validate_created_at(self, value):
        """Validate created_at timestamp"""
        if value and value > timezone.now():
            raise serializers.ValidationError("Creation date cannot be in the future")
        return value


class ReadOnlySerializerMixin:
    """
    Mixin for read-only serializers
    Raises error if used for create/update operations
    """

    def create(self, validated_data):
        raise serializers.ValidationError("This endpoint is read-only")

    def update(self, instance, validated_data):
        raise serializers.ValidationError("This endpoint is read-only")


class PaginatedResponseSerializer(serializers.Serializer):
    """
    Serializer for paginated API responses
    Provides consistent pagination format
    """

    count = serializers.IntegerField(
        help_text="Total number of objects"
    )
    next = serializers.URLField(
        allow_null=True,
        help_text="URL for next page of results"
    )
    previous = serializers.URLField(
        allow_null=True,
        help_text="URL for previous page of results"
    )
    results = serializers.ListField(
        help_text="Array of result objects"
    )

    # Additional pagination metadata
    page_size = serializers.IntegerField(
        required=False,
        help_text="Number of objects per page"
    )
    total_pages = serializers.IntegerField(
        required=False,
        help_text="Total number of pages"
    )
    current_page = serializers.IntegerField(
        required=False,
        help_text="Current page number"
    )


class ErrorSerializer(serializers.Serializer):
    """
    Serializer for API error responses
    Provides consistent error format
    """

    error = serializers.CharField(
        help_text="Error type or code"
    )
    message = serializers.CharField(
        help_text="Human-readable error message"
    )
    details = serializers.JSONField(
        required=False,
        help_text="Additional error details"
    )
    timestamp = serializers.DateTimeField(
        default=timezone.now,
        help_text="When the error occurred"
    )
    request_id = serializers.CharField(
        required=False,
        help_text="Unique request identifier for debugging"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add request ID from context if available
        if self.context.get('request'):
            request = self.context['request']
            if hasattr(request, 'id'):
                self.initial_data = self.initial_data or {}
                self.initial_data['request_id'] = request.id


class ValidationErrorSerializer(ErrorSerializer):
    """
    Serializer for validation error responses
    Extends ErrorSerializer with field-specific errors
    """

    field_errors = serializers.DictField(
        required=False,
        help_text="Field-specific validation errors"
    )
    non_field_errors = serializers.ListField(
        required=False,
        help_text="Non-field validation errors"
    )


class BulkOperationSerializer(serializers.Serializer):
    """
    Base serializer for bulk operations
    Handles multiple objects in a single request
    """

    objects = serializers.ListField(
        help_text="List of objects to process"
    )
    ignore_errors = serializers.BooleanField(
        default=False,
        help_text="Continue processing if individual objects fail"
    )

    def validate_objects(self, value):
        """Validate objects list"""
        if not value:
            raise serializers.ValidationError("Objects list cannot be empty")

        if len(value) > 1000:  # Reasonable limit
            raise serializers.ValidationError("Cannot process more than 1000 objects at once")

        return value


class BulkResponseSerializer(serializers.Serializer):
    """
    Serializer for bulk operation responses
    """

    processed = serializers.IntegerField(
        help_text="Number of objects processed"
    )
    successful = serializers.IntegerField(
        help_text="Number of successful operations"
    )
    failed = serializers.IntegerField(
        help_text="Number of failed operations"
    )
    errors = serializers.ListField(
        required=False,
        help_text="List of errors that occurred"
    )
    results = serializers.ListField(
        required=False,
        help_text="Results for successful operations"
    )


class ChoiceDisplaySerializerMixin:
    """
    Mixin for handling Django choice fields
    Adds display values for choice fields
    """

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # Add display values for choice fields
        for field_name, field in self.fields.items():
            if hasattr(field, 'choices') and field.choices:
                value = data.get(field_name)
                if value is not None:
                    # Add display value
                    display_field = f"{field_name}_display"
                    if hasattr(instance, f"get_{field_name}_display"):
                        data[display_field] = getattr(instance, f"get_{field_name}_display")()

        return data


class OptimizedListSerializer(serializers.ListSerializer):
    """
    Optimized list serializer for better performance
    Uses bulk operations and caching where possible
    """

    def to_representation(self, data):
        """Optimized representation for large datasets"""
        # Use bulk prefetch for related objects
        if hasattr(data, 'prefetch_related') and hasattr(self.child, 'get_prefetch_fields'):
            prefetch_fields = self.child.get_prefetch_fields()
            if prefetch_fields:
                data = data.prefetch_related(*prefetch_fields)

        # Use bulk select for foreign keys
        if hasattr(data, 'select_related') and hasattr(self.child, 'get_select_fields'):
            select_fields = self.child.get_select_fields()
            if select_fields:
                data = data.select_related(*select_fields)

        return super().to_representation(data)


class FilterableSerializerMixin:
    """
    Mixin for adding filtering capabilities to serializers
    Allows field-level filtering based on query parameters
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Apply filters from query parameters
        if self.context.get('request'):
            self.apply_query_filters()

    def apply_query_filters(self):
        """Apply filters based on query parameters"""
        request = self.context['request']

        # Handle field filtering
        only_fields = request.query_params.get('only')
        if only_fields:
            fields_to_keep = set(only_fields.split(','))
            fields_to_remove = set(self.fields.keys()) - fields_to_keep
            for field in fields_to_remove:
                self.fields.pop(field, None)

        # Handle field exclusion
        exclude_fields = request.query_params.get('exclude')
        if exclude_fields:
            for field in exclude_fields.split(','):
                self.fields.pop(field, None)


class VersionedSerializerMixin:
    """
    Mixin for API versioning support
    Handles different field sets for different API versions
    """

    # Define version-specific field configurations
    VERSION_FIELDS = {
        'v1': None,  # All fields
        'v2': None,  # All fields
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Apply version-specific field filtering
        version = self.get_api_version()
        if version and version in self.VERSION_FIELDS:
            version_fields = self.VERSION_FIELDS[version]
            if version_fields is not None:
                # Remove fields not in version spec
                fields_to_remove = set(self.fields.keys()) - set(version_fields)
                for field in fields_to_remove:
                    self.fields.pop(field, None)

    def get_api_version(self) -> Optional[str]:
        """Get API version from request"""
        if not self.context.get('request'):
            return None

        request = self.context['request']

        # Try version from header
        version = request.META.get('HTTP_API_VERSION')
        if version:
            return version

        # Try version from query parameter
        version = request.query_params.get('version')
        if version:
            return version

        # Try version from URL (assuming versioned URLs)
        if hasattr(request, 'version'):
            return request.version

        return 'v1'  # Default version


# Factory functions for common serializer patterns

def create_minimal_serializer(model_class, fields: List[str]):
    """Create a minimal serializer with specified fields"""

    class MinimalSerializer(BaseModelSerializer):
        class Meta:
            model = model_class
            fields = fields
            read_only_fields = fields

    return MinimalSerializer


def create_choice_serializer(choices: List[tuple], field_name: str = 'value'):
    """Create a serializer for choice fields"""

    class ChoiceSerializer(serializers.Serializer):
        value = serializers.ChoiceField(choices=choices)
        display = serializers.SerializerMethodField()

        def get_display(self, obj):
            choice_dict = dict(choices)
            return choice_dict.get(obj[field_name], '')

    return ChoiceSerializer


def create_stats_serializer(stat_fields: List[str]):
    """Create a serializer for statistical data"""

    class StatsSerializer(serializers.Serializer):
        pass

    # Dynamically add stat fields
    for field in stat_fields:
        setattr(StatsSerializer, field, serializers.FloatField())

    return StatsSerializer
