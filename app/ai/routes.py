from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from app.models.models import User
from app.auth.utils import get_current_user
from service.auto_site import auto_cite_paragraph
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import json
import os
import asyncio

router = APIRouter(tags=["AI"])
ai_bp = router


def summarize_research_paper(text: str) -> dict:
    try:
        llm = ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.3
        )
        prompt = ChatPromptTemplate.from_template("""
        You are an expert research assistant. Produce a structured summary of the following academic paper text:

        Text:
        {text}

        Provide the summary with:
        - Problem Statement
        - Methodology
        - Key Findings
        - Conclusion
        """)
        chain = prompt | llm | StrOutputParser()
        result = chain.invoke({"text": text[:10000]})
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/summarize")
async def summarize_api(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """API endpoint to summarize research paper text into structured JSON"""
    try:
        data = await request.json()
    except Exception:
        data = {}

    if not data or 'text' not in data:
        return JSONResponse(status_code=400, content={"message": "Missing 'text' in request body"})

    result = summarize_research_paper(data['text'])

    if result.get("success"):
        return JSONResponse(status_code=200, content={"message": "Success", "summary": result["data"]})
    elif "raw_output" in result:
        return JSONResponse(status_code=200, content={
            "message": "Model did not return perfect JSON",
            "raw_output": result["raw_output"]
        })
    else:
        return JSONResponse(status_code=500, content={"message": f"Error: {result.get('error')}"})


@router.post("/auto_cite")
async def auto_cite_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    try:
        data = await request.json()
        paragraph = data.get("paragraph", "")
        references = data.get("references", {})

        if not paragraph or not references:
            return JSONResponse(status_code=400, content={"message": "Missing paragraph or references"})

        result = auto_cite_paragraph(paragraph, references)
        return JSONResponse(status_code=200, content={"message": "Success", "cited_paragraph": result})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"message": f"Error: {str(e)}"})


@router.get("/test")
async def test_stream():
    async def generate():
        for i in range(5):
            msg = {"phase": i + 1, "status": "running", "message": f"Processing phase {i + 1}..."}
            yield f"data: {json.dumps(msg)}\n\n"
            await asyncio.sleep(1)
        yield f"data: {json.dumps({'phase': 6, 'status': 'complete', 'message': '✅ Test stream finished successfully!'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*"
        }
    )


@router.post("/start")
async def start_analysis(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    print("Received from frontend:", data)
    return JSONResponse(status_code=200, content={"status": "ok", "message": "Processing started!"})
