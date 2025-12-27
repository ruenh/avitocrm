"""Abstract storage interface for Avito AI Auto-Responder."""

from abc import ABC, abstractmethod

from app.models.domain import DialogLog, StoredMessage


class StorageInterface(ABC):
    """Abstract interface for storage implementations.
    
    Allows migration from SQLite to PostgreSQL/Supabase later.
    """

    @abstractmethod
    async def is_event_processed(self, event_id: str) -> bool:
        """Check if an event has already been processed.
        
        Args:
            event_id: Unique identifier of the webhook event.
            
        Returns:
            True if the event was already processed, False otherwise.
        """
        ...

    @abstractmethod
    async def mark_event_processed(self, event_id: str) -> None:
        """Mark an event as processed for deduplication.
        
        Args:
            event_id: Unique identifier of the webhook event.
        """
        ...

    @abstractmethod
    async def save_message(self, msg: StoredMessage) -> None:
        """Save a message (incoming or outgoing) to the database.
        
        Args:
            msg: The message to save.
        """
        ...

    @abstractmethod
    async def get_chat_history(
        self, chat_id: str, limit: int = 20
    ) -> list[StoredMessage]:
        """Retrieve chat history for context.
        
        Args:
            chat_id: The chat identifier.
            limit: Maximum number of messages to retrieve (default 20).
            
        Returns:
            List of messages ordered by created_at descending (most recent first).
        """
        ...

    @abstractmethod
    async def save_dialog_log(self, log: DialogLog) -> None:
        """Save a dialog log entry with RAG results.
        
        Args:
            log: The dialog log entry to save.
        """
        ...
