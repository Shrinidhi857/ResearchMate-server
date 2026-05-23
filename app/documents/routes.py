from flask import Blueprint, request, jsonify
from datetime import datetime
from app.extensions import db
from app.models import Document, Project, PaperBucket
from app.auth.utils import token_required

documents_bp = Blueprint('documents', __name__)


# ============================================================================
# ACCESS CONTROL HELPER
# ============================================================================

def user_has_document_access(current_user, doc_id):
    """
    Check if user has access to a document.
    Access is granted if:
    1. User is the document owner, OR
    2. Document is in a PaperBucket of a project the user is a member of
    """
    doc = Document.query.filter_by(doc_id=doc_id).first()
    
    if not doc:
        return None
    
    # Access 1: User is the owner
    if doc.user_id == current_user.id:
        return doc
    
    # Access 2: Document is in a shared project
    paper_bucket = PaperBucket.query.filter(
        PaperBucket.paper_ids.contains([doc_id])
    ).first()
    
    if paper_bucket:
        project = paper_bucket.project
        if current_user in project.users:
            return doc
    
    return None


@documents_bp.route('/documents', methods=['POST'])
@token_required
def add_document(current_user):
    data = request.get_json()
    if not data or "content" not in data:
        return jsonify({"error": "Document content is required"}), 400

    try:
        doc = Document(
            user_id=current_user.id,
            title=data.get("title"),
            content=data["content"]
        )
        db.session.add(doc)
        db.session.commit()
        return jsonify({
            "message": "Document saved successfully",
            "doc_id": doc.doc_id,
            "title": doc.title,
            "user_id": current_user.id
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@documents_bp.route('/documents', methods=['GET'])
@token_required
def get_documents(current_user):
    # Get documents owned by the user
    owned_docs = Document.query.filter_by(user_id=current_user.id).all()
    
    # Get documents in shared projects
    shared_doc_ids = set()
    for project in current_user.projects:
        if project.paper_bucket and project.paper_bucket.paper_ids:
            shared_doc_ids.update(project.paper_bucket.paper_ids)
    
    shared_docs = []
    if shared_doc_ids:
        shared_docs = Document.query.filter(Document.doc_id.in_(shared_doc_ids)).all()
    
    # Combine and deduplicate by doc_id
    all_docs = {d.doc_id: d for d in owned_docs + shared_docs}.values()
    
    return jsonify([{
        "doc_id": d.doc_id,
        "title": d.title,
        "content": d.content,
        "created_at": d.created_at.isoformat()
    } for d in all_docs]), 200


@documents_bp.route('/documents/<doc_id>', methods=['GET'])
@token_required
def get_document(current_user, doc_id):
    doc = user_has_document_access(current_user, doc_id)
    
    if not doc:
        return jsonify({"error": "Document not found or access denied"}), 404

    return jsonify({
        "doc_id": doc.doc_id,
        "title": doc.title,
        "content": doc.content,
        "created_at": doc.created_at.isoformat()
    }), 200


@documents_bp.route('/documents/<doc_id>', methods=['PUT'])
@token_required
def update_document(current_user, doc_id):
    data = request.get_json()
    if not data or "content" not in data:
        return jsonify({"error": "Document content is required"}), 400

    # Only document owner can edit
    doc = Document.query.filter_by(doc_id=doc_id, user_id=current_user.id).first()
    if not doc:
        return jsonify({"error": "Document not found or you don't have permission to edit"}), 404

    doc.content = data["content"]
    doc.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Document updated successfully"}), 200


@documents_bp.route('/documents/<doc_id>', methods=['DELETE'])
@token_required
def delete_document(current_user, doc_id):
    # Only document owner can delete
    doc = Document.query.filter_by(doc_id=doc_id, user_id=current_user.id).first()
    if not doc:
        return jsonify({"error": "Document not found or you don't have permission to delete"}), 404

    db.session.delete(doc)
    db.session.commit()
    return jsonify({"message": "Document deleted successfully"}), 200


@documents_bp.route('/documents/summary', methods=['GET'])
@token_required
def get_documents_summary(current_user):
    try:
        # Get owned documents
        owned_docs = Document.query.with_entities(
            Document.doc_id, 
            Document.title
        ).filter_by(user_id=current_user.id).all()
        
        # Get shared documents from projects
        shared_doc_ids = set()
        for project in current_user.projects:
            if project.paper_bucket and project.paper_bucket.paper_ids:
                shared_doc_ids.update(project.paper_bucket.paper_ids)
        
        shared_docs = []
        if shared_doc_ids:
            shared_docs = Document.query.with_entities(
                Document.doc_id,
                Document.title
            ).filter(Document.doc_id.in_(shared_doc_ids)).all()
        
        # Combine and deduplicate
        all_docs = {doc.doc_id: doc for doc in owned_docs + shared_docs}
        
        result = [
            {"doc_id": doc.doc_id, "title": doc.title}
            for doc in all_docs.values()
        ]

        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500