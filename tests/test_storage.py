"""Tests for SQLite storage implementation."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from app.models.domain import ChatMessage, DialogLog, Project, ProjectFile, StoredMessage
from app.storage.sqlite import SQLiteStorage


@pytest.fixture
async def storage():
    """Create a temporary SQLite storage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = SQLiteStorage(str(db_path))
        yield storage


class TestSQLiteStorage:
    """Tests for SQLiteStorage class."""

    async def test_database_initialization(self, storage: SQLiteStorage):
        """Test that database schema is created on first use."""
        # Trigger initialization by calling any method
        result = await storage.is_event_processed("test_event")
        
        assert result is False
        assert storage._initialized is True
        assert Path(storage.database_path).exists()

    async def test_event_deduplication(self, storage: SQLiteStorage):
        """Test event processing and deduplication."""
        event_id = "event_123"
        
        # Event should not be processed initially
        assert await storage.is_event_processed(event_id) is False
        
        # Mark as processed
        await storage.mark_event_processed(event_id)
        
        # Now it should be marked as processed
        assert await storage.is_event_processed(event_id) is True
        
        # Marking again should not raise an error (idempotent)
        await storage.mark_event_processed(event_id)
        assert await storage.is_event_processed(event_id) is True

    async def test_save_and_retrieve_message(self, storage: SQLiteStorage):
        """Test saving and retrieving messages."""
        msg = StoredMessage(
            chat_id="chat_001",
            message_id="msg_001",
            sender_id="user_123",
            text="Hello, world!",
            is_bot_message=False,
            item_id="item_456",
            created_at=datetime(2025, 1, 15, 10, 30, 0),
        )
        
        await storage.save_message(msg)
        
        history = await storage.get_chat_history("chat_001", limit=10)
        
        assert len(history) == 1
        retrieved = history[0]
        assert retrieved.chat_id == msg.chat_id
        assert retrieved.message_id == msg.message_id
        assert retrieved.sender_id == msg.sender_id
        assert retrieved.text == msg.text
        assert retrieved.is_bot_message == msg.is_bot_message
        assert retrieved.item_id == msg.item_id
        assert retrieved.created_at == msg.created_at

    async def test_chat_history_limit(self, storage: SQLiteStorage):
        """Test that chat history respects the limit parameter."""
        chat_id = "chat_limit_test"
        
        # Save 25 messages
        for i in range(25):
            msg = StoredMessage(
                chat_id=chat_id,
                message_id=f"msg_{i:03d}",
                sender_id="user_123",
                text=f"Message {i}",
                is_bot_message=False,
                created_at=datetime(2025, 1, 15, 10, i, 0),
            )
            await storage.save_message(msg)
        
        # Request with default limit (20)
        history = await storage.get_chat_history(chat_id)
        assert len(history) == 20
        
        # Request with custom limit
        history = await storage.get_chat_history(chat_id, limit=5)
        assert len(history) == 5

    async def test_chat_history_ordering(self, storage: SQLiteStorage):
        """Test that chat history is ordered by created_at descending."""
        chat_id = "chat_order_test"
        
        # Save messages in random order
        times = [
            datetime(2025, 1, 15, 10, 0, 0),
            datetime(2025, 1, 15, 12, 0, 0),
            datetime(2025, 1, 15, 11, 0, 0),
        ]
        
        for i, t in enumerate(times):
            msg = StoredMessage(
                chat_id=chat_id,
                message_id=f"msg_{i}",
                sender_id="user_123",
                text=f"Message at {t}",
                is_bot_message=False,
                created_at=t,
            )
            await storage.save_message(msg)
        
        history = await storage.get_chat_history(chat_id)
        
        # Should be ordered most recent first
        assert history[0].created_at == datetime(2025, 1, 15, 12, 0, 0)
        assert history[1].created_at == datetime(2025, 1, 15, 11, 0, 0)
        assert history[2].created_at == datetime(2025, 1, 15, 10, 0, 0)

    async def test_save_dialog_log(self, storage: SQLiteStorage):
        """Test saving dialog logs."""
        log = DialogLog(
            chat_id="chat_001",
            item_id="item_456",
            customer_question="What is the price?",
            bot_answer="The price is 1000 rubles.",
            found_status="FOUND",
            sources=["product_info.txt", "pricing.md"],
        )
        
        # Should not raise an error
        await storage.save_dialog_log(log)

    async def test_message_isolation_by_chat(self, storage: SQLiteStorage):
        """Test that messages are isolated by chat_id."""
        # Save messages to different chats
        for chat_id in ["chat_A", "chat_B"]:
            for i in range(3):
                msg = StoredMessage(
                    chat_id=chat_id,
                    message_id=f"{chat_id}_msg_{i}",
                    sender_id="user_123",
                    text=f"Message {i} in {chat_id}",
                    is_bot_message=False,
                    created_at=datetime(2025, 1, 15, 10, i, 0),
                )
                await storage.save_message(msg)
        
        # Each chat should only see its own messages
        history_a = await storage.get_chat_history("chat_A")
        history_b = await storage.get_chat_history("chat_B")
        
        assert len(history_a) == 3
        assert len(history_b) == 3
        assert all(m.chat_id == "chat_A" for m in history_a)
        assert all(m.chat_id == "chat_B" for m in history_b)


class TestProjectCRUD:
    """Tests for Project CRUD operations."""

    async def test_create_project(self, storage: SQLiteStorage):
        """Test creating a new project."""
        project = Project(
            name="Test Project",
            description="A test project for unit testing",
        )
        
        created = await storage.create_project(project)
        
        assert created.id is not None
        assert created.name == "Test Project"
        assert created.description == "A test project for unit testing"
        assert created.created_at is not None
        assert created.updated_at is not None

    async def test_get_project(self, storage: SQLiteStorage):
        """Test retrieving a project by ID."""
        project = Project(name="Get Test Project")
        created = await storage.create_project(project)
        
        retrieved = await storage.get_project(created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "Get Test Project"

    async def test_get_nonexistent_project(self, storage: SQLiteStorage):
        """Test retrieving a non-existent project returns None."""
        result = await storage.get_project(99999)
        assert result is None

    async def test_get_project_by_avito_user_id(self, storage: SQLiteStorage):
        """Test retrieving a project by Avito user ID."""
        # Create a project with Avito credentials
        project = Project(
            name="Avito Project",
            avito_user_id="avito_user_123",
            avito_client_id="client_123",
            avito_client_secret="secret_123",
            avito_connected=True,
        )
        created = await storage.create_project(project)
        
        # Should find the project by avito_user_id
        retrieved = await storage.get_project_by_avito_user_id("avito_user_123")
        
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.avito_user_id == "avito_user_123"

    async def test_get_project_by_avito_user_id_not_connected(self, storage: SQLiteStorage):
        """Test that disconnected projects are not returned."""
        # Create a project with Avito credentials but not connected
        project = Project(
            name="Disconnected Project",
            avito_user_id="avito_user_456",
            avito_client_id="client_456",
            avito_client_secret="secret_456",
            avito_connected=False,  # Not connected
        )
        await storage.create_project(project)
        
        # Should not find the project because it's not connected
        retrieved = await storage.get_project_by_avito_user_id("avito_user_456")
        
        assert retrieved is None

    async def test_get_project_by_avito_user_id_not_found(self, storage: SQLiteStorage):
        """Test retrieving a non-existent Avito user ID returns None."""
        result = await storage.get_project_by_avito_user_id("nonexistent_user")
        assert result is None

    async def test_list_projects(self, storage: SQLiteStorage):
        """Test listing all projects."""
        # Create multiple projects
        for i in range(3):
            await storage.create_project(Project(name=f"Project {i}"))
        
        projects = await storage.list_projects()
        
        assert len(projects) == 3

    async def test_update_project(self, storage: SQLiteStorage):
        """Test updating a project."""
        project = Project(name="Original Name", description="Original desc")
        created = await storage.create_project(project)
        
        created.name = "Updated Name"
        created.description = "Updated description"
        created.avito_connected = True
        
        updated = await storage.update_project(created)
        
        assert updated.name == "Updated Name"
        assert updated.description == "Updated description"
        assert updated.avito_connected is True

    async def test_delete_project(self, storage: SQLiteStorage):
        """Test deleting a project."""
        project = Project(name="To Delete")
        created = await storage.create_project(project)
        
        await storage.delete_project(created.id)
        
        result = await storage.get_project(created.id)
        assert result is None


class TestProjectFileCRUD:
    """Tests for ProjectFile CRUD operations."""

    async def test_save_project_file(self, storage: SQLiteStorage):
        """Test saving a project file."""
        # First create a project
        project = await storage.create_project(Project(name="File Test Project"))
        
        file = ProjectFile(
            id="gemini_file_123",
            project_id=project.id,
            name="test_document.txt",
            size=1024,
            item_id="item_456",
        )
        
        saved = await storage.save_project_file(file)
        
        assert saved.id == "gemini_file_123"
        assert saved.name == "test_document.txt"

    async def test_list_project_files(self, storage: SQLiteStorage):
        """Test listing files for a project."""
        project = await storage.create_project(Project(name="Files List Project"))
        
        # Add multiple files
        for i in range(3):
            await storage.save_project_file(ProjectFile(
                id=f"file_{i}",
                project_id=project.id,
                name=f"document_{i}.txt",
                size=100 * (i + 1),
            ))
        
        files = await storage.list_project_files(project.id)
        
        assert len(files) == 3

    async def test_delete_project_file(self, storage: SQLiteStorage):
        """Test deleting a project file."""
        project = await storage.create_project(Project(name="File Delete Project"))
        
        file = ProjectFile(
            id="file_to_delete",
            project_id=project.id,
            name="delete_me.txt",
            size=512,
        )
        await storage.save_project_file(file)
        
        await storage.delete_project_file("file_to_delete")
        
        files = await storage.list_project_files(project.id)
        assert len(files) == 0

    async def test_cascade_delete_files_on_project_delete(self, storage: SQLiteStorage):
        """Test that files are deleted when project is deleted."""
        project = await storage.create_project(Project(name="Cascade Test"))
        
        await storage.save_project_file(ProjectFile(
            id="cascade_file",
            project_id=project.id,
            name="cascade.txt",
            size=256,
        ))
        
        await storage.delete_project(project.id)
        
        # Files should be deleted due to CASCADE
        files = await storage.list_project_files(project.id)
        assert len(files) == 0


class TestChatHistoryCRUD:
    """Tests for ChatMessage CRUD operations."""

    async def test_save_chat_message(self, storage: SQLiteStorage):
        """Test saving a chat message."""
        project = await storage.create_project(Project(name="Chat Test Project"))
        
        message = ChatMessage(
            project_id=project.id,
            role="user",
            content="Hello, how are you?",
        )
        
        saved = await storage.save_chat_message(message)
        
        assert saved.id is not None
        assert saved.content == "Hello, how are you?"
        assert saved.role == "user"

    async def test_get_project_chat_history(self, storage: SQLiteStorage):
        """Test retrieving chat history for a project."""
        project = await storage.create_project(Project(name="Chat History Project"))
        
        # Add user message
        await storage.save_chat_message(ChatMessage(
            project_id=project.id,
            role="user",
            content="What is the price?",
        ))
        
        # Add assistant response
        await storage.save_chat_message(ChatMessage(
            project_id=project.id,
            role="assistant",
            content="The price is 1000 rubles.",
            sources=["pricing.txt"],
            found_status="FOUND",
        ))
        
        history = await storage.get_project_chat_history(project.id)
        
        assert len(history) == 2
        # Messages are ordered by id (auto-increment) when created_at is the same
        # First message should be user, second should be assistant
        roles = [msg.role for msg in history]
        assert "user" in roles
        assert "assistant" in roles
        # Verify assistant message has sources
        assistant_msg = next(m for m in history if m.role == "assistant")
        assert assistant_msg.sources == ["pricing.txt"]

    async def test_clear_project_chat_history(self, storage: SQLiteStorage):
        """Test clearing chat history for a project."""
        project = await storage.create_project(Project(name="Clear Chat Project"))
        
        await storage.save_chat_message(ChatMessage(
            project_id=project.id,
            role="user",
            content="Test message",
        ))
        
        await storage.clear_project_chat_history(project.id)
        
        history = await storage.get_project_chat_history(project.id)
        assert len(history) == 0

    async def test_cascade_delete_chat_on_project_delete(self, storage: SQLiteStorage):
        """Test that chat history is deleted when project is deleted."""
        project = await storage.create_project(Project(name="Chat Cascade Test"))
        
        await storage.save_chat_message(ChatMessage(
            project_id=project.id,
            role="user",
            content="Will be deleted",
        ))
        
        await storage.delete_project(project.id)
        
        history = await storage.get_project_chat_history(project.id)
        assert len(history) == 0


class TestDialogLogsWithProject:
    """Tests for DialogLog operations with project filtering."""

    async def test_save_dialog_log_with_project(self, storage: SQLiteStorage):
        """Test saving dialog log with project_id."""
        project = await storage.create_project(Project(name="Dialog Log Project"))
        
        log = DialogLog(
            chat_id="chat_001",
            item_id="item_456",
            project_id=project.id,
            customer_question="What is the price?",
            bot_answer="The price is 1000 rubles.",
            found_status="FOUND",
            sources=["pricing.txt"],
        )
        
        await storage.save_dialog_log(log)
        
        logs = await storage.get_dialog_logs(project_id=project.id)
        assert len(logs) == 1
        assert logs[0].project_id == project.id

    async def test_get_dialog_logs_filter_by_status(self, storage: SQLiteStorage):
        """Test filtering dialog logs by status."""
        project = await storage.create_project(Project(name="Status Filter Project"))
        
        # Add logs with different statuses
        for status in ["FOUND", "NOT_FOUND", "ESCALATION"]:
            await storage.save_dialog_log(DialogLog(
                chat_id=f"chat_{status}",
                project_id=project.id,
                customer_question="Question",
                bot_answer="Answer",
                found_status=status,
            ))
        
        found_logs = await storage.get_dialog_logs(status="FOUND")
        assert len(found_logs) == 1
        assert found_logs[0].found_status == "FOUND"

    async def test_get_dialog_logs_limit(self, storage: SQLiteStorage):
        """Test dialog logs limit parameter."""
        project = await storage.create_project(Project(name="Limit Test Project"))
        
        for i in range(10):
            await storage.save_dialog_log(DialogLog(
                chat_id=f"chat_{i}",
                project_id=project.id,
                customer_question=f"Question {i}",
                bot_answer=f"Answer {i}",
                found_status="FOUND",
            ))
        
        logs = await storage.get_dialog_logs(limit=5)
        assert len(logs) == 5
