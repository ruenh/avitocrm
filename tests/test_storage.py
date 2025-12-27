"""Tests for SQLite storage implementation."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from app.models.domain import DialogLog, StoredMessage
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
