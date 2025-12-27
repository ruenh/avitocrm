"""Avito Messenger API client."""

import logging
from datetime import datetime
from typing import Optional

import httpx
from pydantic import BaseModel

from app.avito.oauth import TokenManager

logger = logging.getLogger(__name__)

AVITO_API_BASE = "https://api.avito.ru"


class Message(BaseModel):
    """Message from Avito Messenger API."""

    id: str
    author_id: str
    content: Optional[str] = None
    type: str
    created: datetime
    direction: Optional[str] = None


class SendResult(BaseModel):
    """Result of sending a message."""

    message_id: str
    success: bool


class MessengerClientError(Exception):
    """Base exception for MessengerClient errors."""

    pass


class MessengerClient:
    """HTTP client for Avito Messenger API.

    Handles authentication via TokenManager and provides methods
    for interacting with Avito chats.
    """

    def __init__(
        self,
        user_id: str,
        token_manager: TokenManager,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ):
        """Initialize MessengerClient.

        Args:
            user_id: Avito user ID for API calls
            token_manager: TokenManager instance for authentication
            max_retries: Maximum retry attempts for failed requests
            base_delay: Base delay for exponential backoff
        """
        self._user_id = user_id
        self._token_manager = token_manager
        self._max_retries = max_retries
        self._base_delay = base_delay

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[dict] = None,
        params: Optional[dict] = None,
        retry_on_401: bool = True,
    ) -> httpx.Response:
        """Make an authenticated request to Avito API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            json_data: JSON body for POST requests
            params: Query parameters
            retry_on_401: Whether to retry on 401 (token refresh)

        Returns:
            httpx.Response object

        Raises:
            MessengerClientError: On request failure
        """
        token = await self._token_manager.get_token()
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.request(
                    method,
                    f"{AVITO_API_BASE}{endpoint}",
                    headers=headers,
                    json=json_data,
                    params=params,
                )

                if response.status_code == 401 and retry_on_401:
                    logger.warning("Got 401, refreshing token and retrying")
                    self._token_manager.invalidate()
                    return await self._make_request(
                        method, endpoint, json_data, params, retry_on_401=False
                    )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "60")
                    raise MessengerClientError(
                        f"Rate limited, retry after {retry_after}s"
                    )

                response.raise_for_status()
                return response

            except httpx.TimeoutException as e:
                raise MessengerClientError(f"Request timed out: {e}")
            except httpx.HTTPStatusError as e:
                raise MessengerClientError(
                    f"HTTP error {e.response.status_code}: {e.response.text}"
                )
            except httpx.RequestError as e:
                raise MessengerClientError(f"Network error: {e}")

    async def get_messages(
        self, chat_id: str, limit: int = 1
    ) -> list[Message]:
        """Get messages from a chat.

        GET /messenger/v3/accounts/{user_id}/chats/{chat_id}/messages/

        Args:
            chat_id: Chat ID to get messages from
            limit: Maximum number of messages to retrieve

        Returns:
            List of Message objects
        """
        endpoint = f"/messenger/v3/accounts/{self._user_id}/chats/{chat_id}/messages/"
        response = await self._make_request("GET", endpoint, params={"limit": limit})

        data = response.json()
        messages = []

        for msg_data in data.get("messages", []):
            messages.append(
                Message(
                    id=msg_data["id"],
                    author_id=msg_data["author_id"],
                    content=msg_data.get("content", {}).get("text"),
                    type=msg_data.get("type", "text"),
                    created=datetime.fromisoformat(
                        msg_data["created"].replace("Z", "+00:00")
                    ),
                    direction=msg_data.get("direction"),
                )
            )

        return messages

    async def send_message(self, chat_id: str, text: str) -> SendResult:
        """Send a text message to a chat.

        POST /messenger/v1/accounts/{user_id}/chats/{chat_id}/messages

        Args:
            chat_id: Chat ID to send message to
            text: Message text content

        Returns:
            SendResult with message_id and success status
        """
        endpoint = f"/messenger/v1/accounts/{self._user_id}/chats/{chat_id}/messages"
        response = await self._make_request(
            "POST",
            endpoint,
            json_data={
                "message": {
                    "text": text,
                },
                "type": "text",
            },
        )

        data = response.json()
        logger.info("Message sent to chat %s", chat_id)

        return SendResult(
            message_id=data.get("id", ""),
            success=True,
        )

    async def mark_as_read(self, chat_id: str) -> None:
        """Mark a chat as read.

        POST /messenger/v1/accounts/{user_id}/chats/{chat_id}/read

        Args:
            chat_id: Chat ID to mark as read
        """
        endpoint = f"/messenger/v1/accounts/{self._user_id}/chats/{chat_id}/read"
        await self._make_request("POST", endpoint)
        logger.debug("Chat %s marked as read", chat_id)

    async def register_webhook(self, url: str) -> None:
        """Register a webhook URL for receiving notifications.

        POST /messenger/v3/webhook

        Args:
            url: Webhook URL to register
        """
        endpoint = "/messenger/v3/webhook"
        await self._make_request(
            "POST",
            endpoint,
            json_data={"url": url},
        )
        logger.info("Webhook registered: %s", url)
