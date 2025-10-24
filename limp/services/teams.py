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


class TeamsEchoBot(ActivityHandler):
    """Simple echo bot using ActivityHandler pattern."""
    
    async def on_message_activity(self, turn_context: TurnContext):
        """Handle incoming messages."""
        text = turn_context.activity.text or ""
        logger.info(f"TeamsEchoBot received message: {text}")
        await turn_context.send_activity(f"Echo: {text}")


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
        
        # Initialize BotFrameworkAdapter and EchoBot
        self._adapter = self._create_adapter()
        self._adapter.on_turn_error = self.on_error
        self._bot = TeamsEchoBot()
        
        # Initialize conversation references storage
        self._conversation_references = {}

    async def on_error(context, error):
        logger.error(f"[on_turn_error] {type(error)}: {error}")
    
    def verify_request(self, request_data: Dict[str, Any]) -> bool:
        """Verify Teams request."""
        # Implementation would verify the request
        # For now, return True as placeholder
        return True
    
    async def process_activity(self, activity_data: Dict[str, Any], auth_header: str = "") -> bool:
        """Process incoming activity using ActivityHandler pattern."""
        try:
            # Deserialize activity from request data
            activity = Activity().deserialize(activity_data)
            
            # Process activity through the adapter and bot
            await self._adapter.process_activity(auth_header, activity, self._bot.on_turn)
            
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
        """Send message to Teams channel using BotFrameworkAdapter.

        channel here is the Teams conversation ID from the incoming activity.
        """
        try:
            logger.info(f"Attempting to send message to channel {channel}: {content}")
            logger.info(f"Available conversation references: {list(self._conversation_references.keys())}")

            conversation_ref = self._conversation_references.get(channel)
            if not conversation_ref:
                logger.warning(f"No conversation reference found for channel {channel}")
                logger.warning(f"Available channels: {list(self._conversation_references.keys())}")
                return False

            service_url = conversation_ref.get("service_url")
            if not service_url:
                logger.warning(f"No service URL found for channel {channel}")
                logger.warning(f"Conversation ref: {conversation_ref}")
                return False

            # Build activity
            activity = Activity(
                type=ActivityTypes.message,
                text=content,
                channel_id="msteams",
                conversation={"id": channel}
            )
            if metadata and metadata.get("attachments"):
                activity.attachments = metadata["attachments"]

            # Use BotFrameworkAdapter to send the message (handles all auth automatically)
            logger.info(f"Using BotFrameworkAdapter to send message via service URL: {service_url}")
            
            # The BotFrameworkAdapter should handle authentication automatically
            # Create a connector client through the adapter (await the coroutine)
            client = await self._adapter.create_connector_client(service_url)
            await client.conversations.send_to_conversation(channel, activity)
            
            logger.info(f"Successfully sent message to Teams conversation {channel}")
            return True

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
        # For Teams, since DMs don't support threads, we send a new message
        # This is still a "reply" conceptually, but implemented as a new message
        # Implementation would use Teams Bot Framework
        # For now, return True as placeholder
        logger.info(f"Replying to Teams message {original_message_ts} in channel {channel} (as new message): {content}")
        return True
    
    def create_authorization_button(self, auth_url: str, button_text: str, button_description: str, request=None) -> List[Dict[str, Any]]:
        """Create authorization link blocks for Teams."""
        # Always use hyperlinks for Teams as well
        return [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "type": "AdaptiveCard",
                    "version": "1.3",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": f"{button_description}\n\n➡️ **{button_text}**",
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": "💻 Click the link above to open authorization in your browser",
                            "wrap": True,
                            "size": "Small"
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": f"🔐 {button_text}",
                            "url": auth_url
                        }
                    ]
                }
            }
        ]
    
    def get_user_dm_channel(self, user_id: str) -> str:
        """Get the DM channel ID for a specific user in Teams."""
        # For Teams, the user_id is typically the conversation ID for DMs
        # Teams handles DM channels differently than Slack
        # The user_id should already be the DM channel ID in Teams
        logger.info(f"Using user_id {user_id} as DM channel for Teams")
        return user_id
    
    def acknowledge_message(self, channel: str, message_ts: str) -> bool:
        """Acknowledge a user's message by sending a brief acknowledgment."""
        # For Teams, we'll send a simple acknowledgment message
        # Since Teams doesn't have reactions like Slack, we use a brief message
        try:
            ack_content = "✅ Processing your request..."
            logger.info(f"Sending acknowledgment to Teams channel {channel}")
            return self.send_message(channel, ack_content)
        except Exception as e:
            logger.error(f"Error sending Teams acknowledgment: {e}")
            return False
    
    def send_temporary_message(self, channel: str, content: str, original_message_ts: str = None) -> Optional[str]:
        """Send a temporary message and return a placeholder identifier."""
        try:
            # Format content with square brackets to indicate it's temporary
            formatted_content = f"[{content}]"
            logger.info(f"Sending temporary message to Teams channel {channel}: {formatted_content}")
            
            # For Teams, we'll use a simple message and return a placeholder ID
            # In a real implementation, you'd use the Teams Bot Framework
            # Teams threading is handled differently, but we can still use the original_message_ts for context
            success = self.send_message(channel, formatted_content)
            if success:
                # Return a placeholder ID - in real implementation, you'd get the actual message ID
                return f"teams_temp_{channel}_{hash(formatted_content)}"
            return None
        except Exception as e:
            logger.error(f"Error sending Teams temporary message: {e}")
            return None
    
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
        """Complete a message (placeholder implementation for Teams)."""
        # For Teams, message completion is more complex and depends on the Bot Framework
        # This is a placeholder implementation
        try:
            status_emoji = "✅" if success else "❌"
            status_text = "completed successfully" if success else "failed"
            logger.info(f"Teams message {message_ts} {status_text} - would show {status_emoji}")
            # In a real implementation, you'd use the Teams Bot Framework to update the message
            # For now, we'll just log the completion status
            return True
        except Exception as e:
            logger.error(f"Error completing Teams message: {e}")
            return False
    
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
