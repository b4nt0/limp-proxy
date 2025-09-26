"""
User model for external chat users.
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime

from .base import Base


class User(Base):
    """External chat user model."""
    
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True, nullable=False)
    platform = Column(String, nullable=False)  # 'slack' or 'teams'
    username = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    auth_tokens = relationship("AuthToken", back_populates="user", cascade="all, delete-orphan")
    auth_states = relationship("AuthState", back_populates="user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, external_id='{self.external_id}', platform='{self.platform}')>"
