from flask import Blueprint, request, jsonify
from datetime import datetime
from app.extensions import db
from app.models import User
from app.auth.utils import admin_required
from sqlalchemy import func

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

# Admin email - set this as admin
ADMIN_EMAIL = "shrinidhiachar857@gmail.com"


@admin_bp.before_request
def handle_preflight():
    """Handle CORS preflight requests"""
    if request.method == "OPTIONS":
        response = jsonify({'status': 'ok'})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
        response.headers.add("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        return response, 200


def initialize_admin():
    """Initialize admin user if not already set"""
    try:
        admin_user = User.query.filter_by(email=ADMIN_EMAIL).first()
        if admin_user and not admin_user.is_admin:
            admin_user.is_admin = True
            db.session.commit()
            print(f"✅ Admin initialized: {ADMIN_EMAIL}")
        elif admin_user and admin_user.is_admin:
            print(f"✅ Admin already set: {ADMIN_EMAIL}")
    except Exception as e:
        print(f"⚠️ Could not initialize admin: {e}")


# ============================================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================================

@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_all_users(current_user):
    """Fetch all users with pagination and filtering"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '', type=str)
        
        query = User.query
        
        # Search by email or name
        if search:
            query = query.filter(
                (User.email.ilike(f"%{search}%")) |
                (User.first_name.ilike(f"%{search}%")) |
                (User.last_name.ilike(f"%{search}%"))
            )
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        users_data = [user.to_dict() for user in pagination.items]
        
        return jsonify({
            'users': users_data,
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page,
            'per_page': per_page
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to fetch users: {str(e)}'}), 500


@admin_bp.route('/users/<int:user_id>', methods=['GET'])
@admin_required
def get_user_details(current_user, user_id):
    """Fetch detailed user information including token usage"""
    try:
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user_info = user.to_dict()
        user_info['projects_count'] = len(user.projects) if hasattr(user, 'projects') else 0
        user_info['documents_count'] = len(user.documents) if hasattr(user, 'documents') else 0
        user_info['sessions_count'] = len(user.sessions) if hasattr(user, 'sessions') else 0
        
        return jsonify({
            'user': user_info
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to fetch user details: {str(e)}'}), 500


# ============================================================================
# TOKEN MANAGEMENT ENDPOINTS
# ============================================================================

@admin_bp.route('/users/<int:user_id>/tokens', methods=['GET'])
@admin_required
def get_user_tokens(current_user, user_id):
    """Get token usage for a specific user"""
    try:
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'user_id': user_id,
            'email': user.email,
            'tokens': user.tokens,
            'created_at': user.created_at.isoformat(),
            'last_updated': user.updated_at.isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to fetch token info: {str(e)}'}), 500


@admin_bp.route('/users/<int:user_id>/tokens/add', methods=['POST'])
@admin_required
def add_user_tokens(current_user, user_id):
    """Add tokens to a user account"""
    try:
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        amount = data.get('amount', 0)
        reason = data.get('reason', 'Admin token addition')
        
        if not isinstance(amount, int) or amount <= 0:
            return jsonify({'error': 'Amount must be a positive integer'}), 400
        
        previous_tokens = user.tokens
        user.add_tokens(amount)
        user.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': f'Added {amount} tokens to {user.email}',
            'user_id': user_id,
            'previous_tokens': previous_tokens,
            'new_tokens': user.tokens,
            'amount_added': amount,
            'reason': reason
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to add tokens: {str(e)}'}), 500


@admin_bp.route('/users/<int:user_id>/tokens/deduct', methods=['POST'])
@admin_required
def deduct_user_tokens(current_user, user_id):
    """Deduct tokens from a user account"""
    try:
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        amount = data.get('amount', 0)
        reason = data.get('reason', 'Admin token deduction')
        
        if not isinstance(amount, int) or amount <= 0:
            return jsonify({'error': 'Amount must be a positive integer'}), 400
        
        previous_tokens = user.tokens
        success = user.deduct_tokens(amount)
        
        if not success:
            return jsonify({
                'error': f'Insufficient tokens. User has {user.tokens} but requested {amount}'
            }), 400
        
        user.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': f'Deducted {amount} tokens from {user.email}',
            'user_id': user_id,
            'previous_tokens': previous_tokens,
            'new_tokens': user.tokens,
            'amount_deducted': amount,
            'reason': reason
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to deduct tokens: {str(e)}'}), 500


@admin_bp.route('/users/<int:user_id>/tokens/set', methods=['POST'])
@admin_required
def set_user_tokens(current_user, user_id):
    """Set tokens to a specific amount"""
    try:
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        amount = data.get('amount', 0)
        reason = data.get('reason', 'Admin token reset')
        
        if not isinstance(amount, int) or amount < 0:
            return jsonify({'error': 'Amount must be a non-negative integer'}), 400
        
        previous_tokens = user.tokens
        user.tokens = amount
        user.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': f'Set tokens to {amount} for {user.email}',
            'user_id': user_id,
            'previous_tokens': previous_tokens,
            'new_tokens': user.tokens,
            'reason': reason
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to set tokens: {str(e)}'}), 500


# ============================================================================
# ANALYTICS & INSIGHTS ENDPOINTS
# ============================================================================

@admin_bp.route('/analytics', methods=['GET'])
@admin_required
def get_analytics(current_user):
    """Get overall platform analytics"""
    try:
        total_users = User.query.count()
        verified_users = User.query.filter_by(is_verified=True).count()
        admin_users = User.query.filter_by(is_admin=True).count()
        
        # Token statistics
        total_tokens = db.session.query(func.sum(User.tokens)).scalar() or 0
        avg_tokens = db.session.query(func.avg(User.tokens)).scalar() or 0
        
        # Most recent users
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        
        return jsonify({
            'summary': {
                'total_users': total_users,
                'verified_users': verified_users,
                'admin_users': admin_users,
                'unverified_users': total_users - verified_users
            },
            'token_stats': {
                'total_tokens_issued': int(total_tokens),
                'average_tokens_per_user': round(float(avg_tokens), 2),
                'total_token_pool': int(total_tokens)
            },
            'recent_users': [user.to_dict() for user in recent_users],
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to fetch analytics: {str(e)}'}), 500


@admin_bp.route('/token-usage-report', methods=['GET'])
@admin_required
def get_token_usage_report(current_user):
    """Get detailed token usage report"""
    try:
        sort_by = request.args.get('sort_by', 'tokens', type=str)  # tokens, email, created_at
        order = request.args.get('order', 'desc', type=str)  # asc, desc
        limit = request.args.get('limit', 100, type=int)
        
        query = User.query
        
        if sort_by == 'tokens':
            query = query.order_by(User.tokens.desc() if order == 'desc' else User.tokens.asc())
        elif sort_by == 'email':
            query = query.order_by(User.email.asc() if order == 'asc' else User.email.desc())
        elif sort_by == 'created_at':
            query = query.order_by(User.created_at.desc() if order == 'desc' else User.created_at.asc())
        
        users = query.limit(limit).all()
        
        report = {
            'total_users_in_report': len(users),
            'total_tokens': sum(u.tokens for u in users),
            'average_tokens': round(sum(u.tokens for u in users) / len(users), 2) if users else 0,
            'users': [
                {
                    'id': u.id,
                    'email': u.email,
                    'tokens': u.tokens,
                    'is_verified': u.is_verified,
                    'is_admin': u.is_admin,
                    'created_at': u.created_at.isoformat()
                }
                for u in users
            ],
            'generated_at': datetime.utcnow().isoformat()
        }
        
        return jsonify(report), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to generate report: {str(e)}'}), 500


# ============================================================================
# USER MANAGEMENT (Verification, Roles, etc.)
# ============================================================================

@admin_bp.route('/users/<int:user_id>/verify', methods=['POST'])
@admin_required
def verify_user(current_user, user_id):
    """Manually verify a user"""
    try:
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user.is_verified = True
        user.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': f'User {user.email} verified',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to verify user: {str(e)}'}), 500


@admin_bp.route('/users/<int:user_id>/grant-admin', methods=['POST'])
@admin_required
def grant_admin(current_user, user_id):
    """Grant admin access to a user"""
    try:
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user.is_admin = True
        user.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': f'Admin access granted to {user.email}',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to grant admin: {str(e)}'}), 500


@admin_bp.route('/users/<int:user_id>/revoke-admin', methods=['POST'])
@admin_required
def revoke_admin(current_user, user_id):
    """Revoke admin access from a user"""
    try:
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if user.email == ADMIN_EMAIL:
            return jsonify({'error': 'Cannot revoke admin from primary admin account'}), 403
        
        user.is_admin = False
        user.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': f'Admin access revoked from {user.email}',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to revoke admin: {str(e)}'}), 500


@admin_bp.route('/users/<int:user_id>/delete', methods=['DELETE'])
@admin_required
def delete_user(current_user, user_id):
    """Delete a user account"""
    try:
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if user.email == ADMIN_EMAIL:
            return jsonify({'error': 'Cannot delete primary admin account'}), 403
        
        email = user.email
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({
            'message': f'User {email} deleted successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to delete user: {str(e)}'}), 500


# ============================================================================
# ADMIN INFO ENDPOINT
# ============================================================================

@admin_bp.route('/info', methods=['GET'])
@admin_required
def get_admin_info(current_user):
    """Get admin information and available endpoints"""
    return jsonify({
        'admin': current_user.to_dict(),
        'admin_email_configured': ADMIN_EMAIL,
        'available_endpoints': {
            'user_management': {
                'GET /admin/users': 'Fetch all users with pagination',
                'GET /admin/users/<user_id>': 'Get specific user details',
                'POST /admin/users/<user_id>/verify': 'Verify a user',
                'POST /admin/users/<user_id>/grant-admin': 'Grant admin access',
                'POST /admin/users/<user_id>/revoke-admin': 'Revoke admin access',
                'DELETE /admin/users/<user_id>/delete': 'Delete a user'
            },
            'token_management': {
                'GET /admin/users/<user_id>/tokens': 'Get user token balance',
                'POST /admin/users/<user_id>/tokens/add': 'Add tokens to user',
                'POST /admin/users/<user_id>/tokens/deduct': 'Deduct tokens from user',
                'POST /admin/users/<user_id>/tokens/set': 'Set token balance'
            },
            'analytics': {
                'GET /admin/analytics': 'Get platform analytics',
                'GET /admin/token-usage-report': 'Get token usage report'
            }
        }
    }), 200
