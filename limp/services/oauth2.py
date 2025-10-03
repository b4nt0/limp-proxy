"""
OAuth2 authentication service.
"""

import secrets
import requests
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging

from ..models.user import User
from ..models.auth import AuthToken, AuthState
from ..config import OAuth2Config, ExternalSystemConfig

logger = logging.getLogger(__name__)


class OAuth2Service:
    """OAuth2 authentication service."""
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
    
    def generate_auth_url(self, user_id: int, system_config: ExternalSystemConfig) -> str:
        """Generate OAuth2 authorization URL."""
        # Generate state parameter
        state = secrets.token_urlsafe(32)
        
        # Save state to database
        auth_state = AuthState(
            state=state,
            user_id=user_id,
            system_name=system_config.name,
            redirect_uri=system_config.oauth2.redirect_uri,
            expires_at=datetime.utcnow() + timedelta(minutes=10)
        )
        self.db_session.add(auth_state)
        self.db_session.commit()
        
        # Build authorization URL
        params = {
            "client_id": system_config.oauth2.client_id,
            "redirect_uri": system_config.oauth2.redirect_uri,
            "state": state,
            "response_type": "code"
        }
        
        if system_config.oauth2.scope:
            params["scope"] = system_config.oauth2.scope
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{system_config.oauth2.authorization_url}?{query_string}"
    
    def handle_callback(self, code: str, state: str) -> Optional[AuthToken]:
        """Handle OAuth2 callback and exchange code for token."""
        # Find auth state
        auth_state = self.db_session.query(AuthState).filter(
            AuthState.state == state,
            AuthState.expires_at > datetime.utcnow()
        ).first()
        
        if not auth_state:
            logger.error(f"Invalid or expired auth state: {state}")
            return None
        
        # Exchange code for token
        token_data = self._exchange_code_for_token(code, auth_state)
        if not token_data:
            return None
        
        # Save token to database
        auth_token = AuthToken(
            user_id=auth_state.user_id,
            system_name=auth_state.system_name,
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_type=token_data.get("token_type", "Bearer"),
            expires_at=self._parse_expires_at(token_data.get("expires_in")),
            scope=token_data.get("scope")
        )
        
        # Remove old tokens for this user/system
        self.db_session.query(AuthToken).filter(
            AuthToken.user_id == auth_state.user_id,
            AuthToken.system_name == auth_state.system_name
        ).delete()
        
        self.db_session.add(auth_token)
        self.db_session.delete(auth_state)
        self.db_session.commit()
        
        return auth_token
    
    def get_valid_token(self, user_id: int, system_name: str) -> Optional[AuthToken]:
        """Get valid OAuth2 token for user and system."""
        token = self.db_session.query(AuthToken).filter(
            AuthToken.user_id == user_id,
            AuthToken.system_name == system_name,
            AuthToken.expires_at > datetime.utcnow()
        ).first()
        
        if not token:
            return None
        
        # Check if token needs refresh
        if token.refresh_token and self._should_refresh_token(token):
            refreshed_token = self._refresh_token(token)
            if refreshed_token:
                return refreshed_token
        
        return token
    
    def validate_token(self, token: AuthToken, system_config: ExternalSystemConfig) -> bool:
        """Validate OAuth2 token using test endpoint or introspection."""
        if not token:
            return False
        
        # If token is expired, it's invalid
        if token.expires_at and token.expires_at <= datetime.utcnow():
            return False
        
        # Try to validate using test endpoint or introspection
        test_endpoint = system_config.oauth2.test_endpoint
        if not test_endpoint:
            # Use heuristic: replace last URL component with "/introspect"
            auth_url = system_config.oauth2.authorization_url
            if auth_url.endswith('/'):
                auth_url = auth_url[:-1]
            test_endpoint = '/'.join(auth_url.split('/')[:-1]) + "/introspect"
        
        try:
            # Try introspection endpoint first
            if self._validate_with_introspection(token, test_endpoint):
                return True
        except Exception as e:
            logger.warning(f"Introspection validation failed: {e}")
        
        # Fallback: try a simple test request to base_url
        try:
            return self._validate_with_test_request(token, system_config.base_url)
        except Exception as e:
            logger.warning(f"Test request validation failed: {e}")
            return False
    
    def _validate_with_introspection(self, token: AuthToken, introspection_url: str) -> bool:
        """Validate token using OAuth2 introspection endpoint."""
        try:
            response = requests.post(
                introspection_url,
                data={
                    "token": token.access_token,
                    "token_type_hint": "access_token"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            # Check if token is active
            return result.get("active", False)
        except Exception as e:
            logger.error(f"Introspection request failed: {e}")
            return False
    
    def _validate_with_test_request(self, token: AuthToken, base_url: str) -> bool:
        """Validate token by making a test request to the base URL."""
        try:
            # Try a simple GET request to the base URL
            headers = {
                "Authorization": f"{token.token_type} {token.access_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(
                base_url,
                headers=headers,
                timeout=10
            )
            
            # Consider 200-299 and 401 as valid responses (401 means token is invalid)
            return response.status_code < 500
        except Exception as e:
            logger.error(f"Test request failed: {e}")
            return False
    
    def _exchange_code_for_token(self, code: str, auth_state: AuthState) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for access token."""
        # Find system config (this would come from config in real implementation)
        # For now, we'll use a placeholder
        system_config = None  # This should be loaded from config
        
        if not system_config:
            logger.error("System configuration not found")
            return None
        
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": auth_state.redirect_uri,
            "client_id": system_config.oauth2.client_id,
            "client_secret": system_config.oauth2.client_secret
        }
        
        try:
            response = requests.post(
                system_config.oauth2.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to exchange code for token: {e}")
            return None
    
    def _refresh_token(self, token: AuthToken) -> Optional[AuthToken]:
        """Refresh OAuth2 token."""
        # Implementation would refresh the token using refresh_token
        # For now, return None to indicate refresh failed
        logger.warning("Token refresh not implemented")
        return None
    
    def _should_refresh_token(self, token: AuthToken) -> bool:
        """Check if token should be refreshed."""
        if not token.expires_at:
            return False
        
        # Refresh if expires within 5 minutes
        return token.expires_at <= datetime.utcnow() + timedelta(minutes=5)
    
    def _parse_expires_at(self, expires_in: Optional[int]) -> Optional[datetime]:
        """Parse expires_in seconds to datetime."""
        if not expires_in:
            return None
        
        return datetime.utcnow() + timedelta(seconds=expires_in)

