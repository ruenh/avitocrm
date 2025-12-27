"""SQLite storage implementation for Avito AI Auto-Responder."""

import json
from datetime import datetime
from pathlib import Path

import aiosqlite

from app.models.domain import DialogLog, StoredMessage
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

    async def _ensure_initialized(self) -> None:
        """Ensure database schema is initialized."""
        if self._initialized:
            return
        
        # Ensure data directory exists
        db_path = Path(self.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        async with aiosqlite.connect(self.database_path) as db:
            await db.executescript(self._get_schema())
            await db.commit()
        
        self._initialized = True

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

        CREATE TABLE IF NOT EXISTS dialog_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            item_id TEXT,
            customer_question TEXT NOT NULL,
            bot_answer TEXT NOT NULL,
            found_status TEXT NOT NULL,
            sources TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
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
                (chat_id, item_id, customer_question, bot_answer, found_status, sources)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    log.chat_id,
                    log.item_id,
                    log.customer_question,
                    log.bot_answer,
                    log.found_status,
                    json.dumps(log.sources),
                )
            )
            await db.commit()
