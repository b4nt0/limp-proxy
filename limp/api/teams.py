"""
Microsoft Teams-specific API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Dict, Any
import logging
import asyncio

from ..database import get_session
from ..services.im import IMServiceFactory
from ..config import get_config
from .im import handle_user_message

logger = logging.getLogger(__name__)

teams_router = APIRouter()


async def process_teams_activity_background(request_data: Dict[str, Any], auth_header: str, db: Session, request: Request):
    """Background task to process Teams activity asynchronously."""
    try:
        logger.info(f"Processing Teams activity in background: {request_data}")
        
        # Create Teams service
        teams_config = get_config().get_im_platform_by_key("teams")
        teams_service = IMServiceFactory.create_service("teams", teams_config.model_dump())
        
        # Process activity using the full message processing pipeline (same as Slack)
        success = await teams_service.process_activity(request_data, auth_header, db, request)
        
        if success:
            logger.info("Successfully processed Teams activity in background")
        else:
            logger.error("Failed to process Teams activity in background")
        
    except Exception as e:
        logger.error(f"Background Teams activity processing error: {e}")


@teams_router.post("/webhook")
async def handle_teams_webhook(request: Request, db: Session = Depends(get_session)):
    """Handle Microsoft Teams webhook requests using ActivityHandler pattern."""
    try:
        # Get request data
        request_data = await request.json()
        logger.info(f"Received Teams webhook: {request_data}")
        
        # Create Teams service for verification only
        teams_config = get_config().get_im_platform_by_key("teams")
        teams_service = IMServiceFactory.create_service("teams", teams_config.model_dump())
        
        # Verify request
        if not teams_service.verify_request(request_data):
            raise HTTPException(status_code=401, detail="Invalid request signature")
        
        # Get authorization header
        auth_header = request.headers.get("Authorization", "")
        
        # Queue the activity processing as a background task (matching Slack pattern)
        asyncio.create_task(process_teams_activity_background(request_data, auth_header, db, request))
        
        # Respond immediately to Teams
        logger.info("Teams webhook queued for background processing, responding immediately")
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Teams webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


