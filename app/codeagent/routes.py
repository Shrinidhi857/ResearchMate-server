from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime
from typing import Dict, Any, List
import json
import asyncio
import traceback

from app.database import SessionLocal
from app.models.models import Project, PaperBucket, Document, Paper

from .llm import GeminiLLM
from .agent import LaTeXAgent
from .utils import Config, MessageType, ConnectionManager, AgentState, AgentConfig

router = APIRouter(tags=["CodeAgent"])

# Initialize LLM and Agent
llm = GeminiLLM(model=Config.GEMINI_MODEL, api_key=Config.GEMINI_API_KEY)
agent = LaTeXAgent(llm)
manager = ConnectionManager()


# ============================================================================
# UTILS
# ============================================================================

def get_project_context(project_id: str):
    """Fetch document context from PaperBucket for a project"""
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.project_id == project_id).first()
        if not project:
            return None, ""

        paper_bucket = project.paper_bucket
        doc_context = ""
        if paper_bucket and paper_bucket.paper_ids:
            docs = db.query(Document).filter(Document.doc_id.in_(paper_bucket.paper_ids)).all()
            for d in docs:
                doc_context += f"Document: {d.title or 'Untitled'}\nContent: {d.content}\n---\n"

        return project, doc_context
    finally:
        db.close()


def save_to_paper(project_id_val: str, content: str):
    """Save LaTeX content to project's paper"""
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.project_id == project_id_val).first()
        if not project:
            return False

        paper = project.paper
        if not paper:
            paper = Paper(project_id=project.id, content=content)
            db.add(paper)
        else:
            paper.content = content
            paper.updated_at = datetime.utcnow()

        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"Error saving to paper: {e}")
        return False
    finally:
        db.close()


# ============================================================================
# AGENT TOOL FETCHERS
# ============================================================================

class ContextFetcher:
    """Helper class to provide DB access to the Agent tools"""
    def __init__(self, manager: ConnectionManager, client_id: str):
        self.manager = manager
        self.client_id = client_id

    async def get_project_info(self, project_id: str) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == project_id).first()
            if not project:
                return {"error": "Project not found"}

            docs = []
            if project.paper_bucket and project.paper_bucket.paper_ids:
                d_objs = db.query(Document).filter(Document.doc_id.in_(project.paper_bucket.paper_ids)).all()
                docs = [{"id": d.doc_id, "title": d.title or "Untitled"} for d in d_objs]

            return {
                "name": project.project_name,
                "documents": docs
            }
        finally:
            db.close()

    async def search_docs(self, project_id: str, query: str) -> str:
        db = SessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == project_id).first()
            if not project or not project.paper_bucket:
                return "No documents found."

            query_str = query.lower()
            docs = db.query(Document).filter(
                Document.doc_id.in_(project.paper_bucket.paper_ids),
                (Document.title.ilike(f"%{query_str}%")) | (Document.content.ilike(f"%{query_str}%"))
            ).limit(5).all()

            if not docs:
                return f"No documents matching '{query}' found."

            res = "Found documents:\n"
            for d in docs:
                res += f"- ID: {d.doc_id}, Title: {d.title}\n"
            return res
        finally:
            db.close()

    async def read_doc(self, doc_id: str) -> str:
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.doc_id == doc_id).first()
            if not doc:
                return f"Document {doc_id} not found."
            return f"Content of {doc.title or doc_id}:\n{doc.content[:5000]}"
        finally:
            db.close()

    async def read_current_paper(self, project_id: str) -> str:
        db = SessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == project_id).first()
            if not project or not project.paper:
                return "The paper is currently empty. Start from scratch."
            return f"Current LaTeX Paper Content:\n{project.paper.content}"
        finally:
            db.close()

    async def signal_thinking(self, message: str):
        """Send a thinking update to the client"""
        await self.manager.send_message(self.client_id, {
            "type": MessageType.AGENT_THINKING.value,
            "content": message
        })


# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================

@router.websocket("/ws/{client_id}/{project_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str, project_id: str):
    print(f"DEBUG: New connection request - Client: {client_id}, Project: {project_id}")
    await manager.connect(websocket, client_id)
    state = manager.get_state(client_id)
    fetcher = ContextFetcher(manager, client_id)

    try:
        db = SessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == project_id).first()
            if not project:
                await manager.send_message(client_id, {"type": "ERROR", "content": "Project not found."})
                manager.disconnect(client_id)
                return
            project_name = project.project_name
        finally:
            db.close()

        await manager.send_message(client_id, {
            "type": "CONNECTED",
            "content": f"Agent active for {project_name}. I can read your docs and edit your paper!",
            "client_id": client_id,
            "project_id": project_id
        })

        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == MessageType.USER_MESSAGE:
                user_request = data.get("content", "")
                document_ids = data.get("document_ids", [])
                state.add_message("user", user_request)

                if document_ids and not isinstance(document_ids, list):
                    await manager.send_message(client_id, {
                        "type": "ERROR",
                        "content": "document_ids must be a list"
                    })
                    continue

                await manager.send_message(client_id, {
                    "type": MessageType.AGENT_THINKING.value,
                    "content": "Analyzing request..."
                })

                try:
                    result = await asyncio.wait_for(
                        agent.run(user_request, project_id, fetcher, document_ids if document_ids else None),
                        timeout=AgentConfig.AGENT_TIMEOUT
                    )

                    if "error" in result:
                        await manager.send_message(client_id, {"type": "ERROR", "content": result["error"]})
                        continue

                    latex_code = result.get("latex")
                    thought = result.get("thought", "Task complete.")
                    warning = result.get("warning")

                    if warning:
                        await manager.send_message(client_id, {
                            "type": "AGENT_THINKING",
                            "content": f"⚠️ {warning}"
                        })

                    if latex_code:
                        state.current_code = latex_code
                        state.add_message("assistant", f"Thought: {thought}")

                        await manager.send_message(client_id, {
                            "type": MessageType.CODE_GENERATED.value,
                            "content": latex_code,
                            "thought": thought,
                            "attempt": 1,
                            "max_attempts": state.max_attempts
                        })
                        state.waiting_for_compilation = True
                    else:
                        await manager.send_message(client_id, {
                            "type": "AGENT_RESPONSE",
                            "content": thought
                        })

                except Exception as e:
                    print(f"ERROR: {str(e)}")
                    traceback.print_exc()
                    await manager.send_message(client_id, {"type": "ERROR", "content": f"Agent loop failed: {str(e)}"})

            elif message_type == MessageType.EXECUTION_ERROR:
                if not state.waiting_for_compilation:
                    continue
                state.compilation_attempts += 1
                error_logs = data.get("logs", "Unknown error")

                if state.compilation_attempts >= state.max_attempts:
                    await manager.send_message(client_id, {
                        "type": MessageType.MAX_ATTEMPTS_REACHED.value,
                        "content": "Giving up after too many errors."
                    })
                    continue

                fixed_code = await agent.fix_latex(state.current_code, error_logs)
                state.current_code = fixed_code
                await manager.send_message(client_id, {
                    "type": MessageType.CODE_GENERATED.value,
                    "content": fixed_code,
                    "is_retry": True
                })

            elif message_type == MessageType.EXECUTION_SUCCESS:
                state.waiting_for_compilation = False
                await manager.send_message(client_id, {"type": MessageType.COMPILATION_COMPLETE.value, "content": "Compiled!"})

            elif message_type == MessageType.SAVE_TO_PAPER:
                content = data.get("content") or state.current_code
                if content:
                    success = save_to_paper(project_id, content)
                    await manager.send_message(client_id, {"type": "SAVE_STATUS", "success": success})

    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        print(f"WebSocket error for {client_id}: {str(e)}")
        traceback.print_exc()
        try:
            await manager.send_message(client_id, {
                "type": "ERROR",
                "content": f"Server error: {str(e)}"
            })
        except:
            pass
        manager.disconnect(client_id)


# ============================================================================
# REST ENDPOINTS
# ============================================================================

@router.get("/codeagent")
async def root():
    return {
        "service": "LaTeX Agent API",
        "version": "1.1.0",
        "status": "running",
        "active_sessions": len(manager.active_connections),
        "llm_provider": Config.LLM_PROVIDER,
        "endpoints": {
            "websocket": "/ws/{client_id}/{project_id}",
            "health": "/codeagent/health",
            "sessions": "/codeagent/sessions"
        }
    }


@router.get("/codeagent/health")
async def health_check():
    try:
        test_response = await llm.generate("test", max_tokens=10)
        llm_status = "healthy"
    except:
        llm_status = "unavailable"

    return {
        "status": "healthy",
        "llm_status": llm_status,
        "active_sessions": len(manager.active_connections),
        "timestamp": datetime.now().isoformat()
    }


@router.get("/codeagent/sessions")
async def list_sessions():
    return {
        "active_sessions": [
            {
                "client_id": cid,
                "messages": len(state.messages),
                "attempts": state.compilation_attempts,
                "waiting": state.waiting_for_compilation
            }
            for cid, state in manager.agent_states.items()
        ],
        "total": len(manager.active_connections)
    }
