from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from datetime import datetime

from app.admin.routes import initialize_admin
from app.auth.routes import router as auth_router
from app.users.routes import router as users_router
from app.documents.routes import router as documents_router
from app.projects.routes import router as projects_router
from app.rag.routes import router as rag_router
from app.ai.routes import router as ai_router
from app.analyse.routes import router as analyse_router
from app.admin.routes import router as admin_router
from app.codeagent.routes import router as codeagent_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize default admin account
    print("🚀 Starting ResearchMate API Server...")
    initialize_admin()
    yield
    print("🛑 Shutting down ResearchMate API Server...")


app = FastAPI(
    title="ResearchMate API",
    description="Research Paper Analysis, Collaboration, and LaTeX Agent Platform",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check route
@app.get("/health", tags=["Health"])
def health_check():
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


# Include Routers with exact Flask URL prefixes
app.include_router(auth_router, prefix="/auth")
app.include_router(users_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(rag_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(analyse_router, prefix="/api")
app.include_router(admin_router, prefix="/api/admin")
app.include_router(codeagent_router)


# Global Exception Handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Endpoint not found"}
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": f"Internal server error: {str(exc)}"}
    )
