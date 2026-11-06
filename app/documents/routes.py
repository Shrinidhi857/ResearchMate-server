import uuid
import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, Request, UploadFile, File
from app.config import Config

# S3 client -- credentials come from EC2 instance profile or env vars
_s3 = boto3.client('s3', region_name=Config.AWS_REGION)
S3_BUCKET = Config.AWS_S3_BUCKET
from fastapi.responses import JSONResponse
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Document, PaperBucket, User
from app.auth.utils import get_current_user

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
                "content": d.content,
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
            "content": doc.content,
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
# S3 PDF ENDPOINTS
# ============================================================================

@router.post("/documents/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a PDF to S3 and store only its S3 key in the Document record."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return JSONResponse(status_code=400, content={"error": "Only PDF files are accepted"})

    doc_id = str(uuid.uuid4())
    s3_key = f"documents/{current_user.id}/{doc_id}.pdf"

    try:
        contents = await file.read()
        _s3.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=contents,
            ContentType="application/pdf",
        )
    except ClientError as e:
        return JSONResponse(status_code=500, content={"error": f"S3 upload failed: {e}"})

    try:
        doc = Document(
            doc_id=doc_id,
            user_id=current_user.id,
            title=file.filename.removesuffix(".pdf"),
            content=s3_key,   # the content column now stores the S3 key
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
        "s3_key": s3_key,
    })


@router.get("/documents/{doc_id}/pdf-url")
def get_pdf_presigned_url(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return a short-lived presigned S3 GET URL so the browser can render the PDF
    inline. The URL expires in 1 hour. The backend never proxies the PDF bytes.
    """
    doc = user_has_document_access(current_user, doc_id, db)
    if not doc:
        return JSONResponse(
            status_code=404,
            content={"error": "Document not found or access denied"},
        )

    try:
        presigned_url = _s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": S3_BUCKET,
                "Key": doc.content,                        # doc.content = S3 key
                "ResponseContentType": "application/pdf",
                "ResponseContentDisposition": "inline",   # render in browser, not download
            },
            ExpiresIn=3600,   # 1 hour
        )
    except ClientError as e:
        return JSONResponse(status_code=500, content={"error": f"Could not generate URL: {e}"})

    return JSONResponse(status_code=200, content={
        "doc_id": doc.doc_id,
        "title": doc.title,
        "pdf_url": presigned_url,
    })
