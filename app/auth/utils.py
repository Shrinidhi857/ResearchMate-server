import re
import jwt
from datetime import datetime
from functools import wraps
from flask import request, jsonify, current_app
from app.models import User


def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password):
    return len(password) >= 8


def generate_token(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
    }
    return jwt.encode(payload, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')


def verify_token(token):
    try:
        payload = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
        return payload['user_id']
    except jwt.ExpiredSignatureError:
        print("DEBUG: Token expired")
        return None
    except jwt.InvalidTokenError as e:
        print(f"DEBUG: Invalid token error: {e}")
        return None


def token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        print(f"DEBUG: Auth Header: {auth_header}")

        if auth_header:
            try:
                token = auth_header.split(' ')[1]  # Bearer <token>
            except IndexError:
                print("DEBUG: Invalid token format")
                return jsonify({'error': 'Invalid token format'}), 401

        if not token:
            print("DEBUG: Token is missing")
            return jsonify({'error': 'Token is missing'}), 401

        user_id = verify_token(token)
        if user_id is None:
            print("DEBUG: Token verification returned None")
            return jsonify({'error': 'Token is invalid or expired'}), 401

        current_user = User.query.get(user_id)
        if not current_user:
            print(f"DEBUG: User not found for ID {user_id}")
            return jsonify({'error': 'User not found'}), 401

        return f(current_user, *args, **kwargs)

    return decorated_function