"""Core Auto Responder - main message processing logic."""

import logging
from datetime import datetime
from typing import Optional

from app.avito.messenger_client import MessengerClient, MessengerClientError
from app.avito.oauth import TokenManager
from app.avito.webhook_models import WebhookPayload
from app.models.domain import DialogLog, Project, StoredMessage
from app.rag.answer_policy import AnswerPolicy
from app.rag.file_search_client import FileSearchClient
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
    
    Supports two modes:
    - Global mode: Uses global credentials from environment (legacy)
    - Project mode: Looks up project by Avito user_id and uses project credentials
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
        gemini_api_key: str = "",
    ):
        """Initialize AutoResponder.
        
        Args:
            storage: Storage interface for persistence
            messenger_client: Avito Messenger API client (default/fallback)
            cascading_retrieval: RAG retrieval component (default/fallback)
            answer_policy: Answer generation policy
            telegram_notifier: Telegram notification sender
            bot_user_id: The bot's Avito user ID (to filter own messages, fallback)
            context_limit: Max messages to load for context (default 20)
            gemini_api_key: Gemini API key for creating project-specific retrievals
        """
        self._storage = storage
        self._messenger = messenger_client
        self._retrieval = cascading_retrieval
        self._answer_policy = answer_policy
        self._telegram = telegram_notifier
        self._bot_user_id = bot_user_id
        self._context_limit = context_limit
        self._gemini_api_key = gemini_api_key

    async def _get_project_for_webhook(self, payload: WebhookPayload) -> Optional[Project]:
        """Find the project associated with this webhook.
        
        Looks up project by the Avito user_id from the webhook payload.
        
        Args:
            payload: The webhook payload
            
        Returns:
            Project if found, None otherwise
        """
        avito_user_id = payload.payload.user_id
        if not avito_user_id:
            return None
        
        return await self._storage.get_project_by_avito_user_id(avito_user_id)

    def _create_messenger_for_project(self, project: Project) -> MessengerClient:
        """Create a MessengerClient for a specific project.
        
        Args:
            project: The project with Avito credentials
            
        Returns:
            MessengerClient configured for the project
        """
        token_manager = TokenManager(
            client_id=project.avito_client_id or "",
            client_secret=project.avito_client_secret or "",
        )
        return MessengerClient(
            user_id=project.avito_user_id or "",
            token_manager=token_manager,
        )

    def _create_retrieval_for_project(self, project: Project) -> CascadingRetrieval:
        """Create a CascadingRetrieval for a specific project.
        
        Args:
            project: The project with FileSearch store
            
        Returns:
            CascadingRetrieval configured for the project's store
        """
        file_search_client = FileSearchClient(
            api_key=self._gemini_api_key,
            store_name=project.filesearch_store_id or "",
        )
        return CascadingRetrieval(file_search_client=file_search_client)

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

        # Step 4: Look up project by Avito user_id
        project = await self._get_project_for_webhook(payload)
        
        # Determine which bot_user_id to use for filtering own messages
        if project and project.avito_user_id:
            bot_user_id = project.avito_user_id
            logger.info(f"Using project {project.id} ({project.name}) for processing")
        else:
            bot_user_id = self._bot_user_id
            logger.info("No project found, using default credentials")

        # Step 5: Filter own messages (bot's own messages)
        if payload.author_id == bot_user_id:
            logger.info(f"Message is from bot itself, skipping")
            return

        # Step 6: Save incoming message
        incoming_message = self._create_stored_message(payload)
        await self._storage.save_message(incoming_message)
        logger.debug(f"Saved incoming message {payload.message_id}")

        # Get message text for processing
        message_text = payload.message_text
        if not message_text:
            logger.info("Message has no text content, skipping")
            return

        item_id = payload.item_id
        project_id = project.id if project else None

        # Step 7: Load chat context
        context = await self._storage.get_chat_history(
            chat_id, limit=self._context_limit
        )
        logger.debug(f"Loaded {len(context)} messages for context")

        # Step 8: Get messenger and retrieval for this request
        if project and project.avito_connected:
            messenger = self._create_messenger_for_project(project)
            retrieval = self._create_retrieval_for_project(project) if project.filesearch_store_id else self._retrieval
        else:
            messenger = self._messenger
            retrieval = self._retrieval

        # Step 9: Check for escalation
        if self._answer_policy.needs_escalation(message_text):
            await self._handle_escalation(
                chat_id=chat_id,
                item_id=item_id,
                customer_message=message_text,
                context=context,
                messenger=messenger,
                bot_user_id=bot_user_id,
                project_id=project_id,
            )
            return

        # Step 10: RAG retrieval + answer generation
        retrieval_result = await retrieval.retrieve(
            query=message_text,
            item_id=item_id,
        )

        answer_result = await self._answer_policy.generate_answer(
            question=message_text,
            context=context,
            retrieval_result=retrieval_result,
        )

        # Step 11: Send response to Avito
        try:
            await messenger.send_message(chat_id, answer_result.answer)
            await messenger.mark_as_read(chat_id)
            logger.info(f"Sent response to chat {chat_id}")
        except MessengerClientError as e:
            logger.error(f"Failed to send message to Avito: {e}")
            # Don't save response if sending failed
            return

        # Step 12: Save bot response
        bot_message = StoredMessage(
            chat_id=chat_id,
            sender_id=bot_user_id,
            text=answer_result.answer,
            is_bot_message=True,
            item_id=item_id,
            created_at=datetime.utcnow(),
        )
        await self._storage.save_message(bot_message)

        # Step 13: Save dialog log with project_id
        dialog_log = DialogLog(
            chat_id=chat_id,
            item_id=item_id,
            project_id=project_id,
            customer_question=message_text,
            bot_answer=answer_result.answer,
            found_status=answer_result.found_status,
            sources=answer_result.sources,
        )
        await self._storage.save_dialog_log(dialog_log)

        # Step 14: Log to Telegram
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
            f"status={answer_result.found_status}, project_id={project_id}"
        )

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
        messenger: MessengerClient,
        bot_user_id: str,
        project_id: Optional[int] = None,
    ) -> None:
        """Handle escalation request from customer.
        
        Args:
            chat_id: The chat ID
            item_id: Optional item ID
            customer_message: The customer's message
            context: Chat history context
            messenger: MessengerClient to use for sending
            bot_user_id: Bot user ID for saving messages
            project_id: Optional project ID for logging
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
            await messenger.send_message(chat_id, escalation_response)
            await messenger.mark_as_read(chat_id)
            logger.info(f"Sent escalation response to chat {chat_id}")
        except MessengerClientError as e:
            logger.error(f"Failed to send escalation response: {e}")
            return

        # Save bot response
        bot_message = StoredMessage(
            chat_id=chat_id,
            sender_id=bot_user_id,
            text=escalation_response,
            is_bot_message=True,
            item_id=item_id,
            created_at=datetime.utcnow(),
        )
        await self._storage.save_message(bot_message)

        # Save dialog log for escalation with project_id
        dialog_log = DialogLog(
            chat_id=chat_id,
            item_id=item_id,
            project_id=project_id,
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
