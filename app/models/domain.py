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

    chat_id: str
    item_id: Optional[str] = None
    customer_question: str
    bot_answer: str
    found_status: Literal["FOUND", "NOT_FOUND", "ESCALATION"]
    sources: list[str] = Field(default_factory=list)
