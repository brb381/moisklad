from __future__ import annotations

import asyncio
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT_DIR, settings
from .data_sources import get_sales_provider
from .dates import parse_month
from .models import JobStatus, ReportJob
from .report import build_report
from .stores import resolve_store


DB_PATH = ROOT_DIR / "jobs.sqlite3"
_worker_tasks: list[asyncio.Task] = []
_stop_event: asyncio.Event | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def from_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def job_result_is_fresh(job: ReportJob) -> bool:
    if not job.finished_at:
        return False
    age_seconds = (utc_now() - job.finished_at).total_seconds()
    return age_seconds <= settings.report_result_ttl_seconds


def delete_job_file(job: ReportJob | None) -> None:
    if not job or not job.file_path:
        return
    try:
        if job.file_path.exists() and ROOT_DIR in job.file_path.resolve().parents:
            job.file_path.unlink()
    except OSError:
        pass


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS report_jobs (
                id TEXT PRIMARY KEY,
                store TEXT NOT NULL,
                month TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                file_path TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                UNIQUE(store, month, source)
            )
            """
        )


def row_to_job(row: sqlite3.Row | None) -> ReportJob | None:
    if row is None:
        return None
    file_path = Path(row["file_path"]) if row["file_path"] else None
    return ReportJob(
        id=row["id"],
        store=row["store"],
        month=row["month"],
        source=row["source"],
        status=JobStatus(row["status"]),
        file_path=file_path,
        error=row["error"],
        created_at=from_iso(row["created_at"]) or utc_now(),
        started_at=from_iso(row["started_at"]),
        finished_at=from_iso(row["finished_at"]),
    )


def create_report_job(store: str, month: str, source: str | None = None) -> ReportJob:
    parse_month(month)
    store_config = resolve_store(store)
    source_name = (source or settings.data_source).strip().lower()
    get_sales_provider(source_name)

    now = utc_now()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            """
            SELECT * FROM report_jobs
            WHERE store = ? AND month = ? AND source = ?
            """,
            (store_config.name, month, source_name),
        ).fetchone()
        if existing:
            job = row_to_job(existing)
            if job and job.status in {JobStatus.queued, JobStatus.processing}:
                return job
            if (
                job
                and job.status == JobStatus.done
                and job.file_path
                and job.file_path.exists()
                and job_result_is_fresh(job)
            ):
                return job
            delete_job_file(job)
            conn.execute("DELETE FROM report_jobs WHERE id = ?", (existing["id"],))

        job = ReportJob(
            id=uuid.uuid4().hex,
            store=store_config.name,
            month=month,
            source=source_name,
            created_at=now,
        )
        conn.execute(
            """
            INSERT INTO report_jobs (
                id, store, month, source, status, file_path, error,
                created_at, started_at, finished_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.id,
                job.store,
                job.month,
                job.source,
                job.status.value,
                None,
                None,
                to_iso(job.created_at),
                None,
                None,
            ),
        )
        return job


def get_report_job(job_id: str) -> ReportJob | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM report_jobs WHERE id = ?", (job_id,)).fetchone()
        return row_to_job(row)


def claim_next_job() -> ReportJob | None:
    now = utc_now()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT * FROM report_jobs
            WHERE status = ?
            ORDER BY created_at
            LIMIT 1
            """,
            (JobStatus.queued.value,),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            """
            UPDATE report_jobs
            SET status = ?, started_at = ?, error = NULL
            WHERE id = ?
            """,
            (JobStatus.processing.value, to_iso(now), row["id"]),
        )
        updated = conn.execute("SELECT * FROM report_jobs WHERE id = ?", (row["id"],)).fetchone()
        return row_to_job(updated)


def finish_job(job_id: str, file_path: Path) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE report_jobs
            SET status = ?, file_path = ?, finished_at = ?
            WHERE id = ?
            """,
            (JobStatus.done.value, str(file_path), to_iso(utc_now()), job_id),
        )


def fail_job(job_id: str, error: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE report_jobs
            SET status = ?, error = ?, finished_at = ?
            WHERE id = ?
            """,
            (JobStatus.failed.value, error, to_iso(utc_now()), job_id),
        )


async def run_report_job(job: ReportJob) -> None:
    try:
        start, end = parse_month(job.month)
        provider = get_sales_provider(job.source)
        daily_sales = await provider.load_daily_sales(job.store, start, end)
        output = await asyncio.to_thread(build_report, job.store, start, end, daily_sales, job.id)
        finish_job(job.id, output)
    except Exception as exc:
        fail_job(job.id, str(exc))


async def worker_loop(worker_id: int) -> None:
    assert _stop_event is not None
    while not _stop_event.is_set():
        job = claim_next_job()
        if job:
            await run_report_job(job)
            continue
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass


async def start_workers() -> None:
    global _stop_event
    init_db()
    if _worker_tasks:
        return
    _stop_event = asyncio.Event()
    for worker_id in range(settings.report_workers):
        _worker_tasks.append(asyncio.create_task(worker_loop(worker_id)))


async def stop_workers() -> None:
    if _stop_event:
        _stop_event.set()
    if _worker_tasks:
        await asyncio.gather(*_worker_tasks, return_exceptions=True)
        _worker_tasks.clear()
