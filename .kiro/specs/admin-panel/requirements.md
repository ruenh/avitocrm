# Requirements Document

## Introduction

Минималистичная админ-панель для управления Avito AI Auto-Responder. Встроена в FastAPI приложение с использованием Jinja2 + HTMX + Tailwind CSS. Предназначена для индивидуального использования без многопользовательской авторизации.

Ключевые возможности:

- Управление проектами (базами знаний)
- Загрузка и управление документами в FileSearch
- Чат с Gemini для тестирования базы знаний
- Привязка Avito аккаунтов к проектам
- Просмотр статистики и истории диалогов

## Glossary

- **Admin_Panel**: Веб-интерфейс для управления системой
- **Project**: Логическая единица, объединяющая базу знаний и Avito аккаунт
- **FileSearch_Manager**: Компонент управления документами в Gemini File Search
- **Chat_Interface**: Интерфейс для тестового общения с Gemini по базе знаний проекта
- **Avito_Integration**: Компонент привязки и мониторинга Avito аккаунта
- **Dashboard**: Главная страница со статистикой

## Requirements

### Requirement 1: Управление проектами

**User Story:** As a user, I want to create and manage projects, so that I can organize different knowledge bases and Avito accounts.

#### Acceptance Criteria

1. THE Admin_Panel SHALL display a list of all projects on the main page
2. WHEN a user clicks "Create Project", THE Admin_Panel SHALL show a form with fields: name, description
3. WHEN a project is created, THE Admin_Panel SHALL create a corresponding FileSearch store in Gemini
4. THE Admin_Panel SHALL allow editing project name and description
5. THE Admin_Panel SHALL allow deleting a project with confirmation dialog
6. WHEN a project is deleted, THE Admin_Panel SHALL remove associated FileSearch store and documents

### Requirement 2: Управление документами FileSearch

**User Story:** As a user, I want to upload and manage documents in a project's knowledge base, so that the AI can answer questions based on them.

#### Acceptance Criteria

1. THE FileSearch_Manager SHALL display a list of documents in the selected project
2. WHEN a user uploads a file, THE FileSearch_Manager SHALL upload it to the project's FileSearch store
3. THE FileSearch_Manager SHALL support file formats: txt, md, pdf, docx, json
4. THE FileSearch_Manager SHALL display document metadata: name, size, upload date, item_id (if set)
5. THE FileSearch_Manager SHALL allow setting item_id for product-specific documents
6. THE FileSearch_Manager SHALL allow deleting documents from the store
7. WHEN uploading, THE FileSearch_Manager SHALL show upload progress

### Requirement 3: Чат с Gemini

**User Story:** As a user, I want to test the knowledge base by chatting with Gemini, so that I can verify answers before connecting to Avito.

#### Acceptance Criteria

1. THE Chat_Interface SHALL provide a chat input field and message history
2. WHEN a user sends a message, THE Chat_Interface SHALL query Gemini with the project's FileSearch store
3. THE Chat_Interface SHALL display the AI response with source citations
4. THE Chat_Interface SHALL indicate if the answer was found in the knowledge base or is a fallback
5. THE Chat_Interface SHALL allow clearing chat history
6. THE Chat_Interface SHALL show typing indicator while waiting for response

### Requirement 4: Интеграция с Avito

**User Story:** As a user, I want to connect my Avito account to a project, so that the AI can respond to customer messages.

#### Acceptance Criteria

1. THE Avito_Integration SHALL allow entering Avito credentials: client_id, client_secret, user_id
2. WHEN credentials are saved, THE Avito_Integration SHALL verify them by fetching a token
3. THE Avito_Integration SHALL display connection status: connected/disconnected/error
4. THE Avito_Integration SHALL allow registering webhook for the project
5. THE Avito_Integration SHALL display webhook registration status
6. IF credentials are invalid, THEN THE Avito_Integration SHALL show an error message

### Requirement 5: Статистика и история

**User Story:** As a user, I want to see statistics and dialog history, so that I can monitor the bot's performance.

#### Acceptance Criteria

1. THE Dashboard SHALL display total statistics: messages received, responses sent, escalations
2. THE Dashboard SHALL display statistics per project
3. THE Admin_Panel SHALL show a list of recent dialogs with: chat_id, question, answer, status, timestamp
4. THE Admin_Panel SHALL allow filtering dialogs by project and status (FOUND/NOT_FOUND/ESCALATION)
5. THE Admin_Panel SHALL allow viewing full dialog history for a specific chat_id

### Requirement 6: UI/UX дизайн

**User Story:** As a user, I want a clean and minimal interface, so that I can efficiently manage the system.

#### Acceptance Criteria

1. THE Admin_Panel SHALL use Tailwind CSS for styling
2. THE Admin_Panel SHALL have a sidebar navigation with: Projects, Statistics
3. THE Admin_Panel SHALL use HTMX for dynamic updates without full page reloads
4. THE Admin_Panel SHALL be responsive and work on mobile devices
5. THE Admin_Panel SHALL use a light color scheme with subtle accents
6. THE Admin_Panel SHALL show loading states for async operations
7. THE Admin_Panel SHALL display toast notifications for success/error messages

### Requirement 7: Безопасность

**User Story:** As a user, I want basic protection for the admin panel, so that unauthorized users cannot access it.

#### Acceptance Criteria

1. THE Admin_Panel SHALL require a password to access (configured via ADMIN_PASSWORD env variable)
2. THE Admin_Panel SHALL use session cookies for authentication
3. THE Admin_Panel SHALL have a logout button
4. IF no password is configured, THEN THE Admin_Panel SHALL be accessible without authentication (development mode)
