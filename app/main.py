from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .data_sources import get_sales_provider
from .dates import parse_month
from .jobs import create_report_job, get_report_job, start_workers, stop_workers
from .models import JobStatus
from .moysklad import MoySkladClient
from .report import build_report
from .stores import list_stores


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_workers()
    try:
        yield
    finally:
        await stop_workers()


app = FastAPI(title="MoySklad Gross Turnover Reports", lifespan=lifespan)

MONTH_NAMES = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


class ReportRequest(BaseModel):
    store: str = Field(..., min_length=1)
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    source: str | None = Field(default=None, pattern=r"^moysklad$")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stores")
def stores():
    return {"stores": list_stores()}


@app.get("/months")
def months(months_back: int = Query(24, ge=1, le=120)):
    today = date.today()
    current_index = today.year * 12 + today.month - 1
    result = []
    for offset in range(months_back):
        month_index = current_index - offset
        year = month_index // 12
        month = month_index % 12 + 1
        result.append(
            {
                "value": f"{year:04d}-{month:02d}",
                "label": f"{MONTH_NAMES[month]} {year}",
                "year": year,
                "month": month,
                "is_current": offset == 0,
            }
        )
    return {"months": result}


@app.get("/moysklad/stores")
async def moysklad_stores():
    try:
        async with MoySkladClient() as client:
            return {"stores": await client.list_retail_stores()}
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
async def gross_turnover_report(
    store: str = Query(..., description="Retail store name or part of name"),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    source: str = Query("moysklad", pattern=r"^moysklad$"),
):
    try:
        start, end = parse_month(month)
        provider = get_sales_provider(source)
        daily_sales = await provider.load_daily_sales(store, start, end)
        output = await asyncio.to_thread(build_report, store, start, end, daily_sales)
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
