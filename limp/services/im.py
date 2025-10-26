"""
Abstract base class for instant messaging services.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
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


class IMServiceFactory:
    """Factory for creating IM services."""
    
    @staticmethod
    def create_service(platform: str, config: Dict[str, Any]) -> IMService:
        """Create IM service based on platform."""
        if platform.lower() == "slack":
            from .slack import SlackService
            return SlackService(
                client_id=config["client_id"],
                client_secret=config["client_secret"],
                signing_secret=config.get("signing_secret", ""),
                bot_token=config.get("bot_token"),
                app_id=config.get("app_id")
            )
        elif platform.lower() == "teams":
            from .teams import TeamsService
            return TeamsService(
                app_id=config["app_id"],
                client_id=config["client_id"],
                client_secret=config["client_secret"]
            )
        else:
            raise ValueError(f"Unsupported platform: {platform}")

