"""
Common instant messaging functionality.
"""

from sqlalchemy.orm import Session
from typing import Dict, Any
import logging

from ..database import get_session
from ..services.oauth2 import OAuth2Service
from ..services.llm import LLMService
from ..services.tools import ToolsService
from ..config import get_config
from ..models.user import User

logger = logging.getLogger(__name__)


async def handle_user_message(
    message_data: Dict[str, Any],
    im_service: Any,
    db: Session,
    platform: str,
    request: Any = None
) -> Dict[str, Any]:
    """Handle user message and generate response."""
    try:
        # Get or create user
        user = get_or_create_user(db, message_data["user_id"], platform)
        
        # Determine bot URL early
        config = get_config()
        bot_url = get_bot_url(config, request)
        
        # Check primary system authentication
        primary_system = config.get_primary_system()
        
        if primary_system:
            oauth2_service = OAuth2Service(db)
            token = oauth2_service.get_valid_token(user.id, primary_system.name)
            
            # If no token or token is invalid, send authorization prompt
            if not token or not oauth2_service.validate_token(token, primary_system):
                auth_url = oauth2_service.generate_auth_url(user.id, primary_system, bot_url)
                
                # Send DM with authorization prompt and button
                authorization_prompt = f"🔐 **Authorization Required**\n\nTo use this bot, you need to authorize access to {primary_system.name}.\n\nClick the button below to authorize:"
                
                # Create button metadata for the IM service
                button_metadata = {
                    "blocks": im_service.create_authorization_button(
                        auth_url, 
                        f"Authorize {primary_system.name}",
                        f"Click to authorize access to {primary_system.name}",
                        request
                    )
                }
                
                # Send DM to user's private channel (not the original channel)
                user_dm_channel = im_service.get_user_dm_channel(message_data["user_id"])
                im_service.send_message(
                    user_dm_channel,
                    authorization_prompt,
                    button_metadata
                )
                
                return {"status": "ok", "action": "authorization_required"}
        
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
            db,
            bot_url
        )
        
        # Send response - always use reply_to_message
        # The specific implementation (thread vs new message) is handled by each platform
        im_service.reply_to_message(
            message_data["channel"],
            response["content"],
            message_data.get("timestamp"),  # Use the original message timestamp
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
    db: Session,
    bot_url: str
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
                    auth_url = oauth2_service.generate_auth_url(user.id, system_config, bot_url)
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


def get_bot_url(config, request=None) -> str:
    """Get bot URL from config or fall back to request host."""
    # First try to use config.bot.url if it's set and not empty
    if config.bot.url and config.bot.url.strip():
        return config.bot.url.strip()
    
    # Fall back to request host URL if available
    if request:
        return str(request.base_url).rstrip('/')
    
    # Final fallback
    return "http://localhost:8000"