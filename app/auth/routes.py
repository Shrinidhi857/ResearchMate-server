from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import urllib.parse
import requests

from app.database import get_db
from app.config import Config
from app.models.models import User, UserSession
from app.auth.utils import (
    validate_email,
    validate_password,
    generate_token,
    get_current_user
)

router = APIRouter(tags=["Auth"])
auth_bp = router


@router.post("/register")
async def register(request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
    except Exception:
        data = None

    if not data:
        return JSONResponse(status_code=400, content={'error': 'No data provided'})

    email = data.get('email', '').lower().strip()
    password = data.get('password', '')
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()

    if not email or not validate_email(email):
        return JSONResponse(status_code=400, content={'error': 'Valid email is required'})

    if not password or not validate_password(password):
        return JSONResponse(status_code=400, content={'error': 'Password must be at least 8 characters long'})

    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        return JSONResponse(status_code=409, content={'error': 'User with this email already exists'})

    try:
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_verified=False
        )
        user.set_password(password)
        user.add_tokens(30000)  # Award 30k tokens to new user

        db.add(user)
        db.commit()
        db.refresh(user)

        token = generate_token(user.id)

        session_record = UserSession(
            user_id=user.id,
            token=token,
            expires_at=datetime.utcnow() + Config.JWT_ACCESS_TOKEN_EXPIRES
        )
        db.add(session_record)
        db.commit()

        return JSONResponse(
            status_code=201,
            content={
                'message': 'User registered successfully',
                'token': token,
                'user': user.to_dict()
            }
        )

    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={'error': f'Registration failed: {str(e)}'})


@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
    except Exception:
        data = None

    if not data:
        return JSONResponse(status_code=400, content={'error': 'No data provided'})

    email = data.get('email', '').lower().strip()
    password = data.get('password', '')

    if not email or not password:
        return JSONResponse(status_code=400, content={'error': 'Email and password are required'})

    try:
        user = db.query(User).filter(User.email == email).first()

        if not user or not user.check_password(password):
            return JSONResponse(status_code=401, content={'error': 'Invalid credentials'})

        token = generate_token(user.id)

        session_record = UserSession(
            user_id=user.id,
            token=token,
            expires_at=datetime.utcnow() + Config.JWT_ACCESS_TOKEN_EXPIRES
        )
        db.add(session_record)
        db.commit()

        return JSONResponse(
            status_code=200,
            content={
                'message': 'Login successful',
                'token': token,
                'user': user.to_dict()
            }
        )

    except Exception as e:
        return JSONResponse(status_code=500, content={'error': f'Login failed: {str(e)}'})


@router.get("/google")
def google_auth(request: Request):
    client_id = Config.GOOGLE_CLIENT_ID
    if not client_id:
        raise HTTPException(status_code=500, detail="Google Client ID not configured")

    base_url = str(request.base_url).rstrip('/')
    redirect_uri = f"{base_url}/auth/google/callback"
    
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account"
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=url)


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        if error:
            return JSONResponse(status_code=400, content={'error': f'Google OAuth error: {error}'})
        if not code:
            return JSONResponse(status_code=400, content={'error': 'Missing authorization code'})

        frontend_url = Config.FRONTEND_URL
        base_url = str(request.base_url).rstrip('/')
        redirect_uri = f"{base_url}/auth/google/callback"

        # Exchange authorization code for token
        token_resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": Config.GOOGLE_CLIENT_ID,
                "client_secret": Config.GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10
        )
        token_json = token_resp.json()
        access_token = token_json.get("access_token")
        if not access_token:
            return JSONResponse(status_code=400, content={'error': 'Failed to obtain access token from Google'})

        # Fetch user info
        userinfo_resp = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        user_info = userinfo_resp.json()
        if not user_info:
            return JSONResponse(status_code=400, content={'error': 'Failed to get user info from Google'})

        email = user_info.get('email')
        google_id = user_info.get('sub')
        first_name = user_info.get('given_name', '')
        last_name = user_info.get('family_name', '')

        user = db.query(User).filter(User.email == email).first()

        if not user:
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                google_id=google_id,
                is_verified=True
            )
            user.add_tokens(30000)  # Award 30k tokens to new Google user
            db.add(user)
        else:
            if not user.google_id:
                user.google_id = google_id
                user.is_verified = True

        db.commit()
        db.refresh(user)

        jwt_token = generate_token(user.id)

        session_record = UserSession(
            user_id=user.id,
            token=jwt_token,
            expires_at=datetime.utcnow() + Config.JWT_ACCESS_TOKEN_EXPIRES
        )
        db.add(session_record)
        db.commit()

        return RedirectResponse(f"{frontend_url}/auth/success?token={jwt_token}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={'error': f'Google authentication failed: {str(e)}'})


@router.post("/logout")
def logout(
    authorization: Optional[str] = Header(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        if authorization:
            parts = authorization.split(' ')
            token = parts[1] if len(parts) > 1 else parts[0]
            session_record = db.query(UserSession).filter(UserSession.token == token).first()
            if session_record:
                db.delete(session_record)
                db.commit()

        return JSONResponse(status_code=200, content={'message': 'Logged out successfully'})

    except Exception as e:
        return JSONResponse(status_code=500, content={'error': f'Logout failed: {str(e)}'})


@router.get("/profile")
def get_profile(current_user: User = Depends(get_current_user)):
    return JSONResponse(status_code=200, content={'user': current_user.to_dict()})


@router.put("/profile")
async def update_profile(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        data = await request.json()
    except Exception:
        data = None

    if not data:
        return JSONResponse(status_code=400, content={'error': 'No data provided'})

    try:
        if 'first_name' in data and data['first_name'] is not None:
            current_user.first_name = data['first_name'].strip()
        if 'last_name' in data and data['last_name'] is not None:
            current_user.last_name = data['last_name'].strip()

        current_user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(current_user)

        return JSONResponse(
            status_code=200,
            content={
                'message': 'Profile updated successfully',
                'user': current_user.to_dict()
            }
        )

    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={'error': f'Profile update failed: {str(e)}'})


@router.post("/change-password")
async def change_password(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        data = await request.json()
    except Exception:
        data = None

    if not data:
        return JSONResponse(status_code=400, content={'error': 'No data provided'})

    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_password or not new_password:
        return JSONResponse(status_code=400, content={'error': 'Current password and new password are required'})

    if not validate_password(new_password):
        return JSONResponse(status_code=400, content={'error': 'New password must be at least 8 characters long'})

    try:
        if not current_user.check_password(current_password):
            return JSONResponse(status_code=401, content={'error': 'Current password is incorrect'})

        current_user.set_password(new_password)
        current_user.updated_at = datetime.utcnow()
        db.commit()

        return JSONResponse(status_code=200, content={'message': 'Password changed successfully'})

    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={'error': f'Password change failed: {str(e)}'})