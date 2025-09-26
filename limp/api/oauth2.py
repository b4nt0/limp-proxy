"""
OAuth2 API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Dict, Any
import logging

from ..database import get_session
from ..services.oauth2 import OAuth2Service
from ..config import Config, get_config

logger = logging.getLogger(__name__)

oauth2_router = APIRouter()


@oauth2_router.get("/authorize/{system_name}")
async def start_authorization(
    system_name: str,
    user_id: int,
    db: Session = Depends(get_session)
):
    """Start OAuth2 authorization flow."""
    try:
        # Get system configuration
        system_config = get_system_config(system_name)
        if not system_config:
            raise HTTPException(status_code=404, detail="System not found")
        
        # Create OAuth2 service
        oauth2_service = OAuth2Service(db)
        
        # Generate authorization URL
        auth_url = oauth2_service.generate_auth_url(user_id, system_config)
        
        return {
            "authorization_url": auth_url,
            "system_name": system_name
        }
        
    except Exception as e:
        logger.error(f"Authorization start error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@oauth2_router.get("/callback/{system_name}")
async def handle_callback(
    system_name: str,
    code: str,
    state: str,
    db: Session = Depends(get_session)
):
    """Handle OAuth2 callback."""
    try:
        # Create OAuth2 service
        oauth2_service = OAuth2Service(db)
        
        # Handle callback
        auth_token = oauth2_service.handle_callback(code, state)
        
        if not auth_token:
            raise HTTPException(status_code=400, detail="Authorization failed")
        
        return {
            "status": "success",
            "message": "Authorization completed successfully",
            "system_name": system_name
        }
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"Callback handling error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@oauth2_router.get("/status/{user_id}/{system_name}")
async def get_authorization_status(
    user_id: int,
    system_name: str,
    db: Session = Depends(get_session)
):
    """Get authorization status for user and system."""
    try:
        # Create OAuth2 service
        oauth2_service = OAuth2Service(db)
        
        # Check for valid token
        auth_token = oauth2_service.get_valid_token(user_id, system_name)
        
        if auth_token:
            return {
                "authorized": True,
                "expires_at": auth_token.expires_at.isoformat() if auth_token.expires_at else None
            }
        else:
            return {
                "authorized": False
            }
        
    except Exception as e:
        logger.error(f"Status check error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def get_system_config(system_name: str):
    """Get system configuration by name."""
    config = get_config()
    for system in config.external_systems:
        if system.name == system_name:
            return system
    return None

