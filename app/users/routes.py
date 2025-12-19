from flask import Blueprint, jsonify
from datetime import datetime
from app.auth.utils import token_required

users_bp = Blueprint('users', __name__)


@users_bp.route("/user", methods=["GET"])
@token_required
def get_user(current_user):
    try:
        return jsonify({
            "id": current_user.id,
            "email": current_user.email,
            "first_name": current_user.first_name if hasattr(current_user, "first_name") else None,
            "last_name": current_user.last_name if hasattr(current_user, "last_name") else None
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@users_bp.route('/protected', methods=['GET'])
@token_required
def protected_route(current_user):
    return jsonify({
        'message': f'Hello {current_user.first_name or current_user.email}!',
        'user_id': current_user.id,
        'timestamp': datetime.utcnow().isoformat()
    }), 200