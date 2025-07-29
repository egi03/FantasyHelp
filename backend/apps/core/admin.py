# Create apps/core/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from typing import Any, List


class BaseModelAdmin(admin.ModelAdmin):
    """Enhanced base model admin with common functionality"""

    list_per_page = 25
    list_max_show_all = 200
    date_hierarchy = 'created_at'

    # Common fields that most models have
    readonly_fields = ['id', 'created_at', 'updated_at']

    def get_readonly_fields(self, request, obj=None):
        """Return readonly fields, handling cases where they might not exist"""
        readonly_fields = []

        # Check if model has these fields before adding them
        model_fields = [f.name for f in self.model._meta.fields]

        for field in ['id', 'created_at', 'updated_at']:
            if field in model_fields:
                readonly_fields.append(field)

        return readonly_fields

    def get_list_display(self, request):
        """Dynamically set list_display based on available fields"""
        if hasattr(self, 'list_display') and self.list_display:
            return self.list_display

        # Default list display for models
        model_fields = [f.name for f in self.model._meta.fields]
        display_fields = []

        # Add common fields if they exist
        if '__str__' in dir(self.model):
            display_fields.append('__str__')

        for field in ['name', 'title', 'created_at', 'updated_at']:
            if field in model_fields and field not in display_fields:
                display_fields.append(field)

        return display_fields[:5]  # Limit to 5 fields

    def created_at_display(self, obj):
        """Display created_at in a friendly format"""
        if hasattr(obj, 'created_at') and obj.created_at:
            return obj.created_at.strftime('%Y-%m-%d %H:%M')
        return '-'
    created_at_display.short_description = 'Created'
    created_at_display.admin_order_field = 'created_at'

    def updated_at_display(self, obj):
        """Display updated_at in a friendly format"""
        if hasattr(obj, 'updated_at') and obj.updated_at:
            return obj.updated_at.strftime('%Y-%m-%d %H:%M')
        return '-'
    updated_at_display.short_description = 'Updated'
    updated_at_display.admin_order_field = 'updated_at'


class ReadOnlyAdminMixin:
    """Mixin to make admin interface read-only"""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
