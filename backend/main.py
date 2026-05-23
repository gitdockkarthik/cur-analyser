import csv
import os
import random
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from claude_client import ClaudeClient
from cur_engine import CUREngine
from database import Base, engine, get_db
from models import ChatMessage, ChatSession, Report, Settings
from schemas import (
    ChatRequest,
    ChatResponse,
    MessageOut,
    ReportOut,
    SettingsIn,
    SettingsOut,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="CUR Analyser API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", "./uploads"))
UPLOADS_DIR.mkdir(exist_ok=True)

claude = ClaudeClient()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _active_report(db: Session) -> Optional[Report]:
    settings = db.query(Settings).first()
    if not settings or not settings.active_report_id:
        return None
    return db.query(Report).filter(Report.id == settings.active_report_id).first()


def _ensure_settings(db: Session) -> Settings:
    s = db.query(Settings).first()
    if not s:
        s = Settings()
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


# ── Reports ───────────────────────────────────────────────────────────────────

@app.post("/api/reports/upload", response_model=ReportOut)
def upload_report(file: UploadFile = File(...), db: Session = Depends(get_db)):
    ext = Path(file.filename).suffix.lower()
    if ext not in {".csv", ".parquet"}:
        raise HTTPException(400, "Only CSV and Parquet files are supported")

    dest = UPLOADS_DIR / f"{uuid.uuid4()}{ext}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = os.path.getsize(dest)

    try:
        meta = CUREngine(str(dest)).get_metadata()
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"Failed to parse CUR file: {exc}")

    report = Report(
        filename=file.filename,
        filepath=str(dest),
        file_size=file_size,
        row_count=meta["row_count"],
        period_start=meta["period_start"],
        period_end=meta["period_end"],
        status="active",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    settings = _ensure_settings(db)
    if not settings.active_report_id:
        settings.active_report_id = report.id
        db.commit()

    out = ReportOut.model_validate(report)
    out.is_active = (db.query(Settings).first().active_report_id == report.id)
    return out


@app.get("/api/reports", response_model=List[ReportOut])
def list_reports(db: Session = Depends(get_db)):
    reports = db.query(Report).order_by(Report.created_at.desc()).all()
    settings = _ensure_settings(db)
    active_id = settings.active_report_id

    result = []
    for r in reports:
        out = ReportOut.model_validate(r)
        out.is_active = r.id == active_id
        result.append(out)
    return result


@app.put("/api/reports/{report_id}/activate")
def activate_report(report_id: int, db: Session = Depends(get_db)):
    if not db.query(Report).filter(Report.id == report_id).first():
        raise HTTPException(404, "Report not found")
    settings = _ensure_settings(db)
    settings.active_report_id = report_id
    db.commit()
    return {"message": "Report activated", "active_report_id": report_id}


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")

    if report.filepath:
        Path(report.filepath).unlink(missing_ok=True)

    settings = _ensure_settings(db)
    if settings.active_report_id == report_id:
        settings.active_report_id = None
        db.commit()

    db.delete(report)
    db.commit()
    return {"message": "Report deleted"}


@app.post("/api/reports/generate-sample")
def generate_sample(db: Session = Depends(get_db)):
    """Create a synthetic CUR CSV with ~3 months of realistic data."""
    SERVICES = [
        ("AmazonEC2", 450.0),
        ("AmazonRDS", 180.0),
        ("AmazonS3", 45.0),
        ("AWSLambda", 12.0),
        ("AmazonCloudFront", 28.0),
        ("AmazonEKS", 72.0),
        ("AmazonElastiCache", 55.0),
        ("AWSDataTransfer", 32.0),
        ("AmazonRoute53", 8.0),
        ("AWSKeyManagementService", 3.0),
        ("AmazonGuardDuty", 15.0),
    ]

    today = datetime.now()
    start = (today.replace(day=1) - timedelta(days=90)).replace(day=1)

    headers = [
        "lineItem/UsageAccountId", "lineItem/LineItemType",
        "lineItem/UsageStartDate", "lineItem/UsageEndDate",
        "lineItem/ProductCode", "lineItem/UsageType",
        "lineItem/Operation", "lineItem/AvailabilityZone",
        "lineItem/UnblendedRate", "lineItem/UnblendedCost",
        "lineItem/BlendedCost", "lineItem/CurrencyCode",
        "product/ProductName", "product/region",
    ]

    filename = f"sample_cur_{today.strftime('%Y%m%d_%H%M%S')}.csv"
    dest = UPLOADS_DIR / filename

    rows = []
    cur = start
    while cur < today:
        for svc, base in SERVICES:
            variance = random.uniform(0.85, 1.15)
            months_elapsed = max((cur - start).days / 30, 0)
            trend = 1 + months_elapsed * 0.02
            spike = 1.35 if random.random() < 0.04 else 1.0
            daily = (base / 30) * variance * trend * spike

            rows.append([
                "123456789012", "Usage",
                cur.strftime("%Y-%m-%dT00:00:00Z"),
                (cur + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z"),
                svc, f"{svc}:Usage",
                "RunInstances", "us-east-1a",
                str(round(daily / 24, 8)), str(round(daily, 8)),
                str(round(daily, 8)), "USD",
                svc, "us-east-1",
            ])
        cur += timedelta(days=1)

    with open(dest, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    meta = CUREngine(str(dest)).get_metadata()

    report = Report(
        filename=filename,
        filepath=str(dest),
        file_size=os.path.getsize(dest),
        row_count=meta["row_count"],
        period_start=meta["period_start"],
        period_end=meta["period_end"],
        status="active",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    settings = _ensure_settings(db)
    settings.active_report_id = report.id
    db.commit()

    return {
        "message": "Sample report generated and set as active",
        "report_id": report.id,
        "filename": filename,
        "row_count": len(rows),
    }


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    report = _active_report(db)
    if not report:
        raise HTTPException(400, "No active report. Upload and activate a CUR file first.")

    session = db.query(ChatSession).filter(ChatSession.session_id == req.session_id).first()
    if not session:
        session = ChatSession(session_id=req.session_id)
        db.add(session)
        db.commit()

    history = [
        {"role": m.role, "content": m.content}
        for m in db.query(ChatMessage)
            .filter(ChatMessage.session_id == req.session_id)
            .order_by(ChatMessage.created_at)
            .all()
        if m.role in ("user", "assistant") and m.content
    ]

    cur_data = CUREngine(report.filepath).get_summary_for_claude()

    db.add(ChatMessage(session_id=req.session_id, role="user", content=req.message))
    db.commit()

    try:
        result = claude.analyze_costs(req.message, cur_data, history)
    except Exception as exc:
        raise HTTPException(500, f"Claude API error: {exc}")

    content = result.get("content", "")
    asst = ChatMessage(
        session_id=req.session_id,
        role="assistant",
        content=content if isinstance(content, str) else result.get("insight", ""),
        response_type=result.get("type"),
        chart_data=result if result.get("type") in ("table", "chart") else None,
    )
    db.add(asst)
    db.commit()

    return ChatResponse(
        type=result.get("type", "text"),
        content=result.get("content", ""),
        insight=result.get("insight", ""),
        session_id=req.session_id,
    )


@app.get("/api/chat/sessions/{session_id}/messages", response_model=List[MessageOut])
def get_messages(session_id: str, db: Session = Depends(get_db)):
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )


@app.delete("/api/chat/sessions/{session_id}")
def clear_session(session_id: str, db: Session = Depends(get_db)):
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.query(ChatSession).filter(ChatSession.session_id == session_id).delete()
    db.commit()
    return {"message": "Session cleared"}


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/api/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    report = _active_report(db)
    if not report:
        raise HTTPException(400, "No active report")

    eng = CUREngine(report.filepath)
    now = datetime.now()
    this = eng.get_cost_by_service(now.year, now.month)

    prev_dt = (now.replace(day=1) - timedelta(days=1))
    last = eng.get_cost_by_service(prev_dt.year, prev_dt.month)

    total_this = sum(s["cost"] for s in this)
    total_last = sum(s["cost"] for s in last)
    delta = total_this - total_last
    delta_pct = round(delta / total_last * 100, 1) if total_last else 0

    top = this[0] if this else {"service": "N/A", "cost": 0}
    mom = eng.get_mom_delta()
    biggest = max(mom, key=lambda x: x["pct_change"], default={"service": "N/A", "pct_change": 0})

    return {
        "total_spend":              round(total_this, 2),
        "last_month_spend":         round(total_last, 2),
        "delta":                    round(delta, 2),
        "delta_pct":                delta_pct,
        "top_service":              top["service"],
        "top_service_spend":        round(top["cost"], 2),
        "biggest_increase_service": biggest["service"],
        "biggest_increase_pct":     biggest.get("pct_change", 0),
    }


@app.get("/api/dashboard/service-breakdown")
def service_breakdown(
    year: int = Query(default=None),
    month: int = Query(default=None),
    db: Session = Depends(get_db),
):
    report = _active_report(db)
    if not report:
        raise HTTPException(400, "No active report")
    now = datetime.now()
    data = CUREngine(report.filepath).get_cost_by_service(year or now.year, month or now.month)
    return {"year": year or now.year, "month": month or now.month, "services": data[:20]}


@app.get("/api/dashboard/trend")
def monthly_trend(months: int = Query(default=3), db: Session = Depends(get_db)):
    report = _active_report(db)
    if not report:
        raise HTTPException(400, "No active report")
    return CUREngine(report.filepath).get_monthly_trend(months)


@app.get("/api/dashboard/mom-delta")
def mom_delta(db: Session = Depends(get_db)):
    report = _active_report(db)
    if not report:
        raise HTTPException(400, "No active report")
    return {"deltas": CUREngine(report.filepath).get_mom_delta()}


@app.get("/api/dashboard/anomalies")
def anomalies(threshold: float = Query(default=0.2), db: Session = Depends(get_db)):
    report = _active_report(db)
    if not report:
        raise HTTPException(400, "No active report")
    return {"anomalies": CUREngine(report.filepath).get_anomalies(threshold)}


# ── Settings ──────────────────────────────────────────────────────────────────

@app.get("/api/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return _ensure_settings(db)


@app.put("/api/settings", response_model=SettingsOut)
def save_settings(data: SettingsIn, db: Session = Depends(get_db)):
    s = _ensure_settings(db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    s.updated_at = datetime.now()
    db.commit()
    db.refresh(s)
    return s


@app.post("/api/settings/test-connection")
def test_connection():
    raise HTTPException(501, "S3 integration is Phase 2 — not yet implemented")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


# ── Static frontend ───────────────────────────────────────────────────────────

_frontend = Path(__file__).parent / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
