"""
Instant messaging service for Slack and Teams integration.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging
import requests

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
                    "thread_ts": event.get("thread_ts")  # Thread timestamp for replies
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
        # Implementation would use Slack Web API
        # For now, return True as placeholder
        logger.info(f"Sending message to Slack channel {channel}: {content}")
        return True
    
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

