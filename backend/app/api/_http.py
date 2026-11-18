"""HTTP helpers shared by several routers (not a router itself, so routers never import each other)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import Request, Response
from starlette.datastructures import UploadFile

from app.core.errors import AppError
from app.services.io_service import ExportFile

# Headroom for the multipart envelope (boundaries, headers) on top of the file bytes.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


def _declared_length(request: Request) -> int | None:
    raw = request.headers.get("content-length")
    return int(raw) if raw is not None and raw.isdigit() else None


async def read_upload(request: Request, max_bytes: int) -> tuple[str, bytes]:
    """Read the multipart `file` field, refusing anything over `max_bytes` (413)."""
    declared = _declared_length(request)
    # Reject before request.form() spools the body to memory or disk.
    if declared is not None and declared > max_bytes + MULTIPART_OVERHEAD_BYTES:
        raise AppError("file_too_large", "File exceeds the size limit", 413)
    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise AppError("validation_error", "Multipart field 'file' is required", 422)
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise AppError("file_too_large", "File exceeds the size limit", 413)
    return upload.filename or "", content


def file_response(file: ExportFile) -> Response:
    ascii_name = file.filename.encode("ascii", "replace").decode().replace('"', "").replace("?", "_")
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(file.filename)}"
    return Response(file.body, media_type=file.mime, headers={"Content-Disposition": disposition})
