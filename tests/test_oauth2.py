"""
Tests for OAuth2 service.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from limp.services.oauth2 import OAuth2Service
from limp.models.user import User
from limp.models.auth import AuthToken, AuthState


def test_generate_auth_url(test_session):
    """Test generating authorization URL."""
    # Create user
    user = User(external_id="test_user_123", platform="slack")
    test_session.add(user)
    test_session.commit()
    test_session.refresh(user)
    
    # Create OAuth2 service
    oauth2_service = OAuth2Service(test_session)
    
    # Mock system config
    system_config = Mock()
    system_config.name = "test_system"
    system_config.oauth2.client_id = "test_client_id"
    system_config.oauth2.redirect_uri = "http://localhost:8000/callback"
    system_config.oauth2.authorization_url = "https://example.com/oauth/authorize"
    system_config.oauth2.scope = "read write"
    
    # Generate auth URL
    auth_url = oauth2_service.generate_auth_url(user.id, system_config)
    
    # Verify URL contains expected parameters
    assert "https://example.com/oauth/authorize" in auth_url
    assert "client_id=test_client_id" in auth_url
    assert "redirect_uri=http://localhost:8000/callback" in auth_url
    assert "response_type=code" in auth_url
    assert "scope=read write" in auth_url
    assert "state=" in auth_url
    
    # Verify state was saved to database
    auth_states = test_session.query(AuthState).filter(
        AuthState.user_id == user.id
    ).all()
    assert len(auth_states) == 1
    assert auth_states[0].system_name == "test_system"


def test_handle_callback_success(test_session):
    """Test successful callback handling."""
    # Create user
    user = User(external_id="test_user_123", platform="slack")
    test_session.add(user)
    test_session.commit()
    test_session.refresh(user)
    
    # Create auth state
    auth_state = AuthState(
        state="test_state_123",
        user_id=user.id,
        system_name="test_system",
        redirect_uri="http://localhost:8000/callback",
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    test_session.add(auth_state)
    test_session.commit()
    
    # Create OAuth2 service
    oauth2_service = OAuth2Service(test_session)
    
    # Mock token exchange
    with patch.object(oauth2_service, '_exchange_code_for_token') as mock_exchange:
        mock_exchange.return_value = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "read write"
        }
        
        # Handle callback
        auth_token = oauth2_service.handle_callback("test_code", "test_state_123")
        
        # Verify token was created
        assert auth_token is not None
        assert auth_token.user_id == user.id
        assert auth_token.system_name == "test_system"
        assert auth_token.access_token == "test_access_token"
        assert auth_token.refresh_token == "test_refresh_token"
        assert auth_token.token_type == "Bearer"
        
        # Verify auth state was removed
        auth_states = test_session.query(AuthState).filter(
            AuthState.state == "test_state_123"
        ).all()
        assert len(auth_states) == 0


def test_handle_callback_invalid_state(test_session):
    """Test callback with invalid state."""
    # Create user
    user = User(external_id="test_user_123", platform="slack")
    test_session.add(user)
    test_session.commit()
    test_session.refresh(user)
    
    # Create OAuth2 service
    oauth2_service = OAuth2Service(test_session)
    
    # Handle callback with invalid state
    auth_token = oauth2_service.handle_callback("test_code", "invalid_state")
    
    # Verify no token was created
    assert auth_token is None


def test_handle_callback_expired_state(test_session):
    """Test callback with expired state."""
    # Create user
    user = User(external_id="test_user_123", platform="slack")
    test_session.add(user)
    test_session.commit()
    test_session.refresh(user)
    
    # Create expired auth state
    auth_state = AuthState(
        state="test_state_123",
        user_id=user.id,
        system_name="test_system",
        redirect_uri="http://localhost:8000/callback",
        expires_at=datetime.utcnow() - timedelta(minutes=10)  # Expired
    )
    test_session.add(auth_state)
    test_session.commit()
    
    # Create OAuth2 service
    oauth2_service = OAuth2Service(test_session)
    
    # Handle callback with expired state
    auth_token = oauth2_service.handle_callback("test_code", "test_state_123")
    
    # Verify no token was created
    assert auth_token is None


def test_get_valid_token(test_session):
    """Test getting valid token."""
    # Create user
    user = User(external_id="test_user_123", platform="slack")
    test_session.add(user)
    test_session.commit()
    test_session.refresh(user)
    
    # Create valid token
    auth_token = AuthToken(
        user_id=user.id,
        system_name="test_system",
        access_token="test_access_token",
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    test_session.add(auth_token)
    test_session.commit()
    
    # Create OAuth2 service
    oauth2_service = OAuth2Service(test_session)
    
    # Get valid token
    token = oauth2_service.get_valid_token(user.id, "test_system")
    
    # Verify token was returned
    assert token is not None
    assert token.access_token == "test_access_token"


def test_get_valid_token_expired(test_session):
    """Test getting expired token."""
    # Create user
    user = User(external_id="test_user_123", platform="slack")
    test_session.add(user)
    test_session.commit()
    test_session.refresh(user)
    
    # Create expired token
    auth_token = AuthToken(
        user_id=user.id,
        system_name="test_system",
        access_token="test_access_token",
        expires_at=datetime.utcnow() - timedelta(hours=1)  # Expired
    )
    test_session.add(auth_token)
    test_session.commit()
    
    # Create OAuth2 service
    oauth2_service = OAuth2Service(test_session)
    
    # Get expired token
    token = oauth2_service.get_valid_token(user.id, "test_system")
    
    # Verify no token was returned
    assert token is None


def test_get_valid_token_nonexistent(test_session):
    """Test getting token for non-existent user/system."""
    # Create OAuth2 service
    oauth2_service = OAuth2Service(test_session)
    
    # Get token for non-existent user
    token = oauth2_service.get_valid_token(999, "test_system")
    
    # Verify no token was returned
    assert token is None
