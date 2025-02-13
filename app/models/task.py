from sqlalchemy import Column, BigInteger, String, Text, JSON, DateTime
from sqlalchemy.sql import func
from app.db.base_class import Base


class Task(Base):
    __tablename__ = "video_tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(String(100), unique=True, nullable=False)
    uid = Column(String(100), nullable=False)
    url = Column(String(512), nullable=False)
    platform = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    message = Column(Text)
    tags = Column(JSON)
    processed_start = Column(DateTime)
    processed_end = Column(DateTime)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
