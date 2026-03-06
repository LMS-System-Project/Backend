"""
File storage abstraction — local filesystem (dev) or Cloudflare R2 (production).

Usage:
    from storage import upload_file, delete_file

    file_name, file_url = await upload_file(upload_file_obj, folder="materials")
"""

import os
import uuid
import shutil
from pathlib import Path
from fastapi import UploadFile

from config import (
    STORAGE_BACKEND,
    R2_ACCOUNT_ID,
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_BUCKET_NAME,
    R2_PUBLIC_URL,
)

# ── Local storage ────────────────────────────────────────────────

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


async def _local_upload(file: UploadFile, folder: str) -> tuple[str, str]:
    """Save file to ./uploads/<folder>/<uuid>_<filename>."""
    sub_dir = UPLOAD_DIR / folder
    sub_dir.mkdir(parents=True, exist_ok=True)

    # Generate a unique filename
    ext = Path(file.filename or "file").suffix
    unique_name = f"{uuid.uuid4().hex[:12]}_{file.filename or 'upload'}"
    dest = sub_dir / unique_name

    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    file_url = f"/uploads/{folder}/{unique_name}"
    return unique_name, file_url


async def _local_delete(file_url: str) -> None:
    """Delete a locally stored file."""
    # file_url is like /uploads/materials/abc123_file.pdf
    rel_path = file_url.lstrip("/")
    full_path = Path(__file__).parent / rel_path
    if full_path.exists():
        full_path.unlink()


# ── R2 (Cloudflare) storage ──────────────────────────────────────

def _get_r2_client():
    """Create a boto3 S3 client for Cloudflare R2."""
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


async def _r2_upload(file: UploadFile, folder: str) -> tuple[str, str]:
    """Upload file to Cloudflare R2."""
    ext = Path(file.filename or "file").suffix
    unique_name = f"{uuid.uuid4().hex[:12]}_{file.filename or 'upload'}"
    key = f"{folder}/{unique_name}"

    content = await file.read()
    client = _get_r2_client()
    client.put_object(
        Bucket=R2_BUCKET_NAME,
        Key=key,
        Body=content,
        ContentType=file.content_type or "application/octet-stream",
    )

    # Build public URL
    if R2_PUBLIC_URL:
        file_url = f"{R2_PUBLIC_URL.rstrip('/')}/{key}"
    else:
        file_url = f"https://{R2_BUCKET_NAME}.{R2_ACCOUNT_ID}.r2.cloudflarestorage.com/{key}"

    return unique_name, file_url


async def _r2_delete(file_url: str) -> None:
    """Delete a file from Cloudflare R2."""
    # Extract key from URL
    if R2_PUBLIC_URL and file_url.startswith(R2_PUBLIC_URL):
        key = file_url[len(R2_PUBLIC_URL.rstrip("/")) + 1:]
    else:
        # Try to extract from the path portion
        from urllib.parse import urlparse
        parsed = urlparse(file_url)
        key = parsed.path.lstrip("/")

    client = _get_r2_client()
    client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)


# ── Public API ───────────────────────────────────────────────────

async def upload_file(file: UploadFile, folder: str = "general") -> tuple[str, str]:
    """
    Upload a file. Returns (file_name, file_url).

    Uses local storage or R2 depending on STORAGE_BACKEND env var.
    """
    if STORAGE_BACKEND == "r2":
        return await _r2_upload(file, folder)
    return await _local_upload(file, folder)


async def delete_file(file_url: str) -> None:
    """Delete a file by its URL."""
    if STORAGE_BACKEND == "r2":
        await _r2_delete(file_url)
    else:
        await _local_delete(file_url)


def get_file_size(file: UploadFile) -> int:
    """Get file size in bytes."""
    file.file.seek(0, 2)  # Seek to end
    size = file.file.tell()
    file.file.seek(0)  # Reset to beginning
    return size
