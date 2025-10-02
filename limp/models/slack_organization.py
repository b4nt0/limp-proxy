"""
Slack organization model for storing OAuth2 installation data.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from datetime import datetime

from .base import Base


class SlackOrganization(Base):
    """Slack organization model for OAuth2 installation data."""
    
    __tablename__ = "slack_organizations"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(String, unique=True, index=True, nullable=False)  # Team ID where bot was installed
    access_token = Column(Text, nullable=False)  # Bot access token
    token_type = Column(String, default="bot", nullable=False)  # Token type (bot/user)
    scope = Column(Text, nullable=True)  # Granted scopes
    bot_user_id = Column(String, nullable=True)  # Bot user ID
    app_id = Column(String, nullable=True)  # App ID
    
    # Team information
    team_id = Column(String, nullable=True)
    team_name = Column(String, nullable=True)
    
    # Enterprise information (if applicable)
    enterprise_id = Column(String, nullable=True)
    enterprise_name = Column(String, nullable=True)
    
    # Authed user data (the user who installed the app)
    authed_user_id = Column(String, nullable=True)
    authed_user_access_token = Column(Text, nullable=True)
    authed_user_token_type = Column(String, nullable=True)
    authed_user_scope = Column(Text, nullable=True)
    
    # Installation metadata
    installed_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<SlackOrganization(id={self.id}, organization_id='{self.organization_id}', team_name='{self.team_name}')>"

