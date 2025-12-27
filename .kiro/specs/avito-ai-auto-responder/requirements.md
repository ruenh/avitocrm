# Requirements Document

## Introduction

Avito AI Auto-Responder — production-ready backend на Python 3.12 + FastAPI для автоматических ответов на сообщения покупателей в Avito с использованием RAG на базе Google Gemini File Search. Система предназначена для индивидуального использования, развёртывается на одном VDS Ubuntu.

Ключевые особенности:

- Локальное хранение истории сообщений (API Avito в бесплатном плане возвращает только последнее сообщение)
- Каскадный поиск в базе знаний: сначала по item_id, затем в общих документах
- Жёсткий анти-галлюцинационный контракт

## Glossary

- **Auto_Responder**: Основная система, обрабатывающая входящие сообщения и генерирующая ответы
- **Webhook_Handler**: Компонент, принимающий webhook-уведомления от Avito
- **RAG_Engine**: Компонент Retrieval-Augmented Generation на базе Gemini File Search
- **Knowledge_Base**: Хранилище документов с информацией о товарах в File Search Store
- **Telegram_Notifier**: Компонент отправки логов и уведомлений в Telegram
- **Token_Manager**: Компонент управления OAuth2 токенами Avito
- **Deduplicator**: Компонент предотвращения повторной обработки сообщений
- **Message_Store**: Локальное хранилище истории сообщений по chat_id
- **item_id**: Уникальный идентификатор товара на Avito
- **chat_id**: Уникальный идентификатор чата в Avito Messenger
- **File_Search_Store**: Хранилище документов Google Gemini для поиска
- **Cascading_Search**: Стратегия поиска: сначала по item_id, затем в общих документах

## Requirements

### Requirement 1: OAuth2 авторизация Avito

**User Story:** As a system administrator, I want the system to automatically manage Avito OAuth2 tokens, so that API calls are always authenticated without manual intervention.

#### Acceptance Criteria

1. WHEN the system starts, THE Token_Manager SHALL obtain an access token using client_credentials grant from https://api.avito.ru/token
2. WHEN an access token expires or API returns 401, THE Token_Manager SHALL automatically refresh the token
3. THE Token_Manager SHALL cache the access token in memory and reuse it until expiration
4. THE Token_Manager SHALL read AVITO_CLIENT_ID and AVITO_CLIENT_SECRET from environment variables
5. IF token retrieval fails, THEN THE Token_Manager SHALL log the error and retry with exponential backoff

### Requirement 2: Webhook регистрация и обработка

**User Story:** As a system administrator, I want to register and handle Avito webhooks, so that the system receives real-time notifications about new messages.

#### Acceptance Criteria

1. THE Webhook_Handler SHALL expose endpoint POST /avito/webhook for receiving Avito notifications
2. WHEN a webhook request is received, THE Webhook_Handler SHALL respond with HTTP 200 OK within 2 seconds
3. WHEN a webhook event is received, THE Webhook_Handler SHALL queue the event for background processing
4. THE Auto_Responder SHALL provide a script to register webhook via POST /messenger/v3/webhook
5. WHEN a message with type=system is received, THE Auto_Responder SHALL ignore it and not generate a response

### Requirement 3: Локальное хранение и получение контекста чата

**User Story:** As a system, I want to store and retrieve chat history locally, so that I can generate contextually relevant answers despite API limitations.

#### Acceptance Criteria

1. WHEN a new message is received via webhook, THE Message_Store SHALL save it to the database with chat_id, sender info, message text, and timestamp
2. WHEN processing a message for response, THE Auto_Responder SHALL retrieve the last 20 messages from Message_Store by chat_id
3. THE Auto_Responder SHALL extract item_id from the chat context if available
4. THE Auto_Responder SHALL use the locally stored messages to provide conversation context to RAG_Engine
5. THE Message_Store SHALL store both incoming customer messages and outgoing bot responses
6. THE Auto_Responder SHALL only respond to incoming messages from customers (not to own messages or system messages)

### Requirement 4: RAG с Google Gemini File Search

**User Story:** As a seller, I want the system to answer customer questions using my product documentation, so that customers receive accurate information.

#### Acceptance Criteria

1. THE Knowledge_Base SHALL create or use an existing File Search Store in Google Gemini
2. THE Knowledge_Base SHALL support uploading documents in formats: txt, docx, pdf, markdown, json
3. WHEN uploading a product-specific document, THE Knowledge_Base SHALL attach custom_metadata with item_id for filtering
4. WHEN uploading a general document (FAQ, delivery terms), THE Knowledge_Base SHALL mark it as general (no item_id filter)
5. WHEN generating an answer with item_id available, THE RAG_Engine SHALL use Cascading_Search: first search by item_id, then in general documents if no results
6. WHEN generating an answer without item_id, THE RAG_Engine SHALL search only in general documents
7. THE RAG_Engine SHALL return citations/grounding metadata along with the answer

### Requirement 5: Анти-галлюцинационный контракт

**User Story:** As a seller, I want the system to never fabricate product information, so that customers receive only verified information.

#### Acceptance Criteria

1. THE RAG_Engine SHALL NOT generate answers about price, specifications, availability, or conditions without File Search results
2. WHEN File Search returns no relevant fragments, THE Auto_Responder SHALL send exactly: "🤖: в моей базе нет нужной информации по твоему вопросу, можешь задать уточнение или мне вызвать менеджера?"
3. THE RAG_Engine SHALL only use information from File Search citations to compose answers
4. IF the answer cannot be grounded in File Search results, THEN THE Auto_Responder SHALL use the fallback message

### Requirement 6: Эскалация к менеджеру

**User Story:** As a customer, I want to request a human manager, so that I can get help with complex questions.

#### Acceptance Criteria

1. WHEN a customer message contains keywords "вызови менеджера", "позови менеджера", "позови человека", or "оператор", THE Auto_Responder SHALL trigger escalation
2. WHEN escalation is triggered, THE Telegram_Notifier SHALL send a notification to the owner with: customer message, last AI response, and chat link/chat_id
3. WHEN escalation is triggered, THE Auto_Responder SHALL send to customer: a short message that a manager will connect
4. WHEN escalation is triggered, THE Auto_Responder SHALL NOT answer product-related questions

### Requirement 7: Отправка ответов в Avito

**User Story:** As a system, I want to send responses back to Avito chats, so that customers receive answers.

#### Acceptance Criteria

1. WHEN an answer is generated, THE Auto_Responder SHALL send it via POST /messenger/v1/accounts/{user_id}/chats/{chat_id}/messages with type="text"
2. AFTER sending a message, THE Auto_Responder SHALL mark the chat as read via POST /messenger/v1/accounts/{user_id}/chats/{chat_id}/read
3. THE Auto_Responder SHALL send exactly one message per customer inquiry

### Requirement 8: Логирование в Telegram

**User Story:** As a seller, I want to receive logs of all bot responses in Telegram, so that I can monitor the system.

#### Acceptance Criteria

1. WHEN the Auto_Responder sends a message to Avito, THE Telegram_Notifier SHALL send a log to the owner
2. THE log message SHALL contain: chat_id, item_id (if available), customer question, bot answer, and FOUND/NOT_FOUND status
3. THE Telegram_Notifier SHALL optionally include source file names without exposing private data
4. THE Telegram_Notifier SHALL use TELEGRAM_BOT_TOKEN and TELEGRAM_OWNER_CHAT_ID from environment variables

### Requirement 9: Дедупликация событий

**User Story:** As a system, I want to prevent duplicate processing of messages, so that customers don't receive multiple identical responses.

#### Acceptance Criteria

1. THE Deduplicator SHALL store processed message_id/event_id in the database
2. WHEN a webhook event is received, THE Deduplicator SHALL check if it was already processed
3. IF an event was already processed, THEN THE Auto_Responder SHALL skip it without generating a response

### Requirement 10: Хранение данных

**User Story:** As a system administrator, I want data to be persisted locally, so that the system maintains state across restarts.

#### Acceptance Criteria

1. THE Storage SHALL use SQLite for MVP deployment
2. THE Storage SHALL store: processed message/event IDs for deduplication
3. THE Storage SHALL store: full message history per chat_id (sender, text, timestamp, is_bot_message)
4. THE Storage SHALL store: dialog logs with RAG results (question, answer, found_status, sources)
5. THE Storage SHALL optionally store cached Avito tokens
6. THE Storage SHALL provide an interface that allows migration to PostgreSQL/Supabase later
7. THE Storage SHALL initialize the database schema on first run

### Requirement 11: Конфигурация и развёртывание

**User Story:** As a system administrator, I want easy deployment on Ubuntu VDS, so that I can quickly set up the system.

#### Acceptance Criteria

1. THE Auto_Responder SHALL read all secrets from environment variables: AVITO_CLIENT_ID, AVITO_CLIENT_SECRET, AVITO_USER_ID, AVITO_WEBHOOK_URL, GEMINI_API_KEY, FILE_SEARCH_STORE_NAME, TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_CHAT_ID, APP_BASE_URL
2. THE project SHALL include a systemd unit file for auto-start with uvicorn/gunicorn workers
3. THE project SHALL include a README with deployment instructions for Ubuntu
4. THE project SHALL include requirements.txt or pyproject.toml with all dependencies
