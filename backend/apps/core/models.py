import uuid
from django.db import models
from django.utils import timezone
from django.core.cache import cache
from django.db.models import QuerySet
from typing import Optional, Dict, Any, List, Union
import logging

logger = logging.getLogger(__name__)


class OptimizedManager(models.Manager):
    """
    Custom manager with performance optimizations
    Includes caching, bulk operations, and query optimization
    """

    def get_queryset(self) -> QuerySet:
        """Return optimized base queryset"""
        return super().get_queryset()

    def cached_get(self, cache_key: str, **kwargs) -> Optional[models.Model]:
        """Get object with caching support"""
        obj = cache.get(cache_key)
        if obj is None:
            try:
                obj = self.get(**kwargs)
                cache.set(cache_key, obj, 3600)  # Cache for 1 hour
            except self.model.DoesNotExist:
                return None
        return obj

    def bulk_create_or_update(self, objects: List[Dict[str, Any]],
                             unique_fields: List[str],
                             batch_size: int = 1000) -> Dict[str, int]:
        """
        Efficiently create or update objects in bulk
        Returns counts of created and updated objects
        """
        created_count = 0
        updated_count = 0

        # Process in batches
        for i in range(0, len(objects), batch_size):
            batch = objects[i:i + batch_size]

            # Get existing objects for this batch
            lookup_values = []
            for obj_data in batch:
                lookup = {}
                for field in unique_fields:
                    lookup[field] = obj_data[field]
                lookup_values.append(lookup)

            # Create Q objects for lookup
            from django.db.models import Q
            if lookup_values:
                q_objects = Q()
                for lookup in lookup_values:
                    q_objects |= Q(**lookup)

                existing_objects = {
                    tuple(getattr(obj, field) for field in unique_fields): obj
                    for obj in self.filter(q_objects)
                }
            else:
                existing_objects = {}

            # Separate into create and update lists
            to_create = []
            to_update = []

            for obj_data in batch:
                key = tuple(obj_data[field] for field in unique_fields)

                if key in existing_objects:
                    # Update existing object
                    existing_obj = existing_objects[key]
                    for field, value in obj_data.items():
                        if field not in unique_fields:
                            setattr(existing_obj, field, value)
                    to_update.append(existing_obj)
                else:
                    # Create new object
                    to_create.append(self.model(**obj_data))

            # Perform bulk operations
            if to_create:
                self.bulk_create(to_create, batch_size=batch_size, ignore_conflicts=True)
                created_count += len(to_create)

            if to_update:
                self.bulk_update(to_update,
                               [field for field in obj_data.keys() if field not in unique_fields],
                               batch_size=batch_size)
                updated_count += len(to_update)

        logger.info(f"Bulk operation completed: {created_count} created, {updated_count} updated")
        return {'created': created_count, 'updated': updated_count}

    def with_prefetch(self, *prefetch_fields) -> QuerySet:
        """Add prefetch_related for better performance"""
        return self.get_queryset().prefetch_related(*prefetch_fields)

    def with_select(self, *select_fields) -> QuerySet:
        """Add select_related for better performance"""
        return self.get_queryset().select_related(*select_fields)


class BaseModel(models.Model):
    """
    Abstract base model with common fields and methods
    Provides UUID primary key and common functionality
    """

    class Meta:
        abstract = True

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier"
    )

    objects = OptimizedManager()

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.id})"

    def get_cache_key(self, suffix: str = '') -> str:
        """Generate cache key for this object"""
        base_key = f"{self.__class__.__name__.lower()}:{self.id}"
        return f"{base_key}:{suffix}" if suffix else base_key

    def cache_set(self, key: str, value: Any, timeout: int = 3600) -> None:
        """Set cache with object-specific key"""
        cache.set(self.get_cache_key(key), value, timeout)

    def cache_get(self, key: str, default: Any = None) -> Any:
        """Get cache with object-specific key"""
        return cache.get(self.get_cache_key(key), default)

    def cache_delete(self, key: str) -> None:
        """Delete cache with object-specific key"""
        cache.delete(self.get_cache_key(key))

    def to_dict(self, exclude_fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """Convert model to dictionary"""
        exclude_fields = exclude_fields or []
        data = {}

        for field in self._meta.fields:
            if field.name not in exclude_fields:
                value = getattr(self, field.name)
                if hasattr(value, 'isoformat'):  # DateTime fields
                    value = value.isoformat()
                elif hasattr(value, '__str__'):  # Other objects
                    value = str(value)
                data[field.name] = value

        return data


class TimestampedModel(BaseModel):
    """
    Abstract model with automatic timestamp tracking
    Includes created_at and updated_at fields
    """

    class Meta:
        abstract = True

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When this record was created"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_index=True,
        help_text="When this record was last updated"
    )

    def save(self, *args, **kwargs):
        """Override save to handle updated_at properly"""
        if not self.created_at:
            self.created_at = timezone.now()
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

        # Clear related caches
        self._clear_related_caches()

    def _clear_related_caches(self):
        """Clear caches related to this object"""
        # Override in subclasses to clear specific caches
        pass

    @property
    def age(self) -> timezone.timedelta:
        """Get age of this record"""
        return timezone.now() - self.created_at

    @property
    def last_modified(self) -> timezone.timedelta:
        """Get time since last modification"""
        return timezone.now() - self.updated_at


class SoftDeleteManager(OptimizedManager):
    """Manager that excludes soft-deleted objects by default"""

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(deleted_at__isnull=True)

    def with_deleted(self) -> QuerySet:
        """Include soft-deleted objects"""
        return super().get_queryset()

    def deleted_only(self) -> QuerySet:
        """Get only soft-deleted objects"""
        return super().get_queryset().filter(deleted_at__isnull=False)


class SoftDeleteModel(TimestampedModel):
    """
    Abstract model with soft delete functionality
    Objects are marked as deleted instead of being removed
    """

    class Meta:
        abstract = True

    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When this record was soft deleted"
    )

    objects = SoftDeleteManager()
    all_objects = OptimizedManager()  # Manager that includes deleted objects

    def delete(self, soft: bool = True, *args, **kwargs):
        """
        Delete object (soft delete by default)
        Set soft=False for hard delete
        """
        if soft:
            self.deleted_at = timezone.now()
            self.save(update_fields=['deleted_at'])
        else:
            super().delete(*args, **kwargs)

    def restore(self):
        """Restore soft-deleted object"""
        self.deleted_at = None
        self.save(update_fields=['deleted_at'])

    @property
    def is_deleted(self) -> bool:
        """Check if object is soft deleted"""
        return self.deleted_at is not None


class AuditModel(TimestampedModel):
    """
    Abstract model with audit trail functionality
    Tracks who created and modified records
    """

    class Meta:
        abstract = True

    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_created',
        help_text="User who created this record"
    )
    updated_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_updated',
        help_text="User who last updated this record"
    )

    def save(self, *args, **kwargs):
        """Override save to track user changes"""
        user = kwargs.pop('user', None)

        if user and hasattr(user, 'id'):
            if not self.created_at:  # New object
                self.created_by = user
            self.updated_by = user

        super().save(*args, **kwargs)


class CachedModel(TimestampedModel):
    """
    Abstract model with built-in caching support
    Automatically manages cache invalidation
    """

    class Meta:
        abstract = True

    CACHE_TIMEOUT = 3600  # 1 hour default

    @classmethod
    def get_cache_key(cls, identifier: Union[str, int]) -> str:
        """Generate cache key for model instance"""
        return f"{cls.__name__.lower()}:{identifier}"

    @classmethod
    def cached_get(cls, identifier: Union[str, int],
                  field_name: str = 'id') -> Optional['CachedModel']:
        """Get object with caching"""
        cache_key = cls.get_cache_key(identifier)
        obj = cache.get(cache_key)

        if obj is None:
            try:
                obj = cls.objects.get(**{field_name: identifier})
                cache.set(cache_key, obj, cls.CACHE_TIMEOUT)
            except cls.DoesNotExist:
                return None

        return obj

    def save(self, *args, **kwargs):
        """Override save to invalidate cache"""
        super().save(*args, **kwargs)
        self.invalidate_cache()

    def delete(self, *args, **kwargs):
        """Override delete to invalidate cache"""
        self.invalidate_cache()
        super().delete(*args, **kwargs)

    def invalidate_cache(self):
        """Invalidate cache for this object"""
        cache_key = self.get_cache_key(self.id)
        cache.delete(cache_key)

        # Also invalidate any related caches
        self._invalidate_related_caches()

    def _invalidate_related_caches(self):
        """Override in subclasses to invalidate related caches"""
        pass


class VersionedModel(TimestampedModel):
    """
    Abstract model with version tracking
    Useful for tracking changes over time
    """

    class Meta:
        abstract = True

    version = models.PositiveIntegerField(
        default=1,
        help_text="Version number of this record"
    )
    version_comment = models.TextField(
        blank=True,
        help_text="Comment about this version"
    )

    def save(self, *args, **kwargs):
        """Override save to increment version"""
        if self.pk and hasattr(self, '_original_updated_at'):
            # Only increment version if this is an update to existing object
            if self.updated_at != self._original_updated_at:
                self.version += 1

        super().save(*args, **kwargs)

    @classmethod
    def from_db(cls, db, field_names, values):
        """Store original values for version tracking"""
        instance = super().from_db(db, field_names, values)
        instance._original_updated_at = instance.updated_at
        return instance


class ConfigurationModel(BaseModel):
    """
    Abstract model for configuration/settings
    Provides key-value storage with typing
    """

    class Meta:
        abstract = True

    key = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Configuration key"
    )
    value = models.TextField(help_text="Configuration value")
    value_type = models.CharField(
        max_length=20,
        choices=[
            ('str', 'String'),
            ('int', 'Integer'),
            ('float', 'Float'),
            ('bool', 'Boolean'),
            ('json', 'JSON'),
            ('list', 'List'),
        ],
        default='str',
        help_text="Type of the value"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this configuration"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this configuration is active"
    )

    def get_typed_value(self) -> Any:
        """Get value converted to proper type"""
        if self.value_type == 'int':
            return int(self.value)
        elif self.value_type == 'float':
            return float(self.value)
        elif self.value_type == 'bool':
            return self.value.lower() in ('true', '1', 'yes', 'on')
        elif self.value_type == 'json':
            import json
            return json.loads(self.value)
        elif self.value_type == 'list':
            return [item.strip() for item in self.value.split(',')]
        else:
            return self.value

    def set_typed_value(self, value: Any):
        """Set value with automatic type detection"""
        if isinstance(value, bool):
            self.value = str(value).lower()
            self.value_type = 'bool'
        elif isinstance(value, int):
            self.value = str(value)
            self.value_type = 'int'
        elif isinstance(value, float):
            self.value = str(value)
            self.value_type = 'float'
        elif isinstance(value, (list, tuple)):
            self.value = ','.join(str(item) for item in value)
            self.value_type = 'list'
        elif isinstance(value, dict):
            import json
            self.value = json.dumps(value)
            self.value_type = 'json'
        else:
            self.value = str(value)
            self.value_type = 'str'

    def __str__(self) -> str:
        return f"{self.key}: {self.value}"


# Utility functions for common model operations

def bulk_update_or_create(model_class, objects_data: List[Dict[str, Any]],
                         unique_fields: List[str], batch_size: int = 1000) -> Dict[str, int]:
    """
    Utility function for bulk update or create operations
    Works with any model class
    """
    return model_class.objects.bulk_create_or_update(
        objects_data, unique_fields, batch_size
    )


def clear_model_cache(model_class, pattern: str = None):
    """Clear all cache entries for a model"""
    if pattern:
        cache_pattern = f"{model_class.__name__.lower()}:{pattern}"
    else:
        cache_pattern = f"{model_class.__name__.lower()}:*"

    # This would need Redis directly for pattern matching
    # For now, just clear common keys
    common_keys = [
        f"{model_class.__name__.lower()}:all",
        f"{model_class.__name__.lower()}:count",
        f"{model_class.__name__.lower()}:top",
    ]

    cache.delete_many(common_keys)
    logger.info(f"Cleared cache for {model_class.__name__}")


def get_or_create_cached(model_class, cache_timeout: int = 3600, **kwargs):
    """Get or create object with caching"""
    # Create cache key from kwargs
    key_parts = [f"{k}:{v}" for k, v in sorted(kwargs.items())]
    cache_key = f"{model_class.__name__.lower()}:{'_'.join(key_parts)}"

    obj = cache.get(cache_key)
    if obj is None:
        obj, created = model_class.objects.get_or_create(**kwargs)
        cache.set(cache_key, obj, cache_timeout)
    else:
        created = False

    return obj, created
