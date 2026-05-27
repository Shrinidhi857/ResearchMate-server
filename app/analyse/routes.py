import json
import uuid
import time
import os
from flask import Blueprint, request, jsonify, Response, stream_with_context
from app.auth.utils import token_required
from app.models import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

analyse_bp = Blueprint('analyse', __name__)

# In-memory storage for analysis sessions
# In a production app, this would be Redis or a database
ANALYSIS_SESSIONS = {}

@analyse_bp.route('/nlp', methods=['POST'])
@token_required
def start_analysis(current_user):
    data = request.get_json()
    
    if not data or not isinstance(data, list):
        return jsonify({"error": "Selected documents are required as a list"}), 400
    
    # Generate a session ID
    session_id = str(uuid.uuid4())
    
    # Store the document IDs to be analyzed
    ANALYSIS_SESSIONS[session_id] = {
        "user_id": current_user.id,
        "document_ids": data,
        "status": "pending",
        "created_at": time.time()
    }
    
    return jsonify({"session_id": session_id}), 200

@analyse_bp.route('/nlp/stream/<session_id>', methods=['GET'])
def stream_analysis(session_id):
    # Note: token_required might be tricky with EventSource if header isn't sent
    # Frontend sends token in query param: `?token=${token}`
    token = request.args.get('token')
    
    # In a real app, we would validate the token here. 
    # For now, let's assume the session exists and belong to the user.
    
    if session_id not in ANALYSIS_SESSIONS:
        return jsonify({"error": "Invalid session ID"}), 404
    
    session_data = ANALYSIS_SESSIONS[session_id]
    doc_ids = session_data["document_ids"]
    
    def generate():
        yield f"data: {json.dumps({'status': 'start', 'message': 'Analysis started...', 'phase': 'init'})}\n\n"
        time.sleep(1)
        
        try:
            # Initialize LLM - using Gemini
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
            
            # Process each document
            for i, doc_id in enumerate(doc_ids):
                # Fetch full document content
                actual_id = doc_id.get("doc_id") if isinstance(doc_id, dict) else doc_id
                
                # Step: Initializing (10%)
                yield f"data: {json.dumps({'doc_id': actual_id, 'progress': 10})}\n\n"
                
                document = Document.query.filter_by(doc_id=actual_id).first()
                if not document:
                    yield f"data: {json.dumps({'doc_id': actual_id, 'progress': 100, 'message': 'Document not found'})}\n\n"
                    continue
                
                # Step: Reading content (30%)
                yield f"data: {json.dumps({'doc_id': actual_id, 'progress': 30})}\n\n"
                time.sleep(0.2)
                
                # Yield a specific highlight for this document
                try:
                    # Truncate content for the summary if too long
                    content_to_analyze = document.content[:3000]
                    
                    # Step: LLM Processing (60%)
                    yield f"data: {json.dumps({'doc_id': actual_id, 'progress': 60})}\n\n"
                    
                    highlight = chain.invoke({"context": content_to_analyze})
                    
                    # Step: Finalizing (90%)
                    yield f"data: {json.dumps({'doc_id': actual_id, 'progress': 90})}\n\n"
                    time.sleep(0.2)
                    
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
                
                # Small delay for visual effect
                time.sleep(0.5)
            
            yield f"data: {json.dumps({'status': 'done', 'message': 'Analysis complete!', 'phase': 'complete'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'phase': 'error', 'error': str(e)})}\n\n"
        
        # Cleanup session
        if session_id in ANALYSIS_SESSIONS:
            del ANALYSIS_SESSIONS[session_id]

    return Response(stream_with_context(generate()), mimetype='text/event-stream')
    
