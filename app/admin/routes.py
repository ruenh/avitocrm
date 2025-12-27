"""Admin panel routes.

Requirements: 1.1, 1.2, 1.4, 1.5, 2.1, 2.2, 2.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 7.1, 7.2, 7.3
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.admin.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE,
    create_session_token,
    is_auth_required,
    verify_password,
)
from app.admin.services import AvitoService, ChatService, FileService, ProjectService, StatsService
from app.storage.sqlite import SQLiteStorage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/admin/templates")


def _get_project_service() -> ProjectService:
    """Get ProjectService instance.
    
    Creates a new instance with storage and Gemini API key.
    In production, this would use dependency injection.
    """
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
    database_url = os.environ.get("DATABASE_URL", "sqlite:///./data/avito_responder.db")
    
    db_path = database_url.replace("sqlite:///", "")
    if db_path.startswith("./"):
        db_path = db_path[2:]
    
    storage = SQLiteStorage(database_path=db_path)
    return ProjectService(storage=storage, gemini_api_key=gemini_api_key)


def _get_file_service() -> FileService:
    """Get FileService instance.
    
    Creates a new instance with storage and Gemini API key.
    In production, this would use dependency injection.
    """
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
    database_url = os.environ.get("DATABASE_URL", "sqlite:///./data/avito_responder.db")
    
    db_path = database_url.replace("sqlite:///", "")
    if db_path.startswith("./"):
        db_path = db_path[2:]
    
    storage = SQLiteStorage(database_path=db_path)
    return FileService(storage=storage, gemini_api_key=gemini_api_key)


def _get_chat_service() -> ChatService:
    """Get ChatService instance.
    
    Creates a new instance with storage and Gemini API key.
    In production, this would use dependency injection.
    """
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
    database_url = os.environ.get("DATABASE_URL", "sqlite:///./data/avito_responder.db")
    
    db_path = database_url.replace("sqlite:///", "")
    if db_path.startswith("./"):
        db_path = db_path[2:]
    
    storage = SQLiteStorage(database_path=db_path)
    return ChatService(storage=storage, gemini_api_key=gemini_api_key)


def _get_avito_service() -> AvitoService:
    """Get AvitoService instance.
    
    Creates a new instance with storage.
    In production, this would use dependency injection.
    """
    database_url = os.environ.get("DATABASE_URL", "sqlite:///./data/avito_responder.db")
    
    db_path = database_url.replace("sqlite:///", "")
    if db_path.startswith("./"):
        db_path = db_path[2:]
    
    storage = SQLiteStorage(database_path=db_path)
    return AvitoService(storage=storage)


def _get_stats_service() -> StatsService:
    """Get StatsService instance.
    
    Creates a new instance with storage.
    In production, this would use dependency injection.
    """
    database_url = os.environ.get("DATABASE_URL", "sqlite:///./data/avito_responder.db")
    
    db_path = database_url.replace("sqlite:///", "")
    if db_path.startswith("./"):
        db_path = db_path[2:]
    
    storage = SQLiteStorage(database_path=db_path)
    return StatsService(storage=storage)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None) -> HTMLResponse:
    """Display login page.
    
    Requirements: 7.1
    
    Args:
        request: The incoming request.
        error: Optional error message to display.
        
    Returns:
        Login page HTML.
    """
    # If no auth required, redirect to main page
    if not is_auth_required():
        return RedirectResponse(url="/admin/projects", status_code=302)
    
    return templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "error": error,
        },
    )


@router.post("/login")
async def login(
    request: Request,
    password: str = Form(...),
) -> RedirectResponse:
    """Process login form submission.
    
    Requirements: 7.1, 7.2
    
    Args:
        request: The incoming request.
        password: The submitted password.
        
    Returns:
        Redirect to projects page on success, or back to login with error.
    """
    if not verify_password(password):
        logger.warning("Failed login attempt from %s", request.client.host if request.client else "unknown")
        return templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "error": "Неверный пароль",
            },
            status_code=401,
        )
    
    logger.info("Successful login from %s", request.client.host if request.client else "unknown")
    
    # Create session and redirect
    response = RedirectResponse(url="/admin/projects", status_code=302)
    session_token = create_session_token()
    
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    
    return response


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Log out and clear session.
    
    Requirements: 7.3
    
    Args:
        request: The incoming request.
        
    Returns:
        Redirect to login page with cleared cookie.
    """
    logger.info("User logged out from %s", request.client.host if request.client else "unknown")
    
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    
    return response


# Redirect root admin path to projects
@router.get("/", response_class=HTMLResponse)
async def admin_root(request: Request) -> RedirectResponse:
    """Redirect admin root to projects page.
    
    Args:
        request: The incoming request.
        
    Returns:
        Redirect to projects page.
    """
    return RedirectResponse(url="/admin/projects", status_code=302)


@router.get("/projects", response_class=HTMLResponse)
async def projects_list(request: Request) -> HTMLResponse:
    """Display projects list page.
    
    Requirements: 1.1
    
    Args:
        request: The incoming request.
        
    Returns:
        Projects list page HTML.
    """
    service = _get_project_service()
    projects = await service.list_projects()
    
    # Get file and message counts for each project
    project_stats = []
    for project in projects:
        file_count = await service.get_project_file_count(project.id)
        message_count = await service.get_project_message_count(project.id)
        project_stats.append({
            "project": project,
            "file_count": file_count,
            "message_count": message_count,
        })
    
    return templates.TemplateResponse(
        "projects/list.html",
        {
            "request": request,
            "project_stats": project_stats,
        },
    )


@router.post("/projects", response_class=HTMLResponse)
async def create_project(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
) -> HTMLResponse:
    """Create a new project.
    
    Requirements: 1.2, 1.3
    
    Args:
        request: The incoming request.
        name: Project name.
        description: Project description.
        
    Returns:
        Updated projects list or error toast.
    """
    service = _get_project_service()
    
    try:
        project = await service.create_project(name=name, description=description)
        logger.info(f"Created project: {project.id} - {project.name}")
        
        # Return updated project list with success toast
        projects = await service.list_projects()
        project_stats = []
        for p in projects:
            file_count = await service.get_project_file_count(p.id)
            message_count = await service.get_project_message_count(p.id)
            project_stats.append({
                "project": p,
                "file_count": file_count,
                "message_count": message_count,
            })
        
        response = templates.TemplateResponse(
            "projects/list.html",
            {
                "request": request,
                "project_stats": project_stats,
                "toast": {"type": "success", "message": f"Проект '{name}' создан"},
            },
        )
        response.headers["HX-Trigger"] = "projectCreated"
        return response
        
    except Exception as e:
        logger.error(f"Failed to create project: {e}")
        
        # Return error toast
        projects = await service.list_projects()
        project_stats = []
        for p in projects:
            file_count = await service.get_project_file_count(p.id)
            message_count = await service.get_project_message_count(p.id)
            project_stats.append({
                "project": p,
                "file_count": file_count,
                "message_count": message_count,
            })
        
        return templates.TemplateResponse(
            "projects/list.html",
            {
                "request": request,
                "project_stats": project_stats,
                "toast": {"type": "error", "message": f"Ошибка создания проекта: {str(e)}"},
            },
        )


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: int) -> RedirectResponse:
    """Redirect to project files page.
    
    Args:
        request: The incoming request.
        project_id: The project ID.
        
    Returns:
        Redirect to project files page.
    """
    return RedirectResponse(url=f"/admin/projects/{project_id}/files", status_code=302)


@router.put("/projects/{project_id}", response_class=HTMLResponse)
async def update_project(
    request: Request,
    project_id: int,
    name: str = Form(...),
    description: str = Form(""),
) -> HTMLResponse:
    """Update an existing project.
    
    Requirements: 1.4
    
    Args:
        request: The incoming request.
        project_id: The project ID.
        name: New project name.
        description: New project description.
        
    Returns:
        Updated project card or error.
    """
    service = _get_project_service()
    
    project = await service.update_project(
        project_id=project_id,
        name=name,
        description=description,
    )
    
    if project is None:
        return HTMLResponse(
            content="<div class='text-red-500'>Проект не найден</div>",
            status_code=404,
        )
    
    file_count = await service.get_project_file_count(project_id)
    message_count = await service.get_project_message_count(project_id)
    
    return templates.TemplateResponse(
        "projects/card.html",
        {
            "request": request,
            "project": project,
            "file_count": file_count,
            "message_count": message_count,
            "toast": {"type": "success", "message": "Проект обновлён"},
        },
    )


@router.delete("/projects/{project_id}", response_class=HTMLResponse)
async def delete_project(request: Request, project_id: int) -> HTMLResponse:
    """Delete a project.
    
    Requirements: 1.5, 1.6
    
    Args:
        request: The incoming request.
        project_id: The project ID.
        
    Returns:
        Empty response with HX-Trigger for UI update.
    """
    service = _get_project_service()
    
    project = await service.get_project(project_id)
    project_name = project.name if project else "Unknown"
    
    deleted = await service.delete_project(project_id)
    
    if not deleted:
        return HTMLResponse(
            content="",
            status_code=404,
            headers={"HX-Trigger": '{"showToast": {"type": "error", "message": "Проект не найден"}}'},
        )
    
    logger.info(f"Deleted project: {project_id} - {project_name}")
    
    return HTMLResponse(
        content="",
        status_code=200,
        headers={"HX-Trigger": f'{{"showToast": {{"type": "success", "message": "Проект \'{project_name}\' удалён"}}, "projectDeleted": true}}'}, 
    )


# File management routes

@router.get("/projects/{project_id}/files", response_class=HTMLResponse)
async def files_list(request: Request, project_id: int) -> HTMLResponse:
    """Display files list for a project.
    
    Requirements: 2.1
    
    Args:
        request: The incoming request.
        project_id: The project ID.
        
    Returns:
        Files list page HTML or 404.
    """
    project_service = _get_project_service()
    file_service = _get_file_service()
    
    project = await project_service.get_project(project_id)
    
    if project is None:
        return templates.TemplateResponse(
            "projects/list.html",
            {
                "request": request,
                "project_stats": [],
                "toast": {"type": "error", "message": "Проект не найден"},
            },
            status_code=404,
        )
    
    files = await file_service.list_files(project_id)
    file_count = len(files)
    message_count = await project_service.get_project_message_count(project_id)
    supported_formats = file_service.get_supported_formats()
    
    return templates.TemplateResponse(
        "files/list.html",
        {
            "request": request,
            "project": project,
            "files": files,
            "file_count": file_count,
            "message_count": message_count,
            "supported_formats": ", ".join(sorted(supported_formats)),
        },
    )


@router.post("/projects/{project_id}/files", response_class=HTMLResponse)
async def upload_file(
    request: Request,
    project_id: int,
    file: UploadFile = File(...),
    item_id: Optional[str] = Form(None),
) -> HTMLResponse:
    """Upload a file to the project.
    
    Requirements: 2.2, 2.3, 2.5
    
    Args:
        request: The incoming request.
        project_id: The project ID.
        file: The uploaded file.
        item_id: Optional item ID for product-specific documents.
        
    Returns:
        Updated files list or error.
    """
    project_service = _get_project_service()
    file_service = _get_file_service()
    
    project = await project_service.get_project(project_id)
    
    if project is None:
        return HTMLResponse(
            content="<div class='text-red-500'>Проект не найден</div>",
            status_code=404,
        )
    
    # Clean up item_id (empty string -> None)
    if item_id is not None and item_id.strip() == "":
        item_id = None
    
    try:
        await file_service.upload_file(
            project_id=project_id,
            file=file,
            item_id=item_id,
            filesearch_store_id=project.filesearch_store_id,
        )
        
        logger.info(f"Uploaded file to project {project_id}: {file.filename}")
        
        # Return updated files list
        files = await file_service.list_files(project_id)
        file_count = len(files)
        message_count = await project_service.get_project_message_count(project_id)
        supported_formats = file_service.get_supported_formats()
        
        return templates.TemplateResponse(
            "files/list.html",
            {
                "request": request,
                "project": project,
                "files": files,
                "file_count": file_count,
                "message_count": message_count,
                "supported_formats": ", ".join(sorted(supported_formats)),
                "toast": {"type": "success", "message": f"Файл '{file.filename}' загружен"},
            },
        )
        
    except ValueError as e:
        # Invalid file format
        logger.warning(f"Invalid file format: {e}")
        
        files = await file_service.list_files(project_id)
        file_count = len(files)
        message_count = await project_service.get_project_message_count(project_id)
        supported_formats = file_service.get_supported_formats()
        
        return templates.TemplateResponse(
            "files/list.html",
            {
                "request": request,
                "project": project,
                "files": files,
                "file_count": file_count,
                "message_count": message_count,
                "supported_formats": ", ".join(sorted(supported_formats)),
                "toast": {"type": "error", "message": str(e)},
            },
        )
        
    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        
        files = await file_service.list_files(project_id)
        file_count = len(files)
        message_count = await project_service.get_project_message_count(project_id)
        supported_formats = file_service.get_supported_formats()
        
        return templates.TemplateResponse(
            "files/list.html",
            {
                "request": request,
                "project": project,
                "files": files,
                "file_count": file_count,
                "message_count": message_count,
                "supported_formats": ", ".join(sorted(supported_formats)),
                "toast": {"type": "error", "message": f"Ошибка загрузки: {str(e)}"},
            },
        )


@router.delete("/projects/{project_id}/files/{file_id:path}", response_class=HTMLResponse)
async def delete_file(
    request: Request,
    project_id: int,
    file_id: str,
) -> HTMLResponse:
    """Delete a file from the project.
    
    Requirements: 2.6
    
    Args:
        request: The incoming request.
        project_id: The project ID.
        file_id: The file/document ID.
        
    Returns:
        Empty response with HX-Trigger for UI update.
    """
    project_service = _get_project_service()
    file_service = _get_file_service()
    
    project = await project_service.get_project(project_id)
    
    if project is None:
        return HTMLResponse(
            content="",
            status_code=404,
            headers={"HX-Trigger": '{"showToast": {"type": "error", "message": "Проект не найден"}}'},
        )
    
    try:
        await file_service.delete_file(
            file_id=file_id,
            filesearch_store_id=project.filesearch_store_id,
        )
        
        logger.info(f"Deleted file from project {project_id}: {file_id}")
        
        return HTMLResponse(
            content="",
            status_code=200,
            headers={"HX-Trigger": '{"showToast": {"type": "success", "message": "Файл удалён"}, "fileDeleted": true}'},
        )
        
    except Exception as e:
        logger.error(f"Failed to delete file: {e}")
        
        return HTMLResponse(
            content="",
            status_code=500,
            headers={"HX-Trigger": f'{{"showToast": {{"type": "error", "message": "Ошибка удаления: {str(e)}"}}}}'},
        )


# Chat routes

@router.get("/projects/{project_id}/chat", response_class=HTMLResponse)
async def chat_page(request: Request, project_id: int) -> HTMLResponse:
    """Display chat page for a project.
    
    Requirements: 3.1
    
    Args:
        request: The incoming request.
        project_id: The project ID.
        
    Returns:
        Chat page HTML or 404.
    """
    project_service = _get_project_service()
    chat_service = _get_chat_service()
    file_service = _get_file_service()
    
    project = await project_service.get_project(project_id)
    
    if project is None:
        return templates.TemplateResponse(
            "projects/list.html",
            {
                "request": request,
                "project_stats": [],
                "toast": {"type": "error", "message": "Проект не найден"},
            },
            status_code=404,
        )
    
    # Get chat history and file count
    messages = await chat_service.get_history(project_id)
    files = await file_service.list_files(project_id)
    file_count = len(files)
    message_count = await project_service.get_project_message_count(project_id)
    
    return templates.TemplateResponse(
        "chat/index.html",
        {
            "request": request,
            "project": project,
            "messages": messages,
            "file_count": file_count,
            "message_count": message_count,
        },
    )


@router.post("/projects/{project_id}/chat", response_class=HTMLResponse)
async def send_chat_message(
    request: Request,
    project_id: int,
    message: str = Form(...),
) -> HTMLResponse:
    """Send a message to the chat and get AI response.
    
    Requirements: 3.2, 3.3, 3.4
    
    Args:
        request: The incoming request.
        project_id: The project ID.
        message: The user's message.
        
    Returns:
        Chat message partial HTML with both user and assistant messages.
    """
    project_service = _get_project_service()
    chat_service = _get_chat_service()
    
    project = await project_service.get_project(project_id)
    
    if project is None:
        return HTMLResponse(
            content="<div class='text-red-500'>Проект не найден</div>",
            status_code=404,
        )
    
    # Clean up message
    message = message.strip()
    if not message:
        return HTMLResponse(
            content="",
            status_code=400,
        )
    
    try:
        # Send message and get response
        response = await chat_service.send_message(
            project_id=project_id,
            message=message,
            filesearch_store_id=project.filesearch_store_id,
        )
        
        # Get the user message (second to last in history)
        history = await chat_service.get_history(project_id, limit=2)
        user_message = None
        for msg in history:
            if msg.role == "user":
                user_message = msg
                break
        
        # Return both messages as HTML
        return templates.TemplateResponse(
            "chat/message.html",
            {
                "request": request,
                "user_message": user_message,
                "assistant_message": response.message,
            },
        )
        
    except Exception as e:
        logger.error(f"Failed to send chat message: {e}")
        
        return HTMLResponse(
            content=f"<div class='text-red-500 p-4'>Ошибка: {str(e)}</div>",
            status_code=500,
        )


@router.delete("/projects/{project_id}/chat", response_class=HTMLResponse)
async def clear_chat_history(request: Request, project_id: int) -> HTMLResponse:
    """Clear chat history for a project.
    
    Requirements: 3.5
    
    Args:
        request: The incoming request.
        project_id: The project ID.
        
    Returns:
        Empty response with HX-Trigger for UI update.
    """
    project_service = _get_project_service()
    chat_service = _get_chat_service()
    
    project = await project_service.get_project(project_id)
    
    if project is None:
        return HTMLResponse(
            content="",
            status_code=404,
            headers={"HX-Trigger": '{"showToast": {"type": "error", "message": "Проект не найден"}}'},
        )
    
    try:
        await chat_service.clear_history(project_id)
        
        logger.info(f"Cleared chat history for project {project_id}")
        
        return HTMLResponse(
            content="",
            status_code=200,
            headers={"HX-Trigger": '{"showToast": {"type": "success", "message": "История чата очищена"}, "chatCleared": true}'},
        )
        
    except Exception as e:
        logger.error(f"Failed to clear chat history: {e}")
        
        return HTMLResponse(
            content="",
            status_code=500,
            headers={"HX-Trigger": f'{{"showToast": {{"type": "error", "message": "Ошибка: {str(e)}"}}}}'},
        )



# Avito integration routes

@router.get("/projects/{project_id}/avito", response_class=HTMLResponse)
async def avito_settings_page(request: Request, project_id: int) -> HTMLResponse:
    """Display Avito settings page for a project.
    
    Requirements: 4.1, 4.3, 4.5
    
    Args:
        request: The incoming request.
        project_id: The project ID.
        
    Returns:
        Avito settings page HTML or 404.
    """
    project_service = _get_project_service()
    file_service = _get_file_service()
    
    project = await project_service.get_project(project_id)
    
    if project is None:
        return templates.TemplateResponse(
            "projects/list.html",
            {
                "request": request,
                "project_stats": [],
                "toast": {"type": "error", "message": "Проект не найден"},
            },
            status_code=404,
        )
    
    # Get file count and message count for header
    files = await file_service.list_files(project_id)
    file_count = len(files)
    message_count = await project_service.get_project_message_count(project_id)
    
    # Get webhook URL from environment
    webhook_base_url = os.environ.get("WEBHOOK_BASE_URL", "")
    webhook_url = f"{webhook_base_url}/avito/webhook" if webhook_base_url else ""
    
    return templates.TemplateResponse(
        "avito/settings.html",
        {
            "request": request,
            "project": project,
            "file_count": file_count,
            "message_count": message_count,
            "webhook_url": webhook_url,
        },
    )


@router.post("/projects/{project_id}/avito", response_class=HTMLResponse)
async def save_avito_credentials(
    request: Request,
    project_id: int,
    client_id: str = Form(...),
    client_secret: str = Form(...),
    user_id: str = Form(...),
) -> HTMLResponse:
    """Save Avito credentials for a project.
    
    Requirements: 4.1, 4.2
    
    Args:
        request: The incoming request.
        project_id: The project ID.
        client_id: Avito OAuth2 client ID.
        client_secret: Avito OAuth2 client secret.
        user_id: Avito user ID.
        
    Returns:
        Updated Avito settings page with success/error toast.
    """
    project_service = _get_project_service()
    avito_service = _get_avito_service()
    file_service = _get_file_service()
    
    project = await project_service.get_project(project_id)
    
    if project is None:
        return HTMLResponse(
            content="<div class='text-red-500'>Проект не найден</div>",
            status_code=404,
        )
    
    try:
        # Save credentials (this also verifies them)
        updated_project = await avito_service.save_credentials(
            project_id=project_id,
            client_id=client_id.strip(),
            client_secret=client_secret.strip(),
            user_id=user_id.strip(),
        )
        
        logger.info(f"Saved Avito credentials for project {project_id}")
        
        # Get file count and message count for header
        files = await file_service.list_files(project_id)
        file_count = len(files)
        message_count = await project_service.get_project_message_count(project_id)
        
        # Get webhook URL from environment
        webhook_base_url = os.environ.get("WEBHOOK_BASE_URL", "")
        webhook_url = f"{webhook_base_url}/avito/webhook" if webhook_base_url else ""
        
        return templates.TemplateResponse(
            "avito/settings.html",
            {
                "request": request,
                "project": updated_project,
                "file_count": file_count,
                "message_count": message_count,
                "webhook_url": webhook_url,
                "toast": {"type": "success", "message": "Учётные данные сохранены и проверены"},
            },
        )
        
    except Exception as e:
        logger.error(f"Failed to save Avito credentials: {e}")
        
        # Get file count and message count for header
        files = await file_service.list_files(project_id)
        file_count = len(files)
        message_count = await project_service.get_project_message_count(project_id)
        
        # Get webhook URL from environment
        webhook_base_url = os.environ.get("WEBHOOK_BASE_URL", "")
        webhook_url = f"{webhook_base_url}/avito/webhook" if webhook_base_url else ""
        
        return templates.TemplateResponse(
            "avito/settings.html",
            {
                "request": request,
                "project": project,
                "file_count": file_count,
                "message_count": message_count,
                "webhook_url": webhook_url,
                "toast": {"type": "error", "message": f"Ошибка: {str(e)}"},
            },
        )


@router.post("/projects/{project_id}/avito/test", response_class=HTMLResponse)
async def test_avito_connection(request: Request, project_id: int) -> HTMLResponse:
    """Test Avito connection for a project.
    
    Requirements: 4.2, 4.3, 4.6
    
    Args:
        request: The incoming request.
        project_id: The project ID.
        
    Returns:
        HTML response with connection test result.
    """
    project_service = _get_project_service()
    avito_service = _get_avito_service()
    
    project = await project_service.get_project(project_id)
    
    if project is None:
        return HTMLResponse(
            content="",
            status_code=404,
            headers={"HX-Trigger": '{"showToast": {"type": "error", "message": "Проект не найден"}}'},
        )
    
    if not project.avito_client_id or not project.avito_client_secret:
        return HTMLResponse(
            content="",
            status_code=400,
            headers={"HX-Trigger": '{"showToast": {"type": "error", "message": "Сначала сохраните учётные данные"}}'},
        )
    
    try:
        is_connected = await avito_service.test_connection(
            client_id=project.avito_client_id,
            client_secret=project.avito_client_secret,
        )
        
        if is_connected:
            logger.info(f"Avito connection test successful for project {project_id}")
            return HTMLResponse(
                content="",
                status_code=200,
                headers={"HX-Trigger": '{"showToast": {"type": "success", "message": "Подключение успешно!"}}'},
            )
        else:
            return HTMLResponse(
                content="",
                status_code=400,
                headers={"HX-Trigger": '{"showToast": {"type": "error", "message": "Не удалось подключиться"}}'},
            )
            
    except Exception as e:
        logger.error(f"Avito connection test failed: {e}")
        return HTMLResponse(
            content="",
            status_code=500,
            headers={"HX-Trigger": f'{{"showToast": {{"type": "error", "message": "Ошибка: {str(e)}"}}}}'},
        )


@router.post("/projects/{project_id}/avito/webhook", response_class=HTMLResponse)
async def register_avito_webhook(request: Request, project_id: int) -> HTMLResponse:
    """Register Avito webhook for a project.
    
    Requirements: 4.4, 4.5
    
    Args:
        request: The incoming request.
        project_id: The project ID.
        
    Returns:
        HTML response with webhook registration result.
    """
    project_service = _get_project_service()
    avito_service = _get_avito_service()
    file_service = _get_file_service()
    
    project = await project_service.get_project(project_id)
    
    if project is None:
        return HTMLResponse(
            content="",
            status_code=404,
            headers={"HX-Trigger": '{"showToast": {"type": "error", "message": "Проект не найден"}}'},
        )
    
    if not project.avito_client_id or not project.avito_client_secret or not project.avito_user_id:
        return HTMLResponse(
            content="",
            status_code=400,
            headers={"HX-Trigger": '{"showToast": {"type": "error", "message": "Сначала сохраните учётные данные"}}'},
        )
    
    # Get webhook URL from environment
    webhook_base_url = os.environ.get("WEBHOOK_BASE_URL", "")
    if not webhook_base_url:
        return HTMLResponse(
            content="",
            status_code=400,
            headers={"HX-Trigger": '{"showToast": {"type": "error", "message": "WEBHOOK_BASE_URL не настроен"}}'},
        )
    
    webhook_url = f"{webhook_base_url}/avito/webhook"
    
    try:
        updated_project = await avito_service.register_webhook(
            project_id=project_id,
            client_id=project.avito_client_id,
            client_secret=project.avito_client_secret,
            user_id=project.avito_user_id,
            webhook_url=webhook_url,
        )
        
        logger.info(f"Webhook registered for project {project_id}: {webhook_url}")
        
        # Get file count and message count for header
        files = await file_service.list_files(project_id)
        file_count = len(files)
        message_count = await project_service.get_project_message_count(project_id)
        
        return templates.TemplateResponse(
            "avito/settings.html",
            {
                "request": request,
                "project": updated_project,
                "file_count": file_count,
                "message_count": message_count,
                "webhook_url": webhook_url,
                "toast": {"type": "success", "message": "Webhook зарегистрирован"},
            },
        )
        
    except Exception as e:
        logger.error(f"Failed to register webhook: {e}")
        return HTMLResponse(
            content="",
            status_code=500,
            headers={"HX-Trigger": f'{{"showToast": {{"type": "error", "message": "Ошибка: {str(e)}"}}}}'},
        )


# Statistics routes

@router.get("/stats", response_class=HTMLResponse)
async def stats_dashboard(request: Request) -> HTMLResponse:
    """Display statistics dashboard.
    
    Requirements: 5.1, 5.2
    
    Args:
        request: The incoming request.
        
    Returns:
        Dashboard page HTML with statistics.
    """
    stats_service = _get_stats_service()
    project_service = _get_project_service()
    
    # Get dashboard stats
    dashboard_stats = await stats_service.get_dashboard_stats()
    
    # Get recent dialogs
    recent_dialogs = await stats_service.get_dialogs(limit=10)
    
    # Get all projects for filter dropdown
    projects = await project_service.list_projects()
    
    # Get project stats for each project
    project_stats_list = []
    for project in projects:
        project_stats = await stats_service.get_project_stats(project.id)
        project_stats_list.append({
            "project": project,
            "stats": project_stats,
        })
    
    return templates.TemplateResponse(
        "stats/dashboard.html",
        {
            "request": request,
            "stats": dashboard_stats,
            "recent_dialogs": recent_dialogs,
            "projects": projects,
            "project_stats_list": project_stats_list,
        },
    )


@router.get("/stats/dialogs", response_class=HTMLResponse)
async def dialogs_list(
    request: Request,
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> HTMLResponse:
    """Display dialog history with filters.
    
    Requirements: 5.3, 5.4, 5.5
    
    Args:
        request: The incoming request.
        project_id: Filter by project ID (optional).
        status: Filter by found_status (optional).
        chat_id: Filter by chat_id for full history (optional).
        
    Returns:
        Dialogs list page HTML.
    """
    stats_service = _get_stats_service()
    project_service = _get_project_service()
    
    # Get all projects for filter dropdown
    projects = await project_service.list_projects()
    
    # Get dialogs with filters
    if chat_id:
        # Get full dialog history for a specific chat
        dialogs = await stats_service.get_dialog_by_chat_id(chat_id)
    else:
        dialogs = await stats_service.get_dialogs(
            project_id=project_id,
            status=status,
            limit=100,
        )
    
    # Create a map of project_id to project name
    project_map = {p.id: p.name for p in projects}
    
    return templates.TemplateResponse(
        "stats/dialogs.html",
        {
            "request": request,
            "dialogs": dialogs,
            "projects": projects,
            "project_map": project_map,
            "selected_project_id": project_id,
            "selected_status": status,
            "selected_chat_id": chat_id,
        },
    )
