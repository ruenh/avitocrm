# Implementation Plan: Avito AI Auto-Responder

## Overview

Пошаговая реализация production-ready backend на Python 3.12 + FastAPI для автоматических ответов в Avito с RAG на Google Gemini File Search. Каждая задача строится на предыдущих, обеспечивая инкрементальный прогресс.

## Tasks

- [x] 1. Инициализация проекта и конфигурация

  - [x] 1.1 Создать структуру проекта и pyproject.toml с зависимостями
    - Создать директории: app/, app/avito/, app/rag/, app/telegram/, app/storage/, app/core/, app/models/, scripts/, systemd/, data/, docs/, tests/
    - Создать pyproject.toml с FastAPI, uvicorn, pydantic, httpx, aiosqlite, google-generativeai, hypothesis
    - Создать requirements.txt
    - _Requirements: 11.4_
  - [x] 1.2 Реализовать config.py с Pydantic Settings
    - Создать класс Settings с полями: avito_client_id, avito_client_secret, avito_user_id, gemini_api_key, file_search_store_name, telegram_bot_token, telegram_owner_chat_id, app_base_url, database_url, message_context_limit
    - Загрузка из .env файла
    - Создать .env.example
    - _Requirements: 11.1_
  - [ ]\* 1.3 Написать unit тест для загрузки конфигурации
    - Тест на загрузку из env переменных
    - Тест на ошибку при отсутствии обязательных переменных
    - _Requirements: 11.1_

- [x] 2. Реализация Storage Layer

  - [x] 2.1 Создать абстрактный интерфейс StorageInterface
    - Определить ABC класс с методами: is_event_processed, mark_event_processed, save_message, get_chat_history, save_dialog_log
    - Создать Pydantic модели: StoredMessage, DialogLog
    - _Requirements: 10.6_
  - [x] 2.2 Реализовать SQLiteStorage
    - Создать схему БД: processed_events, messages, dialog_logs
    - Реализовать все методы StorageInterface
    - Автоматическая инициализация схемы при первом запуске
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.7_
  - [ ]\* 2.3 Написать property тест для Message Persistence Round-Trip
    - **Property 5: Message Persistence Round-Trip**
    - **Validates: Requirements 3.1, 3.5**
  - [ ]\* 2.4 Написать property тест для Context Size Limit
    - **Property 6: Context Size Limit**
    - **Validates: Requirements 3.2**
  - [ ]\* 2.5 Написать property тест для Deduplication Idempotence
    - **Property 15: Deduplication Idempotence**
    - **Validates: Requirements 9.1, 9.2, 9.3**

- [x] 3. Checkpoint - Storage Layer

  - Убедиться, что все тесты проходят
  - Проверить создание БД и таблиц
  - Спросить пользователя, если есть вопросы

- [x] 4. Реализация Avito OAuth2 и Messenger Client

  - [x] 4.1 Реализовать TokenManager
    - Получение токена через client_credentials grant
    - Кэширование токена в памяти
    - Автоматическое обновление при истечении или 401
    - Retry с exponential backoff при ошибках
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - [x] 4.2 Реализовать MessengerClient
    - Метод get_messages(chat_id, limit)
    - Метод send_message(chat_id, text)
    - Метод mark_as_read(chat_id)
    - Интеграция с TokenManager для авторизации
    - _Requirements: 7.1, 7.2_
  - [x] 4.3 Создать webhook_models.py с Pydantic моделями
    - WebhookPayload, MessagePayload, MessageContent, ChatContext
    - Валидация входящих данных
    - _Requirements: 2.1_
  - [ ]\* 4.4 Написать property тест для Token Caching Consistency
    - **Property 2: Token Caching Consistency**
    - **Validates: Requirements 1.3**
  - [ ]\* 4.5 Написать unit тест для TokenManager
    - Тест на получение токена
    - Тест на обновление при 401
    - _Requirements: 1.1, 1.2_

- [x] 5. Checkpoint - Avito Integration

  - Убедиться, что все тесты проходят
  - Спросить пользователя, если есть вопросы

- [x] 6. Реализация RAG Engine

  - [x] 6.1 Реализовать FileSearchClient
    - Метод ensure_store_exists() для создания/получения File Search Store
    - Метод upload_document(file_path, item_id, metadata)
    - Метод search(query, item_id) с фильтрацией по метаданным
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.7_
  - [x] 6.2 Реализовать CascadingRetrieval
    - Каскадный поиск: сначала по item_id, затем в общих документах
    - Возврат RetrievalResult с found, chunks, search_strategy
    - _Requirements: 4.5, 4.6_
  - [x] 6.3 Реализовать AnswerPolicy
    - Метод needs_escalation(message) для детекции ключевых слов
    - Метод generate_answer(question, context, retrieval_result)
    - Fallback сообщение при отсутствии результатов
    - Анти-галлюцинационный контракт
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.1_
  - [ ]\* 6.4 Написать property тест для Anti-Hallucination Contract
    - **Property 11: Anti-Hallucination Contract**
    - **Validates: Requirements 5.1, 5.2**
  - [ ]\* 6.5 Написать property тест для Escalation Handling
    - **Property 12: Escalation Handling**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
  - [ ]\* 6.6 Написать property тест для Cascading Search Strategy
    - **Property 9: Cascading Search Strategy**
    - **Validates: Requirements 4.5, 4.6**

- [x] 7. Checkpoint - RAG Engine

  - Убедиться, что все тесты проходят
  - Спросить пользователя, если есть вопросы

- [x] 8. Реализация Telegram Notifier

  - [x] 8.1 Реализовать TelegramNotifier
    - Метод send_log(chat_id, item_id, question, answer, found_status, sources)
    - Метод send_escalation(chat_id, item_id, customer_message, last_ai_response)
    - Форматирование сообщений с emoji
    - Обработка ошибок без влияния на основной flow
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 6.2_
  - [ ]\* 8.2 Написать property тест для Telegram Logging Completeness
    - **Property 14: Telegram Logging Completeness**
    - **Validates: Requirements 8.1, 8.2**

- [x] 9. Реализация Core Auto Responder

  - [x] 9.1 Реализовать AutoResponder
    - Метод process_event(payload) с полным циклом обработки
    - Дедупликация через Deduplicator
    - Фильтрация system и own messages
    - Сохранение входящих сообщений
    - Загрузка контекста (20 сообщений)
    - Проверка на эскалацию
    - RAG retrieval + генерация ответа
    - Отправка в Avito + mark as read
    - Сохранение ответа и лога
    - Логирование в Telegram
    - _Requirements: 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 6.3, 6.4, 7.1, 7.2, 7.3_
  - [ ]\* 9.2 Написать property тест для Message Filtering
    - **Property 4: Message Filtering**
    - **Validates: Requirements 2.5, 3.6**
  - [ ]\* 9.3 Написать property тест для Response Delivery Completeness
    - **Property 13: Response Delivery Completeness**
    - **Validates: Requirements 7.1, 7.2, 7.3**

- [x] 10. Реализация FastAPI Webhook Handler

  - [x] 10.1 Создать main.py с FastAPI приложением
    - Endpoint POST /avito/webhook
    - Немедленный ответ 200 OK
    - BackgroundTasks для асинхронной обработки
    - Health check endpoint GET /health
    - _Requirements: 2.1, 2.2, 2.3_
  - [x] 10.2 Интегрировать все компоненты
    - Dependency injection для Storage, TokenManager, MessengerClient, RAG, Telegram
    - Lifespan для инициализации и cleanup
    - _Requirements: 2.1, 2.2, 2.3_
  - [ ]\* 10.3 Написать property тест для Webhook Async Processing
    - **Property 3: Webhook Async Processing**
    - **Validates: Requirements 2.3**

- [x] 11. Checkpoint - Core Application

  - Убедиться, что все тесты проходят
  - Проверить end-to-end flow с mock данными
  - Спросить пользователя, если есть вопросы

- [x] 12. Скрипты и деплой

  - [x] 12.1 Создать скрипт register_webhook.py
    - Регистрация webhook через POST /messenger/v3/webhook
    - Вывод результата и инструкций
    - _Requirements: 2.4_
  - [x] 12.2 Создать скрипт sync_filesearch.py
    - Загрузка документов из docs/ в File Search Store
    - Поддержка item_id в имени файла или метаданных
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - [x] 12.3 Создать systemd unit file
    - avito-responder.service для автозапуска
    - Конфигурация uvicorn/gunicorn с workers
    - _Requirements: 11.2_
  - [x] 12.4 Создать README.md
    - Инструкции по установке зависимостей
    - Настройка ENV переменных
    - Регистрация webhook
    - Загрузка документов в File Search
    - Запуск и проверка
    - curl примеры для тестирования
    - _Requirements: 11.3_

- [x] 13. Final Checkpoint
  - Убедиться, что все тесты проходят
  - Проверить документацию
  - Спросить пользователя, если есть вопросы

## Notes

- Задачи с `*` являются опциональными (тесты) и могут быть пропущены для быстрого MVP
- Каждая задача ссылается на конкретные требования для трассируемости
- Checkpoints обеспечивают инкрементальную валидацию
- Property тесты валидируют универсальные свойства корректности
- Unit тесты валидируют конкретные примеры и edge cases
