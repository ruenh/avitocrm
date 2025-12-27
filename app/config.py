"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Avito OAuth2
    avito_client_id: str
    avito_client_secret: str
    avito_user_id: str

    # Google Gemini
    gemini_api_key: str
    file_search_store_name: str

    # Telegram
    telegram_bot_token: str
    telegram_owner_chat_id: str

    # App
    app_base_url: str
    database_url: str = "sqlite:///./data/avito_responder.db"
    message_context_limit: int = 20
    
    # Admin panel
    admin_password: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


def get_settings() -> Settings:
    """Get application settings instance."""
    return Settings()
