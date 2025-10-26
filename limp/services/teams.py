"""
Microsoft Teams integration service.
"""

from typing import Dict, Any, Optional, List
import logging
from botbuilder.schema import Activity, ActivityTypes
from botbuilder.integration.aiohttp import CloudAdapter, ConfigurationBotFrameworkAuthentication
from botbuilder.core.integration import aiohttp_error_middleware
from botbuilder.core import (
    ActivityHandler,
    TurnContext,
)

from .im import IMService

logger = logging.getLogger(__name__)


class TeamsLIMPBot(ActivityHandler):
    """Teams bot that integrates with the shared message handling pipeline."""
    
    def __init__(self, teams_service, db_session, request=None):
        self.teams_service = teams_service
        self.db_session = db_session
        self.current_turn_context = None
        self.request = request
    
    async def on_message_activity(self, turn_context: TurnContext):
        """Handle incoming messages through the shared pipeline."""
        try:
            text = turn_context.activity.text or ""
            logger.info(f"TeamsLIMPBot received message: {text}")
            
            # Store the turn context for use in responses
            self.current_turn_context = turn_context
            
            # If no database session, fall back to simple response
            if not self.db_session:
                await turn_context.send_activity(f"Hello! I received your message: {text}")
                return
            
            # Parse the activity into message data for the shared pipeline
            message_data = self.teams_service.parse_message(turn_context.activity.as_dict())
            
            if message_data.get("type") == "message":
                # Import here to avoid circular imports
                from ..api.im import handle_user_message
                
                # Process through the shared message handling pipeline
                result = await handle_user_message(
                    message_data,
                    self.teams_service,
                    self.db_session,
                    "teams",
                    self.request
                )
                
                logger.info(f"Teams message processing result: {result}")
            else:
                # For non-message activities, just acknowledge
                await turn_context.send_activity(f"I received your activity: {text}")
                
        except Exception as e:
            logger.error(f"Error in TeamsLIMPBot message handling: {e}")
            # Fallback to simple response on error
            await turn_context.send_activity(f"I received your message: {turn_context.activity.text or ''}")
    
    async def send_response(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Send a response using the current turn context."""
        try:
            if not self.current_turn_context:
                logger.error("No turn context available for sending response")
                return False
            
            logger.info(f"TeamsLIMPBot sending response: {content}")
            logger.info(f"TeamsLIMPBot metadata: {metadata}")
            
            # Create activity with content and metadata
            activity = Activity(
                type=ActivityTypes.message,
                text=content,
                channel_id="msteams"
            )
            
            if metadata and metadata.get("blocks"):
                # Handle Teams-specific content from the blocks
                blocks = metadata["blocks"]
                logger.info(f"TeamsLIMPBot blocks: {blocks}")
                
                # Check if we have Adaptive Cards (authorization buttons)
                if blocks and len(blocks) > 0:
                    first_block = blocks[0]
                    if first_block.get("contentType") == "application/vnd.microsoft.card.adaptive":
                        # This is an Adaptive Card - send it as an attachment
                        logger.info("TeamsLIMPBot detected Adaptive Card, sending as attachment")
                        activity.attachments = [first_block]
                        # Keep the main content as text
                        logger.info(f"TeamsLIMPBot sending Adaptive Card with text: {content}")
                    else:
                        # This is plain text content - combine it
                        auth_content = first_block.get("content", "")
                        if auth_content:
                            combined_content = f"{content}\n\n{auth_content}"
                            activity.text = combined_content
                            logger.info(f"TeamsLIMPBot combined content: {combined_content}")
            
            if metadata and metadata.get("attachments"):
                activity.attachments = metadata["attachments"]
                logger.info(f"TeamsLIMPBot attachments: {metadata['attachments']}")
            
            # Send using turn context (this is the working pattern)
            await self.current_turn_context.send_activity(activity)
            logger.info(f"Successfully sent Teams response: {content}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending Teams response: {e}")
            return False


class TeamsServiceConfig:
    """Microsoft Teams connection configuration."""

    def __init__(self, app_id: str, app_password: str, app_type: str, app_tenantid: str):
        self.APP_ID = app_id
        self.APP_PASSWORD = app_password
        self.APP_TYPE = app_type
        self.APP_TENANTID = app_tenantid
        self.PORT = 3978


class TeamsService(IMService):
    """Microsoft Teams integration service using Bot Framework ActivityHandler pattern."""
    
    def __init__(self, app_id: str, client_id: str, client_secret: str):
        self.app_id = app_id
        self.client_id = client_id
        self.client_secret = client_secret

        self._config = TeamsServiceConfig(self.app_id, 
          self.client_secret, 'SingleTenant', self.client_id)
        
        # Initialize BotFrameworkAdapter and LIMPBot
        self._adapter = self._create_adapter()
        self._adapter.on_turn_error = self.on_error
        
        # Initialize conversation references storage
        self._conversation_references = {}
        
        # Bot will be created per request with database session
        self._current_bot = None

    async def on_error(context, error):
        logger.error(f"[on_turn_error] {type(error)}: {error}")
    
    def verify_request(self, request_data: Dict[str, Any]) -> bool:
        """Verify Teams request."""
        # Implementation would verify the request
        # For now, return True as placeholder
        return True
    
    async def process_activity(self, activity_data: Dict[str, Any], auth_header: str = "", db=None, request=None) -> bool:
        """Process incoming activity using ActivityHandler pattern."""
        try:
            # Deserialize activity from request data
            activity = Activity().deserialize(activity_data)
            
            bot = TeamsLIMPBot(self, db, request)

            # Store the current bot instance so send_message can access it
            self._current_bot = bot
            
            # Process activity through the adapter and bot
            await self._adapter.process_activity(auth_header, activity, bot.on_turn)
            
            logger.info(f"Successfully processed activity: {activity.type}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing activity: {e}")
            return False
    
    def parse_message(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Teams message from Bot Framework activity."""
        try:
            # Handle different activity types
            activity_type = request_data.get("type", "")
            
            if activity_type == "message":
                # Store conversation reference for async responses
                self.store_conversation_reference(request_data)
                
                return {
                    "type": "message",
                    "user_id": request_data.get("from", {}).get("id", ""),
                    "channel": request_data.get("conversation", {}).get("id", ""),
                    "text": request_data.get("text", ""),
                    "timestamp": request_data.get("timestamp", ""),
                    "activity": request_data  # Store full activity for reference
                }
            elif activity_type == "conversationUpdate":
                # Handle bot added to conversation
                self.store_conversation_reference(request_data)
                return {
                    "type": "conversation_update",
                    "channel": request_data.get("conversation", {}).get("id", ""),
                    "activity": request_data
                }
            else:
                return {
                    "type": "unknown",
                    "activity": request_data
                }
        except Exception as e:
            logger.error(f"Error parsing Teams message: {e}")
            return {"type": "error", "error": str(e)}
    
    def format_response(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Format response for Teams."""
        response = {
            "type": "message",
            "text": content
        }
        
        if metadata and metadata.get("attachments"):
            response["attachments"] = metadata["attachments"]
        
        return response
    
    async def send_message(self, channel: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Send a message to Teams using the current bot's turn context."""
        try:
            logger.info(f"TeamsService sending message to channel {channel}: {content}")
            logger.info(f"TeamsService metadata: {metadata}")
            
            # Check if we have a current bot instance with turn context
            if hasattr(self, '_current_bot') and self._current_bot and self._current_bot.current_turn_context:
                logger.info("TeamsService delegating to bot.send_response")
                # Use the bot's send_response method (uses turn_context.send_activity)
                return await self._current_bot.send_response(content, metadata)
            else:
                logger.warning("No current bot turn context available for sending message")
                logger.warning("This usually means the message is being sent outside of a message activity context")
                return False

        except Exception as e:
            logger.error(f"Error sending Teams message: {e}")
            return False

    def _create_adapter(self) -> CloudAdapter:
        """Create BotFrameworkAdapter for Bot Framework integration."""
        settings = ConfigurationBotFrameworkAuthentication(
            configuration=self._config,
        )

        return CloudAdapter(settings)
    
    
    def reply_to_message(self, channel: str, content: str, original_message_ts: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Reply to a message in Teams."""
        try:
            logger.info(f"Replying to Teams message {original_message_ts} in channel {channel}: {content}")
            logger.info(f"Teams reply metadata: {metadata}")
            
            # For Teams, since DMs don't support threads, we send a new message
            # This is still a "reply" conceptually, but implemented as a new message
            # Use the current bot's turn context if available
            if hasattr(self, '_current_bot') and self._current_bot and self._current_bot.current_turn_context:
                logger.info("TeamsService delegating reply to bot.send_response")
                # Use the bot's send_response method (uses turn_context.send_activity)
                import asyncio
                asyncio.create_task(self._current_bot.send_response(content, metadata))
                logger.info(f"Successfully sent Teams reply: {content}")
                return True
            else:
                logger.warning("No current bot turn context available for reply")
                logger.warning("This usually means the reply is being sent outside of a message activity context")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Teams reply: {e}")
            return False
    
    def create_authorization_button(self, auth_url: str, button_text: str, button_description: str, request=None) -> List[Dict[str, Any]]:
        """Create authorization button blocks for Teams using Adaptive Cards."""
        logger.info(f"Creating Teams authorization button: {button_text} -> {auth_url}")
        logger.info(f"Button description: {button_description}")
        
        # Create an Adaptive Card with a proper button
        adaptive_card = {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard",
                "version": "1.3",
                "body": [
                    {
                        "type": "TextBlock",
                        "text": button_description,
                        "wrap": True,
                        "size": "Medium"
                    },
                    {
                        "type": "TextBlock",
                        "text": "Click the button below to authorize access:",
                        "wrap": True,
                        "size": "Small",
                        "color": "Accent"
                    }
                ],
                "actions": [
                    {
                        "type": "Action.OpenUrl",
                        "title": f"🔐 {button_text}",
                        "url": auth_url,
                        "style": "positive"
                    }
                ]
            }
        }
        
        logger.info(f"Generated Teams Adaptive Card: {adaptive_card}")
        
        return [adaptive_card]
    
    def get_user_dm_channel(self, user_id: str) -> str:
        """Get the DM channel ID for a specific user in Teams."""
        # For Teams, the user_id is typically the conversation ID for DMs
        # Teams handles DM channels differently than Slack
        # The user_id should already be the DM channel ID in Teams
        logger.info(f"Using user_id {user_id} as DM channel for Teams")
        return user_id
    
    def acknowledge_message(self, channel: str, message_ts: str) -> bool:
        """Acknowledge a user's message (Teams stub - just logs)."""
        logger.info(f"Teams acknowledgment requested for channel {channel}, message {message_ts}")
        return True
    
    def send_temporary_message(self, channel: str, content: str, original_message_ts: str = None) -> Optional[str]:
        """Send a temporary message (Teams stub - just logs)."""
        logger.info(f"Teams temporary message requested for channel {channel}: {content}")
        return f"teams_temp_{channel}_{hash(content)}"
    
    def cleanup_temporary_messages(self, channel: str, message_ids: List[str]) -> bool:
        """Clean up temporary messages (placeholder implementation for Teams)."""
        # For Teams, message deletion is more complex and depends on the Bot Framework
        # This is a placeholder implementation
        try:
            logger.info(f"Cleaning up {len(message_ids)} temporary messages in Teams channel {channel}")
            # In a real implementation, you'd use the Teams Bot Framework to delete messages
            # For now, we'll just log the cleanup attempt
            for message_id in message_ids:
                logger.info(f"Would delete Teams message {message_id}")
            return True
        except Exception as e:
            logger.error(f"Error cleaning up Teams temporary messages: {e}")
            return False
    
    def complete_message(self, channel: str, message_ts: str, success: bool) -> bool:
        """Complete a message (Teams stub - just logs)."""
        status = "completed successfully" if success else "failed"
        logger.info(f"Teams message completion requested for channel {channel}, message {message_ts}: {status}")
        return True
    
    def store_conversation_reference(self, activity: Dict[str, Any]) -> None:
        """Store conversation reference for immediate async responses only."""
        try:
            conversation_id = activity.get("conversation", {}).get("id")
            if conversation_id:
                # Store minimal reference for immediate response needs
                self._conversation_references[conversation_id] = {
                    "conversation_id": conversation_id,
                    "service_url": activity.get("serviceUrl"),
                    "channel_id": activity.get("channelId")
                }
                logger.debug(f"Stored conversation reference for {conversation_id}: {self._conversation_references[conversation_id]}")
        except Exception as e:
            logger.error(f"Error storing conversation reference: {e}")
    
    async def send_async_response(self, conversation_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Send asynchronous response to Teams conversation."""
        try:
            if conversation_id in self._conversation_references:
                logger.info(f"Sending async response to Teams conversation {conversation_id}: {content}")
                # In a real implementation, you'd use the stored conversation reference
                # to send the response via the Bot Framework
                return True
            else:
                logger.warning(f"No conversation reference found for {conversation_id}")
                return False
        except Exception as e:
            logger.error(f"Error sending async Teams response: {e}")
            return False
