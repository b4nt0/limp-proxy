"""
API endpoints for LIMP system.
"""

from .main import create_app
from .im import im_router
from .oauth2 import oauth2_router
from .admin import admin_router

__all__ = ["create_app", "im_router", "oauth2_router", "admin_router"]
