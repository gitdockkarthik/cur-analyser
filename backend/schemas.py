from pydantic import BaseModel
from typing import Optional, Any, List, Dict
from datetime import datetime, date


class ReportOut(BaseModel):
    id: int
    filename: str
    upload_date: Optional[datetime] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    row_count: Optional[int] = None
    file_size: Optional[int] = None
    status: str
    is_active: bool = False

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    type: str
    content: Any
    insight: str
    session_id: str


class MessageOut(BaseModel):
    id: int
    role: str
    content: Optional[str] = None
    response_type: Optional[str] = None
    chart_data: Optional[Dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SettingsIn(BaseModel):
    data_source: str = "file_upload"
    s3_bucket: Optional[str] = None
    s3_prefix: Optional[str] = None
    s3_region: Optional[str] = "us-east-1"
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    active_report_id: Optional[int] = None


class SettingsOut(BaseModel):
    id: int
    data_source: str
    s3_bucket: Optional[str] = None
    s3_prefix: Optional[str] = None
    s3_region: Optional[str] = None
    aws_access_key: Optional[str] = None
    active_report_id: Optional[int] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
