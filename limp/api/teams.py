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
    """Handle Microsoft Teams webhook requests using ActivityHandler pattern."""
    try:
        # Get request data
        request_data = await request.json()
        logger.info(f"Received Teams webhook: {request_data}")
        
        # Create Teams service
        teams_config = get_config().get_im_platform_by_key("teams")
        teams_service = IMServiceFactory.create_service("teams", teams_config.model_dump())
        
        # Verify request
        if not teams_service.verify_request(request_data):
            raise HTTPException(status_code=401, detail="Invalid request signature")
        
        # Get authorization header
        auth_header = request.headers.get("Authorization", "")
        
        # Process activity using ActivityHandler pattern
        success = await teams_service.process_activity(request_data, auth_header)
        
        if success:
            return {"status": "ok"}
        else:
            raise HTTPException(status_code=500, detail="Failed to process activity")
        
    except Exception as e:
        logger.error(f"Teams webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


