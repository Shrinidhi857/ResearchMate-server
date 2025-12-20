from flask import Blueprint, request, jsonify
from app.auth.utils import token_required
from rag.raptor import RaptorPipeline, get_retriever
from rag.raptor_middleman import asking_llm

rag_bp = Blueprint('rag', __name__)


@rag_bp.route('/analyse', methods=['POST'])
@token_required
def raptor_analysis(current_user):
    data = request.get_json()
    project_id = data.get("project_id")

    if not project_id:
        return jsonify({"message": "project_id is required"}), 400

    if not data or not data.get("documents") or len(data.get("documents")) == 0:
        return jsonify({"message": "No documents selected"}), 400

    try:
        # RaptorPipeline now takes project_id and handles persistence
        RaptorPipeline(current_user, data.get("documents"), project_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"message": str(e)}), 500

    return jsonify({"message": "Documents successfully Analysed"}), 200


@rag_bp.route('/ask', methods=['POST'])
@token_required
def raptor_ask(current_user):
    data = request.get_json()
    project_id = data.get("project_id")
    question = data.get("question")
    
    if not project_id:
        return jsonify({"message": "project_id is required"}), 400
    
    if not question:
        return jsonify({"message": "question is required"}), 400
        
    # Load the retriever for this project
    retriever = get_retriever(project_id)
    
    if retriever is not None:
        try:
            answer = asking_llm(retriever, question)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"message": f"Error asking Question: {str(e)}"}), 500
    else:
        return jsonify({"message": "No document Context for this project. Please analyse documents first."}), 404
    
    return jsonify({"message": "Success", "answer": answer}), 200
