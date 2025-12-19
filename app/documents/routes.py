from flask import Blueprint, request, jsonify
from datetime import datetime
from app.extensions import db
from app.models import Document
from app.auth.utils import token_required

documents_bp = Blueprint('documents', __name__)


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
    docs = Document.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        "doc_id": d.doc_id,
        "title": d.title,
        "content": d.content,
        "created_at": d.created_at.isoformat()
    } for d in docs]), 200


@documents_bp.route('/documents/<doc_id>', methods=['GET'])
@token_required
def get_document(current_user, doc_id):
    doc = Document.query.filter_by(doc_id=doc_id, user_id=current_user.id).first()
    
    if not doc:
        return jsonify({"error": "Document not found"}), 404

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

    doc = Document.query.filter_by(doc_id=doc_id, user_id=current_user.id).first()
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    doc.content = data["content"]
    doc.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Document updated successfully"}), 200


@documents_bp.route('/documents/<doc_id>', methods=['DELETE'])
@token_required
def delete_document(current_user, doc_id):
    doc = Document.query.filter_by(doc_id=doc_id, user_id=current_user.id).first()
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    db.session.delete(doc)
    db.session.commit()
    return jsonify({"message": "Document deleted successfully"}), 200


@documents_bp.route('/documents/summary', methods=['GET'])
@token_required
def get_documents_summary(current_user):
    try:
        docs = Document.query.with_entities(
            Document.doc_id, 
            Document.title
        ).filter_by(user_id=current_user.id).all()

        result = [
            {"doc_id": doc.doc_id, "title": doc.title}
            for doc in docs
        ]

        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500