"""
Slack-specific API endpoints.

This module provides endpoints for Slack integration including:
- OAuth2 installation callback at /install
- Webhook handling for Slack events at /webhook

The /install endpoint handles the OAuth2 flow completion and stores
installation data in the slack_organizations table.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
import logging
import httpx
import json

from ..database import get_session
from ..services.im import IMServiceFactory
from ..config import get_config
from ..models.slack_organization import SlackOrganization
from .im import handle_user_message

logger = logging.getLogger(__name__)

slack_router = APIRouter()


@slack_router.get("/install")
async def handle_slack_install(
    code: str = Query(..., description="Authorization code from Slack"),
    state: Optional[str] = Query(None, description="State parameter for security"),
    db: Session = Depends(get_session)
):
    """
    Handle Slack OAuth2 installation callback.
    
    This endpoint is called by Slack after a user completes the OAuth2 flow.
    It exchanges the authorization code for an access token and stores the
    installation data in the database.
    
    Args:
        code: Authorization code from Slack OAuth2 flow
        state: Optional state parameter for security
        db: Database session
        
    Returns:
        JSON response with installation status and organization details
    """
    try:
        logger.info(f"Received Slack installation callback with code: {code[:10]}...")
        
        # Get Slack configuration
        config = get_config()
        slack_config = config.get_im_platform_by_key("slack")
        
        # Exchange authorization code for access token
        token_data = await exchange_code_for_token(
            code=code,
            client_id=slack_config.client_id,
            client_secret=slack_config.client_secret
        )
        
        if not token_data.get("ok"):
            logger.error(f"Token exchange failed: {token_data}")
            raise HTTPException(status_code=400, detail="Failed to exchange code for token")
        
        # Store installation data in database
        organization = await store_slack_installation(token_data, db)
        
        # Send confirmation DM to installing user
        await send_installation_confirmation(token_data, slack_config)
        
        logger.info(f"Successfully installed Slack app for organization: {organization.organization_id}")
        
        # Redirect to success page
        from fastapi.responses import RedirectResponse
        success_url = f"/install-success?system=slack&organization={organization.team_name or organization.organization_id}"
        return RedirectResponse(url=success_url, status_code=302)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Slack installation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


async def exchange_code_for_token(code: str, client_id: str, client_secret: str) -> Dict[str, Any]:
    """Exchange authorization code for access token."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret
                }
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"HTTP error during token exchange: {e}")
        raise HTTPException(status_code=500, detail="Failed to exchange code for token")
    except Exception as e:
        logger.error(f"Error during token exchange: {e}")
        raise HTTPException(status_code=500, detail="Token exchange failed")


async def store_slack_installation(token_data: Dict[str, Any], db: Session) -> SlackOrganization:
    """Store Slack installation data in database."""
    try:
        logger.debug(f"Storing Slack installation: {token_data}")

        # Extract data from token response
        access_token = token_data.get("access_token")
        token_type = token_data.get("token_type", "bot")
        scope = token_data.get("scope")
        bot_user_id = token_data.get("bot_user_id")
        app_id = token_data.get("app_id")
        
        # Team information (can be empty)
        team = token_data.get("team")
        team_id = team.get("id") if team else None
        team_name = team.get("name") if team else None
        
        # Enterprise information (can be empty)
        enterprise = token_data.get("enterprise")
        enterprise_id = enterprise.get("id") if enterprise else None
        enterprise_name = enterprise.get("name") if enterprise else None
        
        # Authed user information (can be empty)
        authed_user = token_data.get("authed_user")
        authed_user_id = authed_user.get("id") if authed_user else None
        authed_user_access_token = authed_user.get("access_token") if authed_user else None
        authed_user_token_type = authed_user.get("token_type") if authed_user else None
        authed_user_scope = authed_user.get("scope") if authed_user else None
        
        # Use team_id as organization_id, fallback to app_id if no team
        organization_id = team_id or token_data.get("app_id")
        
        if not organization_id:
            raise ValueError("No organization identifier found in token data (neither team_id nor app_id)")
        
        # Check if organization already exists
        existing_org = db.query(SlackOrganization).filter(
            SlackOrganization.organization_id == organization_id
        ).first()
        
        if existing_org:
            # Update existing organization
            existing_org.access_token = access_token
            existing_org.token_type = token_type
            existing_org.scope = scope
            existing_org.bot_user_id = bot_user_id
            existing_org.app_id = app_id
            existing_org.team_id = team_id
            existing_org.team_name = team_name
            existing_org.enterprise_id = enterprise_id
            existing_org.enterprise_name = enterprise_name
            existing_org.authed_user_id = authed_user_id
            existing_org.authed_user_access_token = authed_user_access_token
            existing_org.authed_user_token_type = authed_user_token_type
            existing_org.authed_user_scope = authed_user_scope
            db.commit()
            return existing_org
        else:
            # Create new organization
            organization = SlackOrganization(
                organization_id=organization_id,
                access_token=access_token,
                token_type=token_type,
                scope=scope,
                bot_user_id=bot_user_id,
                app_id=app_id,
                team_id=team_id,
                team_name=team_name,
                enterprise_id=enterprise_id,
                enterprise_name=enterprise_name,
                authed_user_id=authed_user_id,
                authed_user_access_token=authed_user_access_token,
                authed_user_token_type=authed_user_token_type,
                authed_user_scope=authed_user_scope
            )
            db.add(organization)
            db.commit()
            db.refresh(organization)
            return organization
            
    except Exception as e:
        logger.error(f"Error storing Slack installation: {e}")
        logger.error(f"Slack token data: {token_data}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to store installation data")


async def send_installation_confirmation(token_data: Dict[str, Any], slack_config) -> None:
    """Send confirmation DM to the installing user."""
    try:
        # Check if authed_user data exists and is not empty
        authed_user = token_data.get("authed_user")
        if not authed_user:
            logger.info("No authed user data available for confirmation DM - skipping")
            return
            
        authed_user_id = authed_user.get("id")
        authed_user_access_token = authed_user.get("access_token")
        
        if not authed_user_id or not authed_user_access_token:
            logger.info("Incomplete authed user data (missing ID or access token) - skipping confirmation DM")
            return
        
        # Send DM to the installing user
        message = {
            "channel": authed_user_id,
            "text": "🎉 Thank you for installing the LIMP bot! The installation was successful and the bot is now ready to help you with your tasks.",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "🎉 *Installation Successful!*\n\nThank you for installing the LIMP bot! The bot is now ready to help you with your tasks."
                    }
                }
            ]
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {authed_user_access_token}",
                    "Content-Type": "application/json"
                },
                json=message
            )
            
            if response.status_code == 200:
                logger.info(f"Sent confirmation DM to user {authed_user_id}")
            else:
                logger.warning(f"Failed to send confirmation DM: {response.status_code} - {response.text}")
                
    except Exception as e:
        logger.error(f"Error sending confirmation DM: {e}")


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
            
            # Get bot token from database for the organization
            # For now, we'll use the first available organization
            # In a real implementation, you'd need to determine which organization
            # the message is coming from based on the request data
            organization = db.query(SlackOrganization).first()
            bot_token = organization.access_token if organization else None
            
            slack_service = IMServiceFactory.create_service("slack", {
                **slack_config.model_dump(),
                "bot_token": bot_token
            })
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
        
        if message_data["type"] == "ignored":
            logger.info("Message ignored (from own bot)")
            return {"status": "ignored"}
        
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
