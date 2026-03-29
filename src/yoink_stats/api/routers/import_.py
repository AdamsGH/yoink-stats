"""Import endpoints - Telegram Desktop chat export ingestion."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from yoink.core.auth.rbac import require_role
from yoink.core.db.models import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stats"])


class ImportStatus(BaseModel):
    job_id: str
    status: str
    inserted: int = 0
    skipped: int = 0
    events: int = 0
    processed: int = 0
    total: int = 0
    error: str | None = None


_import_jobs: dict[str, ImportStatus] = {}


@router.post("/import", response_model=ImportStatus, summary="Import Telegram Desktop chat export (result.json)")
async def import_history(
    background_tasks: BackgroundTasks,
    chat_id: int = Query(...),
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(UserRole.owner)),
) -> ImportStatus:
    """Upload a Telegram Desktop chat history export (result.json) and import it.
    Runs in background; returns job_id to poll status."""
    import shutil
    import tempfile
    import uuid

    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="File must be a .json export from Telegram Desktop")

    job_id = str(uuid.uuid4())
    _import_jobs[job_id] = ImportStatus(job_id=job_id, status="running")

    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    try:
        shutil.copyfileobj(file.file, tmp)
    finally:
        tmp.close()

    background_tasks.add_task(_run_import, tmp.name, chat_id, job_id)
    return _import_jobs[job_id]


class ImportByPathRequest(BaseModel):
    path: str
    chat_id: int


@router.post("/import/by-path", response_model=ImportStatus, summary="Import from server-side file path (owner only)")
async def import_history_by_path(
    body: ImportByPathRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role(UserRole.owner)),
) -> ImportStatus:
    """Start import from a file path already on the server (no upload needed)."""
    import uuid
    from pathlib import Path

    p = Path(body.path)
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {body.path}")
    if not p.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {body.path}")

    job_id = str(uuid.uuid4())
    _import_jobs[job_id] = ImportStatus(job_id=job_id, status="running")
    background_tasks.add_task(_run_import, str(p), body.chat_id, job_id)
    return _import_jobs[job_id]


@router.get("/import/{job_id}", response_model=ImportStatus, summary="Get import job status")
async def import_status(
    job_id: str,
    current_user: User = Depends(require_role(UserRole.owner)),
) -> ImportStatus:
    """Poll the status of a running import job."""
    job = _import_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


async def _run_import(path: str, chat_id: int, job_id: str) -> None:
    import os

    def _progress(done: int, total: int) -> None:
        job = _import_jobs.get(job_id)
        if job:
            _import_jobs[job_id] = ImportStatus(
                job_id=job_id, status="running",
                processed=done, total=total,
                inserted=job.inserted, skipped=job.skipped, events=job.events,
            )

    try:
        from yoink.core.config import CoreSettings  # noqa: PLC0415
        from yoink_stats.importer.json_dump import import_json  # noqa: PLC0415

        cfg = CoreSettings()
        result = await import_json(json_path=path, db_url=cfg.database_url, chat_id=chat_id, progress_cb=_progress)
        _import_jobs[job_id] = ImportStatus(
            job_id=job_id, status="done",
            inserted=result["inserted"], skipped=result["skipped"], events=result["events"],
            processed=result["inserted"] + result["skipped"],
            total=result["inserted"] + result["skipped"],
        )
    except Exception as exc:
        logger.exception("Import job %s failed", job_id)
        _import_jobs[job_id] = ImportStatus(job_id=job_id, status="error", error=str(exc))
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
