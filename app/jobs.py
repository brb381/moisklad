from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .config import settings
from .data_sources import get_sales_provider
from .dates import parse_month
from .models import JobStatus, ReportJob
from .report import build_report
from .stores import resolve_store


_jobs: dict[str, ReportJob] = {}
_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=settings.max_report_workers)


def create_report_job(store: str, month: str, source: str | None = None) -> ReportJob:
    parse_month(month)
    store_config = resolve_store(store)
    source_name = (source or settings.data_source).strip().lower()
    get_sales_provider(source_name)
    job = ReportJob(id=uuid.uuid4().hex, store=store_config.name, month=month, source=source_name)
    with _lock:
        _jobs[job.id] = job
    _executor.submit(_run_report_job, job.id)
    return job


def get_report_job(job_id: str) -> ReportJob | None:
    with _lock:
        return _jobs.get(job_id)


def _update_job(job_id: str, **changes) -> None:
    with _lock:
        job = _jobs[job_id]
        for key, value in changes.items():
            setattr(job, key, value)


def _run_report_job(job_id: str) -> None:
    job = get_report_job(job_id)
    if not job:
        return
    _update_job(job_id, status=JobStatus.processing, started_at=datetime.now(timezone.utc))
    try:
        start, end = parse_month(job.month)
        provider = get_sales_provider(job.source)
        daily_sales = provider.load_daily_sales(job.store, start, end)
        output = build_report(job.store, start, end, daily_sales, job_id=job.id)
        _update_job(
            job_id,
            status=JobStatus.done,
            file_path=output,
            finished_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        _update_job(
            job_id,
            status=JobStatus.failed,
            error=str(exc),
            finished_at=datetime.now(timezone.utc),
        )
