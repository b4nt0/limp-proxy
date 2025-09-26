"""
Instant messaging service for Slack and Teams integration.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

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


class SlackService(IMService):
    """Slack integration service."""
    
    def __init__(self, client_id: str, client_secret: str, signing_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.signing_secret = signing_secret
    
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
            if event.get("type") == "message" and not event.get("bot_id"):
                return {
                    "type": "message",
                    "user_id": event.get("user"),
                    "channel": event.get("channel"),
                    "text": event.get("text"),
                    "timestamp": event.get("ts")
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


class IMServiceFactory:
    """Factory for creating IM services."""
    
    @staticmethod
    def create_service(platform: str, config: Dict[str, Any]) -> IMService:
        """Create IM service based on platform."""
        if platform.lower() == "slack":
            return SlackService(
                client_id=config["client_id"],
                client_secret=config["client_secret"],
                signing_secret=config.get("signing_secret", "")
            )
        elif platform.lower() == "teams":
            return TeamsService(
                app_id=config["app_id"],
                client_id=config["client_id"],
                client_secret=config["client_secret"]
            )
        else:
            raise ValueError(f"Unsupported platform: {platform}")

