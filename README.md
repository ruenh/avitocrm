# Avito AI Auto-Responder

🤖 Production-ready backend для автоматических ответов на сообщения покупателей в Avito с использованием RAG на базе Google Gemini File Search.

## Возможности

- ✅ Автоматические ответы на вопросы покупателей
- 📚 RAG на базе Google Gemini File Search
- 🔍 Каскадный поиск: сначала по товару, затем в общих документах
- 🛡️ Анти-галлюцинационный контракт — ответы только на основе базы знаний
- 📱 Логирование всех ответов в Telegram
- 👨‍💼 Эскалация к менеджеру по запросу
- 💾 Локальное хранение истории сообщений (SQLite)
- 🖥️ Веб-админка для управления проектами, файлами и настройками Avito

## Требования

- Python 3.12+
- Ubuntu 22.04+ (для production)
- Доступ к Avito API (client_id, client_secret)
- Google Gemini API key
- Telegram Bot Token (для логирования)
- Публичный HTTPS URL для webhook

## Быстрый старт

### 1. Клонирование и установка

```bash
git clone https://github.com/your-repo/avito-ai-auto-responder.git
cd avito-ai-auto-responder

# Создание виртуального окружения
python3.12 -m venv .venv
source .venv/bin/activate

# Установка зависимостей
pip install -e .
# или
pip install -r requirements.txt
```

### 2. Настройка переменных окружения

```bash
cp .env.example .env
nano .env
```

Заполните все переменные:

```env
# Avito OAuth2 credentials (получить в личном кабинете разработчика)
AVITO_CLIENT_ID=your_avito_client_id
AVITO_CLIENT_SECRET=your_avito_client_secret
AVITO_USER_ID=your_avito_user_id

# Google Gemini API (получить в Google AI Studio)
GEMINI_API_KEY=your_gemini_api_key
FILE_SEARCH_STORE_NAME=avito_knowledge_base

# Telegram notifications (создать бота через @BotFather)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_OWNER_CHAT_ID=your_telegram_chat_id

# Application settings
APP_BASE_URL=https://your-domain.com
DATABASE_URL=sqlite:///./data/avito_responder.db
MESSAGE_CONTEXT_LIMIT=20

# Admin panel (optional - if not set, admin panel is accessible without password)
ADMIN_PASSWORD=your_secure_admin_password
```

### 3. Загрузка документов в базу знаний

Поместите документы в директорию `docs/`:

```bash
# Структура файлов
docs/
├── faq.txt                    # Общий FAQ
├── delivery_terms.md          # Условия доставки
├── item_12345.txt             # Описание товара 12345
├── item_67890_specs.md        # Характеристики товара 67890
└── product.txt.meta.json      # Метаданные для product.txt
```

**Соглашения об именовании:**

- `item_<ID>.txt` — документ привязан к товару с item_id
- `faq.txt`, `delivery.md` — общие документы
- `*.meta.json` — файл метаданных: `{"item_id": "12345"}`

Загрузка в File Search:

```bash
# Предпросмотр
python scripts/sync_filesearch.py --dry-run

# Загрузка
python scripts/sync_filesearch.py
```

### 4. Запуск сервера

```bash
# Development
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

### 5. Регистрация webhook

```bash
python scripts/register_webhook.py
```

## Production деплой (Ubuntu)

### Установка как systemd сервис

```bash
# Копирование файлов
sudo mkdir -p /opt/avito-responder
sudo cp -r . /opt/avito-responder/
sudo chown -R www-data:www-data /opt/avito-responder

# Создание виртуального окружения
cd /opt/avito-responder
sudo -u www-data python3.12 -m venv .venv
sudo -u www-data .venv/bin/pip install -e .

# Настройка .env
sudo cp .env.example .env
sudo nano .env
sudo chmod 600 .env

# Установка systemd unit
sudo cp systemd/avito-responder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable avito-responder
sudo systemctl start avito-responder

# Проверка статуса
sudo systemctl status avito-responder
sudo journalctl -u avito-responder -f
```

### Настройка Nginx (reverse proxy)

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## API Endpoints

### Health Check

```bash
curl https://your-domain.com/health
```

Ответ:

```json
{ "status": "healthy" }
```

### Webhook (для Avito)

```bash
# Тестовый запрос
curl -X POST https://your-domain.com/avito/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-event-123",
    "type": "message",
    "payload": {
      "chat_id": "chat_123",
      "user_id": "user_456",
      "message": {
        "id": "msg_789",
        "type": "text",
        "text": "Какая цена?",
        "created": "2024-01-15T10:30:00Z",
        "author_id": "user_456"
      },
      "context": {
        "item_id": "12345",
        "item_title": "iPhone 15 Pro"
      }
    }
  }'
```

## Админ-панель

Встроенная веб-админка для управления системой доступна по адресу `/admin/`.

### Возможности админ-панели

- **Управление проектами** — создание, редактирование и удаление проектов (баз знаний)
- **Загрузка файлов** — загрузка документов в FileSearch (txt, md, pdf, docx, json)
- **Тестовый чат** — проверка ответов Gemini на основе загруженной базы знаний
- **Настройки Avito** — привязка Avito аккаунта и регистрация webhook
- **Статистика** — просмотр метрик и истории диалогов

### Доступ к админ-панели

```bash
# Открыть в браузере
https://your-domain.com/admin/
```

Если установлена переменная `ADMIN_PASSWORD`, потребуется ввести пароль для входа.
В режиме разработки (без пароля) админка доступна без авторизации.

### Workflow использования

1. **Создайте проект** — укажите название и описание
2. **Загрузите документы** — файлы автоматически индексируются в Gemini FileSearch
3. **Протестируйте чат** — убедитесь, что бот отвечает корректно
4. **Подключите Avito** — введите credentials и зарегистрируйте webhook
5. **Мониторьте статистику** — отслеживайте работу бота в разделе статистики

### Технологии

- **Jinja2** — серверный рендеринг шаблонов
- **HTMX** — динамические обновления без перезагрузки страницы
- **Tailwind CSS** — стилизация интерфейса

## Тестирование

```bash
# Запуск всех тестов
pytest

# С покрытием
pytest --cov=app

# Только unit тесты
pytest tests/test_storage.py

# E2E тесты
pytest tests/test_e2e_flow.py
```

## Структура проекта

```
avito-ai-auto-responder/
├── app/
│   ├── main.py              # FastAPI приложение
│   ├── config.py            # Конфигурация
│   ├── admin/               # Админ-панель
│   │   ├── auth.py          # Авторизация (session cookies)
│   │   ├── routes.py        # FastAPI роуты админки
│   │   ├── services.py      # Бизнес-логика (ProjectService, FileService, etc.)
│   │   └── templates/       # Jinja2 шаблоны
│   │       ├── base.html    # Базовый layout
│   │       ├── auth/        # Страница входа
│   │       ├── projects/    # Управление проектами
│   │       ├── files/       # Управление файлами
│   │       ├── chat/        # Тестовый чат
│   │       ├── avito/       # Настройки Avito
│   │       ├── stats/       # Статистика
│   │       └── components/  # Переиспользуемые компоненты
│   ├── avito/               # Avito API клиенты
│   │   ├── oauth.py         # OAuth2 Token Manager
│   │   ├── messenger_client.py
│   │   └── webhook_models.py
│   ├── rag/                 # RAG компоненты
│   │   ├── file_search_client.py
│   │   ├── retrieval.py
│   │   └── answer_policy.py
│   ├── telegram/            # Telegram уведомления
│   │   └── notify.py
│   ├── storage/             # Хранилище данных
│   │   ├── base.py
│   │   └── sqlite.py
│   ├── core/                # Основная логика
│   │   └── responder.py
│   ├── models/              # Pydantic модели
│   │   └── domain.py
│   └── static/              # Статические файлы
│       └── css/admin.css
├── scripts/
│   ├── register_webhook.py  # Регистрация webhook
│   └── sync_filesearch.py   # Загрузка документов
├── systemd/
│   └── avito-responder.service
├── docs/                    # База знаний
├── data/                    # SQLite база данных
├── tests/
├── .env.example
├── pyproject.toml
└── README.md
```

## Эскалация к менеджеру

Бот автоматически передаёт диалог менеджеру при обнаружении ключевых слов:

- "вызови менеджера"
- "позови менеджера"
- "позови человека"
- "оператор"

При эскалации:

1. Клиент получает сообщение о подключении менеджера
2. Владелец получает уведомление в Telegram с контекстом диалога

## Логирование

Все ответы бота логируются в Telegram:

```
📨 Новый ответ бота

Chat: chat_123
Item: 12345
Status: FOUND

❓ Вопрос:
Какая цена?

🤖 Ответ:
Цена iPhone 15 Pro составляет 120 000 рублей.

📚 Источники: item_12345.txt
```

## Troubleshooting

### Webhook не получает события

1. Проверьте, что URL доступен извне: `curl https://your-domain.com/health`
2. Убедитесь, что используется HTTPS
3. Перерегистрируйте webhook: `python scripts/register_webhook.py`

### Ошибка авторизации Avito

1. Проверьте AVITO_CLIENT_ID и AVITO_CLIENT_SECRET
2. Убедитесь, что приложение активно в личном кабинете Avito

### Бот не отвечает на вопросы

1. Проверьте логи: `sudo journalctl -u avito-responder -f`
2. Убедитесь, что документы загружены: `python scripts/sync_filesearch.py --dry-run`
3. Проверьте GEMINI_API_KEY

### База данных

```bash
# Просмотр базы
sqlite3 data/avito_responder.db ".tables"
sqlite3 data/avito_responder.db "SELECT * FROM messages LIMIT 10;"
```

## Лицензия

MIT
