from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from app.models.models import User
from app.auth.utils import get_current_user
from rag.raptor import RaptorPipeline
from rag.raptor_middleman import asking_llm

router = APIRouter(tags=["RAG"])
rag_bp = router

# Global retriever instance
retriever = None


@router.post("/analyse")
async def raptor_analysis(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    global retriever
    retriever = None
    try:
        data = await request.json()
    except Exception:
        data = None

    if not data or len(data) == 0:
        return JSONResponse(status_code=400, content={"message": "No document selected"})

    try:
        retriever = RaptorPipeline(current_user, data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

    return JSONResponse(status_code=200, content={"message": "Document successfully Analysed"})


@router.post("/ask")
async def raptor_ask(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    try:
        data = await request.json()
    except Exception:
        data = {}

    if retriever is not None:
        try:
            answer = asking_llm(retriever, data.get("question"))
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JSONResponse(status_code=500, content={"message": f"Error asking Question: {str(e)}"})
    else:
        return JSONResponse(status_code=500, content={"message": "No document Context"})

    return JSONResponse(status_code=200, content={"message": "Success", "answer": answer})
