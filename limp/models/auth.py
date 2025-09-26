"""
Authentication models for OAuth2 tokens and states.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from .base import Base


class AuthToken(Base):
    """OAuth2 token storage for external systems."""
    
    __tablename__ = "auth_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    system_name = Column(String, nullable=False)  # Name of the external system
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    token_type = Column(String, default="Bearer")
    expires_at = Column(DateTime, nullable=True)
    scope = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = relationship("User", back_populates="auth_tokens")
    
    def __repr__(self):
        return f"<AuthToken(id={self.id}, user_id={self.user_id}, system='{self.system_name}')>"


class AuthState(Base):
    """OAuth2 authorization state for handling callbacks."""
    
    __tablename__ = "auth_states"
    
    id = Column(Integer, primary_key=True, index=True)
    state = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    system_name = Column(String, nullable=False)
    redirect_uri = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    
    # Relationship
    user = relationship("User", back_populates="auth_states")
    
    def __repr__(self):
        return f"<AuthState(id={self.id}, state='{self.state}', user_id={self.user_id})>"
