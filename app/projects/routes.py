from flask import Blueprint, request, jsonify, send_file
from datetime import datetime
import tempfile
import subprocess
import os
import io
import shutil
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from app.extensions import db
from app.models import Project, User, Message, Response, PaperBucket, Paper, Document
from app.auth.utils import token_required
from app.services.email_service import send_invitation_email
from rag.raptor import RaptorPipeline, get_retriever, temporary_query_pipeline
from rag.raptor_middleman import asking_llm

projects_bp = Blueprint('projects', __name__)


# ═══════════════════════════════════════════════════════════════════════════
# FEATURE 1: TEMPORARY QUERY (No Permanent Storage)
# ═══════════════════════════════════════════════════════════════════════════

@projects_bp.route("/query-temporary", methods=["POST"])
def query_temporary():
    """
    Feature 1: Direct text embedding for one-off queries
    
    No authentication required (modify if needed)
    No permanent storage - embeddings discarded after query
    
    Request JSON:
    {
        "text": "Document content to query against",
        "question": "What do you want to know?"
    }
    
    Response:
    {
        "answer": "LLM's answer based on text",
        "mode": "temporary",
        "storage": "none"
    }
    """
    try:
        data = request.get_json()
        
        # Validation
        text = data.get("text", "").strip()
        question = data.get("question", "").strip()
        
        if not text or not question:
            return jsonify({
                "error": "Both 'text' and 'question' fields are required"
            }), 400
        
        if len(text) < 10:
            return jsonify({
                "error": "Text must be at least 10 characters long"
            }), 400
        
        if len(question) < 5:
            return jsonify({
                "error": "Question must be at least 5 characters long"
            }), 400
        
        # ✅ FEATURE 1: Execute temporary query
        answer = temporary_query_pipeline(text, question)
        
        return jsonify({
            "answer": answer,
            "mode": "temporary",
            "storage": "none",
            "text_length": len(text),
            "question": question
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "type": "temporary_query_error"
        }), 500


# ═══════════════════════════════════════════════════════════════════════════
# FEATURE 2: PROJECT-BASED PERSISTENT STORAGE
# ═══════════════════════════════════════════════════════════════════════════



@projects_bp.route("/projects/create", methods=["POST"])
@token_required
def create_project(current_user):
    data = request.get_json()
    project_name = data.get("project_name")

    if not project_name:
        return jsonify({"error": "project_name is required"}), 400

    project = Project(
        project_name=project_name,
        owner_id=current_user.id
    )
    project.users.append(current_user)

    db.session.add(project)
    db.session.commit()

    return jsonify({
        "message": "Project created successfully",
        "project_id": project.project_id
    }), 201


@projects_bp.route("/projects/<project_id>/invite", methods=["POST"])
@token_required
def invite_user(current_user, project_id):
    data = request.get_json()
    user_email = data.get("email")

    if not user_email:
        return jsonify({"error": "Email is required"}), 400

    project = Project.query.filter_by(project_id=project_id).first()

    if not project:
        return jsonify({"error": "Project not found"}), 404

    if project.owner_id != current_user.id:
        return jsonify({"error": "Only project owner can invite users"}), 403

    invited_user = User.query.filter_by(email=user_email).first()
    inviter_name = f"{current_user.first_name} {current_user.last_name}".strip() or current_user.email

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
                return jsonify({
                    "message": f"Signup invitation sent to {user_email}",
                    "status": "signup_required"
                }), 200
            else:
                return jsonify({
                    "message": f"User doesn't exist. Failed to send signup invitation email.",
                    "status": "email_failed"
                }), 200
                
        except Exception as e:
            print(f"Email sending error: {str(e)}")
            return jsonify({
                "message": f"User doesn't exist. Please ask them to sign up first.",
                "status": "signup_required",
                "error": str(e)
            }), 200

    # Case 2: User EXISTS in database
    if invited_user in project.users:
        return jsonify({"error": "User already added to this project"}), 400

    # Add user to project
    project.users.append(invited_user)
    db.session.commit()

    try:
        recipient_name = f"{invited_user.first_name} {invited_user.last_name}".strip() or invited_user.email
        
        email_sent = send_invitation_email(
            recipient_email=invited_user.email,
            recipient_name=recipient_name,
            project_name=project.project_name,
            inviter_name=inviter_name
        )
        
        if email_sent:
            return jsonify({
                "message": f"✅ {recipient_name} invited successfully! Notification email sent.",
                "status": "invited"
            }), 200
        else:
            return jsonify({
                "message": f"✅ {recipient_name} added to project, but notification email failed to send.",
                "status": "invited_no_email"
            }), 200
            
    except Exception as e:
        print(f"Email sending error: {str(e)}")
        return jsonify({
            "message": f"✅ User added to project, but notification email failed: {str(e)}",
            "status": "invited_no_email"
        }), 200



@projects_bp.route("/projects/<project_id>/messages", methods=["POST"])
@token_required
def save_message(current_user, project_id):
    project = Project.query.filter_by(project_id=project_id).first()

    if not project:
        return jsonify({"error": "Project not found"}), 404

    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403

    data = request.get_json()

    msg = Message(
        message_number=len(project.messages) + 1,
        message_sender=current_user.email,
        message_content=data.get("content"),
        project_id=project.id
    )

    db.session.add(msg)
    db.session.commit()

    return jsonify({"message": "Message saved"}), 200


@projects_bp.route("/messages/<int:msg_id>", methods=["DELETE"])
@token_required
def delete_message(current_user, msg_id):
    msg = Message.query.get(msg_id)
    if not msg:
        return jsonify({"error": "Message not found"}), 404

    project = msg.project

    if project.owner_id != current_user.id and msg.message_sender != current_user.email:
        return jsonify({"error": "You cannot delete this message"}), 403

    db.session.delete(msg)
    db.session.commit()

    return jsonify({"message": "Message deleted"}), 200


@projects_bp.route("/projects/<project_id>/responses", methods=["POST"])
@token_required
def save_response(current_user, project_id):
    project = Project.query.filter_by(project_id=project_id).first()

    if not project:
        return jsonify({"error": "Project not found"}), 404

    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403

    data = request.get_json()

    res = Response(
        summary=data.get("summary"),
        response_by=current_user.email,
        project_id=project.id
    )

    db.session.add(res)
    db.session.commit()

    return jsonify({"message": "Response saved"}), 200


@projects_bp.route("/projects", methods=["GET"])
@token_required
def get_user_projects(current_user):
    projects = current_user.projects
    return jsonify([p.to_dict() for p in projects]), 200


@projects_bp.route("/projects/<project_id>", methods=["GET"])
@token_required
def get_project(current_user, project_id):
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    project_dict = project.to_dict()
    project_dict['messages'] = [m.to_dict() for m in project.messages]
    project_dict['responses'] = [r.to_dict() for r in project.responses]
    
    return jsonify(project_dict), 200


@projects_bp.route("/projects/<project_id>/messages", methods=["GET"])
@token_required
def get_project_messages(current_user, project_id):
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    return jsonify([m.to_dict() for m in project.messages]), 200


@projects_bp.route("/projects/<project_id>/responses", methods=["GET"])
@token_required
def get_project_responses(current_user, project_id):
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    return jsonify([r.to_dict() for r in project.responses]), 200


@projects_bp.route("/projects/<project_id>/conversation", methods=["GET"])
@token_required
def get_conversation(current_user, project_id):
    """
    Get unified, chronologically-ordered conversation thread for a project.
    Merges all Messages (user questions) and Responses (AI answers) into a single thread.
    """
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    conversation = []
    
    # Add all messages to conversation
    for message in project.messages:
        conversation.append({
            "type": "message",
            "content": message.message_content,
            "sender": message.message_sender,
            "timestamp": message.created_at.isoformat() if message.created_at else None,
            "id": message.id
        })
    
    # Add all responses to conversation
    for response in project.responses:
        conversation.append({
            "type": "response",
            "content": response.summary,
            "sender": response.response_by,
            "timestamp": response.created_at.isoformat() if response.created_at else None,
            "id": response.response_id
        })
    
    # Sort by timestamp ascending (chronological order)
    conversation.sort(key=lambda x: x["timestamp"] or "")
    
    return jsonify({"conversation": conversation}), 200


@projects_bp.route("/projects/<project_id>/top-users", methods=["GET"])
@token_required
def get_project_top_users(current_user, project_id):
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
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
    
    return jsonify({"users": top_users}), 200


@projects_bp.route("/projects/<project_id>/rename", methods=["POST"])
@token_required
def rename_project(current_user, project_id):
    data = request.get_json()
    new_name = data.get("project_name") or data.get("new_name")

    if not new_name:
        return jsonify({"error": "New project name is required"}), 400

    project = Project.query.filter_by(project_id=project_id).first()

    if not project:
        return jsonify({"error": "Project not found"}), 404

    if project.owner_id != current_user.id:
        return jsonify({"error": "Only the owner can rename this project"}), 403

    project.project_name = new_name
    db.session.commit()

    return jsonify({
        "message": "Project renamed successfully",
        "project": project.to_dict()
    }), 200


@projects_bp.route("/projects/<project_id>", methods=["DELETE"])
@token_required
def delete_project(current_user, project_id):
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if project.owner_id != current_user.id:
        return jsonify({"error": "Only the owner can delete this project"}), 403
    
    db.session.delete(project)
    db.session.commit()
    
    return jsonify({"message": "Project deleted successfully"}), 200


@projects_bp.route("/responses/<response_id>", methods=["DELETE"])
@token_required
def delete_response(current_user, response_id):
    response = Response.query.filter_by(response_id=response_id).first()
    
    if not response:
        return jsonify({"error": "Response not found"}), 404
    
    project = response.project
    
    if project.owner_id != current_user.id and response.response_by != current_user.email:
        return jsonify({"error": "You cannot delete this response"}), 403
    
    db.session.delete(response)
    db.session.commit()
    
    return jsonify({"message": "Response deleted successfully"}), 200


# Paper Bucket Management
@projects_bp.route("/projects/<project_id>/paper-bucket", methods=["GET"])
@token_required
def get_paper_bucket(current_user, project_id):
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    paper_bucket = PaperBucket.query.filter_by(project_id=project.id).first()
    
    if not paper_bucket:
        return jsonify({"paper_ids": []}), 200
    
    return jsonify({"paper_ids": paper_bucket.paper_ids if paper_bucket.paper_ids else []}), 200


@projects_bp.route("/projects/<project_id>/paper-bucket", methods=["PUT"])
@token_required
def update_paper_bucket(current_user, project_id):
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    data = request.get_json()
    paper_ids = data.get("paper_ids", [])
    
    if not isinstance(paper_ids, list):
        return jsonify({"error": "paper_ids must be an array"}), 400
    
    paper_bucket = PaperBucket.query.filter_by(project_id=project.id).first()
    
    if not paper_bucket:
        paper_bucket = PaperBucket(
            project_id=project.id,
            paper_ids=paper_ids
        )
        db.session.add(paper_bucket)
    else:
        paper_bucket.paper_ids = paper_ids
        paper_bucket.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({"message": "Paper bucket updated successfully", "paper_ids": paper_ids}), 200


@projects_bp.route("/projects/<project_id>/paper-bucket/add", methods=["POST"])
@token_required
def add_paper_to_bucket(current_user, project_id):
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    data = request.get_json()
    paper_id = data.get("paper_id")
    
    if not paper_id:
        return jsonify({"error": "paper_id is required"}), 400
    
    paper_bucket = PaperBucket.query.filter_by(project_id=project.id).first()
    
    if not paper_bucket:
        paper_bucket = PaperBucket(
            project_id=project.id,
            paper_ids=[paper_id]
        )
        db.session.add(paper_bucket)
    else:
        if paper_bucket.paper_ids is None:
            paper_bucket.paper_ids = []
        
        if paper_id not in paper_bucket.paper_ids:
            paper_bucket.paper_ids = paper_bucket.paper_ids + [paper_id]
            paper_bucket.updated_at = datetime.utcnow()
        else:
            return jsonify({"message": "Paper already in bucket", "paper_ids": paper_bucket.paper_ids}), 200
    
    db.session.commit()
    
    return jsonify({"message": "Paper added to bucket", "paper_ids": paper_bucket.paper_ids}), 200


@projects_bp.route("/projects/<project_id>/paper-bucket/<paper_id>", methods=["DELETE"])
@token_required
def remove_paper_from_bucket(current_user, project_id, paper_id):
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    paper_bucket = PaperBucket.query.filter_by(project_id=project.id).first()
    
    if not paper_bucket or not paper_bucket.paper_ids:
        return jsonify({"error": "Paper bucket is empty"}), 404
    
    if paper_id in paper_bucket.paper_ids:
        paper_bucket.paper_ids = [pid for pid in paper_bucket.paper_ids if pid != paper_id]
        paper_bucket.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"message": "Paper removed from bucket", "paper_ids": paper_bucket.paper_ids}), 200
    else:
        return jsonify({"error": "Paper not found in bucket"}), 404


# Paper Content Management
@projects_bp.route("/projects/<project_id>/paper", methods=["GET"])
@token_required
def get_paper(current_user, project_id):
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    # Access paper via relationship
    paper = project.paper
    
    if not paper:
        return jsonify({"content": ""}), 200
    
    return jsonify(paper.to_dict()), 200


@projects_bp.route("/projects/<project_id>/paper", methods=["PUT"])
@token_required
def update_paper(current_user, project_id):
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    data = request.get_json()
    content = data.get("content")
    
    paper = project.paper
    
    if not paper:
        paper = Paper(project_id=project.id, content=content)
        db.session.add(paper)
    else:
        paper.content = content
        paper.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        "message": "Paper updated successfully", 
        "paper": paper.to_dict()
    }), 200


# Vector Status and Context Building
@projects_bp.route("/projects/<project_id>/vector-status", methods=["GET"])
@token_required
def get_vector_status(current_user, project_id):
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    return jsonify({
        "status": project.vector_status,
        "is_ready": project.vector_status == "ready"
    }), 200


@projects_bp.route("/projects/<project_id>/build-context", methods=["POST"])
@token_required
def build_context(current_user, project_id):
    """
    ✅ CORRECTED: Build RAPTOR context for project
    
    Steps:
    1. Fetch papers from paper_bucket
    2. Retrieve document content for each paper_id
    3. Run RAPTOR pipeline
    4. Store embeddings in PGVector (permanent)
    5. Update vector_status to "ready"
    """
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    # Check if paper bucket is populated
    paper_bucket = PaperBucket.query.filter_by(project_id=project.id).first()
    if not paper_bucket or not paper_bucket.paper_ids:
        return jsonify({
            "error": "No papers in bucket. Add papers before building context."
        }), 400
    
    # Update status to processing
    project.vector_status = "processing"
    db.session.commit()
    
    try:
        # ✅ STEP 1: Fetch documents with actual content
        docs = Document.query.filter(
            Document.doc_id.in_(paper_bucket.paper_ids)
        ).all()
        
        if not docs:
            project.vector_status = "not_started"
            db.session.commit()
            return jsonify({
                "error": f"No documents found for {len(paper_bucket.paper_ids)} paper IDs",
                "paper_ids": paper_bucket.paper_ids
            }), 404
        
        # ✅ STEP 2: Format documents for RAPTOR (includes content!)
        documents_content = [
            {
                "doc_id": str(d.doc_id),
                "content": d.content
            }
            for d in docs
        ]
        
        print(f"DEBUG: Prepared {len(documents_content)} documents for RAPTOR")
        
        # ✅ STEP 3: Parse request options (handle missing Content-Type)
        try:
            data = request.get_json(force=True, silent=True) or {}
        except:
            data = {}
        
        fast_mode = data.get("fast_mode", True)
        replace_collection = data.get("replace", True)
        
        print(f"DEBUG: fast_mode={fast_mode}, replace={replace_collection}")
        
        # ✅ STEP 4: Run RAPTOR pipeline
        # This creates embeddings and stores them in PGVector
        retriever = RaptorPipeline(
            documents_content=documents_content,
            project_id=project_id,
            fast_mode=fast_mode,
            replace_collection=replace_collection
        )
        
        # ✅ STEP 5: Mark project as ready
        project.vector_status = "ready"
        project.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            "message": "Context built successfully",
            "status": "ready",
            "documents_processed": len(documents_content),
            "fast_mode": fast_mode,
            "replace_mode": replace_collection,
            "project_id": project_id
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        project.vector_status = "error"
        db.session.commit()
        
        return jsonify({
            "error": str(e),
            "status": "error",
            "project_id": project_id
        }), 500


@projects_bp.route("/projects/<project_id>/ask", methods=["POST"])
@token_required
def ask_question(current_user, project_id):
    """
    ✅ Query project context using RAPTOR retriever
    
    Prerequisites:
    - Project must have vector_status == "ready"
    - Must call /build-context first
    
    Request JSON:
    {
        "question": "Your question about the documents"
    }
    
    Response:
    {
        "answer": "LLM's answer based on RAPTOR embeddings",
        "vector_status": "ready"
    }
    """
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    # ✅ Check vector status BEFORE attempting to query
    if project.vector_status != "ready":
        status_messages = {
            "not_started": "Context has not been built yet. Please call /build-context first.",
            "processing": "Context is currently being built. Please wait and try again.",
            "error": "An error occurred while building context. Please rebuild using /build-context."
        }
        return jsonify({
            "error": status_messages.get(
                project.vector_status,
                "Context not ready"
            ),
            "vector_status": project.vector_status,
            "help": "Call POST /projects/<project_id>/build-context to build embeddings"
        }), 400
    
    # Validate question
    data = request.get_json(force=True, silent=True) or {}
    question = data.get("question", "").strip() if data else ""
    
    if not question:
        return jsonify({"error": "Question field is required"}), 400
    
    if len(question) < 5:
        return jsonify({"error": "Question must be at least 5 characters"}), 400
    
    # ✅ Load retriever from PGVector
    retriever = get_retriever(project_id)
    
    if retriever is None:
        # Retriever failed to load even though status is "ready"
        # This shouldn't happen, but handle gracefully
        project.vector_status = "error"
        db.session.commit()
        
        return jsonify({
            "error": "Failed to load retriever despite 'ready' status",
            "suggestion": "Rebuild context using /build-context",
            "vector_status": "error"
        }), 500
    
    try:
        # ✅ Query with RAPTOR embeddings
        answer = asking_llm(retriever, question)
        
        return jsonify({
            "answer": answer,
            "vector_status": "ready",
            "question": question,
            "project_id": project_id
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "error": str(e),
            "type": "query_error",
            "suggestion": "Try rebuilding context"
        }), 500


# LaTeX to PDF Compilation
@projects_bp.route("/projects/<project_id>/latex-to-pdf", methods=["POST"])
@token_required
def latex_to_pdf(current_user, project_id):
    """
    Compile LaTeX code to PDF and send back to client
    Expects JSON with 'latex_code' field
    Returns PDF file or error message
    """
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    data = request.get_json()
    latex_code = data.get("latex_code")
    filename = data.get("filename", "document")
    
    if not latex_code:
        return jsonify({"error": "latex_code is required"}), 400
    
    # Ensure filename doesn't have .pdf extension yet
    if filename.endswith('.pdf'):
        filename = filename[:-4]
    
    # Create a temporary directory for compilation
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Write LaTeX code to a .tex file
        tex_file_path = os.path.join(temp_dir, f"{filename}.tex")
        with open(tex_file_path, 'w', encoding='utf-8') as f:
            f.write(latex_code)
        
        print(f"[LaTeX] Compiling {filename}.tex in {temp_dir}")
        
        # Run pdflatex to compile the LaTeX file
        # Run twice to resolve references
        for i in range(2):
            process = subprocess.run(
                ['pdflatex', '-interaction=nonstopmode', f'{filename}.tex'],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            print(f"[LaTeX] Compilation pass {i+1} return code: {process.returncode}")
        
        # Check if PDF was created
        pdf_file_path = os.path.join(temp_dir, f"{filename}.pdf")
        
        if not os.path.exists(pdf_file_path):
            # If compilation failed, return the error log
            log_file_path = os.path.join(temp_dir, f"{filename}.log")
            error_message = "PDF compilation failed."
            
            print(f"[LaTeX] PDF not created. Checking log file...")
            
            if os.path.exists(log_file_path):
                with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as log_file:
                    log_content = log_file.read()
                    # Extract relevant error lines
                    error_lines = [line for line in log_content.split('\n') if '!' in line or 'Error' in line]
                    if error_lines:
                        error_message = f"PDF compilation failed:\n" + "\n".join(error_lines[:10])
                    print(f"[LaTeX] Error: {error_message}")
            
            # Cleanup before returning error
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            return jsonify({
                "error": error_message,
                "stdout": process.stdout[-1000:] if process.stdout else "",  # Last 1000 chars
                "stderr": process.stderr[-1000:] if process.stderr else ""
            }), 400
        
        # Read PDF into memory
        print(f"[LaTeX] PDF created successfully. Size: {os.path.getsize(pdf_file_path)} bytes")
        
        with open(pdf_file_path, 'rb') as pdf_file:
            pdf_data = pdf_file.read()
        
        # Clean up temporary directory NOW (before sending file)
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Create BytesIO object from PDF data
        pdf_io = io.BytesIO(pdf_data)
        pdf_io.seek(0)
        
        # Send the PDF file from memory
        return send_file(
            pdf_io,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{filename}.pdf"
        )
        
    except subprocess.TimeoutExpired:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return jsonify({"error": "LaTeX compilation timed out (>30s)"}), 400
    
    except FileNotFoundError as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"[LaTeX] FileNotFoundError: {str(e)}")
        return jsonify({
            "error": "pdflatex not found. Please ensure LaTeX is installed on the server.",
            "hint": "Install TeX Live or MiKTeX"
        }), 500
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        shutil.rmtree(temp_dir, ignore_errors=True)
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


# Simple PDF Generation from Database (No LaTeX required)
@projects_bp.route("/projects/<project_id>/generate-pdf", methods=["GET"])
@token_required
def generate_pdf_from_db(current_user, project_id):
    """
    Generate PDF from paper content stored in database
    No LaTeX installation required - uses ReportLab
    """
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    # Get paper content from database
    paper = project.paper
    
    if not paper or not paper.content:
        return jsonify({"error": "No paper content found for this project"}), 404
    
    try:
        # Create PDF in memory
        buffer = io.BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
        )
        
        # Container for the 'Flowable' objects
        elements = []
        
        # Define styles
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='Justify',
            parent=styles['BodyText'],
            alignment=TA_JUSTIFY,
            fontSize=11,
            leading=14,
        ))
        
        # Title style
        title_style = ParagraphStyle(
            name='CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor='#1a1a1a',
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        # Add project title
        title = Paragraph(f"<b>{project.project_name}</b>", title_style)
        elements.append(title)
        elements.append(Spacer(1, 0.2*inch))
        
        # Process content - handle LaTeX content
        content = paper.content
        
        # Better LaTeX processing using regex
        import re
        
        # Remove document structure commands
        content = re.sub(r'\\documentclass\{[^}]*\}', '', content)
        content = re.sub(r'\\usepackage(\[[^\]]*\])?\{[^}]*\}', '', content)
        content = re.sub(r'\\begin\{document\}', '', content)
        content = re.sub(r'\\end\{document\}', '', content)
        
        # Process title, author, date
        title_match = re.search(r'\\title\{([^}]*)\}', content)
        author_match = re.search(r'\\author\{([^}]*)\}', content)
        date_match = re.search(r'\\date\{([^}]*)\}', content)
        
        # Remove these commands from content and add them as formatted elements
        content = re.sub(r'\\title\{[^}]*\}', '', content)
        content = re.sub(r'\\author\{[^}]*\}', '', content)
        content = re.sub(r'\\date\{[^}]*\}', '', content)
        content = re.sub(r'\\maketitle', '', content)
        
        # Add title, author, date if found
        if title_match:
            doc_title = Paragraph(f"<b>{title_match.group(1)}</b>", title_style)
            elements.append(doc_title)
            elements.append(Spacer(1, 0.1*inch))
        
        if author_match:
            author_text = author_match.group(1)
            author_para = Paragraph(f"<i>{author_text}</i>", styles['Normal'])
            elements.append(author_para)
            elements.append(Spacer(1, 0.05*inch))
        
        if date_match:
            date_text = date_match.group(1)
            if date_text == '\\today':
                from datetime import datetime
                date_text = datetime.now().strftime('%B %d, %Y')
            date_para = Paragraph(date_text, styles['Normal'])
            elements.append(date_para)
            elements.append(Spacer(1, 0.3*inch))
        
        # Process sections - convert to bold headings
        def replace_section(match):
            return f'<br/><br/><b><font size="14">{match.group(1)}</font></b><br/>'
        
        def replace_subsection(match):
            return f'<br/><b><font size="12">{match.group(1)}</font></b><br/>'
        
        def replace_subsubsection(match):
            return f'<br/><i>{match.group(1)}</i><br/>'
        
        content = re.sub(r'\\section\{([^}]*)\}', replace_section, content)
        content = re.sub(r'\\subsection\{([^}]*)\}', replace_subsection, content)
        content = re.sub(r'\\subsubsection\{([^}]*)\}', replace_subsubsection, content)
        
        # Process text formatting
        content = re.sub(r'\\textbf\{([^}]*)\}', r'<b>\1</b>', content)
        content = re.sub(r'\\textit\{([^}]*)\}', r'<i>\1</i>', content)
        content = re.sub(r'\\emph\{([^}]*)\}', r'<i>\1</i>', content)
        content = re.sub(r'\\underline\{([^}]*)\}', r'<u>\1</u>', content)
        
        # Process line breaks
        content = content.replace('\\\\', '<br/>')
        content = content.replace('\\newpage', '<br/><br/>')
        
        # Remove comments
        content = re.sub(r'%.*$', '', content, flags=re.MULTILINE)
        
        # Clean up extra whitespace
        content = re.sub(r'\n\s*\n', '\n\n', content)
        
        # Split into paragraphs
        paragraphs = content.split('\n\n')
        
        for para in paragraphs:
            para = para.strip()
            if para:
                # Create paragraph
                try:
                    p = Paragraph(para, styles['Justify'])
                    elements.append(p)
                    elements.append(Spacer(1, 0.1*inch))
                except Exception as e:
                    # If paragraph fails, just add as plain text
                    print(f"Error processing paragraph: {e}")
                    p = Paragraph(para.replace('<', '&lt;').replace('>', '&gt;'), styles['Justify'])
                    elements.append(p)
                    elements.append(Spacer(1, 0.1*inch))
        
        # Build PDF
        doc.build(elements)
        
        # Get PDF data
        pdf_data = buffer.getvalue()
        buffer.close()
        
        # Create new BytesIO for sending
        pdf_io = io.BytesIO(pdf_data)
        pdf_io.seek(0)
        
        filename = project.project_name.replace(' ', '_')
        
        print(f"[PDF] Generated PDF from database. Size: {len(pdf_data)} bytes")
        
        return send_file(
            pdf_io,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{filename}.pdf"
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to generate PDF: {str(e)}"}), 500

