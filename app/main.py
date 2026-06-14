from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from .data_sources import get_sales_provider
from .dates import parse_month
from .jobs import create_report_job, get_report_job
from .models import JobStatus
from .moysklad import MoySkladClient
from .report import build_report
from .stores import list_stores


app = FastAPI(title="MoySklad Gross Turnover Reports")


class ReportRequest(BaseModel):
    store: str = Field(..., min_length=1)
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    source: str | None = Field(default=None, pattern=r"^(mock|moysklad)$")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stores")
def stores():
    return {"stores": list_stores()}


@app.get("/moysklad/stores")
def moysklad_stores():
    """Diagnostic endpoint for binding local store codes to MoySklad retailstore IDs."""
    try:
        return {"stores": MoySkladClient().list_retail_stores()}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"MoySklad diagnostic error: {exc}") from exc


@app.post("/reports/gross-turnover", status_code=202)
def create_gross_turnover_report(payload: ReportRequest):
    try:
        job = create_report_job(payload.store, payload.month, payload.source)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "job_id": job.id,
        "status": job.status,
        "store": job.store,
        "month": job.month,
        "source": job.source,
        "status_url": f"/reports/jobs/{job.id}",
        "download_url": f"/reports/jobs/{job.id}/download",
        "created_at": job.created_at.isoformat(),
    }


@app.get("/reports/jobs/{job_id}")
def get_job_status(job_id: str):
    job = get_report_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.id,
        "status": job.status,
        "store": job.store,
        "month": job.month,
        "source": job.source,
        "error": job.error,
        "download_url": (
            f"/reports/jobs/{job.id}/download" if job.status == JobStatus.done else None
        ),
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@app.get("/reports/jobs/{job_id}/download")
def download_job_result(job_id: str):
    job = get_report_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == JobStatus.failed:
        raise HTTPException(status_code=500, detail=job.error or "Job failed")
    if job.status != JobStatus.done or not job.file_path:
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")
    if not job.file_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(
        job.file_path,
        filename=job.file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/reports/gross-turnover")
def gross_turnover_report(
    store: str = Query(..., description="Retail store name or part of name"),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    source: str = Query("mock", pattern=r"^(mock|moysklad)$"),
):
    """Compatibility endpoint: generate immediately.

    Production clients should use POST /reports/gross-turnover and poll job status.
    """
    try:
        start, end = parse_month(month)
        provider = get_sales_provider(source)
        daily_sales = provider.load_daily_sales(store, start, end)
        output = build_report(store, start, end, daily_sales)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"MoySklad report error: {exc}") from exc

    return FileResponse(
        output,
        filename=output.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
