"""Abstract storage interface for Avito AI Auto-Responder."""

from abc import ABC, abstractmethod
from typing import Optional

from app.models.domain import (
    ChatMessage,
    DialogLog,
    Project,
    ProjectFile,
    StoredMessage,
)


class StorageInterface(ABC):
    """Abstract interface for storage implementations.
    
    Allows migration from SQLite to PostgreSQL/Supabase later.
    """

    # Event processing methods
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

    # Message methods
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

    # Project CRUD methods
    @abstractmethod
    async def list_projects(self) -> list[Project]:
        """List all projects.
        
        Returns:
            List of all projects.
        """
        ...

    @abstractmethod
    async def get_project(self, project_id: int) -> Optional[Project]:
        """Get a project by ID.
        
        Args:
            project_id: The project ID.
            
        Returns:
            The project or None if not found.
        """
        ...

    @abstractmethod
    async def create_project(self, project: Project) -> Project:
        """Create a new project.
        
        Args:
            project: The project to create.
            
        Returns:
            The created project with ID.
        """
        ...

    @abstractmethod
    async def update_project(self, project: Project) -> Project:
        """Update an existing project.
        
        Args:
            project: The project to update (must have ID).
            
        Returns:
            The updated project.
        """
        ...

    @abstractmethod
    async def delete_project(self, project_id: int) -> None:
        """Delete a project.
        
        Args:
            project_id: The project ID to delete.
        """
        ...

    # Project files methods
    @abstractmethod
    async def list_project_files(self, project_id: int) -> list[ProjectFile]:
        """List all files for a project.
        
        Args:
            project_id: The project ID.
            
        Returns:
            List of project files.
        """
        ...

    @abstractmethod
    async def save_project_file(self, file: ProjectFile) -> ProjectFile:
        """Save a project file record.
        
        Args:
            file: The file to save.
            
        Returns:
            The saved file.
        """
        ...

    @abstractmethod
    async def delete_project_file(self, file_id: str) -> None:
        """Delete a project file record.
        
        Args:
            file_id: The file ID to delete.
        """
        ...

    # Chat history methods (for test chat in admin panel)
    @abstractmethod
    async def get_project_chat_history(
        self, project_id: int, limit: int = 50
    ) -> list[ChatMessage]:
        """Get chat history for a project's test chat.
        
        Args:
            project_id: The project ID.
            limit: Maximum number of messages to retrieve.
            
        Returns:
            List of chat messages ordered by created_at ascending.
        """
        ...

    @abstractmethod
    async def save_chat_message(self, message: ChatMessage) -> ChatMessage:
        """Save a chat message to the test chat history.
        
        Args:
            message: The message to save.
            
        Returns:
            The saved message with ID.
        """
        ...

    @abstractmethod
    async def clear_project_chat_history(self, project_id: int) -> None:
        """Clear all chat history for a project.
        
        Args:
            project_id: The project ID.
        """
        ...

    # Project lookup methods
    @abstractmethod
    async def get_project_by_avito_user_id(self, avito_user_id: str) -> Optional[Project]:
        """Get a project by Avito user ID.
        
        Args:
            avito_user_id: The Avito user ID associated with the project.
            
        Returns:
            The project or None if not found.
        """
        ...

    # Dialog logs methods (for statistics)
    @abstractmethod
    async def get_dialog_logs(
        self,
        project_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[DialogLog]:
        """Get dialog logs with optional filtering.
        
        Args:
            project_id: Filter by project ID (optional).
            status: Filter by found_status (optional).
            limit: Maximum number of logs to retrieve.
            
        Returns:
            List of dialog logs ordered by created_at descending.
        """
        ...
