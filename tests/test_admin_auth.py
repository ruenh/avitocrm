"""Tests for admin panel authentication and layout.

Requirements: 7.1, 7.2, 7.3, 7.4
"""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.admin.auth import (
    SESSION_COOKIE_NAME,
    create_session_token,
    is_auth_required,
    verify_password,
    verify_session_token,
)


class TestAuthFunctions:
    """Tests for authentication utility functions."""

    def test_verify_password_no_password_set(self):
        """Test that any password is accepted when ADMIN_PASSWORD is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove ADMIN_PASSWORD if it exists
            os.environ.pop("ADMIN_PASSWORD", None)
            assert verify_password("any_password") is True
            assert verify_password("") is True

    def test_verify_password_correct(self):
        """Test that correct password is accepted."""
        with patch.dict(os.environ, {"ADMIN_PASSWORD": "secret123"}):
            assert verify_password("secret123") is True

    def test_verify_password_incorrect(self):
        """Test that incorrect password is rejected."""
        with patch.dict(os.environ, {"ADMIN_PASSWORD": "secret123"}):
            assert verify_password("wrong_password") is False
            assert verify_password("") is False

    def test_is_auth_required_with_password(self):
        """Test that auth is required when password is set."""
        with patch.dict(os.environ, {"ADMIN_PASSWORD": "secret123"}):
            assert is_auth_required() is True

    def test_is_auth_required_without_password(self):
        """Test that auth is not required when password is not set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ADMIN_PASSWORD", None)
            assert is_auth_required() is False

    def test_session_token_creation_and_verification(self):
        """Test that created session tokens can be verified."""
        with patch.dict(os.environ, {"ADMIN_PASSWORD": "secret123"}):
            token = create_session_token()
            assert token is not None
            assert len(token) > 0
            assert verify_session_token(token) is True

    def test_invalid_session_token(self):
        """Test that invalid tokens are rejected."""
        with patch.dict(os.environ, {"ADMIN_PASSWORD": "secret123"}):
            assert verify_session_token("invalid_token") is False
            assert verify_session_token("") is False
            assert verify_session_token(None) is False


class TestAdminRoutes:
    """Tests for admin panel routes."""

    @pytest.fixture
    def client(self):
        """Create test client with mocked dependencies."""
        # Import here to avoid initialization issues
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_login_page_accessible(self, client):
        """Test that login page is accessible without authentication."""
        with patch.dict(os.environ, {"ADMIN_PASSWORD": "secret123"}):
            response = client.get("/admin/login")
            assert response.status_code == 200
            assert "Вход" in response.text or "login" in response.text.lower()

    def test_login_page_redirects_when_no_auth_required(self, client):
        """Test that login page redirects to projects when no auth required."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ADMIN_PASSWORD", None)
            response = client.get("/admin/login", follow_redirects=False)
            # Should redirect to projects
            assert response.status_code == 302
            assert "/admin/projects" in response.headers.get("location", "")

    def test_admin_root_redirects_to_projects(self, client):
        """Test that /admin/ redirects to /admin/projects."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ADMIN_PASSWORD", None)
            response = client.get("/admin/", follow_redirects=False)
            assert response.status_code == 302
            assert "/admin/projects" in response.headers.get("location", "")

    def test_protected_route_redirects_to_login(self, client):
        """Test that protected routes redirect to login when not authenticated."""
        with patch.dict(os.environ, {"ADMIN_PASSWORD": "secret123"}):
            response = client.get("/admin/projects", follow_redirects=False)
            assert response.status_code == 302
            assert "/admin/login" in response.headers.get("location", "")

    def test_login_with_correct_password(self, client):
        """Test successful login with correct password."""
        with patch.dict(os.environ, {"ADMIN_PASSWORD": "secret123"}):
            response = client.post(
                "/admin/login",
                data={"password": "secret123"},
                follow_redirects=False,
            )
            assert response.status_code == 302
            assert "/admin/projects" in response.headers.get("location", "")
            # Check that session cookie is set
            assert SESSION_COOKIE_NAME in response.cookies

    def test_login_with_incorrect_password(self, client):
        """Test failed login with incorrect password."""
        with patch.dict(os.environ, {"ADMIN_PASSWORD": "secret123"}):
            response = client.post(
                "/admin/login",
                data={"password": "wrong_password"},
            )
            assert response.status_code == 401
            assert "Неверный пароль" in response.text

    def test_logout_clears_session(self, client):
        """Test that logout clears the session cookie."""
        with patch.dict(os.environ, {"ADMIN_PASSWORD": "secret123"}):
            # First login
            login_response = client.post(
                "/admin/login",
                data={"password": "secret123"},
                follow_redirects=False,
            )
            
            # Then logout
            logout_response = client.get(
                "/admin/logout",
                cookies=login_response.cookies,
                follow_redirects=False,
            )
            assert logout_response.status_code == 302
            assert "/admin/login" in logout_response.headers.get("location", "")

    def test_authenticated_access_to_projects(self, client):
        """Test that authenticated users can access projects page."""
        with patch.dict(os.environ, {"ADMIN_PASSWORD": "secret123"}):
            # Login first
            login_response = client.post(
                "/admin/login",
                data={"password": "secret123"},
                follow_redirects=False,
            )
            
            # Access projects with session cookie
            response = client.get(
                "/admin/projects",
                cookies=login_response.cookies,
            )
            assert response.status_code == 200
            assert "Проекты" in response.text


class TestLayoutComponents:
    """Tests for layout and UI components."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_base_layout_has_sidebar(self, client):
        """Test that base layout includes sidebar navigation."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ADMIN_PASSWORD", None)
            response = client.get("/admin/projects")
            assert response.status_code == 200
            # Check for sidebar elements
            assert "Проекты" in response.text
            assert "Статистика" in response.text

    def test_base_layout_has_logout_button(self, client):
        """Test that base layout includes logout button."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ADMIN_PASSWORD", None)
            response = client.get("/admin/projects")
            assert response.status_code == 200
            assert "Выйти" in response.text or "logout" in response.text.lower()

    def test_static_files_accessible(self, client):
        """Test that static CSS files are accessible."""
        response = client.get("/static/css/admin.css")
        assert response.status_code == 200
        assert "text/css" in response.headers.get("content-type", "")
