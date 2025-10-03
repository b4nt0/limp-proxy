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
    system_config.oauth2.authorization_url = "https://example.com/oauth/authorize"
    system_config.oauth2.scope = "read write"
    
    # Generate auth URL
    bot_url = "https://example.com"
    auth_url = oauth2_service.generate_auth_url(user.id, system_config, bot_url)
    
    # Verify URL contains expected parameters
    assert "https://example.com/oauth/authorize" in auth_url
    assert "client_id=test_client_id" in auth_url
    assert f"redirect_uri={bot_url}/api/oauth2/callback/{system_config.name}" in auth_url
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


def test_validate_token_with_test_endpoint(test_session):
    """Test token validation using configured test endpoint."""
    # Create OAuth2 service
    oauth2_service = OAuth2Service(test_session)
    
    # Mock system config with test endpoint
    mock_system_config = Mock()
    mock_system_config.oauth2.test_endpoint = "https://example.com/oauth/introspect"
    mock_system_config.base_url = "https://example.com/api"
    
    # Mock token
    mock_token = Mock()
    mock_token.access_token = "test_token"
    mock_token.token_type = "Bearer"
    mock_token.expires_at = datetime.utcnow() + timedelta(hours=1)
    
    # Mock introspection response
    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.json.return_value = {"active": True}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        result = oauth2_service.validate_token(mock_token, mock_system_config)
        
        assert result is True
        mock_post.assert_called_once_with(
            "https://example.com/oauth/introspect",
            data={
                "token": "test_token",
                "token_type_hint": "access_token"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10
        )


def test_validate_token_with_heuristic_endpoint(test_session):
    """Test token validation using heuristic endpoint."""
    # Create OAuth2 service
    oauth2_service = OAuth2Service(test_session)
    
    # Mock system config without test endpoint
    mock_system_config = Mock()
    mock_system_config.oauth2.test_endpoint = None
    mock_system_config.oauth2.authorization_url = "https://example.com/oauth/authorize"
    mock_system_config.base_url = "https://example.com/api"
    
    # Mock token
    mock_token = Mock()
    mock_token.access_token = "test_token"
    mock_token.token_type = "Bearer"
    mock_token.expires_at = datetime.utcnow() + timedelta(hours=1)
    
    # Mock introspection response
    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.json.return_value = {"active": True}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        result = oauth2_service.validate_token(mock_token, mock_system_config)
        
        assert result is True
        # Should use heuristic endpoint
        mock_post.assert_called_once_with(
            "https://example.com/oauth/introspect",
            data={
                "token": "test_token",
                "token_type_hint": "access_token"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10
        )


def test_validate_token_expired(test_session):
    """Test token validation with expired token."""
    # Create OAuth2 service
    oauth2_service = OAuth2Service(test_session)
    
    # Mock system config
    mock_system_config = Mock()
    mock_system_config.oauth2.test_endpoint = "https://example.com/oauth/introspect"
    mock_system_config.base_url = "https://example.com/api"
    
    # Mock expired token
    mock_token = Mock()
    mock_token.expires_at = datetime.utcnow() - timedelta(hours=1)  # Expired
    
    result = oauth2_service.validate_token(mock_token, mock_system_config)
    
    assert result is False


def test_validate_token_introspection_fallback(test_session):
    """Test token validation with introspection failure and test request fallback."""
    # Create OAuth2 service
    oauth2_service = OAuth2Service(test_session)
    
    # Mock system config
    mock_system_config = Mock()
    mock_system_config.oauth2.test_endpoint = "https://example.com/oauth/introspect"
    mock_system_config.base_url = "https://example.com/api"
    
    # Mock token
    mock_token = Mock()
    mock_token.access_token = "test_token"
    mock_token.token_type = "Bearer"
    mock_token.expires_at = datetime.utcnow() + timedelta(hours=1)
    
    # Mock introspection failure and test request success
    with patch('requests.post') as mock_post, patch('requests.get') as mock_get:
        # Introspection fails
        mock_post.side_effect = Exception("Introspection failed")
        
        # Test request succeeds
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = oauth2_service.validate_token(mock_token, mock_system_config)
        
        assert result is True
        mock_get.assert_called_once_with(
            "https://example.com/api",
            headers={
                "Authorization": "Bearer test_token",
                "Content-Type": "application/json"
            },
            timeout=10
        )
