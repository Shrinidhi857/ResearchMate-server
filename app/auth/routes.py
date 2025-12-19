from flask import Blueprint, request, jsonify, url_for, redirect, current_app
from datetime import datetime
from app.extensions import db, oauth
from app.models import User, UserSession
from app.auth.utils import (
    validate_email, 
    validate_password, 
    generate_token, 
    token_required
)

auth_bp = Blueprint('auth', __name__)

# Register Google OAuth
google = oauth.register(
    name='google',
    client_id=None,  # Will be set from config
    client_secret=None,  # Will be set from config
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)


@auth_bp.record
def record_params(setup_state):
    """Initialize Google OAuth with config values"""
    app = setup_state.app
    google.client_id = app.config['GOOGLE_CLIENT_ID']
    google.client_secret = app.config['GOOGLE_CLIENT_SECRET']


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    email = data.get('email', '').lower().strip()
    password = data.get('password', '')
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    
    if not email or not validate_email(email):
        return jsonify({'error': 'Valid email is required'}), 400
    
    if not password or not validate_password(password):
        return jsonify({'error': 'Password must be at least 8 characters long'}), 400
    
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({'error': 'User with this email already exists'}), 409
    
    try:
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_verified=False
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        token = generate_token(user.id)
        
        session_record = UserSession(
            user_id=user.id,
            token=token,
            expires_at=datetime.utcnow() + current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
        )
        db.session.add(session_record)
        db.session.commit()
        
        return jsonify({
            'message': 'User registered successfully',
            'token': token,
            'user': user.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Registration failed'}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    email = data.get('email', '').lower().strip()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400
    
    try:
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        token = generate_token(user.id)
        
        session_record = UserSession(
            user_id=user.id,
            token=token,
            expires_at=datetime.utcnow() + current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
        )
        db.session.add(session_record)
        db.session.commit()
        
        return jsonify({
            'message': 'Login successful',
            'token': token,
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Login failed'}), 500


@auth_bp.route('/google')
def google_auth():
    redirect_uri = url_for('auth.google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)


@auth_bp.route('/google/callback')
def google_callback():
    try:
        frontend_url = current_app.config['FRONTEND_URL']
        token = google.authorize_access_token()

        resp = google.get("https://www.googleapis.com/oauth2/v3/userinfo")
        user_info = resp.json()
                    
        if not user_info:
            return jsonify({'error': 'Failed to get user info from Google'}), 400
        
        email = user_info.get('email')
        google_id = user_info.get('sub')
        first_name = user_info.get('given_name', '')
        last_name = user_info.get('family_name', '')
        
        user = User.query.filter_by(email=email).first()
        
        if not user:
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                google_id=google_id,
                is_verified=True
            )
            db.session.add(user)
        else:
            if not user.google_id:
                user.google_id = google_id
                user.is_verified = True
        
        db.session.commit()
        
        jwt_token = generate_token(user.id)
        
        session_record = UserSession(
            user_id=user.id,
            token=jwt_token,
            expires_at=datetime.utcnow() + current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
        )
        db.session.add(session_record)
        db.session.commit()
        
        return redirect(f"{frontend_url}/auth/success?token={jwt_token}")
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Google authentication failed: {str(e)}'}), 500


@auth_bp.route('/logout', methods=['POST'])
@token_required
def logout(current_user):
    try:
        auth_header = request.headers.get('Authorization')
        if auth_header:
            token = auth_header.split(' ')[1]
            
            session_record = UserSession.query.filter_by(token=token).first()
            if session_record:
                db.session.delete(session_record)
                db.session.commit()
        
        return jsonify({'message': 'Logged out successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': 'Logout failed'}), 500


@auth_bp.route('/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    return jsonify({'user': current_user.to_dict()}), 200


@auth_bp.route('/profile', methods=['PUT'])
@token_required
def update_profile(current_user):
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    try:
        if 'first_name' in data:
            current_user.first_name = data['first_name'].strip()
        if 'last_name' in data:
            current_user.last_name = data['last_name'].strip()
        
        current_user.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': 'Profile updated successfully',
            'user': current_user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Profile update failed'}), 500


@auth_bp.route('/change-password', methods=['POST'])
@token_required
def change_password(current_user):
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    
    if not current_password or not new_password:
        return jsonify({'error': 'Current password and new password are required'}), 400
    
    if not validate_password(new_password):
        return jsonify({'error': 'New password must be at least 8 characters long'}), 400
    
    try:
        if not current_user.check_password(current_password):
            return jsonify({'error': 'Current password is incorrect'}), 401
        
        current_user.set_password(new_password)
        current_user.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Password change failed'}), 500