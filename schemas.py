"""
Database Schemas for the Travel Assistant App

Each Pydantic model represents a MongoDB collection. The collection name is the
lowercased class name. Example: class UserProfile -> collection "userprofile".
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class UserProfile(BaseModel):
    user_id: str = Field(..., description="Anonymous ID for the user (client-side generated)")
    name: Optional[str] = Field(None)
    email: Optional[str] = Field(None)
    language: str = Field("auto", description="preferred language: auto/en/hi")
    coins: int = Field(0, ge=0)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChatMessage(BaseModel):
    user_id: str
    role: str = Field(..., description="user or assistant")
    content: str
    meta: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


class RewardLedger(BaseModel):
    user_id: str
    action: str = Field(..., description="earn_source like ad, daily_login, task, referral, upload_content")
    coins: int = Field(...)
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class PremiumPass(BaseModel):
    user_id: str
    feature: str = Field(..., description="premium feature key")
    expires_at: datetime
    created_at: Optional[datetime] = None


class VaultDocument(BaseModel):
    user_id: str
    filename: str
    filetype: str
    size: int
    storage_path: str
    created_at: Optional[datetime] = None


# Lightweight tip schema for reference (tips are generated, not stored persistently by default)
class DailyTip(BaseModel):
    title: str
    body: str
    locale: str = "en"
