from flask import Blueprint, request, jsonify
from datetime import datetime
from app.auth.utils import token_required
from service.web_searcher import getUserInput
from service.web_scraper import researchPipeline

scraper_bp = Blueprint('scraper', __name__)


@scraper_bp.route('/getlinks', methods=['POST'])
@token_required
def askai_route(current_user):
    data = request.get_json()
    
    if not data or "prompt" not in data:
        return jsonify({"error": "Prompt is required"}), 400
    
    try:
        result = getUserInput(data['prompt'])
        return jsonify({
            "message": f"Hello {current_user.first_name or current_user.email}!",
            "user_id": current_user.id,
            "timestamp": datetime.utcnow().isoformat(),
            "result": result
        }), 200   
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@scraper_bp.route('/scraper', methods=['POST'])
@token_required
def scraper_route(current_user):
    data = request.get_json()
    
    if not data or "answers" not in data:
        return jsonify({"error": "Answers are required"}), 400

    try:
        topic = " ".join([f"{k}: {v}" for k, v in data["answers"].items()])
        extracted_texts, links = researchPipeline(topic)

        return jsonify({
            "message": f"Hello {current_user.first_name}!",
            "user_id": current_user.id,
            "timestamp": datetime.utcnow().isoformat(),
            "topic": topic,
            "links": links,
            "documents": extracted_texts
        }), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500