import uuid
from django.db import models
from django.utils import timezone
from django.core.cache import cache
from django.db.models import QuerySet, Count, Sum, Avg, Max, Min  # Added missing imports
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
                # Get all fields except unique fields for bulk_update
                update_fields = []
                if batch:
                    update_fields = [field for field in batch[0].keys() if field not in unique_fields]

                if update_fields and to_update:
                    self.bulk_update(to_update, update_fields, batch_size=batch_size)
                    updated_count += len(to_update)

        logger.info(f"Bulk operation completed: {created_count} created, {updated_count} updated")
        return {'created': created_count, 'updated': updated_count}


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
