"""
Instant messaging service for Slack and Teams integration.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import logging
import requests

from ..config import get_config

logger = logging.getLogger(__name__)


class IMService(ABC):
    """Abstract base class for instant messaging services."""
    
    @abstractmethod
    def verify_request(self, request_data: Dict[str, Any]) -> bool:
        """Verify incoming request from IM platform."""
        pass
    
    @abstractmethod
    def parse_message(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse message from IM platform."""
        pass
    
    @abstractmethod
    def format_response(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Format response for IM platform."""
        pass
    
    @abstractmethod
    def send_message(self, channel: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Send message to IM platform."""
        pass
    
    @abstractmethod
    def reply_to_message(self, channel: str, content: str, original_message_ts: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Reply to a specific message in the IM platform."""
        pass
    
    @abstractmethod
    def create_authorization_button(self, auth_url: str, button_text: str, button_description: str, request=None) -> List[Dict[str, Any]]:
        """Create authorization button blocks for the IM platform."""
        pass
    
    @abstractmethod
    def get_user_dm_channel(self, user_id: str) -> str:
        """Get the DM channel ID for a specific user."""
        pass
    
    @abstractmethod
    def acknowledge_message(self, channel: str, message_ts: str) -> bool:
        """Acknowledge a user's message (e.g., add reaction)."""
        pass
    
    @abstractmethod
    def send_temporary_message(self, channel: str, content: str, original_message_ts: str = None) -> Optional[str]:
        """Send a temporary message and return its identifier for later cleanup."""
        pass
    
    @abstractmethod
    def cleanup_temporary_messages(self, channel: str, message_ids: List[str]) -> bool:
        """Clean up temporary messages by their identifiers."""
        pass
    
    @abstractmethod
    def complete_message(self, channel: str, message_ts: str, success: bool) -> bool:
        """Complete a message by updating the reaction based on success/failure."""
        pass
    


class SlackService(IMService):
    """Slack integration service."""
    
    def __init__(self, client_id: str, client_secret: str, signing_secret: str, bot_token: Optional[str] = None, app_id: Optional[str] = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.signing_secret = signing_secret
        self.bot_token = bot_token
        self.app_id = app_id
    
    def verify_request(self, request_data: Dict[str, Any]) -> bool:
        """Verify Slack request using signing secret."""
        # Implementation would verify the request signature
        # For now, return True as placeholder
        return True
    
    def parse_message(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Slack message."""
        if request_data.get("type") == "url_verification":
            return {
                "type": "challenge",
                "challenge": request_data.get("challenge")
            }
        
        if request_data.get("type") == "event_callback":
            event = request_data.get("event", {})
            
            # Ignore messages from our own bot to prevent infinite loops
            # Only ignore if event has app_id and it matches our app_id
            if self.app_id and event.get("app_id") == self.app_id:
                logger.info(f"Ignoring message from own app_id: {self.app_id}")
                return {"type": "ignored"}
            
            # Handle both message and app_mention events
            # Skip messages from other bots (but not our own, which we already filtered above)
            if event.get("type") in ["message", "app_mention"] and not event.get("bot_id"):
                return {
                    "type": "message",
                    "user_id": event.get("user"),
                    "channel": event.get("channel") or request_data.get("channel"),
                    "text": event.get("text"),
                    "timestamp": event.get("ts"),
                    "thread_ts": event.get("thread_ts"),  # Thread timestamp for replies
                    "team_id": request_data.get("team_id")  # Team/organization ID for duplicate detection
                }
        
        return {"type": "unknown"}
    
    def format_response(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Format response for Slack."""
        response = {
            "text": content,
            "response_type": "in_channel"
        }
        
        if metadata and metadata.get("blocks"):
            response["blocks"] = metadata["blocks"]
        
        return response
    
    def send_message(self, channel: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Send message to Slack channel."""
        if not self.bot_token:
            logger.error("No bot token available for Slack message")
            return False
        
        try:
            # Prepare the message payload
            payload = {
                "channel": channel,
                "text": content
            }
            
            # Add blocks if provided in metadata
            if metadata and metadata.get("blocks"):
                payload["blocks"] = metadata["blocks"]
            
            # Send the message using synchronous requests
            try:
                logger.debug(f"Sending message to Slack channel {channel}: {payload}")
                response = requests.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=10
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("ok"):
                    logger.info(f"Successfully sent message to Slack channel {channel}")
                    return True
                else:
                    logger.error(f"Slack API error: {result.get('error')}")
                    return False
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"HTTP error sending Slack message: {e}")
                return False
            
        except Exception as e:
            logger.error(f"Error sending Slack message: {e}")
            return False
    
    def reply_to_message(self, channel: str, content: str, original_message_ts: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Reply to a message in Slack - always use threads when possible."""
        if not self.bot_token:
            logger.error("No bot token available for Slack reply")
            return False
        
        try:
            # Prepare the message payload
            # Always use thread_ts to create a threaded reply, even for DMs
            payload = {
                "channel": channel,
                "text": content,
                "thread_ts": original_message_ts  # This creates a threaded reply
            }
            
            # Add blocks if provided in metadata
            if metadata and metadata.get("blocks"):
                payload["blocks"] = metadata["blocks"]
            
            # Send the threaded reply using synchronous requests
            try:
                response = requests.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=10
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("ok"):
                    logger.info(f"Successfully sent threaded reply to Slack message {original_message_ts}")
                    return True
                else:
                    logger.error(f"Slack API error: {result.get('error')}")
                    return False
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"HTTP error sending Slack reply: {e}")
                return False
            
        except Exception as e:
            logger.error(f"Error sending Slack reply: {e}")
            return False
    
    def create_authorization_button(self, auth_url: str, button_text: str, button_description: str, request=None) -> List[Dict[str, Any]]:
        """Create authorization button blocks for Slack."""
        # Check if URL is localhost (Slack doesn't like localhost URLs in buttons)
        is_localhost = "localhost" in auth_url or "127.0.0.1" in auth_url
        
        if is_localhost:
            # Use hyperlink for localhost URLs
            return [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{button_description}\n\n:arrow_right: <{auth_url}|*{button_text}*>"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": ":computer: Click the link above to open authorization in your browser"
                        }
                    ]
                }
            ]
        else:
            # Use button for non-localhost URLs
            return [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{button_description}\n\n🔒 Click the button below to authorize:"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": f"🔐 {button_text}"
                            },
                            "url": auth_url,
                            "style": "primary"
                        }
                    ]
                }
            ]
    
    def get_user_dm_channel(self, user_id: str) -> str:
        """Get the DM channel ID for a specific user in Slack."""
        if not self.bot_token:
            logger.error("No bot token available for getting user DM channel")
            return user_id  # Fallback to user_id if no token
        
        try:
            # Use Slack's conversations.open API to get or create a DM channel
            response = requests.post(
                "https://slack.com/api/conversations.open",
                headers={
                    "Authorization": f"Bearer {self.bot_token}",
                    "Content-Type": "application/json"
                },
                json={"users": user_id},
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("ok"):
                channel_id = result.get("channel", {}).get("id")
                if channel_id:
                    logger.info(f"Got DM channel {channel_id} for user {user_id}")
                    return channel_id
                else:
                    logger.error("No channel ID in Slack response")
                    return user_id  # Fallback
            else:
                logger.error(f"Slack API error getting DM channel: {result.get('error')}")
                return user_id  # Fallback
                
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error getting Slack DM channel: {e}")
            return user_id  # Fallback
        except Exception as e:
            logger.error(f"Error getting Slack DM channel: {e}")
            return user_id  # Fallback
    
    def acknowledge_message(self, channel: str, message_ts: str) -> bool:
        """Acknowledge a user's message by adding a thinking emoji reaction."""
        if not self.bot_token:
            logger.error("No bot token available for Slack reaction")
            return False
        
        try:
            response = requests.post(
                "https://slack.com/api/reactions.add",
                headers={
                    "Authorization": f"Bearer {self.bot_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "channel": channel,
                    "timestamp": message_ts,
                    "name": "thinking_face"  # Thinking emoji
                },
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("ok"):
                logger.info(f"Successfully added thinking reaction to Slack message {message_ts}")
                return True
            else:
                logger.error(f"Slack API error adding reaction: {result.get('error')}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error adding Slack reaction: {e}")
            return False
        except Exception as e:
            logger.error(f"Error adding Slack reaction: {e}")
            return False
    
    def send_temporary_message(self, channel: str, content: str, original_message_ts: str = None) -> Optional[str]:
        """Send a temporary message with content in square brackets and return message timestamp."""
        if not self.bot_token:
            logger.error("No bot token available for Slack temporary message")
            return None
        
        try:
            # Format content with square brackets to indicate it's temporary
            formatted_content = f"[{content}]"
            
            payload = {
                "channel": channel,
                "text": formatted_content
            }
            
            # If we have the original message timestamp, use it for threading
            if original_message_ts:
                payload["thread_ts"] = original_message_ts
            
            response = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {self.bot_token}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("ok"):
                message_ts = result.get("ts")
                logger.info(f"Successfully sent temporary message to Slack channel {channel}: {message_ts}")
                return message_ts
            else:
                logger.error(f"Slack API error sending temporary message: {result.get('error')}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error sending Slack temporary message: {e}")
            return None
        except Exception as e:
            logger.error(f"Error sending Slack temporary message: {e}")
            return None
    
    def cleanup_temporary_messages(self, channel: str, message_ids: List[str]) -> bool:
        """Clean up temporary messages by deleting them."""
        if not self.bot_token:
            logger.error("No bot token available for Slack message cleanup")
            return False
        
        success_count = 0
        for message_ts in message_ids:
            try:
                response = requests.post(
                    "https://slack.com/api/chat.delete",
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "channel": channel,
                        "ts": message_ts
                    },
                    timeout=10
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("ok"):
                    logger.info(f"Successfully deleted temporary Slack message {message_ts}")
                    success_count += 1
                else:
                    logger.error(f"Slack API error deleting message {message_ts}: {result.get('error')}")
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"HTTP error deleting Slack message {message_ts}: {e}")
            except Exception as e:
                logger.error(f"Error deleting Slack message {message_ts}: {e}")
        
        return success_count > 0
    
    def complete_message(self, channel: str, message_ts: str, success: bool) -> bool:
        """Complete a message by removing thinking emoji and adding success/failure emoji."""
        if not self.bot_token:
            logger.error("No bot token available for Slack message completion")
            return False
        
        try:
            # First, remove the thinking_face emoji
            remove_response = requests.post(
                "https://slack.com/api/reactions.remove",
                headers={
                    "Authorization": f"Bearer {self.bot_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "channel": channel,
                    "timestamp": message_ts,
                    "name": "thinking_face"
                },
                timeout=10
            )
            remove_response.raise_for_status()
            remove_result = remove_response.json()
            
            # Log the removal attempt (don't fail if thinking emoji wasn't there)
            if remove_result.get("ok"):
                logger.info(f"Successfully removed thinking reaction from Slack message {message_ts}")
            else:
                logger.debug(f"Thinking reaction removal result: {remove_result.get('error', 'unknown')}")
            
            # Add the appropriate completion emoji
            emoji_name = "white_check_mark" if success else "x"
            emoji_display = "green checkmark" if success else "red X"
            
            add_response = requests.post(
                "https://slack.com/api/reactions.add",
                headers={
                    "Authorization": f"Bearer {self.bot_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "channel": channel,
                    "timestamp": message_ts,
                    "name": emoji_name
                },
                timeout=10
            )
            add_response.raise_for_status()
            add_result = add_response.json()
            
            if add_result.get("ok"):
                logger.info(f"Successfully added {emoji_display} reaction to Slack message {message_ts}")
                return True
            else:
                logger.error(f"Slack API error adding completion reaction: {add_result.get('error')}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error completing Slack message: {e}")
            return False
        except Exception as e:
            logger.error(f"Error completing Slack message: {e}")
            return False


class TeamsService(IMService):
    """Microsoft Teams integration service."""
    
    def __init__(self, app_id: str, client_id: str, client_secret: str):
        self.app_id = app_id
        self.client_id = client_id
        self.client_secret = client_secret
    
    def verify_request(self, request_data: Dict[str, Any]) -> bool:
        """Verify Teams request."""
        # Implementation would verify the request
        # For now, return True as placeholder
        return True
    
    def parse_message(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Teams message."""
        if request_data.get("type") == "message":
            return {
                "type": "message",
                "user_id": request_data.get("from", {}).get("id"),
                "channel": request_data.get("conversation", {}).get("id"),
                "text": request_data.get("text"),
                "timestamp": request_data.get("timestamp")
            }
        
        return {"type": "unknown"}
    
    def format_response(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Format response for Teams."""
        response = {
            "type": "message",
            "text": content
        }
        
        if metadata and metadata.get("attachments"):
            response["attachments"] = metadata["attachments"]
        
        return response
    
    def send_message(self, channel: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Send message to Teams channel."""
        # Implementation would use Teams Bot Framework
        # For now, return True as placeholder
        logger.info(f"Sending message to Teams channel {channel}: {content}")
        return True
    
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


class IMServiceFactory:
    """Factory for creating IM services."""
    
    @staticmethod
    def create_service(platform: str, config: Dict[str, Any]) -> IMService:
        """Create IM service based on platform."""
        if platform.lower() == "slack":
            return SlackService(
                client_id=config["client_id"],
                client_secret=config["client_secret"],
                signing_secret=config.get("signing_secret", ""),
                bot_token=config.get("bot_token"),
                app_id=config.get("app_id")
            )
        elif platform.lower() == "teams":
            return TeamsService(
                app_id=config["app_id"],
                client_id=config["client_id"],
                client_secret=config["client_secret"]
            )
        else:
            raise ValueError(f"Unsupported platform: {platform}")

