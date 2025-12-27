# Implementation Plan: Admin Panel

## Overview

Пошаговая реализация минималистичной админ-панели для Avito AI Auto-Responder. Используем Jinja2 + HTMX + Tailwind CSS, встроенные в существующее FastAPI приложение.

## Tasks

- [x] 1. Подготовка инфраструктуры

  - [x] 1.1 Обновить зависимости в pyproject.toml

    - Добавить jinja2, itsdangerous
    - _Requirements: 6.1_

  - [x] 1.2 Создать структуру директорий для админки

    - app/admin/, app/admin/templates/, app/static/
    - _Requirements: 6.1_

  - [x] 1.3 Настроить Tailwind CSS
    - Создать tailwind.config.js и скомпилировать CSS
    - Или использовать CDN версию для простоты
    - _Requirements: 6.1_

- [x] 2. База данных и модели

  - [x] 2.1 Обновить схему SQLite

    - Добавить таблицы: projects, project_files, chat_history
    - Добавить project_id в dialog_logs
    - _Requirements: 1.1, 2.1_

  - [x] 2.2 Создать Pydantic модели для админки

    - Project, ProjectFile, ChatMessage, DashboardStats
    - _Requirements: 1.1, 2.4, 3.1, 5.1_

  - [x] 2.3 Расширить StorageInterface для проектов
    - Методы CRUD для projects, project_files, chat_history
    - _Requirements: 1.1, 1.4, 1.5, 2.1, 2.6_

- [x] 3. Checkpoint - Database Layer

  - Проверить миграцию схемы
  - Протестировать CRUD операции

- [x] 4. Авторизация

  - [x] 4.1 Создать auth middleware

    - Проверка session cookie
    - Редирект на /admin/login если не авторизован
    - _Requirements: 7.1, 7.2_

  - [x] 4.2 Реализовать login/logout endpoints

    - POST /admin/login с проверкой ADMIN_PASSWORD
    - GET /admin/logout с очисткой cookie
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 4.3 Создать login template
    - Минималистичная форма входа
    - _Requirements: 7.1, 6.5_

- [x] 5. Base Layout и навигация

  - [x] 5.1 Создать base.html template

    - Sidebar с навигацией
    - Header с logout
    - Content area
    - Toast container
    - _Requirements: 6.2, 6.3_

  - [x] 5.2 Создать компоненты

    - sidebar.html, toast.html, loading.html
    - _Requirements: 6.6_

  - [x] 5.3 Подключить HTMX
    - Добавить htmx.js
    - Настроить базовые паттерны
    - _Requirements: 6.3_

- [x] 6. Checkpoint - Auth & Layout

  - Проверить авторизацию
  - Проверить базовый layout

- [x] 7. Управление проектами

  - [x] 7.1 Создать ProjectService

    - list_projects, get_project, create_project, update_project, delete_project
    - Интеграция с FileSearchClient для создания/удаления store
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 7.2 Реализовать routes для проектов

    - GET /admin/projects - список
    - POST /admin/projects - создание
    - GET /admin/projects/{id} - детали
    - PUT /admin/projects/{id} - обновление
    - DELETE /admin/projects/{id} - удаление
    - _Requirements: 1.1, 1.2, 1.4, 1.5_

  - [x] 7.3 Создать templates для проектов
    - projects/list.html - список с карточками
    - projects/card.html - карточка проекта (partial)
    - projects/form.html - форма создания/редактирования
    - _Requirements: 1.1, 1.2, 6.5_

- [x] 8. Управление файлами

  - [x] 8.1 Создать FileService

    - list_files, upload_file, delete_file
    - Интеграция с FileSearchClient
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6_

  - [x] 8.2 Реализовать routes для файлов

    - GET /admin/projects/{id}/files - список
    - POST /admin/projects/{id}/files - загрузка
    - DELETE /admin/projects/{id}/files/{file_id} - удаление
    - _Requirements: 2.1, 2.2, 2.6_

  - [x] 8.3 Создать templates для файлов
    - files/list.html - список с формой загрузки
    - files/row.html - строка файла (partial)
    - _Requirements: 2.1, 2.4, 2.7, 6.6_

- [x] 9. Checkpoint - Projects & Files

  - Проверить создание проекта с FileSearch store
  - Проверить загрузку и удаление файлов

- [x] 10. Чат с Gemini

  - [x] 10.1 Создать ChatService

    - send_message с RAG retrieval
    - get_history, clear_history
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 10.2 Реализовать routes для чата

    - GET /admin/projects/{id}/chat - страница чата
    - POST /admin/projects/{id}/chat - отправка сообщения
    - DELETE /admin/projects/{id}/chat - очистка истории
    - _Requirements: 3.1, 3.2, 3.5_

  - [x] 10.3 Создать templates для чата
    - chat/index.html - интерфейс чата
    - chat/message.html - сообщение (partial)
    - _Requirements: 3.1, 3.3, 3.4, 3.6, 6.6_

- [x] 11. Интеграция с Avito

  - [x] 11.1 Реализовать routes для Avito настроек

    - GET /admin/projects/{id}/avito - страница настроек
    - POST /admin/projects/{id}/avito - сохранение credentials
    - POST /admin/projects/{id}/avito/test - тест подключения
    - POST /admin/projects/{id}/avito/webhook - регистрация webhook
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 11.2 Создать templates для Avito
    - avito/settings.html - форма настроек
    - _Requirements: 4.1, 4.3, 4.5, 6.6_

- [x] 12. Checkpoint - Chat & Avito

  - Проверить чат с Gemini
  - Проверить сохранение Avito credentials

- [x] 13. Статистика и история

  - [x] 13.1 Создать StatsService

    - get_dashboard_stats, get_project_stats, get_dialogs
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 13.2 Реализовать routes для статистики

    - GET /admin/stats - дашборд
    - GET /admin/stats/dialogs - история диалогов
    - _Requirements: 5.1, 5.3, 5.4_

  - [x] 13.3 Создать templates для статистики
    - stats/dashboard.html - карточки метрик
    - stats/dialogs.html - таблица диалогов с фильтрами
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 14. Интеграция с main.py

  - [x] 14.1 Подключить admin router к приложению

    - Добавить middleware для авторизации
    - Настроить static files
    - _Requirements: 6.1, 7.1_

  - [x] 14.2 Обновить AutoResponder для работы с проектами
    - Определение проекта по chat_id/item_id
    - Использование credentials проекта
    - _Requirements: 4.4_

- [x] 15. Final Checkpoint
  - Проверить полный flow: создание проекта → загрузка файлов → чат → Avito
  - Проверить статистику
  - Обновить README

## Notes

- Все задачи обязательные (нет опциональных тестов в этой спеке)
- HTMX используется для динамических обновлений без перезагрузки страницы
- Tailwind CSS через CDN для простоты (можно заменить на compiled позже)
- Авторизация простая — один пароль через env переменную
