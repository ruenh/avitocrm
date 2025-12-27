"""Telegram notification module for sending logs and escalations."""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends logs and escalation notifications to Telegram."""

    TELEGRAM_API_BASE = "https://api.telegram.org/bot"

    def __init__(self, bot_token: str, owner_chat_id: str) -> None:
        """Initialize TelegramNotifier.

        Args:
            bot_token: Telegram bot token from BotFather.
            owner_chat_id: Chat ID of the owner to receive notifications.
        """
        self._bot_token = bot_token
        self._owner_chat_id = owner_chat_id
        self._api_url = f"{self.TELEGRAM_API_BASE}{bot_token}/sendMessage"

    async def send_log(
        self,
        chat_id: str,
        item_id: Optional[str],
        question: str,
        answer: str,
        found_status: str,
        sources: list[str],
    ) -> None:
        """Send a log message about bot response to the owner.

        Args:
            chat_id: Avito chat ID.
            item_id: Item ID if available.
            question: Customer's question.
            answer: Bot's answer.
            found_status: FOUND, NOT_FOUND, or ESCALATION.
            sources: List of source file names.
        """
        sources_text = ", ".join(sources) if sources else "—"
        item_text = item_id or "—"

        message = (
            f"📨 Новый ответ бота\n\n"
            f"Chat: {chat_id}\n"
            f"Item: {item_text}\n"
            f"Status: {found_status}\n\n"
            f"❓ Вопрос:\n{question}\n\n"
            f"🤖 Ответ:\n{answer}\n\n"
            f"📚 Источники: {sources_text}"
        )

        await self._send_message(message)


    async def send_escalation(
        self,
        chat_id: str,
        item_id: Optional[str],
        customer_message: str,
        last_ai_response: Optional[str],
    ) -> None:
        """Send an escalation notification to the owner.

        Args:
            chat_id: Avito chat ID.
            item_id: Item ID if available.
            customer_message: The customer's message requesting escalation.
            last_ai_response: The last AI response before escalation, if any.
        """
        item_text = item_id or "—"
        last_response_text = last_ai_response or "—"

        message = (
            f"🚨 Запрос на эскалацию!\n\n"
            f"Chat: {chat_id}\n"
            f"Item: {item_text}\n\n"
            f"💬 Сообщение клиента:\n{customer_message}\n\n"
            f"🤖 Последний ответ бота:\n{last_response_text}"
        )

        await self._send_message(message)

    async def _send_message(self, text: str) -> None:
        """Send a message to the owner's Telegram chat.

        Errors are logged but do not propagate to avoid affecting the main flow.

        Args:
            text: Message text to send.
        """
        payload = {
            "chat_id": self._owner_chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self._api_url, json=payload)
                response.raise_for_status()
                logger.debug("Telegram notification sent successfully")
        except httpx.TimeoutException:
            logger.warning("Telegram notification timed out, skipping")
        except httpx.HTTPStatusError as e:
            logger.error(
                "Telegram API error: %s - %s",
                e.response.status_code,
                e.response.text,
            )
        except Exception as e:
            logger.error("Failed to send Telegram notification: %s", e)
