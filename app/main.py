"""FastAPI application for Avito AI Auto-Responder webhook handling."""

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator

from fastapi import BackgroundTasks, Depends, FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from app.admin.auth import AdminAuthMiddleware
from app.admin.routes import router as admin_router
from app.avito.messenger_client import MessengerClient
from app.avito.oauth import TokenManager
from app.avito.webhook_models import WebhookPayload
from app.config import Settings, get_settings
from app.core.responder import AutoResponder
from app.rag.answer_policy import AnswerPolicy
from app.rag.file_search_client import FileSearchClient
from app.rag.retrieval import CascadingRetrieval
from app.storage.sqlite import SQLiteStorage
from app.telegram.notify import TelegramNotifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class AppState:
    """Application state container for dependency injection."""

    settings: Settings
    storage: SQLiteStorage
    token_manager: TokenManager
    messenger_client: MessengerClient
    file_search_client: FileSearchClient
    cascading_retrieval: CascadingRetrieval
    answer_policy: AnswerPolicy
    telegram_notifier: TelegramNotifier
    auto_responder: AutoResponder


# Global app state (initialized in lifespan)
app_state: AppState | None = None


def get_app_state() -> AppState:
    """Dependency to get application state."""
    if app_state is None:
        raise RuntimeError("Application not initialized")
    return app_state


def get_storage(state: AppState = Depends(get_app_state)) -> SQLiteStorage:
    """Dependency to get storage instance."""
    return state.storage


def get_auto_responder(state: AppState = Depends(get_app_state)) -> AutoResponder:
    """Dependency to get auto responder instance."""
    return state.auto_responder


def get_messenger_client(state: AppState = Depends(get_app_state)) -> MessengerClient:
    """Dependency to get messenger client instance."""
    return state.messenger_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for initialization and cleanup.
    
    Initializes all components with proper dependency injection:
    - Storage (SQLite)
    - TokenManager (Avito OAuth2)
    - MessengerClient (Avito API)
    - FileSearchClient (Google Gemini)
    - CascadingRetrieval (RAG)
    - AnswerPolicy (Response generation)
    - TelegramNotifier (Logging)
    - AutoResponder (Core logic)
    
    Requirements: 2.1, 2.2, 2.3
    """
    global app_state

    logger.info("Starting Avito AI Auto-Responder...")

    # Load settings
    settings = get_settings()
    logger.info("Configuration loaded")

    # Initialize storage
    db_path = settings.database_url.replace("sqlite:///", "")
    if db_path.startswith("./"):
        db_path = db_path[2:]
    storage = SQLiteStorage(database_path=db_path)
    await storage._ensure_initialized()
    logger.info("Storage initialized: %s", db_path)

    # Initialize Token Manager
    token_manager = TokenManager(
        client_id=settings.avito_client_id,
        client_secret=settings.avito_client_secret,
    )
    logger.info("Token Manager initialized")

    # Initialize Messenger Client
    messenger_client = MessengerClient(
        user_id=settings.avito_user_id,
        token_manager=token_manager,
    )
    logger.info("Messenger Client initialized")

    # Initialize File Search Client
    file_search_client = FileSearchClient(
        api_key=settings.gemini_api_key,
        store_name=settings.file_search_store_name,
    )
    logger.info("File Search Client initialized")

    # Initialize Cascading Retrieval
    cascading_retrieval = CascadingRetrieval(
        file_search_client=file_search_client,
    )
    logger.info("Cascading Retrieval initialized")

    # Initialize Answer Policy
    answer_policy = AnswerPolicy(
        api_key=settings.gemini_api_key,
    )
    logger.info("Answer Policy initialized")

    # Initialize Telegram Notifier
    telegram_notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        owner_chat_id=settings.telegram_owner_chat_id,
    )
    logger.info("Telegram Notifier initialized")

    # Initialize Auto Responder
    auto_responder = AutoResponder(
        storage=storage,
        messenger_client=messenger_client,
        cascading_retrieval=cascading_retrieval,
        answer_policy=answer_policy,
        telegram_notifier=telegram_notifier,
        bot_user_id=settings.avito_user_id,
        context_limit=settings.message_context_limit,
        gemini_api_key=settings.gemini_api_key,
    )
    logger.info("Auto Responder initialized")

    # Create app state for dependency injection
    app_state = AppState(
        settings=settings,
        storage=storage,
        token_manager=token_manager,
        messenger_client=messenger_client,
        file_search_client=file_search_client,
        cascading_retrieval=cascading_retrieval,
        answer_policy=answer_policy,
        telegram_notifier=telegram_notifier,
        auto_responder=auto_responder,
    )

    logger.info("Avito AI Auto-Responder started successfully")

    yield

    # Cleanup
    logger.info("Shutting down Avito AI Auto-Responder...")
    app_state = None
    logger.info("Shutdown complete")


app = FastAPI(
    title="Avito AI Auto-Responder",
    description="Automatic response system for Avito messages using RAG",
    version="1.0.0",
    lifespan=lifespan,
)

# Add admin auth middleware
app.add_middleware(AdminAuthMiddleware)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include admin router
app.include_router(admin_router)


async def process_webhook_event(
    payload: WebhookPayload,
    responder: AutoResponder,
) -> None:
    """Background task to process webhook event.
    
    Args:
        payload: The webhook payload to process.
        responder: The auto responder instance.
    """
    try:
        await responder.process_event(payload)
    except Exception as e:
        logger.error(f"Error processing webhook event: {e}", exc_info=True)


@app.post("/avito/webhook")
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """Handle incoming Avito webhook notifications.
    
    Immediately returns 200 OK and processes the event in background.
    
    Requirements: 2.1, 2.2, 2.3
    """
    try:
        body = await request.json()
        payload = WebhookPayload.model_validate(body)
        
        logger.info(
            f"Received webhook event: id={payload.event_id}, "
            f"type={payload.type}, chat_id={payload.chat_id}"
        )
        
        # Get auto responder from app state
        state = get_app_state()
        
        # Queue for background processing
        background_tasks.add_task(
            process_webhook_event,
            payload,
            state.auto_responder,
        )
        
    except RuntimeError as e:
        logger.error(f"Application not initialized: {e}")
        return Response(status_code=503, content="Service unavailable")
    except Exception as e:
        logger.error(f"Error parsing webhook payload: {e}")
        # Still return 200 to acknowledge receipt
        # Invalid payloads are logged but not retried
    
    # Immediate 200 OK response (Requirements 2.2)
    return Response(status_code=200)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint.
    
    Returns:
        Health status information.
    """
    initialized = app_state is not None
    return {
        "status": "healthy" if initialized else "starting",
        "service": "avito-ai-auto-responder",
        "version": "1.0.0",
        "initialized": initialized,
    }
