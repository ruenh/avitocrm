"""Avito OAuth2 Token Manager with caching and auto-refresh."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

AVITO_TOKEN_URL = "https://api.avito.ru/token"


class TokenResponse(BaseModel):
    """OAuth2 token response from Avito API."""

    access_token: str
    token_type: str
    expires_in: int
    obtained_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 60s buffer)."""
        return datetime.utcnow() > self.obtained_at + timedelta(
            seconds=self.expires_in - 60
        )


class TokenManagerError(Exception):
    """Base exception for TokenManager errors."""

    pass


class ConfigurationError(TokenManagerError):
    """Raised when credentials are invalid."""

    pass


class TokenManager:
    """Manages Avito OAuth2 tokens with caching and auto-refresh.

    Features:
    - Token caching in memory
    - Automatic refresh on expiration
    - Retry with exponential backoff on errors
    - Thread-safe token refresh
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ):
        """Initialize TokenManager.

        Args:
            client_id: Avito OAuth2 client ID
            client_secret: Avito OAuth2 client secret
            max_retries: Maximum number of retry attempts
            base_delay: Base delay for exponential backoff (seconds)
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._cached_token: Optional[TokenResponse] = None
        self._refresh_lock = asyncio.Lock()

    async def get_token(self) -> str:
        """Get a valid access token, refreshing if necessary.

        Returns:
            Valid access token string

        Raises:
            TokenManagerError: If token cannot be obtained
        """
        if self._cached_token and not self._cached_token.is_expired:
            return self._cached_token.access_token

        return await self.refresh_token()

    async def refresh_token(self) -> str:
        """Force refresh the token.

        Returns:
            New access token string

        Raises:
            TokenManagerError: If token cannot be obtained
        """
        async with self._refresh_lock:
            # Double-check after acquiring lock
            if self._cached_token and not self._cached_token.is_expired:
                return self._cached_token.access_token

            token_response = await self._fetch_token_with_retry()
            self._cached_token = token_response
            logger.info("Token refreshed successfully, expires in %ds", token_response.expires_in)
            return token_response.access_token

    async def _fetch_token_with_retry(self) -> TokenResponse:
        """Fetch token with exponential backoff retry.

        Returns:
            TokenResponse with new token

        Raises:
            TokenManagerError: If all retries fail
            ConfigurationError: If credentials are invalid
        """
        last_error: Optional[Exception] = None

        for attempt in range(self._max_retries):
            try:
                return await self._fetch_token()
            except ConfigurationError:
                # Don't retry on invalid credentials
                raise
            except TokenManagerError as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    delay = self._base_delay * (2**attempt)
                    logger.warning(
                        "Token fetch failed (attempt %d/%d), retrying in %.1fs: %s",
                        attempt + 1,
                        self._max_retries,
                        delay,
                        str(e),
                    )
                    await asyncio.sleep(delay)

        raise TokenManagerError(
            f"Failed to obtain token after {self._max_retries} attempts: {last_error}"
        )

    async def _fetch_token(self) -> TokenResponse:
        """Fetch a new token from Avito API.

        Returns:
            TokenResponse with new token

        Raises:
            ConfigurationError: If credentials are invalid (400)
            TokenManagerError: On network or API errors
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    AVITO_TOKEN_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                    },
                )

                if response.status_code == 400:
                    logger.error("Invalid credentials: %s", response.text)
                    raise ConfigurationError(
                        f"Invalid Avito credentials: {response.text}"
                    )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "60")
                    raise TokenManagerError(
                        f"Rate limited, retry after {retry_after}s"
                    )

                response.raise_for_status()

                data = response.json()
                return TokenResponse(
                    access_token=data["access_token"],
                    token_type=data.get("token_type", "Bearer"),
                    expires_in=data["expires_in"],
                )

            except httpx.TimeoutException as e:
                raise TokenManagerError(f"Token request timed out: {e}")
            except httpx.HTTPStatusError as e:
                raise TokenManagerError(f"HTTP error: {e.response.status_code}")
            except httpx.RequestError as e:
                raise TokenManagerError(f"Network error: {e}")

    def invalidate(self) -> None:
        """Invalidate the cached token (e.g., after receiving 401)."""
        self._cached_token = None
        logger.info("Token invalidated")

    @property
    def has_valid_token(self) -> bool:
        """Check if a valid (non-expired) token is cached."""
        return self._cached_token is not None and not self._cached_token.is_expired
