#!/usr/bin/env python3
"""Script to register Avito webhook for receiving message notifications.

Usage:
    python scripts/register_webhook.py

The script reads configuration from .env file and registers the webhook URL
with Avito Messenger API.

Requirements: 2.4
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.avito.messenger_client import MessengerClient, MessengerClientError
from app.avito.oauth import TokenManager, TokenManagerError
from app.config import get_settings


async def register_webhook() -> bool:
    """Register webhook with Avito API.
    
    Returns:
        True if registration successful, False otherwise
    """
    try:
        settings = get_settings()
    except Exception as e:
        print(f"❌ Ошибка загрузки конфигурации: {e}")
        print("\nУбедитесь, что файл .env существует и содержит все необходимые переменные:")
        print("  - AVITO_CLIENT_ID")
        print("  - AVITO_CLIENT_SECRET")
        print("  - AVITO_USER_ID")
        print("  - APP_BASE_URL")
        return False

    webhook_url = f"{settings.app_base_url.rstrip('/')}/avito/webhook"
    
    print("=" * 60)
    print("🔗 Регистрация Avito Webhook")
    print("=" * 60)
    print(f"\n📍 Webhook URL: {webhook_url}")
    print(f"👤 User ID: {settings.avito_user_id}")
    
    # Initialize token manager
    token_manager = TokenManager(
        client_id=settings.avito_client_id,
        client_secret=settings.avito_client_secret,
    )
    
    # Initialize messenger client
    messenger = MessengerClient(
        user_id=settings.avito_user_id,
        token_manager=token_manager,
    )
    
    try:
        print("\n⏳ Получение OAuth2 токена...")
        await token_manager.get_token()
        print("✅ Токен получен успешно")
        
        print("\n⏳ Регистрация webhook...")
        await messenger.register_webhook(webhook_url)
        print("✅ Webhook зарегистрирован успешно!")
        
        print("\n" + "=" * 60)
        print("📋 Инструкции по проверке:")
        print("=" * 60)
        print(f"""
1. Убедитесь, что ваш сервер доступен по адресу:
   {webhook_url}

2. Проверьте health endpoint:
   curl {settings.app_base_url.rstrip('/')}/health

3. Отправьте тестовое сообщение в любой чат на Avito
   и проверьте логи сервера.

4. Для проверки webhook вручную:
   curl -X POST {webhook_url} \\
     -H "Content-Type: application/json" \\
     -d '{{"id": "test-event", "type": "message", "payload": {{}}}}'
""")
        return True
        
    except TokenManagerError as e:
        print(f"\n❌ Ошибка авторизации: {e}")
        print("\nПроверьте правильность AVITO_CLIENT_ID и AVITO_CLIENT_SECRET")
        return False
        
    except MessengerClientError as e:
        print(f"\n❌ Ошибка регистрации webhook: {e}")
        print("\nВозможные причины:")
        print("  - Неверный URL (должен быть HTTPS)")
        print("  - Сервер недоступен извне")
        print("  - Проблемы с сертификатом SSL")
        return False
        
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        return False


def main():
    """Entry point."""
    print("\n🚀 Avito AI Auto-Responder - Регистрация Webhook\n")
    
    success = asyncio.run(register_webhook())
    
    if success:
        print("\n✅ Готово! Webhook успешно зарегистрирован.\n")
        sys.exit(0)
    else:
        print("\n❌ Регистрация не удалась. Проверьте ошибки выше.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
