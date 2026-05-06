import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# ── Auth Tests ────────────────────────────────────────────────────────────────

def test_register_user():
    response = client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "testuser@test.com",
        "password": "testpass123"
    })
    # 201 = success, 400 = already exists (if test run before)
    assert response.status_code in (201, 400)

def test_register_duplicate_username():
    # Register once
    client.post("/api/v1/auth/register", json={
        "username": "dupuser",
        "email": "dup1@test.com",
        "password": "pass123"
    })
    # Register again with same username
    response = client.post("/api/v1/auth/register", json={
        "username": "dupuser",
        "email": "dup2@test.com",
        "password": "pass123"
    })
    assert response.status_code == 400
    assert "already taken" in response.json()["detail"]

def test_login_success():
    # Ensure user exists
    client.post("/api/v1/auth/register", json={
        "username": "loginuser",
        "email": "loginuser@test.com",
        "password": "pass123"
    })
    response = client.post("/api/v1/auth/login", data={
        "username": "loginuser",
        "password": "pass123"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_wrong_password():
    response = client.post("/api/v1/auth/login", data={
        "username": "loginuser",
        "password": "wrongpassword"
    })
    assert response.status_code == 401

def test_me_without_token():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401

def test_me_with_token():
    # Register + login to get token
    client.post("/api/v1/auth/register", json={
        "username": "meuser",
        "email": "meuser@test.com",
        "password": "pass123"
    })
    login = client.post("/api/v1/auth/login", data={
        "username": "meuser",
        "password": "pass123"
    })
    token = login.json()["access_token"]

    response = client.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {token}"
    })
    assert response.status_code == 200
    assert response.json()["username"] == "meuser"


# ── Protected Route Tests ─────────────────────────────────────────────────────

def test_ask_without_token():
    response = client.post("/api/v1/ask", json={
        "question": "What is the revenue?"
    })
    assert response.status_code == 401

def test_ask_with_invalid_token():
    response = client.post("/api/v1/ask",
        json={"question": "What is the revenue?"},
        headers={"Authorization": "Bearer faketoken123"}
    )
    assert response.status_code == 401


# ── Input Validation Tests ────────────────────────────────────────────────────

def test_question_too_short():
    # Register + login
    client.post("/api/v1/auth/register", json={
        "username": "valuser",
        "email": "valuser@test.com",
        "password": "pass123"
    })
    login = client.post("/api/v1/auth/login", data={
        "username": "valuser",
        "password": "pass123"
    })
    token = login.json()["access_token"]

    response = client.post("/api/v1/ask",
        json={"question": "Hi"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 422

def test_summarise_invalid_style():
    response = client.post("/api/v1/summarise", json={
        "file_name": "test.pdf",
        "style": "random_style"
    })
    assert response.status_code == 422

def test_summarise_file_not_found():
    response = client.post("/api/v1/summarise", json={
        "file_name": "nonexistent_file.pdf",
        "style": "executive"
    })
    assert response.status_code == 404


# ── Home & Status Tests ───────────────────────────────────────────────────────

def test_home():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "VaultIQ Backend Running"

def test_status_not_found():
    response = client.get("/api/v1/process/fake-session-id/status")
    assert response.status_code == 404

def test_results_not_found():
    response = client.get("/api/v1/results/nonexistent.pdf")
    assert response.status_code == 404