# Design Document: Admin Panel

## Overview

Минималистичная админ-панель для Avito AI Auto-Responder, встроенная в FastAPI. Использует серверный рендеринг с Jinja2, динамические обновления через HTMX, и стилизацию Tailwind CSS.

### Ключевые архитектурные решения

1. **Server-Side Rendering** — Jinja2 templates, минимум JavaScript
2. **HTMX для интерактивности** — частичные обновления без SPA
3. **Tailwind CSS** — утилитарные классы, минимальный CSS
4. **Session-based auth** — простая авторизация через cookie

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Application                         │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                     Admin Router                           │  │
│  │  /admin/login     /admin/projects    /admin/stats         │  │
│  │  /admin/projects/{id}/files   /admin/projects/{id}/chat   │  │
│  │  /admin/projects/{id}/avito                               │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│  ┌───────────────────────────┴───────────────────────────────┐  │
│  │                    Jinja2 Templates                        │  │
│  │  base.html → layout, sidebar, navigation                  │  │
│  │  projects/list.html, projects/detail.html                 │  │
│  │  files/list.html, chat/index.html, avito/settings.html   │  │
│  │  stats/dashboard.html, stats/dialogs.html                │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│  ┌───────────────────────────┴───────────────────────────────┐  │
│  │                   Existing Services                        │  │
│  │  SQLiteStorage │ FileSearchClient │ TokenManager          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. Admin Router (app/admin/routes.py)

```python
from fastapi import APIRouter, Request, Depends, Form, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/admin/templates")

# Auth
@router.get("/login")
async def login_page(request: Request) -> HTMLResponse: ...

@router.post("/login")
async def login(request: Request, password: str = Form(...)) -> RedirectResponse: ...

@router.get("/logout")
async def logout(request: Request) -> RedirectResponse: ...

# Projects
@router.get("/")
@router.get("/projects")
async def projects_list(request: Request) -> HTMLResponse: ...

@router.post("/projects")
async def create_project(request: Request, name: str = Form(...), description: str = Form("")) -> HTMLResponse: ...

@router.get("/projects/{project_id}")
async def project_detail(request: Request, project_id: int) -> HTMLResponse: ...

@router.put("/projects/{project_id}")
async def update_project(request: Request, project_id: int, name: str = Form(...)) -> HTMLResponse: ...

@router.delete("/projects/{project_id}")
async def delete_project(request: Request, project_id: int) -> HTMLResponse: ...

# Files
@router.get("/projects/{project_id}/files")
async def files_list(request: Request, project_id: int) -> HTMLResponse: ...

@router.post("/projects/{project_id}/files")
async def upload_file(request: Request, project_id: int, file: UploadFile, item_id: str = Form(None)) -> HTMLResponse: ...

@router.delete("/projects/{project_id}/files/{file_id}")
async def delete_file(request: Request, project_id: int, file_id: str) -> HTMLResponse: ...

# Chat
@router.get("/projects/{project_id}/chat")
async def chat_page(request: Request, project_id: int) -> HTMLResponse: ...

@router.post("/projects/{project_id}/chat")
async def send_message(request: Request, project_id: int, message: str = Form(...)) -> HTMLResponse: ...

# Avito
@router.get("/projects/{project_id}/avito")
async def avito_settings(request: Request, project_id: int) -> HTMLResponse: ...

@router.post("/projects/{project_id}/avito")
async def save_avito_settings(request: Request, project_id: int, client_id: str = Form(...), client_secret: str = Form(...), user_id: str = Form(...)) -> HTMLResponse: ...

@router.post("/projects/{project_id}/avito/webhook")
async def register_webhook(request: Request, project_id: int) -> HTMLResponse: ...

# Stats
@router.get("/stats")
async def stats_dashboard(request: Request) -> HTMLResponse: ...

@router.get("/stats/dialogs")
async def dialogs_list(request: Request, project_id: int = None, status: str = None) -> HTMLResponse: ...
```

### 2. Auth Middleware (app/admin/auth.py)

```python
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class AdminAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/admin") and request.url.path != "/admin/login":
            if not self._is_authenticated(request):
                return RedirectResponse("/admin/login")
        return await call_next(request)

    def _is_authenticated(self, request: Request) -> bool:
        session_token = request.cookies.get("admin_session")
        return session_token == self._get_valid_token()
```

### 3. Project Service (app/admin/services.py)

```python
class ProjectService:
    async def list_projects(self) -> list[Project]: ...
    async def get_project(self, project_id: int) -> Project: ...
    async def create_project(self, name: str, description: str) -> Project: ...
    async def update_project(self, project_id: int, name: str, description: str) -> Project: ...
    async def delete_project(self, project_id: int) -> None: ...

class FileService:
    async def list_files(self, project_id: int) -> list[ProjectFile]: ...
    async def upload_file(self, project_id: int, file: UploadFile, item_id: str = None) -> ProjectFile: ...
    async def delete_file(self, project_id: int, file_id: str) -> None: ...

class ChatService:
    async def send_message(self, project_id: int, message: str) -> ChatResponse: ...
    async def get_history(self, project_id: int) -> list[ChatMessage]: ...
    async def clear_history(self, project_id: int) -> None: ...

class StatsService:
    async def get_dashboard_stats(self) -> DashboardStats: ...
    async def get_project_stats(self, project_id: int) -> ProjectStats: ...
    async def get_dialogs(self, project_id: int = None, status: str = None, limit: int = 50) -> list[DialogLog]: ...
```

## Data Models

### Project

```python
class Project(BaseModel):
    id: int
    name: str
    description: str = ""
    filesearch_store_id: str | None = None
    avito_client_id: str | None = None
    avito_client_secret: str | None = None
    avito_user_id: str | None = None
    avito_connected: bool = False
    webhook_registered: bool = False
    created_at: datetime
    updated_at: datetime
```

### ProjectFile

```python
class ProjectFile(BaseModel):
    id: str  # Gemini file ID
    name: str
    size: int
    item_id: str | None = None
    uploaded_at: datetime
```

### ChatMessage

```python
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    sources: list[str] = []
    found_status: str | None = None
    timestamp: datetime
```

### DashboardStats

```python
class DashboardStats(BaseModel):
    total_messages: int
    total_responses: int
    total_escalations: int
    messages_today: int
    found_rate: float  # процент ответов с найденной информацией
    projects_count: int
```

## Database Schema Updates

```sql
-- Новая таблица для проектов
CREATE TABLE projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    filesearch_store_id TEXT,
    avito_client_id TEXT,
    avito_client_secret TEXT,
    avito_user_id TEXT,
    avito_connected BOOLEAN DEFAULT FALSE,
    webhook_registered BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Новая таблица для файлов проекта
CREATE TABLE project_files (
    id TEXT PRIMARY KEY,  -- Gemini file ID
    project_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    size INTEGER NOT NULL,
    item_id TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Новая таблица для истории чата (тестовый чат)
CREATE TABLE chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    role TEXT NOT NULL,  -- 'user' | 'assistant'
    content TEXT NOT NULL,
    sources TEXT,  -- JSON array
    found_status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Обновление dialog_logs для связи с проектом
ALTER TABLE dialog_logs ADD COLUMN project_id INTEGER REFERENCES projects(id);
```

## Template Structure

```
app/admin/templates/
├── base.html              # Базовый layout с sidebar
├── components/
│   ├── sidebar.html       # Навигация
│   ├── toast.html         # Уведомления
│   ├── modal.html         # Модальные окна
│   └── loading.html       # Индикатор загрузки
├── auth/
│   └── login.html         # Страница входа
├── projects/
│   ├── list.html          # Список проектов
│   ├── card.html          # Карточка проекта (partial)
│   └── form.html          # Форма создания/редактирования
├── files/
│   ├── list.html          # Список файлов проекта
│   ├── row.html           # Строка файла (partial)
│   └── upload.html        # Форма загрузки
├── chat/
│   ├── index.html         # Страница чата
│   └── message.html       # Сообщение (partial)
├── avito/
│   └── settings.html      # Настройки Avito
└── stats/
    ├── dashboard.html     # Дашборд статистики
    └── dialogs.html       # История диалогов
```

## UI Wireframes

### Base Layout

```
┌─────────────────────────────────────────────────────────────┐
│  🤖 Avito AI                                    [Logout]    │
├──────────────┬──────────────────────────────────────────────┤
│              │                                              │
│  📁 Projects │           Main Content Area                  │
│              │                                              │
│  📊 Stats    │                                              │
│              │                                              │
│              │                                              │
│              │                                              │
│              │                                              │
│              │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

### Projects List

```
┌─────────────────────────────────────────────────────────────┐
│  Projects                              [+ New Project]      │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 📁 iPhone Store                                      │   │
│  │ База знаний для магазина iPhone                     │   │
│  │ 📄 12 files  │  ✅ Avito connected  │  📨 45 msgs   │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 📁 Furniture Shop                                    │   │
│  │ Мебельный магазин                                   │   │
│  │ 📄 8 files   │  ⚠️ Avito not connected              │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Project Detail (Files Tab)

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back    iPhone Store                                     │
├─────────────────────────────────────────────────────────────┤
│  [Files]  [Chat]  [Avito]                                   │
├─────────────────────────────────────────────────────────────┤
│  Upload: [Choose file...] Item ID: [______] [Upload]        │
├─────────────────────────────────────────────────────────────┤
│  📄 iphone_15_pro.txt      │ item_12345 │ 2.3 KB │ [🗑️]    │
│  📄 delivery_terms.md      │ —          │ 1.1 KB │ [🗑️]    │
│  📄 faq.txt                │ —          │ 4.5 KB │ [🗑️]    │
└─────────────────────────────────────────────────────────────┘
```

### Chat Interface

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back    iPhone Store                                     │
├─────────────────────────────────────────────────────────────┤
│  [Files]  [Chat]  [Avito]                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  👤 Какая цена на iPhone 15 Pro?                           │
│                                                             │
│  🤖 Цена iPhone 15 Pro составляет 120 000 рублей.          │
│     📚 Источник: iphone_15_pro.txt                         │
│     ✅ FOUND                                                │
│                                                             │
│  👤 А доставка есть?                                       │
│                                                             │
│  🤖 Да, доставка доступна по всей России...                │
│     📚 Источник: delivery_terms.md                         │
│     ✅ FOUND                                                │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  [Type your message...                        ] [Send]      │
└─────────────────────────────────────────────────────────────┘
```

### Avito Settings

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back    iPhone Store                                     │
├─────────────────────────────────────────────────────────────┤
│  [Files]  [Chat]  [Avito]                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Avito Integration                     Status: ✅ Connected │
│                                                             │
│  Client ID:     [tbQPR55N_WXoRPk2ZZWh___________]          │
│  Client Secret: [••••••••••••••••••••••••••••••]           │
│  User ID:       [123456789_____________________]           │
│                                                             │
│  [Save Credentials]    [Test Connection]                    │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  Webhook                              Status: ✅ Registered │
│  URL: https://avito.odindindindun.ru/avito/webhook         │
│                                                             │
│  [Register Webhook]                                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Stats Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│  Statistics                                                 │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │   156    │  │   142    │  │    14    │  │   91%    │   │
│  │ Messages │  │ Responses│  │Escalation│  │Found Rate│   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
├─────────────────────────────────────────────────────────────┤
│  Recent Dialogs                          [View All →]       │
├─────────────────────────────────────────────────────────────┤
│  chat_123 │ Какая цена? │ 120000 руб │ ✅ FOUND │ 5m ago   │
│  chat_456 │ Доставка?   │ Да, по РФ  │ ✅ FOUND │ 12m ago  │
│  chat_789 │ Позови мен..│ Подключаю  │ 🔔 ESCAL │ 1h ago   │
└─────────────────────────────────────────────────────────────┘
```

## HTMX Patterns

### Partial Updates

```html
<!-- Список файлов с HTMX -->
<div id="files-list" hx-get="/admin/projects/1/files" hx-trigger="load">
  <!-- Загружается динамически -->
</div>

<!-- Загрузка файла -->
<form
  hx-post="/admin/projects/1/files"
  hx-target="#files-list"
  hx-swap="innerHTML"
  hx-encoding="multipart/form-data"
>
  <input type="file" name="file" required />
  <input type="text" name="item_id" placeholder="Item ID (optional)" />
  <button type="submit">Upload</button>
</form>

<!-- Удаление файла -->
<button
  hx-delete="/admin/projects/1/files/abc123"
  hx-target="closest tr"
  hx-swap="outerHTML"
  hx-confirm="Delete this file?"
>
  🗑️
</button>
```

### Chat with Streaming

```html
<!-- Отправка сообщения -->
<form
  hx-post="/admin/projects/1/chat"
  hx-target="#chat-messages"
  hx-swap="beforeend"
  hx-on::after-request="this.reset()"
>
  <input type="text" name="message" placeholder="Type your message..." />
  <button type="submit">Send</button>
</form>

<!-- Индикатор загрузки -->
<div id="typing-indicator" class="htmx-indicator">
  <span class="animate-pulse">🤖 Typing...</span>
</div>
```

### Toast Notifications

```html
<!-- Toast container -->
<div id="toast-container" class="fixed top-4 right-4 z-50"></div>

<!-- Server returns toast partial -->
<div
  class="toast bg-green-500 text-white p-4 rounded shadow"
  hx-swap-oob="beforeend:#toast-container"
>
  ✅ File uploaded successfully
</div>
```

## Tailwind Theme

```html
<!-- Цветовая схема -->
<style>
  :root {
    --color-primary: #3b82f6; /* blue-500 */
    --color-success: #22c55e; /* green-500 */
    --color-warning: #f59e0b; /* amber-500 */
    --color-error: #ef4444; /* red-500 */
    --color-bg: #f9fafb; /* gray-50 */
    --color-sidebar: #1f2937; /* gray-800 */
  }
</style>

<!-- Основные классы -->
<!-- Sidebar: bg-gray-800 text-white -->
<!-- Content: bg-gray-50 -->
<!-- Cards: bg-white rounded-lg shadow-sm -->
<!-- Buttons: bg-blue-500 hover:bg-blue-600 text-white rounded px-4 py-2 -->
<!-- Inputs: border border-gray-300 rounded px-3 py-2 focus:ring-2 focus:ring-blue-500 -->
```

## Dependencies

```toml
# Добавить в pyproject.toml
dependencies = [
    # ... existing
    "jinja2>=3.1.0",
    "python-multipart>=0.0.6",  # для загрузки файлов
    "itsdangerous>=2.1.0",      # для session cookies
]
```

## Project Structure Update

```
app/
├── admin/
│   ├── __init__.py
│   ├── routes.py          # FastAPI router
│   ├── auth.py            # Auth middleware
│   ├── services.py        # Business logic
│   ├── models.py          # Pydantic models
│   └── templates/         # Jinja2 templates
│       ├── base.html
│       ├── components/
│       ├── auth/
│       ├── projects/
│       ├── files/
│       ├── chat/
│       ├── avito/
│       └── stats/
├── static/
│   └── css/
│       └── tailwind.css   # Compiled Tailwind
└── ... existing modules
```

## Correctness Properties

_A property is a characteristic or behavior that should hold true across all valid executions of a system._

### Property 1: Project-FileSearch Store Consistency

_For any_ project created in the system, there shall exist a corresponding FileSearch store in Gemini, and deleting the project shall remove the store.

**Validates: Requirements 1.3, 1.6**

### Property 2: File Upload Round-Trip

_For any_ file uploaded to a project, the file shall be retrievable from the project's file list with the same name and item_id.

**Validates: Requirements 2.2, 2.4, 2.5**

### Property 3: Chat Response Grounding

_For any_ chat message sent to a project, the response shall either be grounded in FileSearch results (with sources) or be the fallback message.

**Validates: Requirements 3.3, 3.4**

### Property 4: Avito Credentials Validation

_For any_ Avito credentials saved, the system shall verify them by attempting to fetch a token before marking the connection as successful.

**Validates: Requirements 4.2, 4.3**

### Property 5: Session Authentication

_For any_ request to admin routes (except /login), the request shall be rejected if no valid session cookie is present.

**Validates: Requirements 7.1, 7.2**

## Error Handling

| Error                     | Handling                                                  |
| ------------------------- | --------------------------------------------------------- |
| Invalid password          | Show error on login page, don't reveal if password exists |
| Project not found         | Return 404 page                                           |
| File upload failed        | Show toast error, keep form state                         |
| Gemini API error          | Show toast error, log details                             |
| Avito credentials invalid | Show error in settings, don't save                        |

## Testing Strategy

### Unit Tests

- Auth middleware: valid/invalid session
- Project CRUD operations
- File upload/delete

### Integration Tests

- Full project lifecycle: create → upload files → chat → delete
- Avito connection flow

### E2E Tests (manual)

- Login flow
- Project management
- File upload with drag-and-drop
- Chat interaction
