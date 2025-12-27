"""Domain models for Avito AI Auto-Responder."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class StoredMessage(BaseModel):
    """Represents a message stored in the local database."""

    id: Optional[int] = None
    chat_id: str
    message_id: Optional[str] = None
    sender_id: str
    text: Optional[str] = None
    is_bot_message: bool = False
    item_id: Optional[str] = None
    created_at: datetime


class DialogLog(BaseModel):
    """Represents a dialog log entry with RAG results."""

    id: Optional[int] = None
    chat_id: str
    item_id: Optional[str] = None
    project_id: Optional[int] = None
    customer_question: str
    bot_answer: str
    found_status: Literal["FOUND", "NOT_FOUND", "ESCALATION"]
    sources: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


# Admin Panel Models

class Project(BaseModel):
    """Represents a project in the admin panel."""

    id: Optional[int] = None
    name: str
    description: str = ""
    filesearch_store_id: Optional[str] = None
    avito_client_id: Optional[str] = None
    avito_client_secret: Optional[str] = None
    avito_user_id: Optional[str] = None
    avito_connected: bool = False
    webhook_registered: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectFile(BaseModel):
    """Represents a file in a project's FileSearch store."""

    id: str  # Gemini file ID
    project_id: int
    name: str
    size: int
    item_id: Optional[str] = None
    uploaded_at: Optional[datetime] = None


class ChatMessage(BaseModel):
    """Represents a chat message in the test chat interface."""

    id: Optional[int] = None
    project_id: int
    role: Literal["user", "assistant"]
    content: str
    sources: list[str] = Field(default_factory=list)
    found_status: Optional[str] = None
    created_at: Optional[datetime] = None


class DashboardStats(BaseModel):
    """Statistics for the admin dashboard."""

    total_messages: int = 0
    total_responses: int = 0
    total_escalations: int = 0
    messages_today: int = 0
    found_rate: float = 0.0  # Percentage of responses with found information
    projects_count: int = 0


class ProjectStats(BaseModel):
    """Statistics for a specific project."""

    project_id: int
    total_messages: int = 0
    total_responses: int = 0
    total_escalations: int = 0
    found_rate: float = 0.0
