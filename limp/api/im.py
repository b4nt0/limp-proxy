"""
Common instant messaging functionality.
"""

from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
import logging
from datetime import datetime, timedelta

from ..database import get_session
from ..services.oauth2 import OAuth2Service
from ..services.llm import LLMService
from ..services.tools import ToolsService
from ..config import get_config
from ..models.user import User
from ..models.conversation import Conversation, Message

logger = logging.getLogger(__name__)


def generate_slack_message_id(message_data: Dict[str, Any]) -> str:
    """Generate unique identifier for Slack message to prevent duplicates."""
    # For Slack, use organization (team_id), sender (user), and timestamp
    team_id = message_data.get("team_id", "unknown")
    user_id = message_data.get("user_id", "unknown")
    timestamp = message_data.get("timestamp", "unknown")
    
    # Create a unique identifier by concatenating these values
    return f"slack_{team_id}_{user_id}_{timestamp}"


def is_duplicate_message(db: Session, external_id: str) -> bool:
    """Check if a message with the given external_id already exists."""
    existing_message = db.query(Message).filter(
        Message.external_id == external_id
    ).first()
    return existing_message is not None


async def handle_user_message(
    message_data: Dict[str, Any],
    im_service: Any,
    db: Session,
    platform: str,
    request: Any = None
) -> Dict[str, Any]:
    """Handle user message and generate response."""
    try:
        # Generate external ID for duplicate detection
        external_id = None
        if platform.lower() == "slack":
            external_id = generate_slack_message_id(message_data)
            
            # Check for duplicate message
            if is_duplicate_message(db, external_id):
                logger.info(f"Duplicate message detected, ignoring: {external_id}")
                return {"status": "ok", "action": "duplicate_ignored"}
        
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
        
        # Get or create conversation and store user message
        conversation = get_or_create_conversation(db, user.id, message_data, platform)
        store_user_message(db, conversation.id, message_data["text"], message_data.get("timestamp"), external_id)
        
        # Get conversation history
        conversation_history = get_conversation_history(db, conversation.id)
        
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
        
        # Store assistant response
        store_assistant_message(db, conversation.id, response["content"], response.get("metadata"))
        
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
        tools = tools_service.get_cleaned_tools_for_openai(system_configs)
        
        # Format messages with system prompts
        config = get_config()
        system_prompts = config.bot.system_prompts if config.bot.system_prompts else []
        messages = llm_service.format_messages_with_context(
            user_message,
            conversation_history,
            system_prompts
        )
        
        # Send to LLM
        response = llm_service.chat_completion(messages, tools)
        
        # Check for tool calls
        if llm_service.is_tool_call_response(response):
            tool_calls = llm_service.extract_tool_calls(response)
            
            # Process tool calls
            for tool_call in tool_calls:
                # Check authorization
                system_name = tools_service.get_system_name_for_tool(tool_call["function"]["name"], system_configs)
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


def get_or_create_conversation(db: Session, user_id: int, message_data: Dict[str, Any], platform: str) -> Conversation:
    """Get or create conversation for user based on platform rules."""
    config = get_config()
    
    if platform.lower() == "slack":
        # For Slack, use thread_ts to determine conversation
        thread_ts = message_data.get("thread_ts")
        if thread_ts:
            # This is a reply in a thread - find existing conversation
            # Query all conversations for this user and check JSON manually
            conversations = db.query(Conversation).filter(
                Conversation.user_id == user_id
            ).all()
            
            for conv in conversations:
                if conv.context and conv.context.get("thread_ts") == thread_ts:
                    return conv
        
        # Create new conversation for Slack
        context = {
            "thread_ts": message_data.get("timestamp"),  # Use message timestamp as thread root
            "channel": message_data.get("channel")
        }
        conversation = Conversation(
            user_id=user_id,
            context=context
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation
    
    elif platform.lower() == "teams":
        # For Teams, check if we need a new conversation based on timeout
        # Get the most recent conversation for this user
        recent_conversation = db.query(Conversation).filter(
            Conversation.user_id == user_id
        ).order_by(Conversation.created_at.desc()).first()
        
        # Check for /new command
        text = message_data.get("text", "").strip()
        if text == "/new":
            # Force new conversation
            recent_conversation = None
        
        # Check timeout for Teams DMs (not channels)
        if recent_conversation and should_create_new_conversation(recent_conversation, config, message_data):
            recent_conversation = None
        
        if recent_conversation:
            return recent_conversation
        
        # Create new conversation for Teams
        context = {
            "channel": message_data.get("channel"),
            "conversation_type": "dm" if message_data.get("channel", "").startswith("19:") else "channel"
        }
        conversation = Conversation(
            user_id=user_id,
            context=context
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation
    
    else:
        # Default behavior - create new conversation
        conversation = Conversation(user_id=user_id)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation


def should_create_new_conversation(conversation: Conversation, config, message_data: Dict[str, Any]) -> bool:
    """Check if a new conversation should be created based on timeout rules."""
    # Only apply timeout rules to Teams DMs
    if not conversation.context or conversation.context.get("conversation_type") != "dm":
        return False
    
    # Get Teams platform config
    try:
        teams_config = config.get_im_platform_by_key("teams")
        timeout_hours = teams_config.conversation_timeout_hours or 8
    except ValueError:
        timeout_hours = 8  # Default fallback
    
    # Check if enough time has passed
    time_since_last_message = datetime.utcnow() - conversation.updated_at
    return time_since_last_message > timedelta(hours=timeout_hours)


def store_user_message(db: Session, conversation_id: int, content: str, timestamp: Optional[str] = None, external_id: Optional[str] = None) -> Message:
    """Store user message in database."""
    message = Message(
        conversation_id=conversation_id,
        role="user",
        content=content,
        external_id=external_id,
        message_metadata={"timestamp": timestamp} if timestamp else None
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def store_assistant_message(db: Session, conversation_id: int, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
    """Store assistant message in database."""
    message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=content,
        message_metadata=metadata
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def get_conversation_history(db: Session, conversation_id: int) -> list:
    """Get conversation history for a specific conversation."""
    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()
    
    # Format messages for LLM
    history = []
    for message in messages:
        history.append({
            "role": message.role,
            "content": message.content
        })
    
    return history


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