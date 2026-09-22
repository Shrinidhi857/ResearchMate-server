from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db, SessionLocal
from app.models.models import User
from app.auth.utils import get_current_admin_user

router = APIRouter(tags=["Admin"])
admin_bp = router

ADMIN_EMAIL = "shrinidhiachar857@gmail.com"


def initialize_admin():
    """Initialize admin user if not already set"""
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if admin_user and not admin_user.is_admin:
            admin_user.is_admin = True
            db.commit()
            print(f"✅ Admin initialized: {ADMIN_EMAIL}")
        elif admin_user and admin_user.is_admin:
            print(f"✅ Admin already set: {ADMIN_EMAIL}")
    except Exception as e:
        print(f"⚠️ Could not initialize admin: {e}")
    finally:
        db.close()


# ============================================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/users")
def get_all_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1),
    search: str = Query(""),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Fetch all users with pagination and filtering"""
    try:
        query = db.query(User)

        if search:
            query = query.filter(
                (User.email.ilike(f"%{search}%")) |
                (User.first_name.ilike(f"%{search}%")) |
                (User.last_name.ilike(f"%{search}%"))
            )

        total = query.count()
        pages = (total + per_page - 1) // per_page if per_page > 0 else 0
        users_items = query.offset((page - 1) * per_page).limit(per_page).all()
        users_data = [user.to_dict() for user in users_items]

        return JSONResponse(
            status_code=200,
            content={
                'users': users_data,
                'total': total,
                'pages': pages,
                'current_page': page,
                'per_page': per_page
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': f'Failed to fetch users: {str(e)}'})


@router.get("/users/{user_id}")
def get_user_details(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Fetch detailed user information including token usage"""
    try:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return JSONResponse(status_code=404, content={'error': 'User not found'})

        user_info = user.to_dict()
        user_info['projects_count'] = len(user.projects) if hasattr(user, 'projects') and user.projects else 0
        user_info['documents_count'] = len(user.documents) if hasattr(user, 'documents') and user.documents else 0
        user_info['sessions_count'] = len(user.sessions) if hasattr(user, 'sessions') and user.sessions else 0

        return JSONResponse(status_code=200, content={'user': user_info})
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': f'Failed to fetch user details: {str(e)}'})


# ============================================================================
# TOKEN MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/users/{user_id}/tokens")
def get_user_tokens(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get token usage for a specific user"""
    try:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return JSONResponse(status_code=404, content={'error': 'User not found'})

        return JSONResponse(
            status_code=200,
            content={
                'user_id': user_id,
                'email': user.email,
                'tokens': user.tokens,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'last_updated': user.updated_at.isoformat() if user.updated_at else None
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': f'Failed to fetch token info: {str(e)}'})


@router.post("/users/{user_id}/tokens/add")
async def add_user_tokens(
    user_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Add tokens to a user account"""
    try:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return JSONResponse(status_code=404, content={'error': 'User not found'})

        try:
            data = await request.json()
        except Exception:
            data = {}

        amount = data.get('amount', 0)
        reason = data.get('reason', 'Admin token addition')

        if not isinstance(amount, int) or amount <= 0:
            return JSONResponse(status_code=400, content={'error': 'Amount must be a positive integer'})

        previous_tokens = user.tokens
        user.add_tokens(amount)
        user.updated_at = datetime.utcnow()
        db.commit()

        return JSONResponse(
            status_code=200,
            content={
                'message': f'Added {amount} tokens to {user.email}',
                'user_id': user_id,
                'previous_tokens': previous_tokens,
                'new_tokens': user.tokens,
                'amount_added': amount,
                'reason': reason
            }
        )
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={'error': f'Failed to add tokens: {str(e)}'})


@router.post("/users/{user_id}/tokens/deduct")
async def deduct_user_tokens(
    user_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Deduct tokens from a user account"""
    try:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return JSONResponse(status_code=404, content={'error': 'User not found'})

        try:
            data = await request.json()
        except Exception:
            data = {}

        amount = data.get('amount', 0)
        reason = data.get('reason', 'Admin token deduction')

        if not isinstance(amount, int) or amount <= 0:
            return JSONResponse(status_code=400, content={'error': 'Amount must be a positive integer'})

        previous_tokens = user.tokens
        success = user.deduct_tokens(amount)

        if not success:
            return JSONResponse(
                status_code=400,
                content={'error': f'Insufficient tokens. User has {user.tokens} but requested {amount}'}
            )

        user.updated_at = datetime.utcnow()
        db.commit()

        return JSONResponse(
            status_code=200,
            content={
                'message': f'Deducted {amount} tokens from {user.email}',
                'user_id': user_id,
                'previous_tokens': previous_tokens,
                'new_tokens': user.tokens,
                'amount_deducted': amount,
                'reason': reason
            }
        )
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={'error': f'Failed to deduct tokens: {str(e)}'})


@router.post("/users/{user_id}/tokens/set")
async def set_user_tokens(
    user_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Set tokens to a specific amount"""
    try:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return JSONResponse(status_code=404, content={'error': 'User not found'})

        try:
            data = await request.json()
        except Exception:
            data = {}

        amount = data.get('amount', 0)
        reason = data.get('reason', 'Admin token reset')

        if not isinstance(amount, int) or amount < 0:
            return JSONResponse(status_code=400, content={'error': 'Amount must be a non-negative integer'})

        previous_tokens = user.tokens
        user.tokens = amount
        user.updated_at = datetime.utcnow()
        db.commit()

        return JSONResponse(
            status_code=200,
            content={
                'message': f'Set tokens to {amount} for {user.email}',
                'user_id': user_id,
                'previous_tokens': previous_tokens,
                'new_tokens': user.tokens,
                'reason': reason
            }
        )
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={'error': f'Failed to set tokens: {str(e)}'})


# ============================================================================
# ANALYTICS & INSIGHTS ENDPOINTS
# ============================================================================

@router.get("/analytics")
def get_analytics(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get overall platform analytics"""
    try:
        total_users = db.query(User).count()
        verified_users = db.query(User).filter(User.is_verified.is_(True)).count()
        admin_users = db.query(User).filter(User.is_admin.is_(True)).count()

        total_tokens = db.query(func.sum(User.tokens)).scalar() or 0
        avg_tokens = db.query(func.avg(User.tokens)).scalar() or 0

        recent_users = db.query(User).order_by(User.created_at.desc()).limit(5).all()

        return JSONResponse(
            status_code=200,
            content={
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
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': f'Failed to fetch analytics: {str(e)}'})


@router.get("/token-usage-report")
def get_token_usage_report(
    sort_by: str = Query('tokens'),
    order: str = Query('desc'),
    limit: int = Query(100),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get detailed token usage report"""
    try:
        query = db.query(User)

        if sort_by == 'tokens':
            query = query.order_by(User.tokens.desc() if order == 'desc' else User.tokens.asc())
        elif sort_by == 'email':
            query = query.order_by(User.email.asc() if order == 'asc' else User.email.desc())
        elif sort_by == 'created_at':
            query = query.order_by(User.created_at.desc() if order == 'desc' else User.created_at.asc())

        users = query.limit(limit).all()

        report = {
            'total_users_in_report': len(users),
            'total_tokens': sum(u.tokens for u in users if u.tokens),
            'average_tokens': round(sum(u.tokens for u in users if u.tokens) / len(users), 2) if users else 0,
            'users': [
                {
                    'id': u.id,
                    'email': u.email,
                    'tokens': u.tokens,
                    'is_verified': u.is_verified,
                    'is_admin': u.is_admin,
                    'created_at': u.created_at.isoformat() if u.created_at else None
                }
                for u in users
            ],
            'generated_at': datetime.utcnow().isoformat()
        }

        return JSONResponse(status_code=200, content=report)
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': f'Failed to generate report: {str(e)}'})


# ============================================================================
# USER MANAGEMENT (Verification, Roles, etc.)
# ============================================================================

@router.post("/users/{user_id}/verify")
def verify_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Manually verify a user"""
    try:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return JSONResponse(status_code=404, content={'error': 'User not found'})

        user.is_verified = True
        user.updated_at = datetime.utcnow()
        db.commit()

        return JSONResponse(
            status_code=200,
            content={
                'message': f'User {user.email} verified',
                'user': user.to_dict()
            }
        )
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={'error': f'Failed to verify user: {str(e)}'})


@router.post("/users/{user_id}/grant-admin")
def grant_admin(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Grant admin access to a user"""
    try:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return JSONResponse(status_code=404, content={'error': 'User not found'})

        user.is_admin = True
        user.updated_at = datetime.utcnow()
        db.commit()

        return JSONResponse(
            status_code=200,
            content={
                'message': f'Admin access granted to {user.email}',
                'user': user.to_dict()
            }
        )
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={'error': f'Failed to grant admin: {str(e)}'})


@router.post("/users/{user_id}/revoke-admin")
def revoke_admin(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Revoke admin access from a user"""
    try:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return JSONResponse(status_code=404, content={'error': 'User not found'})

        if user.email == ADMIN_EMAIL:
            return JSONResponse(status_code=403, content={'error': 'Cannot revoke admin from primary admin account'})

        user.is_admin = False
        user.updated_at = datetime.utcnow()
        db.commit()

        return JSONResponse(
            status_code=200,
            content={
                'message': f'Admin access revoked from {user.email}',
                'user': user.to_dict()
            }
        )
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={'error': f'Failed to revoke admin: {str(e)}'})


@router.delete("/users/{user_id}/delete")
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Delete a user account"""
    try:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return JSONResponse(status_code=404, content={'error': 'User not found'})

        if user.email == ADMIN_EMAIL:
            return JSONResponse(status_code=403, content={'error': 'Cannot delete primary admin account'})

        email = user.email
        db.delete(user)
        db.commit()

        return JSONResponse(status_code=200, content={'message': f'User {email} deleted successfully'})
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={'error': f'Failed to delete user: {str(e)}'})


@router.get("/info")
def get_admin_info(current_user: User = Depends(get_current_admin_user)):
    """Get admin information and available endpoints"""
    return JSONResponse(
        status_code=200,
        content={
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
        }
    )
