from sqlalchemy import Column, Integer, String, DateTime, Date, BigInteger, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from database import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    filepath = Column(String(1000))
    s3_key = Column(String(500))
    upload_date = Column(DateTime, default=func.now())
    period_start = Column(Date)
    period_end = Column(Date)
    row_count = Column(Integer)
    file_size = Column(BigInteger)
    status = Column(String(50), default="active")
    file_content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime, default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text)
    response_type = Column(String(20))
    chart_data = Column(JSONB)
    created_at = Column(DateTime, default=func.now())


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    data_source = Column(String(50), default="file_upload")
    s3_bucket = Column(String(255))
    s3_prefix = Column(String(500))
    s3_region = Column(String(50), default="us-east-1")
    aws_access_key = Column(String(255))
    aws_secret_key = Column(String(255))
    active_report_id = Column(Integer, ForeignKey("reports.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
