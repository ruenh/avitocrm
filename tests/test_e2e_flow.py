"""End-to-end tests for the core application flow with mock data."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.avito.messenger_client import MessengerClient, SendResult
from app.avito.webhook_models import (
    ChatContext,
    MessageContent,
    MessagePayload,
    WebhookPayload,
)
from app.core.responder import AutoResponder
from app.models.domain import StoredMessage
from app.rag.answer_policy import AnswerPolicy, AnswerResult
from app.rag.file_search_client import RetrievedChunk
from app.rag.retrieval import CascadingRetrieval, RetrievalResult
from app.storage.sqlite import SQLiteStorage
from app.telegram.notify import TelegramNotifier


@pytest.fixture
async def storage():
    """Create a temporary SQLite storage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = SQLiteStorage(str(db_path))
        yield storage


@pytest.fixture
def mock_messenger():
    """Create a mock MessengerClient."""
    messenger = AsyncMock(spec=MessengerClient)
    messenger.send_message.return_value = SendResult(message_id="sent_msg_1", success=True)
    messenger.mark_as_read.return_value = None
    return messenger


@pytest.fixture
def mock_retrieval():
    """Create a mock CascadingRetrieval."""
    retrieval = AsyncMock(spec=CascadingRetrieval)
    return retrieval


@pytest.fixture
def mock_answer_policy():
    """Create a mock AnswerPolicy."""
    policy = MagicMock(spec=AnswerPolicy)
    policy.ESCALATION_RESPONSE = "Понял, сейчас подключу менеджера."
    policy.ESCALATION_KEYWORDS = ["вызови менеджера", "позови менеджера"]
    policy.needs_escalation = MagicMock(return_value=False)
    policy.generate_answer = AsyncMock()
    return policy


@pytest.fixture
def mock_telegram():
    """Create a mock TelegramNotifier."""
    telegram = AsyncMock(spec=TelegramNotifier)
    return telegram


def create_webhook_payload(
    event_id: str = "event_001",
    chat_id: str = "chat_001",
    message_id: str = "msg_001",
    author_id: str = "customer_123",
    text: str = "Какая цена?",
    msg_type: str = "text",
    item_id: str | None = "item_456",
) -> WebhookPayload:
    """Helper to create webhook payloads for testing."""
    context = ChatContext(item_id=item_id) if item_id else None
    return WebhookPayload(
        id=event_id,
        type="message",
        payload=MessagePayload(
            chat_id=chat_id,
            user_id=author_id,
            message=MessageContent(
                id=message_id,
                type=msg_type,
                text=text,
                created=datetime.utcnow(),
                author_id=author_id,
            ),
            context=context,
        ),
    )


class TestEndToEndFlow:
    """End-to-end tests for the complete message processing flow."""

    async def test_normal_message_flow_with_rag_results(
        self,
        storage: SQLiteStorage,
        mock_messenger: AsyncMock,
        mock_retrieval: AsyncMock,
        mock_answer_policy: MagicMock,
        mock_telegram: AsyncMock,
    ):
        """Test complete flow: customer question -> RAG -> answer -> send."""
        # Setup RAG to return results
        mock_retrieval.retrieve.return_value = RetrievalResult(
            found=True,
            chunks=[
                RetrievedChunk(
                    text="Цена товара 5000 рублей",
                    source_file="product_info.txt",
                    relevance_score=0.95,
                    metadata={"item_id": "item_456"},
                )
            ],
            search_strategy="item_specific",
        )

        # Setup answer policy to return generated answer
        mock_answer_policy.generate_answer.return_value = AnswerResult(
            answer="Цена товара 5000 рублей.",
            found_status="FOUND",
            sources=["product_info.txt"],
            is_escalation=False,
        )

        # Create responder
        responder = AutoResponder(
            storage=storage,
            messenger_client=mock_messenger,
            cascading_retrieval=mock_retrieval,
            answer_policy=mock_answer_policy,
            telegram_notifier=mock_telegram,
            bot_user_id="bot_user_id",
            context_limit=20,
        )

        # Process webhook event
        payload = create_webhook_payload(
            event_id="event_001",
            chat_id="chat_001",
            text="Какая цена?",
            item_id="item_456",
        )
        await responder.process_event(payload)

        # Verify RAG was called with correct parameters
        mock_retrieval.retrieve.assert_called_once_with(
            query="Какая цена?",
            item_id="item_456",
        )

        # Verify message was sent to Avito
        mock_messenger.send_message.assert_called_once_with(
            "chat_001", "Цена товара 5000 рублей."
        )
        mock_messenger.mark_as_read.assert_called_once_with("chat_001")

        # Verify Telegram log was sent
        mock_telegram.send_log.assert_called_once()

        # Verify message was saved to storage
        history = await storage.get_chat_history("chat_001")
        assert len(history) == 2  # incoming + bot response
        
        # Check incoming message
        incoming = [m for m in history if not m.is_bot_message][0]
        assert incoming.text == "Какая цена?"
        assert incoming.sender_id == "customer_123"
        
        # Check bot response
        bot_msg = [m for m in history if m.is_bot_message][0]
        assert bot_msg.text == "Цена товара 5000 рублей."

    async def test_deduplication_prevents_double_processing(
        self,
        storage: SQLiteStorage,
        mock_messenger: AsyncMock,
        mock_retrieval: AsyncMock,
        mock_answer_policy: MagicMock,
        mock_telegram: AsyncMock,
    ):
        """Test that duplicate events are not processed twice."""
        mock_retrieval.retrieve.return_value = RetrievalResult(
            found=True,
            chunks=[RetrievedChunk(
                text="Test", source_file="test.txt",
                relevance_score=0.9, metadata={}
            )],
            search_strategy="general",
        )
        mock_answer_policy.generate_answer.return_value = AnswerResult(
            answer="Test answer",
            found_status="FOUND",
            sources=["test.txt"],
        )

        responder = AutoResponder(
            storage=storage,
            messenger_client=mock_messenger,
            cascading_retrieval=mock_retrieval,
            answer_policy=mock_answer_policy,
            telegram_notifier=mock_telegram,
            bot_user_id="bot_user_id",
        )

        # Process same event twice
        payload = create_webhook_payload(event_id="duplicate_event")
        await responder.process_event(payload)
        await responder.process_event(payload)

        # Should only send one message
        assert mock_messenger.send_message.call_count == 1

    async def test_system_message_is_ignored(
        self,
        storage: SQLiteStorage,
        mock_messenger: AsyncMock,
        mock_retrieval: AsyncMock,
        mock_answer_policy: MagicMock,
        mock_telegram: AsyncMock,
    ):
        """Test that system messages are not processed."""
        responder = AutoResponder(
            storage=storage,
            messenger_client=mock_messenger,
            cascading_retrieval=mock_retrieval,
            answer_policy=mock_answer_policy,
            telegram_notifier=mock_telegram,
            bot_user_id="bot_user_id",
        )

        # Create system message
        payload = create_webhook_payload(
            event_id="system_event",
            msg_type="system",
            text="User joined chat",
        )
        await responder.process_event(payload)

        # Should not send any message
        mock_messenger.send_message.assert_not_called()
        mock_retrieval.retrieve.assert_not_called()

    async def test_own_message_is_ignored(
        self,
        storage: SQLiteStorage,
        mock_messenger: AsyncMock,
        mock_retrieval: AsyncMock,
        mock_answer_policy: MagicMock,
        mock_telegram: AsyncMock,
    ):
        """Test that bot's own messages are not processed."""
        bot_user_id = "bot_user_id"
        
        responder = AutoResponder(
            storage=storage,
            messenger_client=mock_messenger,
            cascading_retrieval=mock_retrieval,
            answer_policy=mock_answer_policy,
            telegram_notifier=mock_telegram,
            bot_user_id=bot_user_id,
        )

        # Create message from bot itself
        payload = create_webhook_payload(
            event_id="own_event",
            author_id=bot_user_id,  # Same as bot
            text="Previous bot response",
        )
        await responder.process_event(payload)

        # Should not send any message
        mock_messenger.send_message.assert_not_called()
        mock_retrieval.retrieve.assert_not_called()

    async def test_escalation_flow(
        self,
        storage: SQLiteStorage,
        mock_messenger: AsyncMock,
        mock_retrieval: AsyncMock,
        mock_answer_policy: MagicMock,
        mock_telegram: AsyncMock,
    ):
        """Test escalation when customer requests manager."""
        # Setup escalation detection
        mock_answer_policy.needs_escalation.return_value = True

        responder = AutoResponder(
            storage=storage,
            messenger_client=mock_messenger,
            cascading_retrieval=mock_retrieval,
            answer_policy=mock_answer_policy,
            telegram_notifier=mock_telegram,
            bot_user_id="bot_user_id",
        )

        payload = create_webhook_payload(
            event_id="escalation_event",
            text="Позови менеджера",
        )
        await responder.process_event(payload)

        # Should send escalation notification to Telegram
        mock_telegram.send_escalation.assert_called_once()

        # Should send escalation response to customer
        mock_messenger.send_message.assert_called_once()
        call_args = mock_messenger.send_message.call_args
        assert "менеджер" in call_args[0][1].lower()

        # RAG should NOT be called for escalation
        mock_retrieval.retrieve.assert_not_called()


class TestWebhookModels:
    """Tests for webhook payload models."""

    def test_webhook_payload_properties(self):
        """Test WebhookPayload convenience properties."""
        payload = create_webhook_payload(
            event_id="evt_123",
            chat_id="chat_456",
            message_id="msg_789",
            author_id="user_abc",
            text="Hello",
            item_id="item_xyz",
        )

        assert payload.event_id == "evt_123"
        assert payload.chat_id == "chat_456"
        assert payload.message_id == "msg_789"
        assert payload.author_id == "user_abc"
        assert payload.message_text == "Hello"
        assert payload.item_id == "item_xyz"
        assert payload.is_message_event is True
        assert payload.is_system_message is False

    def test_system_message_detection(self):
        """Test system message detection."""
        payload = create_webhook_payload(msg_type="system")
        assert payload.is_system_message is True

    def test_missing_item_id(self):
        """Test payload without item_id."""
        payload = create_webhook_payload(item_id=None)
        assert payload.item_id is None


class TestAnswerPolicyEscalation:
    """Tests for AnswerPolicy escalation detection."""

    def test_escalation_keywords_detected(self):
        """Test that escalation keywords are properly detected."""
        # Create a real AnswerPolicy instance for keyword testing
        # We use a dummy API key since we're only testing keyword detection
        policy = AnswerPolicy(api_key="dummy_key")

        # Test various escalation phrases
        assert policy.needs_escalation("Вызови менеджера") is True
        assert policy.needs_escalation("позови менеджера пожалуйста") is True
        assert policy.needs_escalation("Позови человека") is True
        assert policy.needs_escalation("нужен оператор") is True

        # Test non-escalation messages
        assert policy.needs_escalation("Какая цена?") is False
        assert policy.needs_escalation("Есть в наличии?") is False
        assert policy.needs_escalation("Доставка возможна?") is False

