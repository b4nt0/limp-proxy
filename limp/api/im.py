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
from ..services.context import ContextManager
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
                
                return await handle_authorization_request(
                    primary_system.name,
                    auth_url,
                    message_data["user_id"],
                    im_service,
                    message_data,
                    request
                )
        
        # Acknowledge the user's message
        im_service.acknowledge_message(message_data["channel"], message_data.get("timestamp"))
        
        # Get or create conversation and store user message
        conversation = get_or_create_conversation(db, user.id, message_data, platform)
        store_user_message(db, conversation.id, message_data["text"], message_data.get("timestamp"), external_id)
        
        # Get conversation history with context management and temporary messages
        conversation_history = get_conversation_history(
            db, 
            conversation.id, 
            im_service, 
            message_data["channel"], 
            message_data.get("timestamp"),
            platform
        )
        
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
        
        # Check if authorization is required for a specific system
        if response.get("metadata", {}).get("authorization_required", False):
            system_name = response.get("metadata", {}).get("system_name")
            auth_url = response.get("metadata", {}).get("auth_url")
            
            if system_name and auth_url:
                return await handle_authorization_request(
                    system_name,
                    auth_url,
                    message_data["user_id"],
                    im_service,
                    message_data,
                    request
                )
        
        # Send response - always use reply_to_message
        # The specific implementation (thread vs new message) is handled by each platform
        im_service.reply_to_message(
            message_data["channel"],
            response["content"],
            message_data.get("timestamp"),  # Use the original message timestamp
            response.get("metadata")
        )

        if response.get("metadata", {}).get("error", False):
            is_successful = False
        else:
            is_successful = True

        if is_successful:
            # Determine if the response was successful based on finish_reason
            finish_reason = response.get("finish_reason")
            
            # Define successful finish reasons for final user messages
            # "stop" - normal completion (the only successful reason for final responses)
            # Note: "tool_calls" and "function_call" are not successful for final messages
            # as they indicate the LLM wanted to make tool calls but couldn't
            successful_finish_reasons = {"stop"}
            
            # Consider the response successful if finish_reason is in successful reasons
            # or if finish_reason is None/not provided (backward compatibility)
            is_successful = is_successful and (
                finish_reason is None or 
                finish_reason in successful_finish_reasons
            )
        
        # Complete the message with success status
        im_service.complete_message(
            message_data["channel"],
            message_data.get("timestamp"),
            success=is_successful
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
        # Get available tools (external + builtin)
        system_configs = [system.model_dump() for system in get_config().external_systems]
        external_tools = tools_service.get_cleaned_tools_for_openai(system_configs)
        builtin_tools = tools_service.get_builtin_tools()
        tools = external_tools + builtin_tools
        
        # Format messages with system prompts (no tool-specific prompts yet)
        # Note: user_message is already included in conversation_history, so we don't need to pass it separately
        config = get_config()
        system_prompts = config.bot.system_prompts if config.bot.system_prompts else []
        messages = llm_service.format_messages_with_context(
            "",  # Empty user message since it's already in conversation_history
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
            response = llm_service.chat_completion(messages, tools, stream=True)
            
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
                    
                    # Create base progress message
                    base_progress = f"{iteration + 1}. Talking to {system_name}. {tool_description}"
                    
                    # Add context usage percentage based on current messages (including new tool calls)
                    from limp.services.context import ContextManager
                    context_manager = ContextManager(config.llm)
                    progress_content = context_manager.append_context_usage_to_message(
                        base_progress, 
                        messages, 
                        []  # No additional system prompts since they're already in messages
                    )
                    
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
                    
                    tool_name = tool_call["function"]["name"]
                    
                    # Check if this is a builtin tool
                    if tool_name.startswith("LimpBuiltin"):
                        # Execute builtin tool
                        tool_result = tools_service.execute_builtin_tool(
                            tool_name,
                            tool_call["function"]["arguments"]
                        )
                        
                    else:
                        # Execute external tool (existing logic)
                        system_name = tools_service.get_system_name_for_tool(tool_name, system_configs)
                        system_config = get_system_config(system_name, system_configs)
                        auth_token = oauth2_service.get_valid_token(user.id, system_name)
                        
                        if not auth_token:
                            # Store failed tool result for consistency
                            auth_url = oauth2_service.generate_auth_url(user.id, system_config, bot_url)
                            tool_result_content = f"Authorization required for {system_name}. Please authorize access: {auth_url}"
                            
                            # Store tool response in database
                            store_tool_response(
                                db,
                                conversation_id,
                                tool_call["id"],
                                tool_result_content,
                                False  # success=False for authorization required
                            )
                            
                            # Return authorization URL with special metadata
                            return {
                                "content": f"Please authorize access to {system_name}: {auth_url}",
                                "metadata": {"auth_url": auth_url, "authorization_required": True, "system_name": system_name}
                            }
                        
                        # Execute external tool call
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
                        # Handle builtin tool results
                        if tool_name.startswith("LimpBuiltin"):
                            tool_result_content = tool_result.get("result", str(tool_result))
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

                    # Handle special builtin tool actions
                    if tool_name.startswith("LimpBuiltin") and tool_result.get("action") == "start_over":
                        # Store /new system message in database
                        store_system_message(db, conversation_id, "/new")
                    
                    elif tool_name.startswith("LimpBuiltin") and tool_result.get("action") == "request_authorization":
                        # Handle authorization request from built-in tool
                        requested_tool_name = tool_result.get("tool_name")
                        
                        # Determine which system to request authorization for
                        if requested_tool_name:
                            # Try to find the system for the specific tool
                            try:
                                system_name = tools_service.get_system_name_for_tool(requested_tool_name, system_configs)
                                system_config = get_system_config(system_name, system_configs)
                            except (ValueError, KeyError):
                                # Tool not found, fall back to primary system
                                primary_system = get_config().get_primary_system()
                                if primary_system:
                                    system_name = primary_system.name
                                    system_config = primary_system
                                else:
                                    # No primary system available
                                    continue
                        else:
                            # No specific tool requested, use primary system
                            primary_system = get_config().get_primary_system()
                            if primary_system:
                                system_name = primary_system.name
                                system_config = primary_system
                            else:
                                # No primary system available
                                continue
                        
                        # Generate authorization URL
                        auth_url = oauth2_service.generate_auth_url(user.id, system_config, bot_url)
                        
                        # Update the tool result content for proper storage
                        tool_result_content = f"Authorization required for {system_name}. Please authorize access: {auth_url}"
                        
                        # Return authorization URL with special metadata
                        return {
                            "content": f"Please authorize access to {system_name}: {auth_url}",
                            "metadata": {"auth_url": auth_url, "authorization_required": True, "system_name": system_name}
                        }

                    
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
                return {
                    "content": response["content"],
                    "finish_reason": response.get("finish_reason")
                }
        
        # If we've exceeded max iterations, clean up temporary messages and send a final prompt
        logger.warning(f"Maximum iterations ({max_iterations}) exceeded. Sending final prompt.")
        if temporary_message_ids and not config.bot.debug:
            im_service.cleanup_temporary_messages(channel, temporary_message_ids)
        
        final_prompt = "You have reached the maximum number of tool calling iterations. Please provide your best response based on the information you have gathered so far, without calling any more tools."
        messages.append({"role": "user", "content": final_prompt})
        
        # Get final response without tools
        final_response = llm_service.chat_completion(messages)
        return {
            "content": final_response["content"],
            "finish_reason": final_response.get("finish_reason")
        }
        
    except Exception as e:
        logger.error(f"LLM workflow error: {e}")
        # Clean up any temporary messages on error (unless debug mode is enabled)
        if 'temporary_message_ids' in locals() and temporary_message_ids:
            try:
                if not config.bot.debug:
                    im_service.cleanup_temporary_messages(channel, temporary_message_ids)
            except:
                pass  # Ignore cleanup errors

        try:
            if not config.bot.debug:
                return {
                        "content": llm_service.get_error_message(e),
                        "metadata": {"error": True}
                    }
            else:
                import traceback
                import sys
                exc_info_str = ''.join(traceback.format_exception(*sys.exc_info()))
                return {
                    "content": exc_info_str,
                    "metadata": {"error": True}
                }
        except:
            # Fallback error handling
            return {
                "content": "An error occurred while processing your request.",
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
        # For Slack, extract channel and thread identifiers
        channel_id = message_data.get("channel")
        thread_ts = message_data.get("thread_ts")
        
        # If message contains thread identifier, use that (ignore channel for thread messages)
        if thread_ts:
            existing_conversation = db.query(Conversation).filter(
                Conversation.user_id == user_id,
                Conversation.thread_id == thread_ts
            ).first()
            
            if existing_conversation:
                return existing_conversation
        
        # If no thread identifier, try to find conversation by channel with empty thread_id
        if channel_id:
            existing_conversation = db.query(Conversation).filter(
                Conversation.user_id == user_id,
                Conversation.channel_id == channel_id,
                Conversation.thread_id.is_(None)
            ).first()
            
            if existing_conversation:
                return existing_conversation
        
        # If nothing specified, use most recent conversation
        recent_conversation = db.query(Conversation).filter(
            Conversation.user_id == user_id
        ).order_by(Conversation.created_at.desc()).first()
        
        if recent_conversation and not thread_ts and not channel_id:
            return recent_conversation
        
        # Create new conversation for Slack
        context = {
            "channel": channel_id,
            "thread_ts": thread_ts or message_data.get("timestamp")  # Use message timestamp as thread root if no thread_ts
        }
        
        conversation = Conversation(
            user_id=user_id,
            channel_id=channel_id,
            thread_id=thread_ts or message_data.get("timestamp"),
            context=context
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation
    
    elif platform.lower() == "teams":
        # For Teams, extract channel and conversation identifiers
        activity = message_data.get("activity", {})
        channel_id = activity.get("channel_id")
        conversation_id = activity.get("conversation", {}).get("id")
        
        # If message contains thread identifier (conversation_id), use that (ignore channel for thread messages)
        if conversation_id:
            existing_conversation = db.query(Conversation).filter(
                Conversation.user_id == user_id,
                Conversation.thread_id == conversation_id
            ).first()
            
            if existing_conversation:
                return existing_conversation
        
        # If no thread identifier, try to find conversation by channel with empty thread_id
        if channel_id:
            existing_conversation = db.query(Conversation).filter(
                Conversation.user_id == user_id,
                Conversation.channel_id == channel_id,
                Conversation.thread_id.is_(None)
            ).first()
            
            if existing_conversation:
                return existing_conversation
        
        # Get most recent conversation for Teams
        recent_conversation = db.query(Conversation).filter(
            Conversation.user_id == user_id
        ).order_by(Conversation.created_at.desc()).first()
        
        if recent_conversation and not conversation_id and not channel_id:
            # No specific conversation/channel identifiers, use most recent
            return recent_conversation
        
        # Create new conversation for Teams
        context = {
            "channel": message_data.get("channel"),
            "conversation_type": "dm" if message_data.get("channel", "").startswith("19:") else "channel"
        }
        
        # Add conversation identifiers to context for backward compatibility
        if conversation_id:
            context["conversation_id"] = conversation_id
        if channel_id:
            context["channel_id"] = channel_id
            
        conversation = Conversation(
            user_id=user_id,
            channel_id=channel_id,
            thread_id=conversation_id,
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


def store_system_message(db: Session, conversation_id: int, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
    """Store system message in database."""
    message = Message(
        conversation_id=conversation_id,
        role="system",
        content=content,
        message_metadata=metadata
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def detect_conversation_break_from_messages(messages: list, platform: str, config) -> int:
    """
    Detect conversation break indicators in message objects.
    Returns the index of the first message after the break, or -1 if no break found.
    """
    if not messages:
        return -1
    
    # Check for /new command from anyone (both Slack and Teams)
    for i, message in enumerate(messages):
        if message.content.strip() == "/new":
            logger.info(f"Found /new command at message {i}, conversation break detected")
            return i + 1  # Return index of message after /new
    
    # Check for time-based breaks (Teams only)
    if platform.lower() == "teams":
        try:
            teams_config = config.get_im_platform_by_key("teams")
            timeout_hours = teams_config.conversation_timeout_hours or 8
        except ValueError:
            timeout_hours = 8  # Default fallback
        
        # Check for time gaps between messages
        try:
            for i in range(len(messages) - 1, 0, -1):  # Go backwards through history
                current_msg = messages[i]
                prev_msg = messages[i - 1]
                
                # Use created_at timestamps directly
                time_diff = current_msg.created_at - prev_msg.created_at
                if time_diff > timedelta(hours=timeout_hours):
                    logger.info(f"Found time gap of {time_diff} at message {i}, conversation break detected")
                    return i  # Return index of message after the gap
        except Exception as e:
            logger.warning(f"Error in time-based break detection: {e}")
    
    return -1  # No break found


def detect_conversation_break_from_formatted_history(history: list, platform: str, config) -> int:
    """
    Detect conversation break indicators in formatted message history.
    Returns the index of the first message after the break, or -1 if no break found.
    """
    if not history:
        return -1
    
    # Check for /new command from anyone (both Slack and Teams)
    for i, message in enumerate(history):
        if message.get("content", "").strip() == "/new":
            logger.info(f"Found /new command at message {i}, conversation break detected")
            return i + 1  # Return index of message after /new
    
    # Check for time-based breaks (Teams only)
    if platform.lower() == "teams":
        try:
            teams_config = config.get_im_platform_by_key("teams")
            timeout_hours = teams_config.conversation_timeout_hours or 8
        except ValueError:
            timeout_hours = 8  # Default fallback
        
        # Check for time gaps between messages
        try:
            for i in range(len(history) - 1, 0, -1):  # Go backwards through history
                current_msg = history[i]
                prev_msg = history[i - 1]
                
                # Use created_at timestamps directly
                current_created_at = current_msg.get("created_at")
                prev_created_at = prev_msg.get("created_at")
                
                if current_created_at and prev_created_at:
                    time_diff = current_created_at - prev_created_at
                    if time_diff > timedelta(hours=timeout_hours):
                        logger.info(f"Found time gap of {time_diff} at message {i}, conversation break detected")
                        return i  # Return index of message after the gap
        except Exception as e:
            logger.warning(f"Error in time-based break detection: {e}")
    
    return -1  # No break found


def get_conversation_history(db: Session, conversation_id: int, im_service=None, channel: str = None, original_message_ts: str = None, platform: str = "teams") -> list:
    """Get conversation history for a specific conversation with context management."""
    config = get_config()
    context_manager = ContextManager(config.llm)
    
    # Get raw messages for break detection
    raw_messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()
    
    # Check for conversation break indicators using raw messages
    break_index = detect_conversation_break_from_messages(raw_messages, platform, config)
    if break_index > 0:
        logger.info(f"Trimming conversation history at index {break_index}")
        # Trim raw messages before formatting
        raw_messages = raw_messages[break_index:]
        # Use context manager to reconstruct history with summaries (now with trimmed messages)
        history = context_manager.reconstruct_history_with_summary_from_messages(raw_messages)
    else:
        # No break detected, use the original method for backward compatibility
        history = context_manager.reconstruct_history_with_summary(db, conversation_id)
    
    # Check if we need to summarize the conversation
    if context_manager.should_summarize(history):
        logger.info(f"Context threshold reached for conversation {conversation_id}, summarizing...")
        
        # Send summarization notification if IM service is available
        if im_service and channel:
            summarization_message = context_manager.create_summarization_message()
            im_service.send_temporary_message(channel, summarization_message, original_message_ts)
        
        # Get the reconstructed history (original request + latest summary + messages after summary)
        # This ensures we don't include past summaries in the new summary
        all_formatted = context_manager.reconstruct_history_with_summary(db, conversation_id)
        
        # Generate summary
        summary = context_manager.summarize_conversation(all_formatted, exclude_tool_calls=True)
        
        # Store the summary
        context_manager.store_summary(db, conversation_id, summary)
        
        # Reconstruct history with the new summary
        history = context_manager.reconstruct_history_with_summary(db, conversation_id)
    
    return history


def get_system_config(system_name: str, system_configs: list) -> dict:
    """Get system configuration by name."""
    for config in system_configs:
        if config["name"] == system_name:
            return config
    raise ValueError(f"System {system_name} not found")


async def handle_authorization_request(
    system_name: str,
    auth_url: str,
    user_id: str,
    im_service: Any,
    message_data: Dict[str, Any],
    request: Any = None
) -> Dict[str, Any]:
    """Handle authorization request by sending DM with authorization prompt and button."""
    # Send DM with authorization prompt and button
    authorization_prompt = f"🔐 **Authorization Required**\n\nTo use this bot, you need to authorize access to {system_name}.\n\nClick the button below to authorize:"
    
    # Create button metadata for the IM service
    button_metadata = {
        "blocks": im_service.create_authorization_button(
            auth_url, 
            f"Authorize {system_name}",
            f"Click to authorize access to {system_name}",
            request
        )
    }
    
    # Send DM to user's private channel (not the original channel)
    user_dm_channel = im_service.get_user_dm_channel(user_id)
    await im_service.send_message(
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