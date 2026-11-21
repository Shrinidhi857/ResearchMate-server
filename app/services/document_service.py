import os
from typing import Optional, Tuple
from app.config import Config

STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "documents"))
os.makedirs(STORAGE_DIR, exist_ok=True)

# Clean out empty/whitespace AWS env vars so boto3 defaults to EC2 instance profile / IAM role
for _var in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]:
    if _var in os.environ and not os.environ[_var].strip():
        del os.environ[_var]

# S3 Client Initialization - uses EC2 instance profile or OIDC Web Identity
_s3 = None
try:
    import boto3
    _region = os.getenv("AWS_REGION", Config.AWS_REGION or "ap-south-1")
    _s3 = boto3.client("s3", region_name=_region)
except Exception:
    _s3 = None


def is_s3_available() -> bool:
    """Check if S3 is configured and accessible."""
    if _s3 is None or not Config.AWS_S3_BUCKET:
        return False
    try:
        # Check credentials by attempting a lightweight head_bucket
        _s3.head_bucket(Bucket=Config.AWS_S3_BUCKET)
        return True
    except Exception:
        return False


def save_document_file(user_id: int, doc_id: str, file_bytes: bytes, filename: str) -> Tuple[str, str]:
    """
    Save PDF file either to AWS S3 (if configured) or local storage.
    Returns (storage_type, storage_identifier)
    storage_type: 's3' or 'local'
    storage_identifier: S3 key or local relative path
    """
    s3_key = f"documents/{user_id}/{doc_id}.pdf"

    if is_s3_available():
        try:
            _s3.put_object(
                Bucket=Config.AWS_S3_BUCKET,
                Key=s3_key,
                Body=file_bytes,
                ContentType="application/pdf",
            )
            return "s3", s3_key
        except Exception as e:
            print(f"[DocumentService] S3 upload failed, falling back to local storage: {e}")

    # Local fallback
    user_dir = os.path.join(STORAGE_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    file_path = os.path.join(user_dir, f"{doc_id}.pdf")

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    rel_path = f"storage/documents/{user_id}/{doc_id}.pdf"
    return "local", rel_path


def get_document_bytes(doc) -> Optional[bytes]:
    """Retrieve raw PDF bytes from S3 or local disk for a document."""
    identifier = getattr(doc, "content", "") or ""

    # 1. Try S3 if identifier looks like an S3 key or starts with documents/
    if (identifier.startswith("documents/") or identifier.endswith(".pdf")) and is_s3_available():
        try:
            resp = _s3.get_object(Bucket=Config.AWS_S3_BUCKET, Key=identifier)
            return resp["Body"].read()
        except Exception as e:
            print(f"[DocumentService] Failed to read from S3 ({identifier}): {e}")

    # 2. Try Local storage
    # Try direct identifier path
    if os.path.exists(identifier):
        with open(identifier, "rb") as f:
            return f.read()

    # Try relative to storage dir: storage/documents/<user_id>/<doc_id>.pdf
    local_path = os.path.join(STORAGE_DIR, str(doc.user_id), f"{doc.doc_id}.pdf")
    if os.path.exists(local_path):
        with open(local_path, "rb") as f:
            return f.read()

    return None


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract clean text from PDF bytes using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text_parts = []
        for page in doc:
            text = page.get_text()
            if text:
                text_parts.append(text)
        return "\n\n".join(text_parts).strip()
    except Exception as e:
        print(f"[DocumentService] PyMuPDF extraction error: {e}")
        return ""


def get_document_text(doc) -> str:
    """
    Fetch the actual text of the document:
    1. If a PDF exists in storage (S3 or local), dynamically extract text from it.
    2. Fallback: If doc.content is legacy raw text (not a file path/key), return it.
    """
    pdf_bytes = get_document_bytes(doc)
    if pdf_bytes:
        extracted = extract_text_from_pdf_bytes(pdf_bytes)
        if extracted:
            return extracted

    # Legacy fallback: content column stored raw text in older versions
    content = getattr(doc, "content", "") or ""
    # Check if content looks like a path/key
    if not (content.startswith("documents/") or content.endswith(".pdf") or content.startswith("storage/")):
        return content

    return ""


def get_document_pdf_url(doc, base_url: str = "") -> Optional[str]:
    """Generate a presigned S3 URL or a local proxy URL to view the PDF."""
    identifier = getattr(doc, "content", "") or ""

    if (identifier.startswith("documents/") or identifier.endswith(".pdf")) and is_s3_available():
        try:
            return _s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": Config.AWS_S3_BUCKET,
                    "Key": identifier,
                    "ResponseContentType": "application/pdf",
                    "ResponseContentDisposition": "inline",
                },
                ExpiresIn=3600,
            )
        except Exception as e:
            print(f"[DocumentService] Presigned URL failed: {e}")

    # Local fallback URL
    clean_base = base_url.rstrip("/") if base_url else ""
    return f"{clean_base}/api/documents/{doc.doc_id}/view"
