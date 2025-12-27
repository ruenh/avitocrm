"""Pydantic models for Avito webhook payloads."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ChatContext(BaseModel):
    """Context information about the chat (item details)."""

    item_id: Optional[str] = Field(default=None, alias="value")
    item_title: Optional[str] = None

    class Config:
        populate_by_name = True


class MessageContent(BaseModel):
    """Content of a message in webhook payload."""

    id: str
    type: str  # "text" | "system" | "image" | etc.
    text: Optional[str] = None
    created: datetime
    author_id: str

    @property
    def is_system_message(self) -> bool:
        """Check if this is a system message."""
        return self.type == "system"

    @property
    def is_text_message(self) -> bool:
        """Check if this is a text message."""
        return self.type == "text"


class MessagePayload(BaseModel):
    """Payload containing message details."""

    chat_id: str
    user_id: str
    message: MessageContent
    context: Optional[ChatContext] = None

    @property
    def item_id(self) -> Optional[str]:
        """Get item_id from context if available."""
        if self.context:
            return self.context.item_id
        return None


class WebhookPayload(BaseModel):
    """Root webhook payload from Avito.

    Example payload:
    {
        "id": "event-uuid",
        "type": "message",
        "payload": {
            "chat_id": "chat-uuid",
            "user_id": "user-uuid",
            "message": {
                "id": "msg-uuid",
                "type": "text",
                "text": "Hello!",
                "created": "2024-01-01T12:00:00Z",
                "author_id": "author-uuid"
            },
            "context": {
                "value": "item-id-123",
                "item_title": "Product Name"
            }
        }
    }
    """

    id: str  # event_id for deduplication
    type: str  # "message" | "other"
    payload: MessagePayload

    @property
    def event_id(self) -> str:
        """Alias for id (event_id for deduplication)."""
        return self.id

    @property
    def is_message_event(self) -> bool:
        """Check if this is a message event."""
        return self.type == "message"

    @property
    def chat_id(self) -> str:
        """Shortcut to get chat_id from payload."""
        return self.payload.chat_id

    @property
    def message_id(self) -> str:
        """Shortcut to get message_id from payload."""
        return self.payload.message.id

    @property
    def message_text(self) -> Optional[str]:
        """Shortcut to get message text from payload."""
        return self.payload.message.text

    @property
    def author_id(self) -> str:
        """Shortcut to get author_id from payload."""
        return self.payload.message.author_id

    @property
    def item_id(self) -> Optional[str]:
        """Shortcut to get item_id from context."""
        return self.payload.item_id

    @property
    def is_system_message(self) -> bool:
        """Check if the message is a system message."""
        return self.payload.message.is_system_message
