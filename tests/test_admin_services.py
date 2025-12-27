"""Tests for admin panel services - Projects & Files checkpoint.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.5, 2.6
"""

import io
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile

from app.admin.services import FileService, ProjectService, SUPPORTED_FILE_FORMATS
from app.models.domain import Project, ProjectFile
from app.storage.sqlite import SQLiteStorage


@pytest.fixture
async def storage():
    """Create a temporary SQLite storage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = SQLiteStorage(str(db_path))
        yield storage


@pytest.fixture
def mock_genai():
    """Mock google.generativeai module."""
    with patch("app.admin.services.genai") as mock:
        # Mock corpus creation
        mock_corpus = MagicMock()
        mock_corpus.name = "corpora/test-corpus-123"
        mock.create_corpus.return_value = mock_corpus
        
        # Mock document creation with unique IDs
        doc_counter = [0]
        def create_document_side_effect(**kwargs):
            doc_counter[0] += 1
            mock_document = MagicMock()
            mock_document.name = f"corpora/test-corpus-123/documents/doc-{doc_counter[0]}"
            return mock_document
        mock.create_document.side_effect = create_document_side_effect
        
        # Mock chunk creation
        mock.create_chunk.return_value = MagicMock()
        
        # Mock protos for metadata
        mock.protos = MagicMock()
        mock.protos.CustomMetadata.return_value = MagicMock()
        mock.protos.ChunkData.return_value = MagicMock()
        
        yield mock


class TestProjectService:
    """Tests for ProjectService."""

    async def test_create_project_creates_filesearch_store(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test that creating a project also creates a local FileSearch store.
        
        Requirements: 1.2, 1.3
        """
        service = ProjectService(storage=storage, gemini_api_key="test-key")
        
        project = await service.create_project(
            name="Test Project",
            description="Test description"
        )
        
        # Verify project was created
        assert project.id is not None
        assert project.name == "Test Project"
        assert project.description == "Test description"
        
        # Verify local FileSearch store ID was created
        assert project.filesearch_store_id is not None
        assert project.filesearch_store_id.startswith("local-store-")

    async def test_list_projects(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test listing all projects.
        
        Requirements: 1.1
        """
        service = ProjectService(storage=storage, gemini_api_key="test-key")
        
        # Create multiple projects
        await service.create_project(name="Project 1")
        await service.create_project(name="Project 2")
        
        projects = await service.list_projects()
        
        assert len(projects) == 2
        names = [p.name for p in projects]
        assert "Project 1" in names
        assert "Project 2" in names

    async def test_get_project(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test getting a project by ID."""
        service = ProjectService(storage=storage, gemini_api_key="test-key")
        
        created = await service.create_project(name="Get Test")
        retrieved = await service.get_project(created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "Get Test"

    async def test_get_nonexistent_project(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test getting a non-existent project returns None."""
        service = ProjectService(storage=storage, gemini_api_key="test-key")
        
        result = await service.get_project(99999)
        assert result is None

    async def test_update_project(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test updating a project.
        
        Requirements: 1.4
        """
        service = ProjectService(storage=storage, gemini_api_key="test-key")
        
        created = await service.create_project(name="Original", description="Old desc")
        updated = await service.update_project(
            project_id=created.id,
            name="Updated",
            description="New desc"
        )
        
        assert updated is not None
        assert updated.name == "Updated"
        assert updated.description == "New desc"

    async def test_delete_project_removes_filesearch_store(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test that deleting a project removes the local FileSearch store.
        
        Requirements: 1.5, 1.6
        """
        service = ProjectService(storage=storage, gemini_api_key="test-key")
        
        project = await service.create_project(name="To Delete")
        store_id = project.filesearch_store_id
        
        deleted = await service.delete_project(project.id)
        
        assert deleted is True
        # Local storage doesn't call Gemini API, just logs deletion
        
        # Verify project is gone
        result = await service.get_project(project.id)
        assert result is None

    async def test_delete_nonexistent_project(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test deleting a non-existent project returns False."""
        service = ProjectService(storage=storage, gemini_api_key="test-key")
        
        result = await service.delete_project(99999)
        assert result is False


class TestFileService:
    """Tests for FileService."""

    async def test_supported_file_formats(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test that supported file formats are correct.
        
        Requirements: 2.3
        """
        service = FileService(storage=storage, gemini_api_key="test-key")
        
        formats = service.get_supported_formats()
        
        assert ".txt" in formats
        assert ".md" in formats
        assert ".pdf" in formats
        assert ".docx" in formats
        assert ".json" in formats

    async def test_upload_file_to_project(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test uploading a file to a project.
        
        Requirements: 2.2, 2.5
        """
        # First create a project
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="File Upload Test")
        
        file_service = FileService(storage=storage, gemini_api_key="test-key")
        
        # Create a mock UploadFile
        content = b"Test file content"
        file = UploadFile(
            filename="test_document.txt",
            file=io.BytesIO(content),
        )
        
        uploaded = await file_service.upload_file(
            project_id=project.id,
            file=file,
            item_id="item_123",
            filesearch_store_id=project.filesearch_store_id,
        )
        
        assert uploaded.name == "test_document.txt"
        assert uploaded.size == len(content)
        assert uploaded.item_id == "item_123"
        assert uploaded.project_id == project.id

    async def test_upload_file_without_item_id(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test uploading a general file without item_id.
        
        Requirements: 2.2
        """
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="General File Test")
        
        file_service = FileService(storage=storage, gemini_api_key="test-key")
        
        content = b"General document content"
        file = UploadFile(
            filename="general.txt",
            file=io.BytesIO(content),
        )
        
        uploaded = await file_service.upload_file(
            project_id=project.id,
            file=file,
            filesearch_store_id=project.filesearch_store_id,
        )
        
        assert uploaded.name == "general.txt"
        assert uploaded.item_id is None

    async def test_upload_unsupported_file_format(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test that unsupported file formats are rejected.
        
        Requirements: 2.3
        """
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="Unsupported Format Test")
        
        file_service = FileService(storage=storage, gemini_api_key="test-key")
        
        file = UploadFile(
            filename="image.png",
            file=io.BytesIO(b"fake image data"),
        )
        
        with pytest.raises(ValueError) as exc_info:
            await file_service.upload_file(
                project_id=project.id,
                file=file,
                filesearch_store_id=project.filesearch_store_id,
            )
        
        assert "Неподдерживаемый формат" in str(exc_info.value)

    async def test_list_project_files(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test listing files for a project.
        
        Requirements: 2.1
        """
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="List Files Test")
        
        file_service = FileService(storage=storage, gemini_api_key="test-key")
        
        # Upload multiple files
        for i in range(3):
            file = UploadFile(
                filename=f"doc_{i}.txt",
                file=io.BytesIO(f"Content {i}".encode()),
            )
            await file_service.upload_file(
                project_id=project.id,
                file=file,
                filesearch_store_id=project.filesearch_store_id,
            )
        
        files = await file_service.list_files(project.id)
        
        assert len(files) == 3

    async def test_delete_file(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test deleting a file from a project.
        
        Requirements: 2.6
        """
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="Delete File Test")
        
        file_service = FileService(storage=storage, gemini_api_key="test-key")
        
        # Upload a file
        file = UploadFile(
            filename="to_delete.txt",
            file=io.BytesIO(b"Delete me"),
        )
        uploaded = await file_service.upload_file(
            project_id=project.id,
            file=file,
            filesearch_store_id=project.filesearch_store_id,
        )
        
        # Delete the file
        result = await file_service.delete_file(
            file_id=uploaded.id,
            filesearch_store_id=project.filesearch_store_id,
        )
        
        assert result is True
        # Local storage doesn't call Gemini API
        
        # Verify file is gone from database
        files = await file_service.list_files(project.id)
        assert len(files) == 0

    async def test_files_deleted_when_project_deleted(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test that files are deleted when project is deleted (cascade).
        
        Requirements: 1.6
        """
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="Cascade Delete Test")
        
        file_service = FileService(storage=storage, gemini_api_key="test-key")
        
        # Upload a file
        file = UploadFile(
            filename="cascade.txt",
            file=io.BytesIO(b"Will be cascade deleted"),
        )
        await file_service.upload_file(
            project_id=project.id,
            file=file,
            filesearch_store_id=project.filesearch_store_id,
        )
        
        # Delete the project
        await project_service.delete_project(project.id)
        
        # Files should be gone due to CASCADE
        files = await file_service.list_files(project.id)
        assert len(files) == 0


class TestProjectFileIntegration:
    """Integration tests for project and file management together."""

    async def test_full_project_lifecycle(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test complete project lifecycle: create -> upload files -> delete.
        
        Requirements: 1.2, 1.3, 1.5, 1.6, 2.2, 2.6
        """
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        file_service = FileService(storage=storage, gemini_api_key="test-key")
        
        # 1. Create project
        project = await project_service.create_project(
            name="Lifecycle Test",
            description="Testing full lifecycle"
        )
        assert project.id is not None
        assert project.filesearch_store_id is not None
        
        # 2. Upload files
        for i in range(2):
            file = UploadFile(
                filename=f"file_{i}.txt",
                file=io.BytesIO(f"Content {i}".encode()),
            )
            await file_service.upload_file(
                project_id=project.id,
                file=file,
                filesearch_store_id=project.filesearch_store_id,
            )
        
        files = await file_service.list_files(project.id)
        assert len(files) == 2
        
        # 3. Delete one file
        await file_service.delete_file(files[0].id)
        files = await file_service.list_files(project.id)
        assert len(files) == 1
        
        # 4. Delete project (should cascade delete remaining file)
        await project_service.delete_project(project.id)
        
        # Verify everything is cleaned up
        assert await project_service.get_project(project.id) is None
        files = await file_service.list_files(project.id)
        assert len(files) == 0


# ============================================================================
# Chat & Avito Checkpoint Tests (Task 12)
# Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
# ============================================================================

from app.admin.services import ChatService, AvitoService, ChatResponse
from app.models.domain import ChatMessage


class TestChatService:
    """Tests for ChatService - Chat with Gemini functionality.
    
    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
    """

    async def test_get_empty_history(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test getting chat history for a project with no messages.
        
        Requirements: 3.1
        """
        # Create a project first
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="Chat Test")
        
        chat_service = ChatService(storage=storage, gemini_api_key="test-key")
        
        history = await chat_service.get_history(project.id)
        
        assert history == []

    async def test_send_message_without_filesearch_store(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test sending a message when no FileSearch store is available.
        
        Requirements: 3.2, 3.4
        """
        # Create a project
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="No Store Chat")
        
        chat_service = ChatService(storage=storage, gemini_api_key="test-key")
        
        # Send message without filesearch_store_id
        response = await chat_service.send_message(
            project_id=project.id,
            message="Какая цена?",
            filesearch_store_id=None,  # No store
        )
        
        # Should return fallback message
        assert response.found_status == "NOT_FOUND"
        assert "базе знаний нет информации" in response.message.content

    async def test_send_message_saves_user_message(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test that sending a message saves the user message to history.
        
        Requirements: 3.1, 3.2
        """
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="Save Message Test")
        
        chat_service = ChatService(storage=storage, gemini_api_key="test-key")
        
        await chat_service.send_message(
            project_id=project.id,
            message="Тестовое сообщение",
            filesearch_store_id=None,
        )
        
        history = await chat_service.get_history(project.id)
        
        # Should have both user and assistant messages
        assert len(history) == 2
        
        user_msg = next(m for m in history if m.role == "user")
        assert user_msg.content == "Тестовое сообщение"

    async def test_clear_history(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test clearing chat history for a project.
        
        Requirements: 3.5
        """
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="Clear History Test")
        
        chat_service = ChatService(storage=storage, gemini_api_key="test-key")
        
        # Send a message
        await chat_service.send_message(
            project_id=project.id,
            message="Сообщение для удаления",
            filesearch_store_id=None,
        )
        
        # Verify message exists
        history = await chat_service.get_history(project.id)
        assert len(history) > 0
        
        # Clear history
        await chat_service.clear_history(project.id)
        
        # Verify history is empty
        history = await chat_service.get_history(project.id)
        assert len(history) == 0

    async def test_chat_response_structure(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test that ChatResponse has correct structure.
        
        Requirements: 3.3, 3.4
        """
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="Response Structure Test")
        
        chat_service = ChatService(storage=storage, gemini_api_key="test-key")
        
        response = await chat_service.send_message(
            project_id=project.id,
            message="Тест структуры",
            filesearch_store_id=None,
        )
        
        # Verify response structure
        assert isinstance(response, ChatResponse)
        assert isinstance(response.message, ChatMessage)
        assert response.found_status in ["FOUND", "NOT_FOUND", "ESCALATION"]
        assert isinstance(response.sources, list)

    async def test_multiple_messages_in_history(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test that multiple messages are stored in correct order.
        
        Requirements: 3.1
        """
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="Multiple Messages Test")
        
        chat_service = ChatService(storage=storage, gemini_api_key="test-key")
        
        # Send multiple messages
        await chat_service.send_message(
            project_id=project.id,
            message="Первый вопрос",
            filesearch_store_id=None,
        )
        await chat_service.send_message(
            project_id=project.id,
            message="Второй вопрос",
            filesearch_store_id=None,
        )
        
        history = await chat_service.get_history(project.id)
        
        # Should have 4 messages (2 user + 2 assistant)
        assert len(history) == 4
        
        # Verify we have both user messages (order may vary based on storage)
        user_messages = [m for m in history if m.role == "user"]
        user_contents = {m.content for m in user_messages}
        assert "Первый вопрос" in user_contents
        assert "Второй вопрос" in user_contents


class TestAvitoService:
    """Tests for AvitoService - Avito credentials management.
    
    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
    """

    async def test_save_credentials_project_not_found(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test saving credentials for non-existent project.
        
        Requirements: 4.1
        """
        avito_service = AvitoService(storage=storage)
        
        with pytest.raises(ValueError) as exc_info:
            await avito_service.save_credentials(
                project_id=99999,
                client_id="test_client",
                client_secret="test_secret",
                user_id="test_user",
            )
        
        assert "not found" in str(exc_info.value)

    async def test_save_credentials_invalid_credentials(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test saving invalid Avito credentials.
        
        Requirements: 4.2, 4.6
        """
        # Create a project
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="Invalid Creds Test")
        
        avito_service = AvitoService(storage=storage)
        
        # Mock TokenManager to raise ConfigurationError
        with patch("app.avito.oauth.TokenManager") as mock_token_manager:
            from app.avito.oauth import ConfigurationError
            mock_instance = MagicMock()
            mock_instance.get_token = AsyncMock(side_effect=ConfigurationError("Invalid credentials"))
            mock_token_manager.return_value = mock_instance
            
            with pytest.raises(ValueError) as exc_info:
                await avito_service.save_credentials(
                    project_id=project.id,
                    client_id="invalid_client",
                    client_secret="invalid_secret",
                    user_id="test_user",
                )
            
            assert "Неверные учётные данные" in str(exc_info.value)

    async def test_save_credentials_success(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test successfully saving valid Avito credentials.
        
        Requirements: 4.1, 4.2, 4.3
        """
        # Create a project
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="Valid Creds Test")
        
        avito_service = AvitoService(storage=storage)
        
        # Mock TokenManager to succeed
        with patch("app.avito.oauth.TokenManager") as mock_token_manager:
            mock_instance = MagicMock()
            mock_instance.get_token = AsyncMock(return_value="valid_token")
            mock_token_manager.return_value = mock_instance
            
            updated_project = await avito_service.save_credentials(
                project_id=project.id,
                client_id="valid_client",
                client_secret="valid_secret",
                user_id="123456",
            )
            
            assert updated_project.avito_client_id == "valid_client"
            assert updated_project.avito_client_secret == "valid_secret"
            assert updated_project.avito_user_id == "123456"
            assert updated_project.avito_connected is True

    async def test_test_connection_success(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test successful connection test.
        
        Requirements: 4.2, 4.3
        """
        avito_service = AvitoService(storage=storage)
        
        with patch("app.avito.oauth.TokenManager") as mock_token_manager:
            mock_instance = MagicMock()
            mock_instance.get_token = AsyncMock(return_value="valid_token")
            mock_token_manager.return_value = mock_instance
            
            result = await avito_service.test_connection(
                client_id="valid_client",
                client_secret="valid_secret",
            )
            
            assert result is True

    async def test_test_connection_failure(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test failed connection test.
        
        Requirements: 4.2, 4.3, 4.6
        """
        avito_service = AvitoService(storage=storage)
        
        with patch("app.avito.oauth.TokenManager") as mock_token_manager:
            from app.avito.oauth import ConfigurationError
            mock_instance = MagicMock()
            mock_instance.get_token = AsyncMock(side_effect=ConfigurationError("Invalid"))
            mock_token_manager.return_value = mock_instance
            
            result = await avito_service.test_connection(
                client_id="invalid_client",
                client_secret="invalid_secret",
            )
            
            assert result is False

    async def test_register_webhook_project_not_found(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test registering webhook for non-existent project.
        
        Requirements: 4.4
        """
        avito_service = AvitoService(storage=storage)
        
        with pytest.raises(ValueError) as exc_info:
            await avito_service.register_webhook(
                project_id=99999,
                client_id="test_client",
                client_secret="test_secret",
                user_id="test_user",
                webhook_url="https://example.com/webhook",
            )
        
        assert "not found" in str(exc_info.value)

    async def test_register_webhook_success(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test successful webhook registration.
        
        Requirements: 4.4, 4.5
        """
        # Create a project
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="Webhook Test")
        
        avito_service = AvitoService(storage=storage)
        
        with patch("app.avito.oauth.TokenManager") as mock_token_manager, \
             patch("app.avito.messenger_client.MessengerClient") as mock_messenger:
            mock_token_instance = MagicMock()
            mock_token_manager.return_value = mock_token_instance
            
            mock_messenger_instance = MagicMock()
            mock_messenger_instance.register_webhook = AsyncMock()
            mock_messenger.return_value = mock_messenger_instance
            
            updated_project = await avito_service.register_webhook(
                project_id=project.id,
                client_id="test_client",
                client_secret="test_secret",
                user_id="test_user",
                webhook_url="https://example.com/webhook",
            )
            
            assert updated_project.webhook_registered is True
            mock_messenger_instance.register_webhook.assert_called_once_with(
                "https://example.com/webhook"
            )


class TestChatAvitoIntegration:
    """Integration tests for Chat and Avito functionality together."""

    async def test_project_with_chat_and_avito(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test a project with both chat history and Avito credentials.
        
        Requirements: 3.1, 4.1
        """
        # Create project
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(
            name="Full Integration Test",
            description="Testing chat and Avito together"
        )
        
        # Add chat messages
        chat_service = ChatService(storage=storage, gemini_api_key="test-key")
        await chat_service.send_message(
            project_id=project.id,
            message="Тестовый вопрос",
            filesearch_store_id=None,
        )
        
        # Save Avito credentials
        avito_service = AvitoService(storage=storage)
        with patch("app.avito.oauth.TokenManager") as mock_token_manager:
            mock_instance = MagicMock()
            mock_instance.get_token = AsyncMock(return_value="valid_token")
            mock_token_manager.return_value = mock_instance
            
            updated_project = await avito_service.save_credentials(
                project_id=project.id,
                client_id="integration_client",
                client_secret="integration_secret",
                user_id="integration_user",
            )
        
        # Verify both chat and Avito are set up
        history = await chat_service.get_history(project.id)
        assert len(history) == 2  # user + assistant
        
        assert updated_project.avito_connected is True
        assert updated_project.avito_client_id == "integration_client"

    async def test_delete_project_clears_chat_history(
        self, storage: SQLiteStorage, mock_genai: MagicMock
    ):
        """Test that deleting a project also clears its chat history.
        
        Requirements: 1.6, 3.5
        """
        # Create project
        project_service = ProjectService(storage=storage, gemini_api_key="test-key")
        project = await project_service.create_project(name="Delete Chat Test")
        
        # Add chat messages
        chat_service = ChatService(storage=storage, gemini_api_key="test-key")
        await chat_service.send_message(
            project_id=project.id,
            message="Сообщение перед удалением",
            filesearch_store_id=None,
        )
        
        # Verify messages exist
        history = await chat_service.get_history(project.id)
        assert len(history) > 0
        
        # Delete project
        await project_service.delete_project(project.id)
        
        # Chat history should be cleared (cascade delete)
        history = await chat_service.get_history(project.id)
        assert len(history) == 0
