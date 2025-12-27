"""Authentication middleware and utilities for admin panel.

Requirements: 7.1, 7.2, 7.3, 7.4
"""

import hashlib
import os
import secrets
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


# Session configuration
SESSION_COOKIE_NAME = "admin_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def get_admin_password() -> Optional[str]:
    """Get admin password from environment variable.
    
    Returns:
        Admin password or None if not configured (development mode).
    """
    return os.environ.get("ADMIN_PASSWORD")


def get_secret_key() -> str:
    """Get or generate secret key for session signing.
    
    Uses SECRET_KEY env var if set, otherwise generates from ADMIN_PASSWORD.
    """
    secret = os.environ.get("SECRET_KEY")
    if secret:
        return secret
    
    # Derive from admin password if set
    admin_password = get_admin_password()
    if admin_password:
        return hashlib.sha256(f"avito-ai-{admin_password}".encode()).hexdigest()
    
    # Fallback for development (not secure for production)
    return "dev-secret-key-not-for-production"


def get_serializer() -> URLSafeTimedSerializer:
    """Get serializer for session tokens."""
    return URLSafeTimedSerializer(get_secret_key())


def create_session_token() -> str:
    """Create a new session token.
    
    Returns:
        Signed session token string.
    """
    serializer = get_serializer()
    session_id = secrets.token_hex(16)
    return serializer.dumps({"session_id": session_id})


def verify_session_token(token: str) -> bool:
    """Verify a session token.
    
    Args:
        token: The session token to verify.
        
    Returns:
        True if token is valid, False otherwise.
    """
    if not token:
        return False
    
    serializer = get_serializer()
    try:
        serializer.loads(token, max_age=SESSION_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


def verify_password(password: str) -> bool:
    """Verify admin password.
    
    Args:
        password: Password to verify.
        
    Returns:
        True if password matches or no password is configured.
    """
    admin_password = get_admin_password()
    
    # Development mode: no password required
    if not admin_password:
        return True
    
    return secrets.compare_digest(password, admin_password)


def is_auth_required() -> bool:
    """Check if authentication is required.
    
    Returns:
        True if ADMIN_PASSWORD is set, False for development mode.
    """
    return get_admin_password() is not None


class AdminAuthMiddleware(BaseHTTPMiddleware):
    """Middleware to protect admin routes with session authentication.
    
    Requirements: 7.1, 7.2, 7.4
    """
    
    # Routes that don't require authentication
    PUBLIC_PATHS = {
        "/admin/login",
    }
    
    # Paths that should be excluded from admin auth check
    EXCLUDED_PREFIXES = (
        "/static/",
        "/avito/",
        "/health",
        "/docs",
        "/openapi.json",
    )
    
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process request and check authentication for admin routes.
        
        Args:
            request: The incoming request.
            call_next: The next middleware/handler.
            
        Returns:
            Response from handler or redirect to login.
        """
        path = request.url.path
        
        # Skip non-admin routes
        if not path.startswith("/admin"):
            return await call_next(request)
        
        # Skip excluded paths
        for prefix in self.EXCLUDED_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)
        
        # Skip public admin paths
        if path in self.PUBLIC_PATHS:
            return await call_next(request)
        
        # Development mode: no auth required
        if not is_auth_required():
            return await call_next(request)
        
        # Check session cookie
        session_token = request.cookies.get(SESSION_COOKIE_NAME)
        
        if not verify_session_token(session_token):
            # Redirect to login page
            return RedirectResponse(
                url="/admin/login",
                status_code=302,
            )
        
        return await call_next(request)
