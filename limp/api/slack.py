"""
Slack-specific API endpoints.
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

slack_router = APIRouter()


@slack_router.post("/webhook")
async def handle_slack_webhook(request: Request, db: Session = Depends(get_session)):
    """Handle Slack webhook requests."""
    try:
        # Get request data
        request_data = await request.json()
        logger.info(f"Received Slack request: {request_data}")
        
        # Create Slack service
        try:
            config = get_config()
            logger.info(f"Config loaded: {config}")
            slack_config = config.get_im_platform_by_key("slack")
            logger.info(f"Slack config: {slack_config}")
            slack_service = IMServiceFactory.create_service("slack", slack_config.model_dump())
            logger.info(f"Slack service created: {slack_service}")
        except Exception as e:
            logger.error(f"Error creating Slack service: {e}")
            raise HTTPException(status_code=500, detail=f"Service creation error: {str(e)}")
        
        # Verify request
        if not slack_service.verify_request(request_data):
            raise HTTPException(status_code=401, detail="Invalid request signature")
        
        # Parse message
        message_data = slack_service.parse_message(request_data)
        logger.info(f"Parsed message: {message_data}")
        
        if message_data["type"] == "challenge":
            return {"challenge": message_data["challenge"]}
        
        if message_data["type"] == "message":
            return await handle_user_message(
                message_data, slack_service, db, "slack"
            )
        
        return {"status": "ok"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Slack webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
