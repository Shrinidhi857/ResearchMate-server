from flask import Blueprint, jsonify
from datetime import datetime
from app.auth.utils import token_required

users_bp = Blueprint('users', __name__)


@users_bp.route("/user", methods=["GET"])
@token_required
def get_user(current_user):
    """
    Get current user profile with token information
    
    Response:
    {
        "id": 1,
        "email": "user@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "is_verified": true,
        "tokens": 30000,
        "tokens_formatted": "30,000",
        "created_at": "2025-05-26T..."
    }
    """
    try:
        return jsonify({
            "id": current_user.id,
            "email": current_user.email,
            "first_name": current_user.first_name if hasattr(current_user, "first_name") else None,
            "last_name": current_user.last_name if hasattr(current_user, "last_name") else None,
            "is_verified": current_user.is_verified,
            "tokens": current_user.tokens,
            "tokens_formatted": f"{current_user.tokens:,}",
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@users_bp.route("/tokens", methods=["GET"])
@token_required
def get_tokens(current_user):
    """
    Get detailed token information for current user
    
    Response:
    {
        "tokens": 30000,
        "tokens_formatted": "30,000",
        "message": "Your current token balance"
    }
    """
    try:
        return jsonify({
            "tokens": current_user.tokens,
            "tokens_formatted": f"{current_user.tokens:,}",
            "message": f"Your current token balance is {current_user.tokens:,}"
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@users_bp.route("/tokens/check", methods=["POST"])
@token_required
def check_tokens(current_user):
    """
    Check if user has enough tokens for an operation
    
    Request JSON:
    {
        "required_tokens": 1000
    }
    
    Response:
    {
        "has_enough": true,
        "current_tokens": 30000,
        "required_tokens": 1000,
        "remaining_after_deduction": 29000
    }
    """
    from flask import request
    try:
        data = request.get_json(force=True, silent=True) or {}
        required_tokens = data.get("required_tokens", 0)
        
        if required_tokens < 0:
            return jsonify({"error": "required_tokens must be positive"}), 400
        
        has_enough = current_user.tokens >= required_tokens
        remaining = current_user.tokens - required_tokens if has_enough else 0
        
        return jsonify({
            "has_enough": has_enough,
            "current_tokens": current_user.tokens,
            "required_tokens": required_tokens,
            "remaining_after_deduction": remaining
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