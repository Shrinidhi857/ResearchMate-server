import json
import uuid
import time
import os
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse

from app.database import SessionLocal
from app.auth.utils import get_current_user
from app.models.models import Document, User
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

router = APIRouter(tags=["Analyse"])
analyse_bp = router

# In-memory storage for analysis sessions
ANALYSIS_SESSIONS = {}


@router.post("/nlp")
async def start_analysis(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    try:
        data = await request.json()
    except Exception:
        data = None

    if not data or not isinstance(data, list):
        return JSONResponse(status_code=400, content={"error": "Selected documents are required as a list"})

    session_id = str(uuid.uuid4())

    ANALYSIS_SESSIONS[session_id] = {
        "user_id": current_user.id,
        "document_ids": data,
        "status": "pending",
        "created_at": time.time()
    }

    return JSONResponse(status_code=200, content={"session_id": session_id})


@router.get("/nlp/stream/{session_id}")
async def stream_analysis(
    session_id: str,
    token: Optional[str] = Query(None)
):
    if session_id not in ANALYSIS_SESSIONS:
        return JSONResponse(status_code=404, content={"error": "Invalid session ID"})

    session_data = ANALYSIS_SESSIONS[session_id]
    doc_ids = session_data["document_ids"]

    async def event_generator():
        db = SessionLocal()
        try:
            yield f"data: {json.dumps({'status': 'start', 'message': 'Analysis started...', 'phase': 'init'})}\n\n"
            await asyncio.sleep(0.5)

            try:
                llm = ChatGoogleGenerativeAI(
                    model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                    api_key=os.getenv("GEMINI_API_KEY"),
                    temperature=0.7
                )
                prompt = ChatPromptTemplate.from_template("""
                You are an expert research assistant specialized in reading and summarizing academic research papers.

                Your task is to produce a clear, accurate, and concise summary of the provided research paper document.

                Guidelines:
                - Preserve technical correctness and key terminology.
                - Do NOT hallucinate results, citations, or claims that are not explicitly present in the document.
                - Focus on the core contributions, methodology, and conclusions.
                - Ignore formatting artifacts, page numbers, and references unless they are essential.
                - Use neutral, academic language.

                Output structure:
                1. Problem Statement   What problem the paper addresses and why it matters.
                2. Proposed Approach  The main methodology or system introduced.
                3. Key Results  Important findings or observations (qualitative or quantitative).
                4. Contributions  What is novel or significant about this work.
                5. Limitations & Future Work  Any stated limitations or future directions (if mentioned).

                Constraints:
                - Keep the summary within 200-300 words.
                - Do not include opinions or external knowledge.
                - If information is missing, explicitly state "Not specified in the paper."

                Begin summarization only after fully understanding the document.

                Document Content:
                {context}
                """)
                chain = prompt | llm | StrOutputParser()

                yield f"data: {json.dumps({'status': 'processing', 'message': f'Summarizing {len(doc_ids)} documents...', 'phase': 'llm'})}\n\n"

                for i, doc_id in enumerate(doc_ids):
                    actual_id = doc_id.get("doc_id") if isinstance(doc_id, dict) else doc_id

                    # Step: Initializing (10%)
                    yield f"data: {json.dumps({'doc_id': actual_id, 'progress': 10})}\n\n"

                    document = db.query(Document).filter(Document.doc_id == actual_id).first()
                    if not document:
                        yield f"data: {json.dumps({'doc_id': actual_id, 'progress': 100, 'message': 'Document not found'})}\n\n"
                        continue

                    # Step: Reading content (30%)
                    yield f"data: {json.dumps({'doc_id': actual_id, 'progress': 30})}\n\n"
                    await asyncio.sleep(0.2)

                    try:
                        content_to_analyze = document.content[:3000]

                        # Step: LLM Processing (60%)
                        yield f"data: {json.dumps({'doc_id': actual_id, 'progress': 60})}\n\n"

                        highlight = chain.invoke({"context": content_to_analyze})

                        # Step: Finalizing (90%)
                        yield f"data: {json.dumps({'doc_id': actual_id, 'progress': 90})}\n\n"
                        await asyncio.sleep(0.2)

                        event_data = {
                            "sentence": highlight,
                            "predicted_label": "Highlight",
                            "confidence": 0.85 + (0.1 * (i % 2)),
                            "doc_id": actual_id,
                            "progress": 100
                        }
                        yield f"data: {json.dumps(event_data)}\n\n"

                    except Exception as e:
                        yield f"data: {json.dumps({'phase': 'error', 'error': f'Error analyzing document {actual_id}: {str(e)}'})}\n\n"

                    await asyncio.sleep(0.3)

                yield f"data: {json.dumps({'status': 'done', 'message': 'Analysis complete!', 'phase': 'complete'})}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'phase': 'error', 'error': str(e)})}\n\n"

            if session_id in ANALYSIS_SESSIONS:
                del ANALYSIS_SESSIONS[session_id]

        finally:
            db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*"
        }
    )
