"""
Slack-specific API endpoints.

This module provides endpoints for Slack integration including:
- OAuth2 installation callback at /install
- Webhook handling for Slack events at /webhook

The /install endpoint handles the OAuth2 flow completion and stores
installation data in the slack_organizations table.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Query, Form
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
import logging
import httpx
import json
import os

from ..database import get_session
from ..services.im import IMServiceFactory
from ..config import get_config
from ..models.slack_organization import SlackOrganization
from .im import handle_user_message, get_bot_url

logger = logging.getLogger(__name__)

# Slack permissions required by the bot
SLACK_BOT_PERMISSIONS = [
    "app_mentions:read",
    "chat:write", 
    "im:history",
    "im:write",
    "im:read",
    "reactions:write",
    "reactions:read"
]

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
        await send_installation_confirmation(token_data, slack_config, config)
        
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


async def send_installation_confirmation(token_data: Dict[str, Any], slack_config, config) -> None:
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
        
        # Get bot name from configuration
        bot_name = config.bot.name
        
        # Send DM to the installing user
        message = {
            "channel": authed_user_id,
            "text": f"🎉 Thank you for installing the {bot_name} bot! The installation was successful and the bot is now ready to help you with your tasks.",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"🎉 *Installation Successful!*\n\nThank you for installing the {bot_name} bot! The bot is now ready to help you with your tasks."
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
        # Log request headers for debugging
        logger.info(f"Received Slack webhook request with headers: {dict(request.headers)}")
        
        # Log request method and URL for debugging
        logger.info(f"Request method: {request.method}, URL: {request.url}")
        
        # Get request data with timeout and error handling
        try:
            # Set a reasonable timeout for reading the request body
            request_data = await request.json()
            logger.info(f"Successfully parsed Slack request JSON: {request_data}")
        except Exception as json_error:
            logger.warning(f"Failed to parse JSON from Slack request: {json_error}")
            # Check if it's a client disconnect error
            if "ClientDisconnect" in str(type(json_error)):
                logger.warning("Client disconnected while reading request body")
                return {"status": "client_disconnected"}
            
            # Try to get raw body for debugging
            try:
                body = await request.body()
                logger.warning(f"Raw request body: {body}")
            except Exception as body_error:
                logger.warning(f"Failed to read request body: {body_error}")
                if "ClientDisconnect" in str(type(body_error)):
                    logger.warning("Client disconnected while reading raw body")
                    return {"status": "client_disconnected"}
            
            raise HTTPException(status_code=400, detail="Invalid JSON in request body")
        
        # Validate request data
        if not request_data:
            logger.warning("Empty request data received")
            return {"status": "empty_request"}
        
        # EARLY SCREENING: Handle URL verification challenges immediately
        if request_data.get("type") == "url_verification":
            logger.info("Handling Slack challenge request (early filtering)")
            return {"challenge": request_data.get("challenge")}
        
        # Load config for early filtering (we need app_id for bot message filtering)
        try:
            config = get_config()
            slack_config = config.get_im_platform_by_key("slack")
            logger.debug(f"Config loaded: {config}")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            raise HTTPException(status_code=500, detail="Configuration error")
        
        # EARLY SCREENING: Filter out messages from our own bot
        if request_data.get("type") == "event_callback":
            event = request_data.get("event", {})
            
            # Ignore messages from our own bot to prevent infinite loops
            if slack_config.app_id and event.get("app_id") == slack_config.app_id:
                logger.info(f"Ignoring message from own app_id: {slack_config.app_id} (early filtering)")
                return {"status": "ignored"}
            
            # EARLY SCREENING: Filter out bot messages and other inactionable events
            if event.get("type") in ["message", "app_mention"] and event.get("bot_id"):
                logger.info(f"Ignoring message from bot (bot_id: {event.get('bot_id')}) (early filtering)")
                return {"status": "ignored"}
            
            # EARLY SCREENING: Filter out non-message events that we don't handle
            if event.get("type") not in ["message", "app_mention"]:
                logger.info(f"Ignoring non-message event type: {event.get('type')} (early filtering)")
                return {"status": "ignored"}
        
        # EARLY SCREENING: Filter out non-event-callback requests that aren't challenges
        if request_data.get("type") not in ["url_verification", "event_callback"]:
            logger.info(f"Ignoring non-event-callback request type: {request_data.get('type')} (early filtering)")
            return {"status": "ignored"}
        
        try:
            # Get bot token from database for the organization
            # For now, we'll use the first available organization
            # In a real implementation, you'd need to determine which organization
            # the message is coming from based on the request data
            organization = db.query(SlackOrganization).first()
            bot_token = organization.access_token if organization else None
            
            if not bot_token:
                logger.error("No bot token found for Slack organization")
                raise HTTPException(status_code=500, detail="No bot token configured")
            
            slack_service = IMServiceFactory.create_service("slack", {
                **slack_config.model_dump(),
                "bot_token": bot_token
            })
            logger.info(f"Slack service created successfully")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating Slack service: {e}")
            raise HTTPException(status_code=500, detail=f"Service creation error: {str(e)}")
        
        # Verify request
        if not slack_service.verify_request(request_data):
            raise HTTPException(status_code=401, detail="Invalid request signature")
        
        # Parse message
        try:
            message_data = slack_service.parse_message(request_data)
            logger.info(f"Parsed message: {message_data}")
        except Exception as parse_error:
            logger.error(f"Failed to parse message: {parse_error}")
            raise HTTPException(status_code=400, detail="Failed to parse message data")
        
        if message_data["type"] == "message":
            logger.info("Processing user message")
            return await handle_user_message(
                message_data, slack_service, db, "slack", request
            )
        
        return {"status": "ok"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Slack webhook error: {e}", exc_info=True)
        # Check if it's a client disconnect error
        if "ClientDisconnect" in str(type(e)):
            logger.warning("Client disconnected during request processing")
            # Return 200 to prevent Slack from retrying
            return {"status": "client_disconnected"}
        else:
            raise HTTPException(status_code=500, detail="Internal server error")


@slack_router.post("/interactivity")
async def handle_slack_interactivity(
    request: Request,
    db: Session = Depends(get_session)
):
    """
    Handle Slack interactivity (button clicks, etc.).
    
    This endpoint handles button interactions from Slack, particularly
    authorization buttons that need to redirect users to OAuth2 flows.
    
    Args:
        request: FastAPI request object containing the interaction payload
        db: Database session
        
    Returns:
        RedirectResponse to the OAuth2 authorization URL or error response
    """
    try:
        # Parse the form data from Slack
        form_data = await request.form()
        payload_str = form_data.get("payload")
        
        if not payload_str:
            logger.error("No payload in Slack interactivity request")
            raise HTTPException(status_code=400, detail="No payload provided")
        
        # Parse the JSON payload
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in Slack interactivity payload: {e}")
            raise HTTPException(status_code=400, detail="Invalid payload format")
        
        # Check if this is an authorization button click
        if payload.get("type") == "block_actions":
            actions = payload.get("actions", [])
            for action in actions:
                if action.get("action_id") == "authorization_button":
                    auth_url = action.get("value")
                    if auth_url:
                        logger.info(f"Authorization button clicked, auth URL: {auth_url}")
                        
                        # Get the response_url from the payload to send a message back to Slack
                        response_url = payload.get("response_url")
                        if response_url:
                            # Send a message with a clickable link back to Slack
                            import requests
                            try:
                                response_payload = {
                                    "text": f"🔐 **Authorization Required**\n\nClick the link below to authorize:\n\n<{auth_url}|🔐 Authorize Access>",
                                    "replace_original": True
                                }
                                
                                requests.post(response_url, json=response_payload, timeout=5)
                                logger.info("Sent authorization link back to Slack")
                            except Exception as e:
                                logger.error(f"Failed to send response to Slack: {e}")
                        
                        # Return a simple response to Slack
                        return {
                            "text": f"🔐 **Authorization Required**\n\nClick the link below to authorize:\n\n<{auth_url}|🔐 Authorize Access>",
                            "replace_original": True
                        }
                    else:
                        logger.error("No auth URL in authorization button")
                        raise HTTPException(status_code=400, detail="No authorization URL found")
        
        # If not an authorization button, return a simple response
        logger.info("Non-authorization interactivity received")
        return {"status": "ok", "message": "Interaction received"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Slack interactivity error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@slack_router.get("/manifest")
async def get_slack_manifest(request: Request):
    """
    Serve the Slack manifest YAML file.
    
    This endpoint serves the Slack app manifest with the bot_url and bot_name
    dynamically substituted from the current request context using Jinja2 templating.
    
    Args:
        request: FastAPI request object to determine the bot URL
        
    Returns:
        YAML content of the Slack manifest
    """
    try:
        # Get bot URL, name, and description using the global function
        config = get_config()
        bot_url = get_bot_url(config, request)
        bot_name = config.bot.name if config.bot.name else "LIMP"
        bot_description = config.bot.description
        
        # Create templates instance (same as in main.py)
        from fastapi.templating import Jinja2Templates
        templates = Jinja2Templates(directory="templates")
        
        # Render the manifest template
        manifest_content = templates.get_template("slack/manifest.yaml").render(
            bot_url=bot_url,
            bot_name=bot_name,
            bot_description=bot_description,
            bot_permissions=SLACK_BOT_PERMISSIONS
        )
        
        # Return the manifest as YAML
        return Response(
            content=manifest_content,
            media_type="application/x-yaml",
            headers={
                "Content-Disposition": "attachment; filename=slack-manifest.yaml"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving Slack manifest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
