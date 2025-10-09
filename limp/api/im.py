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
                
                # Complete the message with failure status (authorization required)
                im_service.complete_message(
                    message_data["channel"],
                    message_data.get("timestamp"),
                    success=False
                )
                
                return {"status": "ok", "action": "authorization_required"}
        
        # Acknowledge the user's message
        im_service.acknowledge_message(message_data["channel"], message_data.get("timestamp"))
        
        # Get or create conversation and store user message
        conversation = get_or_create_conversation(db, user.id, message_data, platform)
        store_user_message(db, conversation.id, message_data["text"], message_data.get("timestamp"), external_id)
        
        # Get conversation history
        conversation_history = get_conversation_history(db, conversation.id)
        
        # Create services
        oauth2_service = OAuth2Service(db)
        llm_service = LLMService(get_config().llm)
        tools_service = ToolsService()
        
        # Process message through LLM workflow with progress tracking
        response = await process_llm_workflow(
            message_data["text"],
            conversation_history,
            user,
            oauth2_service,
            llm_service,
            tools_service,
            db,
            bot_url,
            im_service,
            message_data["channel"],
            conversation.id,
            message_data.get("timestamp")
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
        
        # Complete the message with success status
        im_service.complete_message(
            message_data["channel"],
            message_data.get("timestamp"),
            success=True
        )
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Message handling error: {e}")
        
        # Complete the message with failure status
        try:
            im_service.complete_message(
                message_data["channel"],
                message_data.get("timestamp"),
                success=False
            )
        except Exception as completion_error:
            logger.error(f"Error completing message: {completion_error}")
        
        return {"status": "error", "message": "Failed to process message"}


async def process_llm_workflow(
    user_message: str,
    conversation_history: list,
    user: User,
    oauth2_service: OAuth2Service,
    llm_service: LLMService,
    tools_service: ToolsService,
    db: Session,
    bot_url: str,
    im_service: Any,
    channel: str,
    conversation_id: int,
    original_message_ts: str = None
) -> Dict[str, Any]:
    """Process message through LLM workflow with iterative tool calling."""
    try:
        # Get available tools
        system_configs = [system.model_dump() for system in get_config().external_systems]
        tools = tools_service.get_cleaned_tools_for_openai(system_configs)
        
        # Format messages with system prompts (no tool-specific prompts yet)
        config = get_config()
        system_prompts = config.bot.system_prompts if config.bot.system_prompts else []
        messages = llm_service.format_messages_with_context(
            user_message,
            conversation_history,
            system_prompts
        )
        
        # Get max iterations from config
        max_iterations = config.llm.max_iterations
        iteration = 0
        temporary_message_ids = []  # Track temporary messages for cleanup
        
        # Iterative tool calling loop
        while iteration < max_iterations:
            # Send to LLM
            response = llm_service.chat_completion(messages, tools)
            
            # Check for tool calls
            if llm_service.is_tool_call_response(response):
                logger.info(f"Tool calls detected in iteration {iteration + 1}: {response}")
                tool_calls = llm_service.extract_tool_calls(response)
                
                # Send temporary progress message for non-final iterations
                if iteration < max_iterations - 1:
                    # Get the system name and tool description for the first tool call
                    system_name = "External System"
                    tool_description = "Processing request"
                    if tool_calls:
                        first_tool_name = tool_calls[0]["function"]["name"]
                        system_name = tools_service.get_system_name_for_tool(first_tool_name, system_configs)
                        tool_description = tools_service.get_tool_description_summary(first_tool_name, system_configs)
                    
                    progress_content = f"{iteration + 1}. Talking to {system_name}. {tool_description}"
                    temp_message_id = im_service.send_temporary_message(channel, progress_content, original_message_ts)
                    if temp_message_id:
                        temporary_message_ids.append(temp_message_id)
                    
                    # Add debug messages if debug mode is enabled
                    if config.bot.debug:
                        for tool_call in tool_calls:
                            # Debug message for tool name and parameters
                            tool_name = tool_call["function"]["name"]
                            tool_args = tool_call["function"]["arguments"]
                            debug_content = f"🔧 Tool: {tool_name}\n📝 Args: {tool_args}"
                            debug_temp_id = im_service.send_temporary_message(channel, debug_content, original_message_ts)
                            if debug_temp_id:
                                temporary_message_ids.append(debug_temp_id)
                
                # Add the assistant's response with tool calls to the messages
                assistant_message = {
                    "role": "assistant",
                    "content": response["content"],
                    "tool_calls": [
                        {
                            "id": tool_call["id"],
                            "type": tool_call["type"],
                            "function": {
                                "name": tool_call["function"]["name"],
                                "arguments": tool_call["function"]["arguments"]
                            }
                        }
                        for tool_call in tool_calls
                    ]
                }
                messages.append(assistant_message)
                
                # Process tool calls
                for tool_call in tool_calls:
                    # Store tool request
                    store_tool_request(
                        db, 
                        conversation_id, 
                        tool_call["function"]["name"], 
                        tool_call["function"]["arguments"], 
                        tool_call["id"]
                    )
                    
                    # Check authorization
                    system_name = tools_service.get_system_name_for_tool(tool_call["function"]["name"], system_configs)
                    system_config = get_system_config(system_name, system_configs)
                    auth_token = oauth2_service.get_valid_token(user.id, system_name)
                    
                    if not auth_token:
                        # Return authorization URL
                        auth_url = oauth2_service.generate_auth_url(user.id, system_config, bot_url)
                        return {
                            "content": f"Please authorize access to {system_name}: {auth_url}",
                            "metadata": {"auth_url": auth_url}
                        }
                    
                    # Execute tool call
                    tool_result = tools_service.execute_tool_call(
                        tool_call,
                        system_config,
                        auth_token.access_token
                    )
                    
                    # Store tool response
                    tool_success = tool_result.get("success", True)
                    if not tool_success:
                        error_msg = tool_result.get("error", "Unknown error")
                        status_code = tool_result.get("status_code")
                        
                        if status_code == 403:
                            tool_result_content = f"Access denied: {error_msg}. Check if there is another way to achieve the user's goal."
                        elif status_code == 401:
                            tool_result_content = f"Authentication failed: {error_msg}. The user likely needs to re-authorize access to {system_name}."
                        else:
                            tool_result_content = f"Tool call failed: {error_msg}. Check if there is another way to achieve the user's goal."
                    else:
                        tool_result_content = str(tool_result)
                    
                    # Store tool response in database
                    store_tool_response(
                        db,
                        conversation_id,
                        tool_call["id"],
                        tool_result_content,
                        tool_success
                    )
                    
                    messages.append({
                        "role": "tool",
                        "content": tool_result_content,
                        "tool_call_id": tool_call["id"]
                    })
                    
                    # Add debug message for tool response if debug mode is enabled
                    if config.bot.debug:
                        tool_name = tool_call["function"]["name"]
                        response_content = f"📤 Response from {tool_name}:\n{str(tool_result)}"
                        response_temp_id = im_service.send_temporary_message(channel, response_content, original_message_ts)
                        if response_temp_id:
                            temporary_message_ids.append(response_temp_id)
                
                # Inject tool-specific system prompts for the next LLM call
                # This provides context about the tool outputs for the next iteration
                tool_system_prompts = {}
                for tool_call in tool_calls:
                    system_name = tools_service.get_system_name_for_tool(tool_call["function"]["name"], system_configs)
                    system_config = get_system_config(system_name, system_configs)
                    
                    # Load OpenAPI spec and generate tool-specific system prompt
                    try:
                        openapi_spec = tools_service._get_or_load_spec(system_config["openapi_spec"])
                        tool_prompts = tools_service.generate_tool_system_prompts(openapi_spec)
                        tool_name = tool_call["function"]["name"]
                        if tool_name in tool_prompts:
                            tool_system_prompts[tool_name] = tool_prompts[tool_name]
                    except Exception as e:
                        logger.warning(f"Failed to load tool system prompt for {tool_call['function']['name']}: {e}")
                
                # Add all tool system prompts for the next LLM call
                for tool_name, prompt in tool_system_prompts.items():
                    messages.append({
                        "role": "system",
                        "content": prompt
                    })
                
                # Increment iteration counter
                iteration += 1
                
            else:
                # No tool calls, clean up temporary messages and return the response
                if temporary_message_ids and not config.bot.debug:
                    im_service.cleanup_temporary_messages(channel, temporary_message_ids)
                return {"content": response["content"]}
        
        # If we've exceeded max iterations, clean up temporary messages and send a final prompt
        logger.warning(f"Maximum iterations ({max_iterations}) exceeded. Sending final prompt.")
        if temporary_message_ids and not config.bot.debug:
            im_service.cleanup_temporary_messages(channel, temporary_message_ids)
        
        final_prompt = "You have reached the maximum number of tool calling iterations. Please provide your best response based on the information you have gathered so far, without calling any more tools."
        messages.append({"role": "user", "content": final_prompt})
        
        # Get final response without tools
        final_response = llm_service.chat_completion(messages)
        return {"content": final_response["content"]}
        
    except Exception as e:
        logger.error(f"LLM workflow error: {e}")
        # Clean up any temporary messages on error (unless debug mode is enabled)
        if 'temporary_message_ids' in locals() and temporary_message_ids and not config.bot.debug:
            im_service.cleanup_temporary_messages(channel, temporary_message_ids)
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


def store_tool_request(db: Session, conversation_id: int, tool_name: str, tool_arguments: str, tool_call_id: str) -> Message:
    """Store tool request in database."""
    message = Message(
        conversation_id=conversation_id,
        role="tool_request",
        content=f"Tool: {tool_name}\nArguments: {tool_arguments}",
        message_metadata={
            "tool_name": tool_name,
            "tool_arguments": tool_arguments,
            "tool_call_id": tool_call_id
        }
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def store_tool_response(db: Session, conversation_id: int, tool_call_id: str, response_content: str, success: bool) -> Message:
    """Store tool response in database."""
    message = Message(
        conversation_id=conversation_id,
        role="tool_response",
        content=response_content,
        message_metadata={
            "tool_call_id": tool_call_id,
            "success": success
        }
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def get_conversation_history(db: Session, conversation_id: int) -> list:
    """Get conversation history for a specific conversation with tool request/response filtering."""
    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()
    
    # Filter messages according to the requirements:
    # - Include all user, assistant, and system messages
    # - For tool requests/responses, only include the latest tool request and response
    #   until the latest successful tool response
    filtered_messages = []
    tool_requests = []
    tool_responses = []
    
    for message in messages:
        if message.role in ["user", "assistant", "system"]:
            # Always include user, assistant, and system messages
            filtered_messages.append(message)
        elif message.role == "tool_request":
            # Collect tool requests
            tool_requests.append(message)
        elif message.role == "tool_response":
            # Collect tool responses
            tool_responses.append(message)
    
    # Find the latest successful tool response
    latest_successful_response = None
    for response in reversed(tool_responses):
        if response.message_metadata and response.message_metadata.get("success", False):
            latest_successful_response = response
            break
    
    # Include tool requests and responses from the latest successful response onwards
    if latest_successful_response:
        # Find the index of the latest successful response
        successful_response_index = tool_responses.index(latest_successful_response)
        
        # Include all tool requests and responses from this point onwards
        for i, response in enumerate(tool_responses):
            if i >= successful_response_index:
                filtered_messages.append(response)
                # Find corresponding tool request
                tool_call_id = response.message_metadata.get("tool_call_id")
                if tool_call_id:
                    for request in tool_requests:
                        if (request.message_metadata and 
                            request.message_metadata.get("tool_call_id") == tool_call_id):
                            filtered_messages.append(request)
                            break
    else:
        # If no successful responses, include all tool requests and responses
        filtered_messages.extend(tool_requests)
        filtered_messages.extend(tool_responses)
    
    # Sort filtered messages by creation time
    filtered_messages.sort(key=lambda x: x.created_at)
    
    # Format messages for LLM
    history = []
    for message in filtered_messages:
        if message.role in ["user", "assistant", "system"]:
            history.append({
                "role": message.role,
                "content": message.content
            })
        elif message.role == "tool_request":
            # Convert tool request to assistant message with tool calls
            tool_name = message.message_metadata.get("tool_name", "unknown")
            tool_arguments = message.message_metadata.get("tool_arguments", "{}")
            tool_call_id = message.message_metadata.get("tool_call_id", "")
            
            history.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [{
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": tool_arguments
                    }
                }]
            })
        elif message.role == "tool_response":
            # Convert tool response to tool message
            tool_call_id = message.message_metadata.get("tool_call_id", "")
            history.append({
                "role": "tool",
                "content": message.content,
                "tool_call_id": tool_call_id
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