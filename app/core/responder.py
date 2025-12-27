"""Core Auto Responder - main message processing logic."""

import logging
from datetime import datetime
from typing import Optional

from app.avito.messenger_client import MessengerClient, MessengerClientError
from app.avito.webhook_models import WebhookPayload
from app.models.domain import DialogLog, StoredMessage
from app.rag.answer_policy import AnswerPolicy
from app.rag.retrieval import CascadingRetrieval
from app.storage.base import StorageInterface
from app.telegram.notify import TelegramNotifier

logger = logging.getLogger(__name__)


class AutoResponder:
    """Main auto-responder logic for processing Avito messages.
    
    Handles the complete message processing cycle:
    1. Deduplication via event_id
    2. Filtering system and own messages
    3. Saving incoming messages
    4. Loading chat context (20 messages)
    5. Checking for escalation requests
    6. RAG retrieval + answer generation
    7. Sending response to Avito + mark as read
    8. Saving response and dialog log
    9. Logging to Telegram
    """

    def __init__(
        self,
        storage: StorageInterface,
        messenger_client: MessengerClient,
        cascading_retrieval: CascadingRetrieval,
        answer_policy: AnswerPolicy,
        telegram_notifier: TelegramNotifier,
        bot_user_id: str,
        context_limit: int = 20,
    ):
        """Initialize AutoResponder.
        
        Args:
            storage: Storage interface for persistence
            messenger_client: Avito Messenger API client
            cascading_retrieval: RAG retrieval component
            answer_policy: Answer generation policy
            telegram_notifier: Telegram notification sender
            bot_user_id: The bot's Avito user ID (to filter own messages)
            context_limit: Max messages to load for context (default 20)
        """
        self._storage = storage
        self._messenger = messenger_client
        self._retrieval = cascading_retrieval
        self._answer_policy = answer_policy
        self._telegram = telegram_notifier
        self._bot_user_id = bot_user_id
        self._context_limit = context_limit

    async def process_event(self, payload: WebhookPayload) -> None:
        """Process a webhook event through the complete cycle.
        
        Args:
            payload: The webhook payload to process
        """
        event_id = payload.event_id
        chat_id = payload.chat_id
        
        logger.info(f"Processing event {event_id} for chat {chat_id}")

        # Step 1: Deduplication check
        if await self._storage.is_event_processed(event_id):
            logger.info(f"Event {event_id} already processed, skipping")
            return

        # Mark event as processed immediately to prevent race conditions
        await self._storage.mark_event_processed(event_id)

        # Step 2: Filter non-message events
        if not payload.is_message_event:
            logger.info(f"Event {event_id} is not a message event, skipping")
            return

        # Step 3: Filter system messages
        if payload.is_system_message:
            logger.info(f"Message is a system message, skipping")
            return

        # Step 4: Filter own messages (bot's own messages)
        if self._is_own_message(payload):
            logger.info(f"Message is from bot itself, skipping")
            return

        # Step 5: Save incoming message
        incoming_message = self._create_stored_message(payload)
        await self._storage.save_message(incoming_message)
        logger.debug(f"Saved incoming message {payload.message_id}")

        # Get message text for processing
        message_text = payload.message_text
        if not message_text:
            logger.info("Message has no text content, skipping")
            return

        item_id = payload.item_id

        # Step 6: Load chat context
        context = await self._storage.get_chat_history(
            chat_id, limit=self._context_limit
        )
        logger.debug(f"Loaded {len(context)} messages for context")

        # Step 7: Check for escalation
        if self._answer_policy.needs_escalation(message_text):
            await self._handle_escalation(
                chat_id=chat_id,
                item_id=item_id,
                customer_message=message_text,
                context=context,
            )
            return

        # Step 8: RAG retrieval + answer generation
        retrieval_result = await self._retrieval.retrieve(
            query=message_text,
            item_id=item_id,
        )

        answer_result = await self._answer_policy.generate_answer(
            question=message_text,
            context=context,
            retrieval_result=retrieval_result,
        )

        # Step 9: Send response to Avito
        try:
            await self._messenger.send_message(chat_id, answer_result.answer)
            await self._messenger.mark_as_read(chat_id)
            logger.info(f"Sent response to chat {chat_id}")
        except MessengerClientError as e:
            logger.error(f"Failed to send message to Avito: {e}")
            # Don't save response if sending failed
            return

        # Step 10: Save bot response
        bot_message = StoredMessage(
            chat_id=chat_id,
            sender_id=self._bot_user_id,
            text=answer_result.answer,
            is_bot_message=True,
            item_id=item_id,
            created_at=datetime.utcnow(),
        )
        await self._storage.save_message(bot_message)

        # Step 11: Save dialog log
        dialog_log = DialogLog(
            chat_id=chat_id,
            item_id=item_id,
            customer_question=message_text,
            bot_answer=answer_result.answer,
            found_status=answer_result.found_status,
            sources=answer_result.sources,
        )
        await self._storage.save_dialog_log(dialog_log)

        # Step 12: Log to Telegram
        await self._telegram.send_log(
            chat_id=chat_id,
            item_id=item_id,
            question=message_text,
            answer=answer_result.answer,
            found_status=answer_result.found_status,
            sources=answer_result.sources,
        )

        logger.info(
            f"Completed processing event {event_id}, "
            f"status={answer_result.found_status}"
        )

    def _is_own_message(self, payload: WebhookPayload) -> bool:
        """Check if the message is from the bot itself.
        
        Args:
            payload: The webhook payload
            
        Returns:
            True if message is from the bot, False otherwise.
        """
        return payload.author_id == self._bot_user_id

    def _create_stored_message(self, payload: WebhookPayload) -> StoredMessage:
        """Create a StoredMessage from webhook payload.
        
        Args:
            payload: The webhook payload
            
        Returns:
            StoredMessage instance for persistence.
        """
        return StoredMessage(
            chat_id=payload.chat_id,
            message_id=payload.message_id,
            sender_id=payload.author_id,
            text=payload.message_text,
            is_bot_message=False,
            item_id=payload.item_id,
            created_at=payload.payload.message.created,
        )

    async def _handle_escalation(
        self,
        chat_id: str,
        item_id: Optional[str],
        customer_message: str,
        context: list[StoredMessage],
    ) -> None:
        """Handle escalation request from customer.
        
        Args:
            chat_id: The chat ID
            item_id: Optional item ID
            customer_message: The customer's message
            context: Chat history context
        """
        logger.info(f"Handling escalation for chat {chat_id}")

        # Get last AI response from context
        last_ai_response: Optional[str] = None
        for msg in context:
            if msg.is_bot_message and msg.text:
                last_ai_response = msg.text
                break

        # Send escalation notification to Telegram
        await self._telegram.send_escalation(
            chat_id=chat_id,
            item_id=item_id,
            customer_message=customer_message,
            last_ai_response=last_ai_response,
        )

        # Send escalation response to customer
        escalation_response = self._answer_policy.ESCALATION_RESPONSE
        try:
            await self._messenger.send_message(chat_id, escalation_response)
            await self._messenger.mark_as_read(chat_id)
            logger.info(f"Sent escalation response to chat {chat_id}")
        except MessengerClientError as e:
            logger.error(f"Failed to send escalation response: {e}")
            return

        # Save bot response
        bot_message = StoredMessage(
            chat_id=chat_id,
            sender_id=self._bot_user_id,
            text=escalation_response,
            is_bot_message=True,
            item_id=item_id,
            created_at=datetime.utcnow(),
        )
        await self._storage.save_message(bot_message)

        # Save dialog log for escalation
        dialog_log = DialogLog(
            chat_id=chat_id,
            item_id=item_id,
            customer_question=customer_message,
            bot_answer=escalation_response,
            found_status="ESCALATION",
            sources=[],
        )
        await self._storage.save_dialog_log(dialog_log)

        # Log escalation to Telegram (as regular log too)
        await self._telegram.send_log(
            chat_id=chat_id,
            item_id=item_id,
            question=customer_message,
            answer=escalation_response,
            found_status="ESCALATION",
            sources=[],
        )

        logger.info(f"Completed escalation handling for chat {chat_id}")
