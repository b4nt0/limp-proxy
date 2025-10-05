"""
Admin interface API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Dict, Any
import logging

from ..database import get_session
from ..config import Config, get_config

logger = logging.getLogger(__name__)

admin_router = APIRouter()
security = HTTPBasic()

# Templates will be set by the main app
templates = None

def set_templates(templates_instance):
    """Set templates instance for admin router."""
    global templates
    templates = templates_instance


@admin_router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Admin dashboard."""
    if templates is None:
        raise HTTPException(status_code=500, detail="Templates not configured")
    
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "title": "Admin Dashboard"
    })


@admin_router.get("/config", response_class=HTMLResponse)
async def get_configuration_html(request: Request):
    """Get configuration page."""
    if templates is None:
        raise HTTPException(status_code=500, detail="Templates not configured")
    
    return templates.TemplateResponse("admin/config.html", {
        "request": request,
        "title": "Configuration"
    })


@admin_router.get("/config/api")
async def get_configuration(
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_session)
):
    """Get current configuration (API endpoint)."""
    # Verify admin credentials
    if not verify_admin_credentials(credentials):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    config = get_config()
    return {
        "database": config.database.dict(),
        "llm": {
            "provider": config.llm.provider,
            "model": config.llm.model,
            "max_tokens": config.llm.max_tokens,
            "temperature": config.llm.temperature,
            "max_iterations": config.llm.max_iterations
        },
        "external_systems": [system.dict() for system in config.external_systems],
        "im_platforms": [platform.dict() for platform in config.im_platforms],
        "admin": config.admin.dict(),
        "alerts": config.alerts.dict()
    }


@admin_router.put("/config")
async def update_configuration(
    config_data: Dict[str, Any],
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_session)
):
    """Update configuration."""
    # Verify admin credentials
    if not verify_admin_credentials(credentials):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # In a real implementation, this would update the configuration file
    # For now, just return success
    return {
        "status": "success",
        "message": "Configuration updated"
    }


@admin_router.get("/users", response_class=HTMLResponse)
async def list_users_html(request: Request):
    """List users page."""
    if templates is None:
        raise HTTPException(status_code=500, detail="Templates not configured")
    
    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "title": "User Management"
    })


@admin_router.get("/users/api")
async def list_users(
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_session)
):
    """List all users (API endpoint)."""
    # Verify admin credentials
    if not verify_admin_credentials(credentials):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    from ..models.user import User
    
    users = db.query(User).all()
    return {
        "users": [
            {
                "id": user.id,
                "external_id": user.external_id,
                "platform": user.platform,
                "username": user.username,
                "display_name": user.display_name,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat()
            }
            for user in users
        ]
    }


@admin_router.get("/users/{user_id}/tokens")
async def get_user_tokens(
    user_id: int,
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_session)
):
    """Get OAuth2 tokens for user."""
    # Verify admin credentials
    if not verify_admin_credentials(credentials):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    from ..models.auth import AuthToken
    
    tokens = db.query(AuthToken).filter(AuthToken.user_id == user_id).all()
    return {
        "tokens": [
            {
                "id": token.id,
                "system_name": token.system_name,
                "token_type": token.token_type,
                "expires_at": token.expires_at.isoformat() if token.expires_at else None,
                "scope": token.scope,
                "created_at": token.created_at.isoformat()
            }
            for token in tokens
        ]
    }


@admin_router.delete("/users/{user_id}/tokens/{token_id}")
async def revoke_user_token(
    user_id: int,
    token_id: int,
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_session)
):
    """Revoke OAuth2 token for user."""
    # Verify admin credentials
    if not verify_admin_credentials(credentials):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    from ..models.auth import AuthToken
    
    token = db.query(AuthToken).filter(
        AuthToken.id == token_id,
        AuthToken.user_id == user_id
    ).first()
    
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    db.delete(token)
    db.commit()
    
    return {"status": "success", "message": "Token revoked"}


def verify_admin_credentials(credentials: HTTPBasicCredentials) -> bool:
    """Verify admin credentials."""
    config = get_config()
    
    if not config.admin.enabled:
        return False
    
    if not config.admin.username or not config.admin.password:
        return False
    
    return (
        credentials.username == config.admin.username and
        credentials.password == config.admin.password
    )

