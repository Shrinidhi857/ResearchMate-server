from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
import tempfile
import subprocess
import os
import io
import shutil
import re
from typing import Optional

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER

from app.database import get_db
from app.models.models import Project, User, Message, Response as ProjectResponse, PaperBucket, Paper, Document
from app.auth.utils import get_current_user
from app.services.email_service import send_invitation_email
from rag.raptor import RaptorPipeline, get_retriever, temporary_query_pipeline
from rag.raptor_middleman import asking_llm

router = APIRouter(tags=["Projects"])
projects_bp = router


# ═══════════════════════════════════════════════════════════════════════════
# FEATURE 1: TEMPORARY QUERY (No Permanent Storage)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/query-temporary")
async def query_temporary(request: Request):
    """
    Feature 1: Direct text embedding for one-off queries
    No authentication required
    No permanent storage - embeddings discarded after query
    """
    try:
        try:
            data = await request.json()
        except Exception:
            data = {}

        text = data.get("text", "").strip()
        question = data.get("question", "").strip()

        if not text or not question:
            return JSONResponse(status_code=400, content={"error": "Both 'text' and 'question' fields are required"})

        if len(text) < 10:
            return JSONResponse(status_code=400, content={"error": "Text must be at least 10 characters long"})

        if len(question) < 5:
            return JSONResponse(status_code=400, content={"error": "Question must be at least 5 characters long"})

        answer = temporary_query_pipeline(text, question)

        return JSONResponse(
            status_code=200,
            content={
                "answer": answer,
                "mode": "temporary",
                "storage": "none",
                "text_length": len(text),
                "question": question
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "type": "temporary_query_error"
            }
        )


# ═══════════════════════════════════════════════════════════════════════════
# FEATURE 2: PROJECT-BASED PERSISTENT STORAGE
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/projects/create")
async def create_project(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        data = await request.json()
    except Exception:
        data = {}

    project_name = data.get("project_name")
    if not project_name:
        return JSONResponse(status_code=400, content={"error": "project_name is required"})

    project = Project(
        project_name=project_name,
        owner_id=current_user.id
    )
    project.users.append(current_user)

    db.add(project)
    db.commit()
    db.refresh(project)

    return JSONResponse(
        status_code=201,
        content={
            "message": "Project created successfully",
            "project_id": project.project_id
        }
    )


@router.post("/projects/{project_id}/invite")
async def invite_user(
    project_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        data = await request.json()
    except Exception:
        data = {}

    user_email = data.get("email")
    if not user_email:
        return JSONResponse(status_code=400, content={"error": "Email is required"})

    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if project.owner_id != current_user.id:
        return JSONResponse(status_code=403, content={"error": "Only project owner can invite users"})

    invited_user = db.query(User).filter(User.email == user_email).first()
    inviter_name = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email

    # Case 1: User does NOT exist in database
    if not invited_user:
        try:
            from app.services.email_service import send_signup_invitation_email

            email_sent = send_signup_invitation_email(
                recipient_email=user_email,
                project_name=project.project_name,
                inviter_name=inviter_name
            )

            if email_sent:
                return JSONResponse(
                    status_code=200,
                    content={
                        "message": f"Signup invitation sent to {user_email}",
                        "status": "signup_required"
                    }
                )
            else:
                return JSONResponse(
                    status_code=200,
                    content={
                        "message": "User doesn't exist. Failed to send signup invitation email.",
                        "status": "email_failed"
                    }
                )

        except Exception as e:
            print(f"Email sending error: {str(e)}")
            return JSONResponse(
                status_code=200,
                content={
                    "message": "User doesn't exist. Please ask them to sign up first.",
                    "status": "signup_required",
                    "error": str(e)
                }
            )

    # Case 2: User EXISTS in database
    if invited_user in project.users:
        return JSONResponse(status_code=400, content={"error": "User already added to this project"})

    project.users.append(invited_user)
    db.commit()

    try:
        recipient_name = f"{invited_user.first_name or ''} {invited_user.last_name or ''}".strip() or invited_user.email

        email_sent = send_invitation_email(
            recipient_email=invited_user.email,
            recipient_name=recipient_name,
            project_name=project.project_name,
            inviter_name=inviter_name
        )

        if email_sent:
            return JSONResponse(
                status_code=200,
                content={
                    "message": f"✅ {recipient_name} invited successfully! Notification email sent.",
                    "status": "invited"
                }
            )
        else:
            return JSONResponse(
                status_code=200,
                content={
                    "message": f"✅ {recipient_name} added to project, but notification email failed to send.",
                    "status": "invited_no_email"
                }
            )

    except Exception as e:
        print(f"Email sending error: {str(e)}")
        return JSONResponse(
            status_code=200,
            content={
                "message": f"✅ User added to project, but notification email failed: {str(e)}",
                "status": "invited_no_email"
            }
        )


@router.post("/projects/{project_id}/messages")
async def save_message(
    project_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    try:
        data = await request.json()
    except Exception:
        data = {}

    msg = Message(
        message_number=len(project.messages) + 1,
        message_sender=current_user.email,
        message_content=data.get("content", ""),
        project_id=project.id
    )

    db.add(msg)
    db.commit()

    return JSONResponse(status_code=200, content={"message": "Message saved"})


@router.delete("/messages/{msg_id}")
def delete_message(
    msg_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    msg = db.query(Message).filter(Message.id == msg_id).first()
    if not msg:
        return JSONResponse(status_code=404, content={"error": "Message not found"})

    project = msg.project

    if project.owner_id != current_user.id and msg.message_sender != current_user.email:
        return JSONResponse(status_code=403, content={"error": "You cannot delete this message"})

    db.delete(msg)
    db.commit()

    return JSONResponse(status_code=200, content={"message": "Message deleted"})


@router.post("/projects/{project_id}/responses")
async def save_response(
    project_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    try:
        data = await request.json()
    except Exception:
        data = {}

    res = ProjectResponse(
        summary=data.get("summary", ""),
        response_by=current_user.email,
        project_id=project.id
    )

    db.add(res)
    db.commit()

    return JSONResponse(status_code=200, content={"message": "Response saved"})


@router.get("/projects")
def get_user_projects(current_user: User = Depends(get_current_user)):
    projects = current_user.projects or []
    return JSONResponse(status_code=200, content=[p.to_dict() for p in projects])


@router.get("/projects/{project_id}")
def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    project_dict = project.to_dict()
    project_dict['messages'] = [m.to_dict() for m in project.messages]
    project_dict['responses'] = [r.to_dict() for r in project.responses]

    return JSONResponse(status_code=200, content=project_dict)


@router.get("/projects/{project_id}/messages")
def get_project_messages(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    return JSONResponse(status_code=200, content=[m.to_dict() for m in project.messages])


@router.get("/projects/{project_id}/responses")
def get_project_responses(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    return JSONResponse(status_code=200, content=[r.to_dict() for r in project.responses])


@router.get("/projects/{project_id}/conversation")
def get_conversation(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get unified, chronologically-ordered conversation thread for a project.
    Merges all Messages (user questions) and Responses (AI answers) into a single thread.
    """
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    conversation = []

    for message in project.messages:
        conversation.append({
            "type": "message",
            "content": message.message_content,
            "sender": message.message_sender,
            "timestamp": message.message_timestamp.isoformat() if message.message_timestamp else None,
            "id": message.id
        })

    for response in project.responses:
        conversation.append({
            "type": "response",
            "content": response.summary,
            "sender": response.response_by,
            "timestamp": response.timestamp.isoformat() if response.timestamp else None,
            "id": response.response_id
        })

    conversation.sort(key=lambda x: x["timestamp"] or "")

    return JSONResponse(status_code=200, content={"conversation": conversation})


@router.get("/projects/{project_id}/top-users")
def get_project_top_users(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    top_users = []
    user_ids_added = set()

    if project.owner:
        top_users.append({
            'id': project.owner.id,
            'email': project.owner.email,
            'first_name': project.owner.first_name,
            'last_name': project.owner.last_name
        })
        user_ids_added.add(project.owner.id)

    if current_user.id not in user_ids_added and len(top_users) < 3:
        top_users.append({
            'id': current_user.id,
            'email': current_user.email,
            'first_name': current_user.first_name,
            'last_name': current_user.last_name
        })
        user_ids_added.add(current_user.id)

    for user in project.users:
        if user.id not in user_ids_added and len(top_users) < 3:
            top_users.append({
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name
            })
            user_ids_added.add(user.id)

    return JSONResponse(status_code=200, content={"users": top_users})


@router.post("/projects/{project_id}/rename")
async def rename_project(
    project_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        data = await request.json()
    except Exception:
        data = {}

    new_name = data.get("project_name") or data.get("new_name")
    if not new_name:
        return JSONResponse(status_code=400, content={"error": "New project name is required"})

    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if project.owner_id != current_user.id:
        return JSONResponse(status_code=403, content={"error": "Only the owner can rename this project"})

    project.project_name = new_name
    db.commit()
    db.refresh(project)

    return JSONResponse(
        status_code=200,
        content={
            "message": "Project renamed successfully",
            "project": project.to_dict()
        }
    )


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if project.owner_id != current_user.id:
        return JSONResponse(status_code=403, content={"error": "Only the owner can delete this project"})

    db.delete(project)
    db.commit()

    return JSONResponse(status_code=200, content={"message": "Project deleted successfully"})


@router.delete("/responses/{response_id}")
def delete_response(
    response_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    response = db.query(ProjectResponse).filter(ProjectResponse.response_id == response_id).first()
    if not response:
        return JSONResponse(status_code=404, content={"error": "Response not found"})

    project = response.project
    if project.owner_id != current_user.id and response.response_by != current_user.email:
        return JSONResponse(status_code=403, content={"error": "You cannot delete this response"})

    db.delete(response)
    db.commit()

    return JSONResponse(status_code=200, content={"message": "Response deleted successfully"})


# Paper Bucket Management
@router.get("/projects/{project_id}/paper-bucket")
def get_paper_bucket(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    paper_bucket = db.query(PaperBucket).filter(PaperBucket.project_id == project.id).first()
    if not paper_bucket:
        return JSONResponse(status_code=200, content={"paper_ids": []})

    return JSONResponse(status_code=200, content={"paper_ids": paper_bucket.paper_ids if paper_bucket.paper_ids else []})


@router.put("/projects/{project_id}/paper-bucket")
async def update_paper_bucket(
    project_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    try:
        data = await request.json()
    except Exception:
        data = {}

    paper_ids = data.get("paper_ids", [])
    if not isinstance(paper_ids, list):
        return JSONResponse(status_code=400, content={"error": "paper_ids must be an array"})

    paper_bucket = db.query(PaperBucket).filter(PaperBucket.project_id == project.id).first()
    if not paper_bucket:
        paper_bucket = PaperBucket(project_id=project.id, paper_ids=paper_ids)
        db.add(paper_bucket)
    else:
        paper_bucket.paper_ids = paper_ids
        paper_bucket.updated_at = datetime.utcnow()

    db.commit()

    return JSONResponse(
        status_code=200,
        content={"message": "Paper bucket updated successfully", "paper_ids": paper_ids}
    )


@router.post("/projects/{project_id}/paper-bucket/add")
async def add_paper_to_bucket(
    project_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    try:
        data = await request.json()
    except Exception:
        data = {}

    paper_id = data.get("paper_id")
    if not paper_id:
        return JSONResponse(status_code=400, content={"error": "paper_id is required"})

    paper_bucket = db.query(PaperBucket).filter(PaperBucket.project_id == project.id).first()
    if not paper_bucket:
        paper_bucket = PaperBucket(project_id=project.id, paper_ids=[paper_id])
        db.add(paper_bucket)
    else:
        if paper_bucket.paper_ids is None:
            paper_bucket.paper_ids = []

        if paper_id not in paper_bucket.paper_ids:
            paper_bucket.paper_ids = paper_bucket.paper_ids + [paper_id]
            paper_bucket.updated_at = datetime.utcnow()
        else:
            return JSONResponse(status_code=200, content={"message": "Paper already in bucket", "paper_ids": paper_bucket.paper_ids})

    db.commit()

    return JSONResponse(
        status_code=200,
        content={"message": "Paper added to bucket", "paper_ids": paper_bucket.paper_ids}
    )


@router.delete("/projects/{project_id}/paper-bucket/{paper_id}")
def remove_paper_from_bucket(
    project_id: str,
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    paper_bucket = db.query(PaperBucket).filter(PaperBucket.project_id == project.id).first()
    if not paper_bucket or not paper_bucket.paper_ids:
        return JSONResponse(status_code=404, content={"error": "Paper bucket is empty"})

    if paper_id in paper_bucket.paper_ids:
        paper_bucket.paper_ids = [pid for pid in paper_bucket.paper_ids if pid != paper_id]
        paper_bucket.updated_at = datetime.utcnow()
        db.commit()
        return JSONResponse(status_code=200, content={"message": "Paper removed from bucket", "paper_ids": paper_bucket.paper_ids})
    else:
        return JSONResponse(status_code=404, content={"error": "Paper not found in bucket"})


# Paper Content Management
@router.get("/projects/{project_id}/paper")
def get_paper(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    paper = project.paper
    if not paper:
        return JSONResponse(status_code=200, content={"content": ""})

    return JSONResponse(status_code=200, content=paper.to_dict())


@router.put("/projects/{project_id}/paper")
async def update_paper(
    project_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    try:
        data = await request.json()
    except Exception:
        data = {}

    content = data.get("content")
    paper = project.paper

    if not paper:
        paper = Paper(project_id=project.id, content=content)
        db.add(paper)
    else:
        paper.content = content
        paper.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(paper)

    return JSONResponse(
        status_code=200,
        content={"message": "Paper updated successfully", "paper": paper.to_dict()}
    )


# Vector Status and Context Building
@router.get("/projects/{project_id}/vector-status")
def get_vector_status(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    return JSONResponse(
        status_code=200,
        content={
            "status": project.vector_status,
            "is_ready": project.vector_status == "ready"
        }
    )


@router.post("/projects/{project_id}/build-context")
async def build_context(
    project_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Build RAPTOR context for project
    """
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    paper_bucket = db.query(PaperBucket).filter(PaperBucket.project_id == project.id).first()
    if not paper_bucket or not paper_bucket.paper_ids:
        return JSONResponse(status_code=400, content={"error": "No papers in bucket. Add papers before building context."})

    project.vector_status = "processing"
    db.commit()

    try:
        docs = db.query(Document).filter(Document.doc_id.in_(paper_bucket.paper_ids)).all()
        if not docs:
            project.vector_status = "not_started"
            db.commit()
            return JSONResponse(
                status_code=404,
                content={
                    "error": f"No documents found for {len(paper_bucket.paper_ids)} paper IDs",
                    "paper_ids": paper_bucket.paper_ids
                }
            )

        documents_content = [
            {
                "doc_id": str(d.doc_id),
                "content": d.content
            }
            for d in docs
        ]

        try:
            data = await request.json()
        except Exception:
            data = {}

        fast_mode = data.get("fast_mode", True)
        replace_collection = data.get("replace", True)

        retriever = RaptorPipeline(
            documents_content=documents_content,
            project_id=project_id,
            fast_mode=fast_mode,
            replace_collection=replace_collection
        )

        project.vector_status = "ready"
        project.updated_at = datetime.utcnow()
        db.commit()

        return JSONResponse(
            status_code=200,
            content={
                "message": "Context built successfully",
                "status": "ready",
                "documents_processed": len(documents_content),
                "fast_mode": fast_mode,
                "replace_mode": replace_collection,
                "project_id": project_id
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        project.vector_status = "error"
        db.commit()
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "status": "error",
                "project_id": project_id
            }
        )


@router.post("/projects/{project_id}/ask")
async def ask_question(
    project_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    if project.vector_status != "ready":
        status_messages = {
            "not_started": "Context has not been built yet. Please call /build-context first.",
            "processing": "Context is currently being built. Please wait and try again.",
            "error": "An error occurred while building context. Please rebuild using /build-context."
        }
        return JSONResponse(
            status_code=400,
            content={
                "error": status_messages.get(project.vector_status, "Context not ready"),
                "vector_status": project.vector_status,
                "help": "Call POST /projects/<project_id>/build-context to build embeddings"
            }
        )

    try:
        data = await request.json()
    except Exception:
        data = {}

    question = data.get("question", "").strip() if data else ""
    if not question:
        return JSONResponse(status_code=400, content={"error": "Question field is required"})

    if len(question) < 5:
        return JSONResponse(status_code=400, content={"error": "Question must be at least 5 characters"})

    retriever = get_retriever(project_id)
    if retriever is None:
        project.vector_status = "error"
        db.commit()
        return JSONResponse(
            status_code=500,
            content={
                "error": "Failed to load retriever despite 'ready' status",
                "suggestion": "Rebuild context using /build-context",
                "vector_status": "error"
            }
        )

    try:
        answer = asking_llm(retriever, question)
        return JSONResponse(
            status_code=200,
            content={
                "answer": answer,
                "vector_status": "ready",
                "question": question,
                "project_id": project_id
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "type": "query_error",
                "suggestion": "Try rebuilding context"
            }
        )


# LaTeX to PDF Compilation
@router.post("/projects/{project_id}/latex-to-pdf")
async def latex_to_pdf(
    project_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    try:
        data = await request.json()
    except Exception:
        data = {}

    latex_code = data.get("latex_code")
    filename = data.get("filename", "document")

    if not latex_code:
        return JSONResponse(status_code=400, content={"error": "latex_code is required"})

    if filename.endswith('.pdf'):
        filename = filename[:-4]

    temp_dir = tempfile.mkdtemp()

    try:
        tex_file_path = os.path.join(temp_dir, f"{filename}.tex")
        with open(tex_file_path, 'w', encoding='utf-8') as f:
            f.write(latex_code)

        for i in range(2):
            process = subprocess.run(
                ['pdflatex', '-interaction=nonstopmode', f'{filename}.tex'],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30
            )

        pdf_file_path = os.path.join(temp_dir, f"{filename}.pdf")

        if not os.path.exists(pdf_file_path):
            log_file_path = os.path.join(temp_dir, f"{filename}.log")
            error_message = "PDF compilation failed."

            if os.path.exists(log_file_path):
                with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as log_file:
                    log_content = log_file.read()
                    error_lines = [line for line in log_content.split('\n') if '!' in line or 'Error' in line]
                    if error_lines:
                        error_message = "PDF compilation failed:\n" + "\n".join(error_lines[:10])

            shutil.rmtree(temp_dir, ignore_errors=True)

            return JSONResponse(
                status_code=400,
                content={
                    "error": error_message,
                    "stdout": process.stdout[-1000:] if process.stdout else "",
                    "stderr": process.stderr[-1000:] if process.stderr else ""
                }
            )

        with open(pdf_file_path, 'rb') as pdf_file:
            pdf_data = pdf_file.read()

        shutil.rmtree(temp_dir, ignore_errors=True)

        return Response(
            content=pdf_data,
            media_type='application/pdf',
            headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'}
        )

    except subprocess.TimeoutExpired:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return JSONResponse(status_code=400, content={"error": "LaTeX compilation timed out (>30s)"})

    except FileNotFoundError as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "pdflatex not found. Please ensure LaTeX is installed on the server.",
                "hint": "Install TeX Live or MiKTeX"
            }
        )

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return JSONResponse(status_code=500, content={"error": f"An error occurred: {str(e)}"})


# Simple PDF Generation from Database (No LaTeX required)
@router.get("/projects/{project_id}/generate-pdf")
def generate_pdf_from_db(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        return JSONResponse(status_code=404, content={"error": "Project not found"})

    if current_user not in project.users:
        return JSONResponse(status_code=403, content={"error": "Not allowed"})

    paper = project.paper
    if not paper or not paper.content:
        return JSONResponse(status_code=404, content={"error": "No paper content found for this project"})

    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
        )

        elements = []
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='Justify',
            parent=styles['BodyText'],
            alignment=TA_JUSTIFY,
            fontSize=11,
            leading=14,
        ))

        title_style = ParagraphStyle(
            name='CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor='#1a1a1a',
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )

        title = Paragraph(f"<b>{project.project_name}</b>", title_style)
        elements.append(title)
        elements.append(Spacer(1, 0.2 * inch))

        content = paper.content

        content = re.sub(r'\\documentclass\{[^}]*\}', '', content)
        content = re.sub(r'\\usepackage(\[[^\]]*\])?\{[^}]*\}', '', content)
        content = re.sub(r'\\begin\{document\}', '', content)
        content = re.sub(r'\\end\{document\}', '', content)

        title_match = re.search(r'\\title\{([^}]*)\}', content)
        author_match = re.search(r'\\author\{([^}]*)\}', content)
        date_match = re.search(r'\\date\{([^}]*)\}', content)

        content = re.sub(r'\\title\{[^}]*\}', '', content)
        content = re.sub(r'\\author\{[^}]*\}', '', content)
        content = re.sub(r'\\date\{[^}]*\}', '', content)
        content = re.sub(r'\\maketitle', '', content)

        if title_match:
            doc_title = Paragraph(f"<b>{title_match.group(1)}</b>", title_style)
            elements.append(doc_title)
            elements.append(Spacer(1, 0.1 * inch))

        if author_match:
            author_text = author_match.group(1)
            author_para = Paragraph(f"<i>{author_text}</i>", styles['Normal'])
            elements.append(author_para)
            elements.append(Spacer(1, 0.05 * inch))

        if date_match:
            date_text = date_match.group(1)
            if date_text == '\\today':
                date_text = datetime.now().strftime('%B %d, %Y')
            date_para = Paragraph(date_text, styles['Normal'])
            elements.append(date_para)
            elements.append(Spacer(1, 0.3 * inch))

        def replace_section(match):
            return f'<br/><br/><b><font size="14">{match.group(1)}</font></b><br/>'

        def replace_subsection(match):
            return f'<br/><b><font size="12">{match.group(1)}</font></b><br/>'

        def replace_subsubsection(match):
            return f'<br/><i>{match.group(1)}</i><br/>'

        content = re.sub(r'\\section\{([^}]*)\}', replace_section, content)
        content = re.sub(r'\\subsection\{([^}]*)\}', replace_subsection, content)
        content = re.sub(r'\\subsubsection\{([^}]*)\}', replace_subsubsection, content)

        content = re.sub(r'\\textbf\{([^}]*)\}', r'<b>\1</b>', content)
        content = re.sub(r'\\textit\{([^}]*)\}', r'<i>\1</i>', content)
        content = re.sub(r'\\emph\{([^}]*)\}', r'<i>\1</i>', content)
        content = re.sub(r'\\underline\{([^}]*)\}', r'<u>\1</u>', content)

        content = content.replace('\\\\', '<br/>')
        content = content.replace('\\newpage', '<br/><br/>')
        content = re.sub(r'%.*$', '', content, flags=re.MULTILINE)
        content = re.sub(r'\n\s*\n', '\n\n', content)

        paragraphs = content.split('\n\n')
        for para in paragraphs:
            para = para.strip()
            if para:
                try:
                    p = Paragraph(para, styles['Justify'])
                    elements.append(p)
                    elements.append(Spacer(1, 0.1 * inch))
                except Exception as e:
                    print(f"Error processing paragraph: {e}")
                    p = Paragraph(para.replace('<', '&lt;').replace('>', '&gt;'), styles['Justify'])
                    elements.append(p)
                    elements.append(Spacer(1, 0.1 * inch))

        doc.build(elements)
        pdf_data = buffer.getvalue()
        buffer.close()

        filename = project.project_name.replace(' ', '_')

        return Response(
            content=pdf_data,
            media_type='application/pdf',
            headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'}
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Failed to generate PDF: {str(e)}"})
