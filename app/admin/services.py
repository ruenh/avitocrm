"""Admin panel services for business logic.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 3.5
"""

import logging
import tempfile
from pathlib import Path
from typing import Literal, Optional

import google.generativeai as genai
from fastapi import UploadFile
from pydantic import BaseModel

from app.models.domain import ChatMessage, Project, ProjectFile
from app.storage.base import StorageInterface

logger = logging.getLogger(__name__)

# Supported file formats for FileSearch
SUPPORTED_FILE_FORMATS = {".txt", ".md", ".pdf", ".docx", ".json"}


class ProjectService:
    """Service for managing projects with FileSearch integration.
    
    Handles CRUD operations for projects and manages corresponding
    FileSearch stores in Gemini.
    
    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
    """

    def __init__(
        self,
        storage: StorageInterface,
        gemini_api_key: str,
    ):
        """Initialize ProjectService.
        
        Args:
            storage: Storage interface for database operations.
            gemini_api_key: Google Gemini API key for FileSearch operations.
        """
        self.storage = storage
        self.gemini_api_key = gemini_api_key
        genai.configure(api_key=gemini_api_key)

    async def list_projects(self) -> list[Project]:
        """List all projects.
        
        Requirements: 1.1
        
        Returns:
            List of all projects.
        """
        return await self.storage.list_projects()

    async def get_project(self, project_id: int) -> Optional[Project]:
        """Get a project by ID.
        
        Args:
            project_id: The project ID.
            
        Returns:
            The project or None if not found.
        """
        return await self.storage.get_project(project_id)

    async def create_project(self, name: str, description: str = "") -> Project:
        """Create a new project with FileSearch store.
        
        Requirements: 1.2, 1.3
        
        Creates a project in the database and a corresponding
        FileSearch corpus in Gemini.
        
        Args:
            name: Project name.
            description: Project description.
            
        Returns:
            The created project with FileSearch store ID.
            
        Raises:
            Exception: If FileSearch store creation fails.
        """
        # Create FileSearch corpus first
        store_id = await self._create_filesearch_store(name)
        
        # Create project in database
        project = Project(
            name=name,
            description=description,
            filesearch_store_id=store_id,
        )
        
        created_project = await self.storage.create_project(project)
        logger.info(f"Created project: id={created_project.id}, name={name}, store_id={store_id}")
        
        return created_project

    async def update_project(
        self,
        project_id: int,
        name: str,
        description: str = "",
    ) -> Optional[Project]:
        """Update an existing project.
        
        Requirements: 1.4
        
        Args:
            project_id: The project ID to update.
            name: New project name.
            description: New project description.
            
        Returns:
            The updated project or None if not found.
        """
        project = await self.storage.get_project(project_id)
        if project is None:
            return None
        
        project.name = name
        project.description = description
        
        updated_project = await self.storage.update_project(project)
        logger.info(f"Updated project: id={project_id}, name={name}")
        
        return updated_project

    async def delete_project(self, project_id: int) -> bool:
        """Delete a project and its FileSearch store.
        
        Requirements: 1.5, 1.6
        
        Deletes the project from the database and removes the
        corresponding FileSearch corpus from Gemini.
        
        Args:
            project_id: The project ID to delete.
            
        Returns:
            True if deleted successfully, False if project not found.
        """
        project = await self.storage.get_project(project_id)
        if project is None:
            return False
        
        # Delete FileSearch store if exists
        if project.filesearch_store_id:
            await self._delete_filesearch_store(project.filesearch_store_id)
        
        # Delete project from database (cascades to files and chat history)
        await self.storage.delete_project(project_id)
        logger.info(f"Deleted project: id={project_id}, name={project.name}")
        
        return True

    async def _create_filesearch_store(self, name: str) -> str:
        """Create a FileSearch corpus in Gemini.
        
        Args:
            name: Display name for the corpus.
            
        Returns:
            The corpus name (store ID).
            
        Raises:
            Exception: If corpus creation fails.
        """
        try:
            corpus = genai.create_corpus(display_name=name)
            logger.info(f"Created FileSearch corpus: {corpus.name}")
            return corpus.name
        except Exception as e:
            logger.error(f"Failed to create FileSearch corpus: {e}")
            raise

    async def _delete_filesearch_store(self, store_id: str) -> None:
        """Delete a FileSearch corpus from Gemini.
        
        Args:
            store_id: The corpus name to delete.
        """
        try:
            genai.delete_corpus(name=store_id, force=True)
            logger.info(f"Deleted FileSearch corpus: {store_id}")
        except Exception as e:
            # Log but don't fail - corpus might already be deleted
            logger.warning(f"Failed to delete FileSearch corpus {store_id}: {e}")

    async def get_project_file_count(self, project_id: int) -> int:
        """Get the number of files in a project.
        
        Args:
            project_id: The project ID.
            
        Returns:
            Number of files in the project.
        """
        files = await self.storage.list_project_files(project_id)
        return len(files)

    async def get_project_message_count(self, project_id: int) -> int:
        """Get the number of dialog messages for a project.
        
        Args:
            project_id: The project ID.
            
        Returns:
            Number of dialog messages.
        """
        logs = await self.storage.get_dialog_logs(project_id=project_id, limit=10000)
        return len(logs)


class FileService:
    """Service for managing project files with FileSearch integration.
    
    Handles file upload, listing, and deletion with Gemini FileSearch.
    
    Requirements: 2.1, 2.2, 2.3, 2.5, 2.6
    """

    def __init__(
        self,
        storage: StorageInterface,
        gemini_api_key: str,
    ):
        """Initialize FileService.
        
        Args:
            storage: Storage interface for database operations.
            gemini_api_key: Google Gemini API key for FileSearch operations.
        """
        self.storage = storage
        self.gemini_api_key = gemini_api_key
        genai.configure(api_key=gemini_api_key)

    async def list_files(self, project_id: int) -> list[ProjectFile]:
        """List all files for a project.
        
        Requirements: 2.1
        
        Args:
            project_id: The project ID.
            
        Returns:
            List of project files.
        """
        return await self.storage.list_project_files(project_id)

    async def upload_file(
        self,
        project_id: int,
        file: UploadFile,
        item_id: Optional[str] = None,
        filesearch_store_id: Optional[str] = None,
    ) -> ProjectFile:
        """Upload a file to the project's FileSearch store.
        
        Requirements: 2.2, 2.3, 2.5
        
        Args:
            project_id: The project ID.
            file: The uploaded file.
            item_id: Optional item ID for product-specific documents.
            filesearch_store_id: The FileSearch corpus ID.
            
        Returns:
            The created ProjectFile record.
            
        Raises:
            ValueError: If file format is not supported.
            Exception: If upload fails.
        """
        # Validate file format
        filename = file.filename or "unknown"
        suffix = Path(filename).suffix.lower()
        
        if suffix not in SUPPORTED_FILE_FORMATS:
            raise ValueError(
                f"Неподдерживаемый формат файла: {suffix}. "
                f"Поддерживаемые форматы: {', '.join(SUPPORTED_FILE_FORMATS)}"
            )
        
        # Read file content
        content = await file.read()
        file_size = len(content)
        
        # Save to temp file for Gemini upload
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=suffix,
            delete=False,
        ) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)
        
        try:
            # Upload to Gemini FileSearch
            document_id = await self._upload_to_filesearch(
                store_id=filesearch_store_id,
                file_path=temp_path,
                display_name=filename,
                item_id=item_id,
            )
            
            # Save file record to database
            project_file = ProjectFile(
                id=document_id,
                project_id=project_id,
                name=filename,
                size=file_size,
                item_id=item_id,
            )
            
            await self.storage.save_project_file(project_file)
            logger.info(
                f"Uploaded file: project_id={project_id}, name={filename}, "
                f"size={file_size}, item_id={item_id}, doc_id={document_id}"
            )
            
            return project_file
            
        finally:
            # Clean up temp file
            temp_path.unlink(missing_ok=True)

    async def delete_file(
        self,
        file_id: str,
        filesearch_store_id: Optional[str] = None,
    ) -> bool:
        """Delete a file from the project and FileSearch store.
        
        Requirements: 2.6
        
        Args:
            file_id: The file/document ID.
            filesearch_store_id: The FileSearch corpus ID (unused, kept for API consistency).
            
        Returns:
            True if deleted successfully.
        """
        try:
            # Delete from Gemini FileSearch
            await self._delete_from_filesearch(file_id)
            
            # Delete from database
            await self.storage.delete_project_file(file_id)
            logger.info(f"Deleted file: doc_id={file_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}")
            # Still try to delete from database even if Gemini fails
            await self.storage.delete_project_file(file_id)
            return True

    async def _upload_to_filesearch(
        self,
        store_id: Optional[str],
        file_path: Path,
        display_name: str,
        item_id: Optional[str] = None,
    ) -> str:
        """Upload a document to Gemini FileSearch.
        
        Args:
            store_id: The corpus name.
            file_path: Path to the file.
            display_name: Display name for the document.
            item_id: Optional item ID for metadata.
            
        Returns:
            The document ID.
            
        Raises:
            Exception: If upload fails.
        """
        if not store_id:
            raise ValueError("FileSearch store ID is required")
        
        try:
            # Build custom metadata
            custom_metadata = []
            if item_id:
                custom_metadata.append(
                    genai.protos.CustomMetadata(key="item_id", string_value=item_id)
                )
            else:
                custom_metadata.append(
                    genai.protos.CustomMetadata(key="is_general", string_value="true")
                )
            
            # Create document in corpus
            document = genai.create_document(
                corpus=store_id,
                display_name=display_name,
                custom_metadata=custom_metadata,
            )
            
            # Read file content
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            
            # Create chunk with the document content
            genai.create_chunk(
                document=document.name,
                data=genai.protos.ChunkData(string_value=content),
            )
            
            logger.info(f"Uploaded to FileSearch: {display_name} -> {document.name}")
            return document.name
            
        except Exception as e:
            logger.error(f"Failed to upload to FileSearch: {e}")
            raise

    async def _delete_from_filesearch(self, document_id: str) -> None:
        """Delete a document from Gemini FileSearch.
        
        Args:
            document_id: The document name/ID.
        """
        try:
            genai.delete_document(name=document_id, force=True)
            logger.info(f"Deleted from FileSearch: {document_id}")
        except Exception as e:
            # Log but don't fail - document might already be deleted
            logger.warning(f"Failed to delete from FileSearch {document_id}: {e}")

    def get_supported_formats(self) -> set[str]:
        """Get the set of supported file formats.
        
        Requirements: 2.3
        
        Returns:
            Set of supported file extensions.
        """
        return SUPPORTED_FILE_FORMATS.copy()


class ChatResponse(BaseModel):
    """Response from chat service."""

    message: ChatMessage
    found_status: Literal["FOUND", "NOT_FOUND", "ESCALATION"]
    sources: list[str]


class ChatService:
    """Service for test chat with Gemini using project's FileSearch store.
    
    Provides chat functionality for testing the knowledge base before
    connecting to Avito.
    
    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
    """

    FALLBACK_MESSAGE = (
        "🤖 В базе знаний нет информации по вашему вопросу. "
        "Попробуйте переформулировать или загрузите дополнительные документы."
    )

    SYSTEM_PROMPT = """Ты — вежливый помощник продавца на Avito. 
Отвечай на вопросы покупателей ТОЛЬКО на основе предоставленной информации из базы знаний.

ВАЖНЫЕ ПРАВИЛА:
1. Используй ТОЛЬКО информацию из предоставленных фрагментов базы знаний
2. НЕ выдумывай цены, характеристики, наличие или условия
3. Если информации недостаточно для ответа — так и скажи
4. Отвечай кратко и по делу
5. Будь дружелюбным и профессиональным

История диалога:
{history}

Информация из базы знаний:
{knowledge}

Вопрос: {question}

Ответ:"""

    def __init__(
        self,
        storage: StorageInterface,
        gemini_api_key: str,
        model_name: str = "gemini-1.5-flash",
    ):
        """Initialize ChatService.
        
        Args:
            storage: Storage interface for database operations.
            gemini_api_key: Google Gemini API key.
            model_name: Name of the Gemini model to use.
        """
        self.storage = storage
        self.gemini_api_key = gemini_api_key
        self.model_name = model_name
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel(model_name)

    async def get_history(self, project_id: int, limit: int = 50) -> list[ChatMessage]:
        """Get chat history for a project.
        
        Requirements: 3.1
        
        Args:
            project_id: The project ID.
            limit: Maximum number of messages to return.
            
        Returns:
            List of chat messages ordered by creation time.
        """
        return await self.storage.get_project_chat_history(project_id, limit=limit)

    async def clear_history(self, project_id: int) -> None:
        """Clear chat history for a project.
        
        Requirements: 3.5
        
        Args:
            project_id: The project ID.
        """
        await self.storage.clear_project_chat_history(project_id)
        logger.info(f"Cleared chat history for project {project_id}")

    async def send_message(
        self,
        project_id: int,
        message: str,
        filesearch_store_id: Optional[str] = None,
    ) -> ChatResponse:
        """Send a message and get AI response with RAG retrieval.
        
        Requirements: 3.2, 3.3, 3.4
        
        Args:
            project_id: The project ID.
            message: The user's message.
            filesearch_store_id: The FileSearch corpus ID for retrieval.
            
        Returns:
            ChatResponse with the assistant's message and metadata.
        """
        # Save user message
        user_message = ChatMessage(
            project_id=project_id,
            role="user",
            content=message,
        )
        await self.storage.save_chat_message(user_message)
        
        # Get chat history for context
        history = await self.get_history(project_id, limit=10)
        
        # Perform RAG retrieval if store is available
        retrieval_result = await self._retrieve_from_filesearch(
            query=message,
            store_id=filesearch_store_id,
        )
        
        # Generate response
        if not retrieval_result["found"]:
            # No relevant information found
            assistant_message = ChatMessage(
                project_id=project_id,
                role="assistant",
                content=self.FALLBACK_MESSAGE,
                sources=[],
                found_status="NOT_FOUND",
            )
            await self.storage.save_chat_message(assistant_message)
            
            return ChatResponse(
                message=assistant_message,
                found_status="NOT_FOUND",
                sources=[],
            )
        
        # Generate answer using Gemini
        try:
            answer = await self._generate_answer(
                question=message,
                history=history,
                knowledge=retrieval_result["knowledge"],
            )
            
            sources = retrieval_result["sources"]
            
            assistant_message = ChatMessage(
                project_id=project_id,
                role="assistant",
                content=answer,
                sources=sources,
                found_status="FOUND",
            )
            await self.storage.save_chat_message(assistant_message)
            
            return ChatResponse(
                message=assistant_message,
                found_status="FOUND",
                sources=sources,
            )
            
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            
            # Return fallback on error
            assistant_message = ChatMessage(
                project_id=project_id,
                role="assistant",
                content=self.FALLBACK_MESSAGE,
                sources=[],
                found_status="NOT_FOUND",
            )
            await self.storage.save_chat_message(assistant_message)
            
            return ChatResponse(
                message=assistant_message,
                found_status="NOT_FOUND",
                sources=[],
            )

    async def _retrieve_from_filesearch(
        self,
        query: str,
        store_id: Optional[str],
    ) -> dict:
        """Retrieve relevant chunks from FileSearch.
        
        Args:
            query: The search query.
            store_id: The FileSearch corpus ID.
            
        Returns:
            Dict with found status, knowledge text, and sources.
        """
        if not store_id:
            return {"found": False, "knowledge": "", "sources": []}
        
        try:
            # Query the corpus
            results = genai.query_corpus(
                corpus=store_id,
                query=query,
                results_count=5,
            )
            
            chunks = []
            sources = set()
            
            for result in results:
                # Extract chunk text
                chunk_text = ""
                if hasattr(result, "chunk") and result.chunk:
                    if hasattr(result.chunk, "data"):
                        chunk_text = result.chunk.data.string_value or ""
                
                # Extract source file
                source_file = "unknown"
                if hasattr(result, "chunk") and hasattr(result.chunk, "name"):
                    # Try to get document display name from chunk name
                    # Format: corpora/{corpus}/documents/{doc}/chunks/{chunk}
                    parts = result.chunk.name.split("/")
                    if len(parts) >= 4:
                        doc_name = parts[3] if len(parts) > 3 else "unknown"
                        # Try to get the actual document to get display name
                        try:
                            doc_path = "/".join(parts[:4])
                            doc = genai.get_document(name=doc_path)
                            source_file = doc.display_name or doc_name
                        except Exception:
                            source_file = doc_name
                
                if chunk_text:
                    chunks.append(chunk_text[:500])  # Limit chunk size
                    if source_file and source_file != "unknown":
                        sources.add(source_file)
            
            if not chunks:
                return {"found": False, "knowledge": "", "sources": []}
            
            # Format knowledge for prompt
            knowledge_parts = []
            for i, chunk in enumerate(chunks, 1):
                knowledge_parts.append(f"[{i}] {chunk}")
            
            knowledge = "\n\n".join(knowledge_parts)
            
            logger.info(f"Retrieved {len(chunks)} chunks for query: {query[:50]}...")
            
            return {
                "found": True,
                "knowledge": knowledge,
                "sources": list(sources),
            }
            
        except Exception as e:
            logger.error(f"Error retrieving from FileSearch: {e}")
            return {"found": False, "knowledge": "", "sources": []}

    async def _generate_answer(
        self,
        question: str,
        history: list[ChatMessage],
        knowledge: str,
    ) -> str:
        """Generate answer using Gemini.
        
        Args:
            question: The user's question.
            history: Chat history for context.
            knowledge: Retrieved knowledge from FileSearch.
            
        Returns:
            The generated answer text.
        """
        # Format history
        history_text = self._format_history(history)
        
        # Build prompt
        prompt = self.SYSTEM_PROMPT.format(
            history=history_text,
            knowledge=knowledge,
            question=question,
        )
        
        # Generate response
        response = await self.model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.3,  # Lower temperature for factual responses
                max_output_tokens=500,
            ),
        )
        
        answer = response.text.strip() if response.text else self.FALLBACK_MESSAGE
        
        return answer

    def _format_history(self, messages: list[ChatMessage]) -> str:
        """Format chat history for the prompt.
        
        Args:
            messages: List of chat messages.
            
        Returns:
            Formatted string with conversation history.
        """
        if not messages:
            return "Нет предыдущих сообщений."
        
        lines = []
        # Take last 10 messages for context (excluding the current one)
        for msg in messages[-10:]:
            sender = "Ассистент" if msg.role == "assistant" else "Пользователь"
            lines.append(f"{sender}: {msg.content}")
        
        return "\n".join(lines)



class AvitoService:
    """Service for managing Avito integration settings.
    
    Handles saving credentials, testing connections, and registering webhooks.
    
    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
    """

    def __init__(self, storage: StorageInterface):
        """Initialize AvitoService.
        
        Args:
            storage: Storage interface for database operations.
        """
        self.storage = storage

    async def save_credentials(
        self,
        project_id: int,
        client_id: str,
        client_secret: str,
        user_id: str,
    ) -> Project:
        """Save Avito credentials for a project and verify them.
        
        Requirements: 4.1, 4.2
        
        Args:
            project_id: The project ID.
            client_id: Avito OAuth2 client ID.
            client_secret: Avito OAuth2 client secret.
            user_id: Avito user ID.
            
        Returns:
            The updated project.
            
        Raises:
            ValueError: If project not found.
            Exception: If credentials are invalid.
        """
        from app.avito.oauth import TokenManager, ConfigurationError
        
        project = await self.storage.get_project(project_id)
        if project is None:
            raise ValueError(f"Project {project_id} not found")
        
        # Verify credentials by attempting to get a token
        token_manager = TokenManager(
            client_id=client_id,
            client_secret=client_secret,
        )
        
        try:
            await token_manager.get_token()
            is_connected = True
        except ConfigurationError as e:
            logger.error(f"Invalid Avito credentials: {e}")
            raise ValueError("Неверные учётные данные Avito")
        except Exception as e:
            logger.error(f"Failed to verify Avito credentials: {e}")
            raise ValueError(f"Ошибка проверки: {str(e)}")
        
        # Update project with credentials
        project.avito_client_id = client_id
        project.avito_client_secret = client_secret
        project.avito_user_id = user_id
        project.avito_connected = is_connected
        
        updated_project = await self.storage.update_project(project)
        logger.info(f"Saved Avito credentials for project {project_id}, connected={is_connected}")
        
        return updated_project

    async def test_connection(
        self,
        client_id: str,
        client_secret: str,
    ) -> bool:
        """Test Avito connection with given credentials.
        
        Requirements: 4.2, 4.3
        
        Args:
            client_id: Avito OAuth2 client ID.
            client_secret: Avito OAuth2 client secret.
            
        Returns:
            True if connection successful, False otherwise.
        """
        from app.avito.oauth import TokenManager, ConfigurationError
        
        token_manager = TokenManager(
            client_id=client_id,
            client_secret=client_secret,
        )
        
        try:
            await token_manager.get_token()
            return True
        except ConfigurationError:
            return False
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    async def register_webhook(
        self,
        project_id: int,
        client_id: str,
        client_secret: str,
        user_id: str,
        webhook_url: str,
    ) -> Project:
        """Register Avito webhook for a project.
        
        Requirements: 4.4, 4.5
        
        Args:
            project_id: The project ID.
            client_id: Avito OAuth2 client ID.
            client_secret: Avito OAuth2 client secret.
            user_id: Avito user ID.
            webhook_url: The webhook URL to register.
            
        Returns:
            The updated project.
            
        Raises:
            ValueError: If project not found.
            Exception: If webhook registration fails.
        """
        from app.avito.oauth import TokenManager
        from app.avito.messenger_client import MessengerClient
        
        project = await self.storage.get_project(project_id)
        if project is None:
            raise ValueError(f"Project {project_id} not found")
        
        # Create token manager and messenger client
        token_manager = TokenManager(
            client_id=client_id,
            client_secret=client_secret,
        )
        
        messenger_client = MessengerClient(
            user_id=user_id,
            token_manager=token_manager,
        )
        
        # Register webhook
        await messenger_client.register_webhook(webhook_url)
        
        # Update project
        project.webhook_registered = True
        updated_project = await self.storage.update_project(project)
        
        logger.info(f"Registered webhook for project {project_id}: {webhook_url}")
        
        return updated_project


class StatsService:
    """Service for dashboard statistics and dialog history.
    
    Provides aggregated statistics and dialog log retrieval for the admin panel.
    
    Requirements: 5.1, 5.2, 5.3
    """

    def __init__(self, storage: StorageInterface):
        """Initialize StatsService.
        
        Args:
            storage: Storage interface for database operations.
        """
        self.storage = storage

    async def get_dashboard_stats(self) -> "DashboardStats":
        """Get aggregated statistics for the dashboard.
        
        Requirements: 5.1
        
        Returns:
            DashboardStats with total messages, responses, escalations, etc.
        """
        from datetime import datetime, timedelta
        from app.models.domain import DashboardStats
        
        # Get all dialog logs
        all_logs = await self.storage.get_dialog_logs(limit=100000)
        
        # Calculate totals
        total_messages = len(all_logs)
        total_responses = sum(1 for log in all_logs if log.found_status in ("FOUND", "NOT_FOUND"))
        total_escalations = sum(1 for log in all_logs if log.found_status == "ESCALATION")
        
        # Calculate messages today
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        messages_today = sum(
            1 for log in all_logs 
            if log.created_at and log.created_at >= today
        )
        
        # Calculate found rate
        found_count = sum(1 for log in all_logs if log.found_status == "FOUND")
        found_rate = (found_count / total_messages * 100) if total_messages > 0 else 0.0
        
        # Get projects count
        projects = await self.storage.list_projects()
        projects_count = len(projects)
        
        return DashboardStats(
            total_messages=total_messages,
            total_responses=total_responses,
            total_escalations=total_escalations,
            messages_today=messages_today,
            found_rate=round(found_rate, 1),
            projects_count=projects_count,
        )

    async def get_project_stats(self, project_id: int) -> "ProjectStats":
        """Get statistics for a specific project.
        
        Requirements: 5.2
        
        Args:
            project_id: The project ID.
            
        Returns:
            ProjectStats with project-specific metrics.
        """
        from app.models.domain import ProjectStats
        
        # Get dialog logs for this project
        logs = await self.storage.get_dialog_logs(project_id=project_id, limit=100000)
        
        total_messages = len(logs)
        total_responses = sum(1 for log in logs if log.found_status in ("FOUND", "NOT_FOUND"))
        total_escalations = sum(1 for log in logs if log.found_status == "ESCALATION")
        
        # Calculate found rate
        found_count = sum(1 for log in logs if log.found_status == "FOUND")
        found_rate = (found_count / total_messages * 100) if total_messages > 0 else 0.0
        
        return ProjectStats(
            project_id=project_id,
            total_messages=total_messages,
            total_responses=total_responses,
            total_escalations=total_escalations,
            found_rate=round(found_rate, 1),
        )

    async def get_dialogs(
        self,
        project_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list["DialogLog"]:
        """Get dialog logs with optional filtering.
        
        Requirements: 5.3
        
        Args:
            project_id: Filter by project ID (optional).
            status: Filter by found_status (optional).
            limit: Maximum number of logs to retrieve.
            
        Returns:
            List of dialog logs ordered by created_at descending.
        """
        from app.models.domain import DialogLog
        
        return await self.storage.get_dialog_logs(
            project_id=project_id,
            status=status,
            limit=limit,
        )

    async def get_dialog_by_chat_id(self, chat_id: str) -> list["DialogLog"]:
        """Get all dialog logs for a specific chat_id.
        
        Requirements: 5.5
        
        Args:
            chat_id: The chat ID to filter by.
            
        Returns:
            List of dialog logs for the chat.
        """
        from app.models.domain import DialogLog
        
        # Get all logs and filter by chat_id
        all_logs = await self.storage.get_dialog_logs(limit=100000)
        return [log for log in all_logs if log.chat_id == chat_id]
