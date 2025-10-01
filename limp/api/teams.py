"""
Microsoft Teams-specific API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Dict, Any
import logging

from ..database import get_session
from ..services.im import IMServiceFactory
from ..config import get_config
from .im import handle_user_message

logger = logging.getLogger(__name__)

teams_router = APIRouter()


@teams_router.post("/webhook")
async def handle_teams_webhook(request: Request, db: Session = Depends(get_session)):
    """Handle Microsoft Teams webhook requests."""
    try:
        # Get request data
        request_data = await request.json()
        
        # Create Teams service
        teams_config = get_config().get_im_platform_by_key("teams")
        teams_service = IMServiceFactory.create_service("teams", teams_config.model_dump())
        
        # Verify request
        if not teams_service.verify_request(request_data):
            raise HTTPException(status_code=401, detail="Invalid request signature")
        
        # Parse message
        message_data = teams_service.parse_message(request_data)
        
        if message_data["type"] == "message":
            return await handle_user_message(
                message_data, teams_service, db, "teams"
            )
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Teams webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
