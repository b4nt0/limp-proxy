"""
Main FastAPI application for LIMP system.
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import logging

from ..database import get_session, init_database, create_engine
from ..config import Config, set_config
from .im import im_router
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
    app.include_router(im_router, prefix="/api/im", tags=["instant-messaging"])
    app.include_router(oauth2_router, prefix="/api/oauth2", tags=["oauth2"])
    
    if config.admin.enabled:
        app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
    
    @app.get("/")
    async def root():
        return {"message": "LLM IM Proxy (LIMP) is running"}
    
    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}
    
    return app


def get_config() -> Config:
    """Get application configuration."""
    return config
