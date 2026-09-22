"""
conftest.py – Shared pytest fixtures for the ResearchMate test suite.

Strategy:
- Mock all heavy ML/AI native modules (torch, umap, spacy, rag.*) in
  sys.modules BEFORE any app code is imported. This lets the suite run in
  lightweight CI environments (GitHub Actions) without installing torch/umap.
- Use SQLite (in-memory) instead of PostgreSQL so no DB server is needed.
- Override the `get_db` FastAPI dependency to inject the test session.
- Seed a regular user and an admin user for auth fixtures.
"""

import os
import sys
from unittest.mock import MagicMock

# ── 1. Environment variables (must come before app imports) ───────────────────
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_researchmate.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-google-client-secret")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")

# ── 2. Mock heavy native/ML modules so they never need to be installed ────────
#    rag.raptor / rag.raptor_middleman pull torch, umap-learn, spacy, chromadb.
#    We stub them out so top-level imports in routes succeed without those libs.
_STUBS = [
    # RAG pipeline
    "rag",
    "rag.raptor",
    "rag.raptor_middleman",
    # PyTorch ecosystem
    "torch",
    "torch.nn",
    "torch.utils",
    "torch.utils.data",
    "torchvision",
    # UMAP / numba
    "umap",
    "umap.umap_",
    "numba",
    "llvmlite",
    # spaCy
    "spacy",
    "spacy.lang",
    "spacy.lang.en",
    # HuggingFace Transformers
    "transformers",
    # ChromaDB
    "chromadb",
    "chromadb.config",
    # tiktoken (optional, used by some LangChain modules)
    "tiktoken",
    # pymupdf / fitz  (PDF extraction)
    "fitz",
    # unstructured
    "unstructured",
]

for _mod in _STUBS:
    if _mod not in sys.modules:
        _mock = MagicMock()
        # Make RaptorPipeline, get_retriever, temporary_query_pipeline importable
        if _mod == "rag.raptor":
            _mock.RaptorPipeline = MagicMock()
            _mock.get_retriever = MagicMock(return_value=MagicMock())
            _mock.temporary_query_pipeline = MagicMock(return_value="Mocked answer")
        if _mod == "rag.raptor_middleman":
            _mock.asking_llm = MagicMock(return_value="Mocked RAG answer")
        sys.modules[_mod] = _mock

# ── 3. Now it is safe to import app code ─────────────────────────────────────
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

# ── Test SQLite engine & session factory ──────────────────────────────────────
TEST_DATABASE_URL = "sqlite:///./test_researchmate.db"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Dependency override: yields a SQLite session."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Create all tables once for the test session, then drop them."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def client(create_tables):
    """A shared TestClient for the entire test session."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── Auth helpers ──────────────────────────────────────────────────────────────

REGULAR_USER = {
    "email": "testuser@example.com",
    "password": "Password123",
    "first_name": "Test",
    "last_name": "User",
}

ADMIN_USER = {
    "email": "adminuser@example.com",
    "password": "AdminPass123",
    "first_name": "Admin",
    "last_name": "User",
}


def _register_and_login(client: TestClient, payload: dict) -> str:
    """Register (ignore if already exists) and login, returning JWT token."""
    client.post("/auth/register", json=payload)
    resp = client.post("/auth/login", json={
        "email": payload["email"],
        "password": payload["password"],
    })
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return resp.json()["token"]


@pytest.fixture(scope="session")
def auth_headers(client):
    """Bearer token headers for a regular authenticated user."""
    token = _register_and_login(client, REGULAR_USER)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def admin_headers(client):
    """Bearer token headers for an admin user (promoted via DB directly)."""
    token = _register_and_login(client, ADMIN_USER)
    db = TestingSessionLocal()
    try:
        from app.models.models import User
        user = db.query(User).filter(User.email == ADMIN_USER["email"]).first()
        if user:
            user.is_admin = True
            db.commit()
    finally:
        db.close()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def regular_user_id(client, auth_headers):
    resp = client.get("/api/user", headers=auth_headers)
    return resp.json()["id"]


@pytest.fixture(scope="session")
def test_project(client, auth_headers):
    """Create a project once and reuse across tests."""
    resp = client.post(
        "/api/projects/create",
        json={"project_name": "Test Project"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()["project_id"]


@pytest.fixture(scope="session")
def test_document(client, auth_headers):
    """Create a document once and reuse across tests."""
    resp = client.post(
        "/api/documents",
        json={"title": "Test Doc", "content": "This is test document content for pytest."},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()["doc_id"]
