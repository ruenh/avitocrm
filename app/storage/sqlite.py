"""SQLite storage implementation for Avito AI Auto-Responder."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from app.models.domain import (
    ChatMessage,
    DialogLog,
    Project,
    ProjectFile,
    StoredMessage,
)
from app.storage.base import StorageInterface


class SQLiteStorage(StorageInterface):
    """SQLite implementation of StorageInterface."""

    def __init__(self, database_path: str = "data/avito_responder.db"):
        """Initialize SQLite storage.
        
        Args:
            database_path: Path to the SQLite database file.
        """
        self.database_path = database_path
        self._initialized = False

    async def _get_connection(self) -> aiosqlite.Connection:
        """Get a database connection with foreign keys enabled."""
        db = await aiosqlite.connect(self.database_path)
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    async def _ensure_initialized(self) -> None:
        """Ensure database schema is initialized."""
        if self._initialized:
            return
        
        # Ensure data directory exists
        db_path = Path(self.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        async with aiosqlite.connect(self.database_path) as db:
            # Enable foreign key constraints
            await db.execute("PRAGMA foreign_keys = ON")
            await db.executescript(self._get_schema())
            await self._run_migrations(db)
            await db.commit()
        
        self._initialized = True

    async def _run_migrations(self, db: aiosqlite.Connection) -> None:
        """Run database migrations for existing databases."""
        # Check if dialog_logs has project_id column
        cursor = await db.execute("PRAGMA table_info(dialog_logs)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if "project_id" not in column_names:
            # Add project_id column to existing dialog_logs table
            await db.execute(
                "ALTER TABLE dialog_logs ADD COLUMN project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL"
            )

    def _get_schema(self) -> str:
        """Return the database schema SQL."""
        return """
        CREATE TABLE IF NOT EXISTS processed_events (
            event_id TEXT PRIMARY KEY,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            message_id TEXT UNIQUE,
            sender_id TEXT NOT NULL,
            text TEXT,
            is_bot_message BOOLEAN DEFAULT FALSE,
            item_id TEXT,
            created_at TIMESTAMP NOT NULL,
            stored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_messages_chat_id 
        ON messages(chat_id, created_at DESC);

        -- Projects table for admin panel
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            filesearch_store_id TEXT,
            avito_client_id TEXT,
            avito_client_secret TEXT,
            avito_user_id TEXT,
            avito_connected BOOLEAN DEFAULT FALSE,
            webhook_registered BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Project files table
        CREATE TABLE IF NOT EXISTS project_files (
            id TEXT PRIMARY KEY,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            size INTEGER NOT NULL,
            item_id TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_project_files_project_id 
        ON project_files(project_id);

        -- Chat history for test chat in admin panel
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sources TEXT,
            found_status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_chat_history_project_id 
        ON chat_history(project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS dialog_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            item_id TEXT,
            project_id INTEGER,
            customer_question TEXT NOT NULL,
            bot_answer TEXT NOT NULL,
            found_status TEXT NOT NULL,
            sources TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_dialog_logs_project_id 
        ON dialog_logs(project_id);
        """


    async def is_event_processed(self, event_id: str) -> bool:
        """Check if an event has already been processed."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM processed_events WHERE event_id = ?",
                (event_id,)
            )
            row = await cursor.fetchone()
            return row is not None

    async def mark_event_processed(self, event_id: str) -> None:
        """Mark an event as processed for deduplication."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO processed_events (event_id) VALUES (?)",
                (event_id,)
            )
            await db.commit()

    async def save_message(self, msg: StoredMessage) -> None:
        """Save a message to the database."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO messages 
                (chat_id, message_id, sender_id, text, is_bot_message, item_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    msg.chat_id,
                    msg.message_id,
                    msg.sender_id,
                    msg.text,
                    msg.is_bot_message,
                    msg.item_id,
                    msg.created_at.isoformat(),
                )
            )
            await db.commit()

    async def get_chat_history(
        self, chat_id: str, limit: int = 20
    ) -> list[StoredMessage]:
        """Retrieve chat history for context."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, chat_id, message_id, sender_id, text, 
                       is_bot_message, item_id, created_at
                FROM messages
                WHERE chat_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (chat_id, limit)
            )
            rows = await cursor.fetchall()
            
            return [
                StoredMessage(
                    id=row["id"],
                    chat_id=row["chat_id"],
                    message_id=row["message_id"],
                    sender_id=row["sender_id"],
                    text=row["text"],
                    is_bot_message=bool(row["is_bot_message"]),
                    item_id=row["item_id"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]

    async def save_dialog_log(self, log: DialogLog) -> None:
        """Save a dialog log entry with RAG results."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                INSERT INTO dialog_logs 
                (chat_id, item_id, project_id, customer_question, bot_answer, found_status, sources)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.chat_id,
                    log.item_id,
                    log.project_id,
                    log.customer_question,
                    log.bot_answer,
                    log.found_status,
                    json.dumps(log.sources),
                )
            )
            await db.commit()

    # Project CRUD methods

    async def list_projects(self) -> list[Project]:
        """List all projects."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, name, description, filesearch_store_id,
                       avito_client_id, avito_client_secret, avito_user_id,
                       avito_connected, webhook_registered, created_at, updated_at
                FROM projects
                ORDER BY created_at DESC
                """
            )
            rows = await cursor.fetchall()
            
            return [self._row_to_project(row) for row in rows]

    async def get_project(self, project_id: int) -> Optional[Project]:
        """Get a project by ID."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, name, description, filesearch_store_id,
                       avito_client_id, avito_client_secret, avito_user_id,
                       avito_connected, webhook_registered, created_at, updated_at
                FROM projects
                WHERE id = ?
                """,
                (project_id,)
            )
            row = await cursor.fetchone()
            
            if row is None:
                return None
            
            return self._row_to_project(row)

    async def get_project_by_avito_user_id(self, avito_user_id: str) -> Optional[Project]:
        """Get a project by Avito user ID."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, name, description, filesearch_store_id,
                       avito_client_id, avito_client_secret, avito_user_id,
                       avito_connected, webhook_registered, created_at, updated_at
                FROM projects
                WHERE avito_user_id = ? AND avito_connected = 1
                """,
                (avito_user_id,)
            )
            row = await cursor.fetchone()
            
            if row is None:
                return None
            
            return self._row_to_project(row)

    async def create_project(self, project: Project) -> Project:
        """Create a new project."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO projects 
                (name, description, filesearch_store_id, avito_client_id, 
                 avito_client_secret, avito_user_id, avito_connected, webhook_registered)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.name,
                    project.description,
                    project.filesearch_store_id,
                    project.avito_client_id,
                    project.avito_client_secret,
                    project.avito_user_id,
                    project.avito_connected,
                    project.webhook_registered,
                )
            )
            await db.commit()
            project.id = cursor.lastrowid
            
            # Fetch the created project to get timestamps
            return await self.get_project(project.id)  # type: ignore

    async def update_project(self, project: Project) -> Project:
        """Update an existing project."""
        await self._ensure_initialized()
        
        if project.id is None:
            raise ValueError("Project ID is required for update")
        
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                UPDATE projects SET
                    name = ?,
                    description = ?,
                    filesearch_store_id = ?,
                    avito_client_id = ?,
                    avito_client_secret = ?,
                    avito_user_id = ?,
                    avito_connected = ?,
                    webhook_registered = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    project.name,
                    project.description,
                    project.filesearch_store_id,
                    project.avito_client_id,
                    project.avito_client_secret,
                    project.avito_user_id,
                    project.avito_connected,
                    project.webhook_registered,
                    project.id,
                )
            )
            await db.commit()
            
            return await self.get_project(project.id)  # type: ignore

    async def delete_project(self, project_id: int) -> None:
        """Delete a project."""
        await self._ensure_initialized()
        
        db = await self._get_connection()
        try:
            await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            await db.commit()
        finally:
            await db.close()

    def _row_to_project(self, row: aiosqlite.Row) -> Project:
        """Convert a database row to a Project model."""
        return Project(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            filesearch_store_id=row["filesearch_store_id"],
            avito_client_id=row["avito_client_id"],
            avito_client_secret=row["avito_client_secret"],
            avito_user_id=row["avito_user_id"],
            avito_connected=bool(row["avito_connected"]),
            webhook_registered=bool(row["webhook_registered"]),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )

    # Project files methods

    async def list_project_files(self, project_id: int) -> list[ProjectFile]:
        """List all files for a project."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, project_id, name, size, item_id, uploaded_at
                FROM project_files
                WHERE project_id = ?
                ORDER BY uploaded_at DESC
                """,
                (project_id,)
            )
            rows = await cursor.fetchall()
            
            return [
                ProjectFile(
                    id=row["id"],
                    project_id=row["project_id"],
                    name=row["name"],
                    size=row["size"],
                    item_id=row["item_id"],
                    uploaded_at=datetime.fromisoformat(row["uploaded_at"]) if row["uploaded_at"] else None,
                )
                for row in rows
            ]

    async def save_project_file(self, file: ProjectFile) -> ProjectFile:
        """Save a project file record."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO project_files 
                (id, project_id, name, size, item_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    file.id,
                    file.project_id,
                    file.name,
                    file.size,
                    file.item_id,
                )
            )
            await db.commit()
            
            return file

    async def delete_project_file(self, file_id: str) -> None:
        """Delete a project file record."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("DELETE FROM project_files WHERE id = ?", (file_id,))
            await db.commit()

    # Chat history methods

    async def get_project_chat_history(
        self, project_id: int, limit: int = 50
    ) -> list[ChatMessage]:
        """Get chat history for a project's test chat."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, project_id, role, content, sources, found_status, created_at
                FROM chat_history
                WHERE project_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (project_id, limit)
            )
            rows = await cursor.fetchall()
            
            return [
                ChatMessage(
                    id=row["id"],
                    project_id=row["project_id"],
                    role=row["role"],
                    content=row["content"],
                    sources=json.loads(row["sources"]) if row["sources"] else [],
                    found_status=row["found_status"],
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                )
                for row in rows
            ]

    async def save_chat_message(self, message: ChatMessage) -> ChatMessage:
        """Save a chat message to the test chat history."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO chat_history 
                (project_id, role, content, sources, found_status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    message.project_id,
                    message.role,
                    message.content,
                    json.dumps(message.sources),
                    message.found_status,
                )
            )
            await db.commit()
            message.id = cursor.lastrowid
            
            return message

    async def clear_project_chat_history(self, project_id: int) -> None:
        """Clear all chat history for a project."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("DELETE FROM chat_history WHERE project_id = ?", (project_id,))
            await db.commit()

    # Dialog logs methods

    async def get_dialog_logs(
        self,
        project_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[DialogLog]:
        """Get dialog logs with optional filtering."""
        await self._ensure_initialized()
        
        query = """
            SELECT id, chat_id, item_id, project_id, customer_question, 
                   bot_answer, found_status, sources, created_at
            FROM dialog_logs
            WHERE 1=1
        """
        params: list = []
        
        if project_id is not None:
            query += " AND project_id = ?"
            params.append(project_id)
        
        if status is not None:
            query += " AND found_status = ?"
            params.append(status)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            
            return [
                DialogLog(
                    id=row["id"],
                    chat_id=row["chat_id"],
                    item_id=row["item_id"],
                    project_id=row["project_id"],
                    customer_question=row["customer_question"],
                    bot_answer=row["bot_answer"],
                    found_status=row["found_status"],
                    sources=json.loads(row["sources"]) if row["sources"] else [],
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                )
                for row in rows
            ]
