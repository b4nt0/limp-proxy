"""
Instant messaging API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Dict, Any
import logging

from ..database import get_session
from ..services.oauth2 import OAuth2Service
from ..services.llm import LLMService
from ..services.tools import ToolsService
from ..services.im import IMServiceFactory
from ..config import Config, get_config
from ..models.user import User

logger = logging.getLogger(__name__)

im_router = APIRouter()


@im_router.post("/slack")
async def handle_slack(request: Request, db: Session = Depends(get_session)):
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
                message_data, slack_service, db
            )
        
        return {"status": "ok"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Slack webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@im_router.post("/teams")
async def handle_teams(request: Request, db: Session = Depends(get_session)):
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
                message_data, teams_service, db
            )
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Teams webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def handle_user_message(
    message_data: Dict[str, Any],
    im_service: Any,
    db: Session
) -> Dict[str, Any]:
    """Handle user message and generate response."""
    try:
        # Get or create user
        user = get_or_create_user(db, message_data["user_id"], "slack")  # Platform should be determined from context
        
        # Get conversation history
        conversation_history = get_conversation_history(db, user.id)
        
        # Create services
        oauth2_service = OAuth2Service(db)
        llm_service = LLMService(get_config().llm)
        tools_service = ToolsService()
        
        # Process message through LLM workflow
        response = await process_llm_workflow(
            message_data["text"],
            conversation_history,
            user,
            oauth2_service,
            llm_service,
            tools_service,
            db
        )
        
        # Send response
        im_service.send_message(
            message_data["channel"],
            response["content"],
            response.get("metadata")
        )
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Message handling error: {e}")
        return {"status": "error", "message": "Failed to process message"}


async def process_llm_workflow(
    user_message: str,
    conversation_history: list,
    user: User,
    oauth2_service: OAuth2Service,
    llm_service: LLMService,
    tools_service: ToolsService,
    db: Session
) -> Dict[str, Any]:
    """Process message through LLM workflow."""
    try:
        # Get available tools
        system_configs = [system.model_dump() for system in get_config().external_systems]
        tools = tools_service.get_available_tools(system_configs)
        
        # Format messages
        messages = llm_service.format_messages_with_context(
            user_message,
            conversation_history
        )
        
        # Send to LLM
        response = llm_service.chat_completion(messages, tools)
        
        # Check for tool calls
        if llm_service.is_tool_call_response(response):
            tool_calls = llm_service.extract_tool_calls(response)
            
            # Process tool calls
            for tool_call in tool_calls:
                # Check authorization
                system_name = get_system_name_for_tool(tool_call["function"]["name"], system_configs)
                auth_token = oauth2_service.get_valid_token(user.id, system_name)
                
                if not auth_token:
                    # Return authorization URL
                    system_config = get_system_config(system_name, system_configs)
                    auth_url = oauth2_service.generate_auth_url(user.id, system_config)
                    return {
                        "content": f"Please authorize access to {system_name}: {auth_url}",
                        "metadata": {"auth_url": auth_url}
                    }
                
                # Execute tool call
                tool_result = tools_service.execute_tool_call(
                    tool_call,
                    get_system_config(system_name, system_configs),
                    auth_token.access_token
                )
                
                # Add tool result to conversation
                messages.append({
                    "role": "tool",
                    "content": str(tool_result),
                    "tool_call_id": tool_call["id"]
                })
            
            # Get final response
            final_response = llm_service.chat_completion(messages)
            return {"content": final_response["content"]}
        
        return {"content": response["content"]}
        
    except Exception as e:
        logger.error(f"LLM workflow error: {e}")
        return {
            "content": llm_service.get_error_message(e),
            "metadata": {"error": True}
        }


def get_or_create_user(db: Session, external_id: str, platform: str) -> User:
    """Get or create user."""
    user = db.query(User).filter(
        User.external_id == external_id,
        User.platform == platform
    ).first()
    
    if not user:
        user = User(external_id=external_id, platform=platform)
        db.add(user)
        db.commit()
        db.refresh(user)
    
    return user


def get_conversation_history(db: Session, user_id: int) -> list:
    """Get conversation history for user."""
    # Implementation would get recent messages from database
    # For now, return empty list
    return []


def get_system_name_for_tool(tool_name: str, system_configs: list) -> str:
    """Get system name for tool."""
    # Implementation would map tool to system
    # For now, return first system
    return system_configs[0]["name"] if system_configs else "default"


def get_system_config(system_name: str, system_configs: list) -> dict:
    """Get system configuration by name."""
    for config in system_configs:
        if config["name"] == system_name:
            return config
    raise ValueError(f"System {system_name} not found")