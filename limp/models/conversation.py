"""
Conversation and message models for chat history.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from datetime import datetime

from .base import Base


class Conversation(Base):
    """Conversation context per user."""
    
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    channel_id = Column(String, nullable=True, index=True)  # Channel identifier (Slack channel, Teams channel, etc.)
    thread_id = Column(String, nullable=True, index=True)  # Thread identifier (Slack thread_ts, Teams conversation_id, etc.)
    context = Column(JSON, nullable=True)  # Additional context data
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Conversation(id={self.id}, user_id={self.user_id})>"


class Message(Base):
    """Individual message in a conversation."""
    
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)  # 'user', 'assistant', 'system', 'tool_request', 'tool_response', 'summary'
    content = Column(Text, nullable=False)
    external_id = Column(String, nullable=True)  # Unique identifier from external system
    message_metadata = Column(JSON, nullable=True)  # Additional message metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Index for external_id to support duplicate detection
    __table_args__ = (
        Index('ix_messages_external_id', 'external_id'),
    )
    
    # Relationship
    conversation = relationship("Conversation", back_populates="messages")
    
    def __repr__(self):
        return f"<Message(id={self.id}, role='{self.role}', conversation_id={self.conversation_id})>"
