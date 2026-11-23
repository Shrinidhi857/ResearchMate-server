import uuid
from fastapi import APIRouter, Depends, Request, Response, UploadFile, File
from fastapi.responses import JSONResponse
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Document, PaperBucket, User
from app.auth.utils import get_current_user
from app.services.document_service import (
    save_document_file,
    get_document_bytes,
    get_document_text,
    get_document_pdf_url,
)

router = APIRouter(tags=["Documents"])
documents_bp = router


# ============================================================================
# ACCESS CONTROL HELPER
# ============================================================================

def user_has_document_access(current_user: User, doc_id: str, db: Session):
    """
    Check if user has access to a document.
    Access is granted if:
    1. User is the document owner, OR
    2. Document is in a PaperBucket of a project the user is a member of
    """
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    if not doc:
        return None

    # Access 1: User is the owner
    if doc.user_id == current_user.id:
        return doc

    # Access 2: Document is in a shared project
    paper_buckets = db.query(PaperBucket).all()
    for bucket in paper_buckets:
        if bucket.paper_ids and doc_id in bucket.paper_ids:
            project = bucket.project
            if project and current_user in project.users:
                return doc

    return None


@router.post("/documents")
async def add_document(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        data = await request.json()
    except Exception:
        data = None

    if not data or "content" not in data:
        return JSONResponse(status_code=400, content={"error": "Document content is required"})

    try:
        doc = Document(
            user_id=current_user.id,
            title=data.get("title"),
            content=data["content"]
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return JSONResponse(
            status_code=201,
            content={
                "message": "Document saved successfully",
                "doc_id": doc.doc_id,
                "title": doc.title,
                "user_id": current_user.id
            }
        )
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/documents")
def get_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Get documents owned by the user
        owned_docs = db.query(Document).filter(Document.user_id == current_user.id).all()

        # Get documents in shared projects
        shared_doc_ids = set()
        for project in current_user.projects:
            if project.paper_bucket and project.paper_bucket.paper_ids:
                shared_doc_ids.update(project.paper_bucket.paper_ids)

        shared_docs = []
        if shared_doc_ids:
            shared_docs = db.query(Document).filter(Document.doc_id.in_(shared_doc_ids)).all()

        # Combine and deduplicate by doc_id
        all_docs = {d.doc_id: d for d in owned_docs + shared_docs}.values()

        return JSONResponse(
            status_code=200,
            content=[{
                "doc_id": d.doc_id,
                "title": d.title,
                "content": get_document_text(d),
                "created_at": d.created_at.isoformat() if d.created_at else None
            } for d in all_docs]
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/documents/summary")
def get_documents_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Get owned documents
        owned_docs = db.query(Document.doc_id, Document.title).filter(Document.user_id == current_user.id).all()

        # Get shared documents from projects
        shared_doc_ids = set()
        for project in current_user.projects:
            if project.paper_bucket and project.paper_bucket.paper_ids:
                shared_doc_ids.update(project.paper_bucket.paper_ids)

        shared_docs = []
        if shared_doc_ids:
            shared_docs = db.query(Document.doc_id, Document.title).filter(Document.doc_id.in_(shared_doc_ids)).all()

        # Combine and deduplicate
        all_docs = {doc[0]: doc for doc in owned_docs + shared_docs}

        result = [
            {"doc_id": doc[0], "title": doc[1]}
            for doc in all_docs.values()
        ]

        return JSONResponse(status_code=200, content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/documents/{doc_id}")
def get_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = user_has_document_access(current_user, doc_id, db)
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Document not found or access denied"})

    return JSONResponse(
        status_code=200,
        content={
            "doc_id": doc.doc_id,
            "title": doc.title,
            "content": get_document_text(doc),
            "created_at": doc.created_at.isoformat() if doc.created_at else None
        }
    )


@router.put("/documents/{doc_id}")
async def update_document(
    doc_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        data = await request.json()
    except Exception:
        data = None

    if not data or "content" not in data:
        return JSONResponse(status_code=400, content={"error": "Document content is required"})

    # Only document owner can edit
    doc = db.query(Document).filter(Document.doc_id == doc_id, Document.user_id == current_user.id).first()
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Document not found or you don't have permission to edit"})

    doc.content = data["content"]
    doc.updated_at = datetime.utcnow()
    db.commit()
    return JSONResponse(status_code=200, content={"message": "Document updated successfully"})


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Only document owner can delete
    doc = db.query(Document).filter(Document.doc_id == doc_id, Document.user_id == current_user.id).first()
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Document not found or you don't have permission to delete"})

    db.delete(doc)
    db.commit()
    return JSONResponse(status_code=200, content={"message": "Document deleted successfully"})


# ============================================================================
# PDF UPLOAD & RETRIEVAL (S3 OR LOCAL FALLBACK)
# ============================================================================

@router.post("/documents/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload a PDF document.
    Stores the binary file in Object Storage (S3) or secure local storage.
    Only the storage identifier is kept in the database, avoiding database bloat.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return JSONResponse(status_code=400, content={"error": "Only PDF files are accepted"})

    doc_id = str(uuid.uuid4())
    contents = await file.read()

    try:
        storage_type, storage_id = save_document_file(
            user_id=current_user.id,
            doc_id=doc_id,
            file_bytes=contents,
            filename=file.filename
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Failed to store PDF file: {str(e)}"})

    try:
        doc = Document(
            doc_id=doc_id,
            user_id=current_user.id,
            title=file.filename.removesuffix(".pdf"),
            content=storage_id,   # stores storage identifier (S3 key or local relative path)
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"error": str(e)})

    return JSONResponse(status_code=201, content={
        "message": "PDF uploaded successfully",
        "doc_id": doc.doc_id,
        "title": doc.title,
        "storage_type": storage_type,
        "storage_id": storage_id,
    })


@router.get("/documents/{doc_id}/pdf-url")
def get_pdf_presigned_url(
    doc_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return a URL so the browser can render the PDF inline.
    - If S3 is active: returns short-lived presigned S3 GET URL.
    - If S3 is not active (local): returns local stream endpoint URL.
    """
    doc = user_has_document_access(current_user, doc_id, db)
    if not doc:
        return JSONResponse(
            status_code=404,
            content={"error": "Document not found or access denied"},
        )

    base_url = str(request.base_url).rstrip("/")
    pdf_url = get_document_pdf_url(doc, base_url=base_url)

    return JSONResponse(status_code=200, content={
        "doc_id": doc.doc_id,
        "title": doc.title,
        "pdf_url": pdf_url,
    })


@router.get("/documents/{doc_id}/view")
def view_document_pdf(
    doc_id: str,
    db: Session = Depends(get_db)
):
    """Stream PDF directly when running without AWS S3."""
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    if not doc:
        return JSONResponse(status_code=404, content={"error": "Document not found"})

    pdf_bytes = get_document_bytes(doc)
    if not pdf_bytes:
        return JSONResponse(status_code=404, content={"error": "PDF file not found in storage"})

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.title or doc_id}.pdf"'}
    )
