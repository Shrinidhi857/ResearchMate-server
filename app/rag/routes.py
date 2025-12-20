from flask import Blueprint, request, jsonify
from app.auth.utils import token_required
from rag.raptor import RaptorPipeline
from rag.raptor_middleman import asking_llm

rag_bp = Blueprint('rag', __name__)

# Global retriever instance
retriever = None


@rag_bp.route('/analyse', methods=['POST'])
@token_required
def raptor_analysis(current_user):
    global retriever
    retriever = None
    data = request.get_json()

    if not data or len(data) == 0:
        return jsonify({"message": "No document selected"}), 400

    try:
        retriever = RaptorPipeline(current_user, data)
    except Exception as e:
        return jsonify({"message": str(e)}), 500

    return jsonify({"message": "Document successfully Analysed"}), 200


@rag_bp.route('/ask', methods=['POST'])
@token_required
def raptor_ask(current_user):
    data = request.get_json()
    
    if retriever is not None:
        try:
            answer = asking_llm(retriever, data.get("question"))
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"message": f"Error asking Question: {str(e)}"}), 500
    else:
        return jsonify({"message": "No document Context"}), 500
    
    return jsonify({"message": "Success", "answer": answer}), 200