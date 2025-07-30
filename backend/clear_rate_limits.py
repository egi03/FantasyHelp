# backend/clear_rate_limits.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fantasyhelp.settings')
django.setup()

from django.core.cache import cache

# Clear all rate limit keys
print("Clearing rate limit cache...")
cache.clear()
print("Rate limit cache cleared!")