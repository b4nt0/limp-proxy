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
    platform: str
) -> Dict[str, Any]:
    """Handle user message and generate response."""
    try:
        # Get or create user
        user = get_or_create_user(db, message_data["user_id"], platform)
        
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