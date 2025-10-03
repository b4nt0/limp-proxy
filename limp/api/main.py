"""
Main FastAPI application for LIMP system.
"""

from fastapi import FastAPI, Depends, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import logging

from ..database import get_session, init_database, create_engine
from ..config import Config, set_config
from .slack import slack_router
from .teams import teams_router
from .oauth2 import oauth2_router
from .admin import admin_router

logger = logging.getLogger(__name__)

# Global config - will be set during startup
config: Config = None


def create_app(app_config: Config) -> FastAPI:
    """Create FastAPI application."""
    global config
    config = app_config
    set_config(app_config)
    
    app = FastAPI(
        title="LLM IM Proxy (LIMP)",
        description="A system to expose LLM-powered tools through instant messaging platforms",
        version="0.1.0"
    )
    
    # Configure Jinja2 templates
    templates = Jinja2Templates(directory="templates")
    app.state.templates = templates
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Initialize database
    engine = create_engine(config.database)
    init_database(engine)
    
    # Include routers
    app.include_router(slack_router, prefix="/api/slack", tags=["slack"])
    app.include_router(teams_router, prefix="/api/teams", tags=["teams"])
    app.include_router(oauth2_router, prefix="/api/oauth2", tags=["oauth2"])
    
    if config.admin.enabled:
        # Set templates for admin router
        from .admin import set_templates
        set_templates(templates)
        app.include_router(admin_router, prefix="/admin", tags=["admin"])
    
    @app.get("/")
    async def root(request: Request):
        """Root page with Slack installation button."""
        config = get_config()
        
        # Use consistent bot URL logic
        from .im import get_bot_url
        bot_url = get_bot_url(config, request)
        
        # Get Slack configuration
        try:
            slack_config = config.get_im_platform_by_key("slack")
            slack_client_id = slack_config.client_id
        except ValueError:
            # Slack not configured
            slack_client_id = None
        
        return templates.TemplateResponse("install.html", {
            "request": request,
            "title": config.bot.name if config.bot.name else "LIMP - LLM IM Proxy",
            "bot_url": bot_url,
            "slack_client_id": slack_client_id
        })
    
    @app.get("/install-success", response_class=HTMLResponse)
    async def install_success(
        request: Request,
        system: str = Query(..., description="Platform system (slack or teams)"),
        organization: str = Query(None, description="Organization name")
    ):
        """Installation success page."""
        return templates.TemplateResponse("install-success.html", {
            "request": request,
            "title": "Installation Successful - LIMP",
            "system": system,
            "organization_name": organization
        })
    
    @app.get("/api/ping")
    async def ping():
        return {"message": "LLM IM Proxy (LIMP) is running"}
    
    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}
    
    @app.get("/status", response_class=HTMLResponse)
    async def status_page(request: Request):
        """System status page."""
        return templates.TemplateResponse("status.html", {
            "request": request,
            "title": "System Status"
        })
    
    return app


def get_config() -> Config:
    """Get application configuration."""
    return config
