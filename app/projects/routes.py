from flask import Blueprint, request, jsonify
from datetime import datetime
from app.extensions import db
from app.models import Project, User, Message, Response, PaperBucket, Paper, Document
from app.auth.utils import token_required
from app.services.email_service import send_invitation_email
from rag.raptor import RaptorPipeline, get_retriever
from rag.raptor_middleman import asking_llm

projects_bp = Blueprint('projects', __name__)


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

    if not invited_user:
        return jsonify({"error": "User does not exist"}), 404

    if invited_user in project.users:
        return jsonify({"error": "User already added"}), 400

    project.users.append(invited_user)
    db.session.commit()

    try:
        inviter_name = f"{current_user.first_name} {current_user.last_name}".strip() or current_user.email
        recipient_name = f"{invited_user.first_name} {invited_user.last_name}".strip() or invited_user.email
        
        email_sent = send_invitation_email(
            recipient_email=invited_user.email,
            recipient_name=recipient_name,
            project_name=project.project_name,
            inviter_name=inviter_name
        )
        
        if email_sent:
            return jsonify({
                "message": "User invited successfully and notification email sent"
            }), 200
        else:
            return jsonify({
                "message": "User invited successfully but failed to send notification email"
            }), 200
            
    except Exception as e:
        print(f"Email sending error: {str(e)}")
        return jsonify({
            "message": "User invited successfully but failed to send notification email",
            "error": str(e)
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
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    # Get paper bucket
    paper_bucket = PaperBucket.query.filter_by(project_id=project.id).first()
    if not paper_bucket or not paper_bucket.paper_ids:
        return jsonify({"error": "No papers in bucket"}), 400
    
    # Update status to processing
    project.vector_status = "processing"
    db.session.commit()
    
    try:
        # Fetch document contents for the papers in the bucket
        docs = Document.query.filter(Document.doc_id.in_(paper_bucket.paper_ids)).all()
        
        if not docs:
            project.vector_status = "not_started"
            db.session.commit()
            return jsonify({"error": "No documents found for paper IDs"}), 404
        
        # Format data for RaptorPipeline
        data_for_raptor = [{"doc_id": d.doc_id} for d in docs]
        
        # Always rebuild embeddings (overwrites existing)
        RaptorPipeline(current_user, data_for_raptor, project_id)
        
        # Update status to ready
        project.vector_status = "ready"
        db.session.commit()
        
        return jsonify({
            "message": "Context built successfully", 
            "status": "ready"
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        project.vector_status = "error"
        db.session.commit()
        return jsonify({"error": str(e), "status": "error"}), 500


@projects_bp.route("/projects/<project_id>/ask", methods=["POST"])
@token_required
def ask_question(current_user, project_id):
    project = Project.query.filter_by(project_id=project_id).first()
    
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if current_user not in project.users:
        return jsonify({"error": "Not allowed"}), 403
    
    # Check vector status before attempting to answer
    if project.vector_status != "ready":
        status_messages = {
            "not_started": "Context has not been built yet. Please build context first.",
            "processing": "Context is currently being built. Please wait and try again.",
            "error": "An error occurred while building context. Please rebuild context."
        }
        return jsonify({
            "error": status_messages.get(project.vector_status, "Context not ready"),
            "vector_status": project.vector_status
        }), 400
    
    data = request.get_json()
    question = data.get("question")
    
    if not question:
        return jsonify({"error": "Question is required"}), 400
    
    # Load the retriever for this project
    retriever = get_retriever(project_id)
    
    if retriever is not None:
        try:
            answer = asking_llm(retriever, question)
            return jsonify({"answer": answer}), 200
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    else:
        # This shouldn't happen if vector_status is "ready", but handle it anyway
        project.vector_status = "error"
        db.session.commit()
        return jsonify({
            "error": "No context found for this project despite ready status. Please rebuild context.",
            "vector_status": "error"
        }), 404
