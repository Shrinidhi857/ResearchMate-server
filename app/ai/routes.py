from flask import Blueprint, request, jsonify, Response
from app.auth.utils import token_required
from service.auto_site import auto_cite_paragraph
import time
import json

ai_bp = Blueprint('ai', __name__)


@ai_bp.route('/summarize', methods=['POST'])
@token_required
def summarize_api(current_user):
    """API endpoint to summarize research paper text into structured JSON"""
    data = request.get_json()

    if not data or 'text' not in data:
        return jsonify({"message": "Missing 'text' in request body"}), 400

    result = summarize_research_paper(data['text'])

    if result["success"]:
        return jsonify({"message": "Success", "summary": result["data"]}), 200
    elif "raw_output" in result:
        return jsonify({
            "message": "Model did not return perfect JSON",
            "raw_output": result["raw_output"]
        }), 200
    else:
        return jsonify({"message": f"Error: {result['error']}"}), 500

""" 
@ai_bp.route('/ieee-ref', methods=['POST'])
@token_required
def generate_ieee_reference(current_user):
    try:
        data = request.get_json()

        if not isinstance(data, list) or len(data) == 0:
            return jsonify({
                "success": False,
                "message": "Request body must be a non-empty list"
            }), 400

        first_item = data[0]

        if 'doc_id' not in first_item:
            return jsonify({
                "success": False,
                "message": "Missing 'doc_id' in the first object"
            }), 400

        doc_id = first_item['doc_id']
        result = generate_ieee_reference_for_doc(current_user, doc_id)

        return result """
""" 
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": "Server error while generating IEEE reference",
            "error": str(e)
        }), 500 """

""" 
@ai_bp.route('/generate_reference/<string:doc_id>', methods=['POST'])
@token_required
def generate_reference(current_user, doc_id):
    return generate_ieee_reference_for_doc(current_user, doc_id)


@ai_bp.route('/auto_cite', methods=['POST'])
@token_required
def auto_cite_endpoint(current_user):
    try:
        data = request.get_json()
        paragraph = data.get("paragraph", "")
        references = data.get("references", {})

        if not paragraph or not references:
            return jsonify({"message": "Missing paragraph or references"}), 400

        result = auto_cite_paragraph(paragraph, references)

        return jsonify({
            "message": "Success",
            "cited_paragraph": result
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"message": f"Error: {str(e)}"}), 500

 """
@ai_bp.route('/test', methods=['GET'])
def test_stream():
    def generate():
        for i in range(5):
            msg = {"phase": i + 1, "status": "running", "message": f"Processing phase {i + 1}..."}
            yield f"data: {json.dumps(msg)}\n\n"
            time.sleep(1)
        yield f"data: {json.dumps({'phase': 6, 'status': 'complete', 'message': '✅ Test stream finished successfully!'})}\n\n"

    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Connection'] = 'keep-alive'
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


@ai_bp.route('/start', methods=['POST'])
def start_analysis():
    data = request.json
    print("Received from frontend:", data)
    return {"status": "ok", "message": "Processing started!"}