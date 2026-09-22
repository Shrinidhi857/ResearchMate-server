from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from datetime import datetime
from app.models.models import User
from app.auth.utils import get_current_user

router = APIRouter(tags=["Users"])
users_bp = router


@router.get("/user")
def get_user(current_user: User = Depends(get_current_user)):
    """
    Get current user profile with token information
    """
    try:
        tokens_val = current_user.tokens if current_user.tokens is not None else 0
        return JSONResponse(
            status_code=200,
            content={
                "id": current_user.id,
                "email": current_user.email,
                "first_name": current_user.first_name,
                "last_name": current_user.last_name,
                "is_verified": current_user.is_verified,
                "tokens": tokens_val,
                "tokens_formatted": f"{tokens_val:,}",
                "created_at": current_user.created_at.isoformat() if current_user.created_at else None
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/tokens")
def get_tokens(current_user: User = Depends(get_current_user)):
    """
    Get detailed token information for current user
    """
    try:
        tokens_val = current_user.tokens if current_user.tokens is not None else 0
        return JSONResponse(
            status_code=200,
            content={
                "tokens": tokens_val,
                "tokens_formatted": f"{tokens_val:,}",
                "message": f"Your current token balance is {tokens_val:,}"
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/tokens/check")
async def check_tokens(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Check if user has enough tokens for an operation
    """
    try:
        try:
            data = await request.json()
        except Exception:
            data = {}

        required_tokens = data.get("required_tokens", 0)

        if required_tokens < 0:
            return JSONResponse(status_code=400, content={"error": "required_tokens must be positive"})

        user_tokens = current_user.tokens if current_user.tokens is not None else 0
        has_enough = user_tokens >= required_tokens
        remaining = user_tokens - required_tokens if has_enough else 0

        return JSONResponse(
            status_code=200,
            content={
                "has_enough": has_enough,
                "current_tokens": user_tokens,
                "required_tokens": required_tokens,
                "remaining_after_deduction": remaining
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/protected")
def protected_route(current_user: User = Depends(get_current_user)):
    return JSONResponse(
        status_code=200,
        content={
            'message': f'Hello {current_user.first_name or current_user.email}!',
            'user_id': current_user.id,
            'timestamp': datetime.utcnow().isoformat()
        }
    )
