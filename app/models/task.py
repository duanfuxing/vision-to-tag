from sqlalchemy import Column, Integer, String, JSON, DateTime, func
from sqlalchemy.sql import func
from app.db.base_class import Base

class Task(Base):
    __tablename__ = "video_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    task_id = Column(String(100), nullable=False, default='', comment='任务ID')
    uid = Column(String(100), nullable=False, default='', comment='用户ID')
    url = Column(String(512), nullable=False, default='', comment='视频URL')
    platform = Column(String(20), nullable=False, default='', comment='平台-rpa,miaobi')
    env = Column(String(20), nullable=False, default='develop', comment='环境 develop，production')
    status = Column(String(20), nullable=False, default='pending', comment='任务状态 pending:待处理, processing:处理中, completed:已完成, failed:失败')
    dismensions = Column(String(30), nullable=False, default='all', comment='提取维度all-全部， vision-视觉，audio-音频，content-semantics-内容语义，commercial-value-商业价值')
    message = Column(JSON, nullable=True, comment='附加信息')
    tags = Column(JSON, nullable=True, comment='视频标签')
    created_at = Column(DateTime, nullable=False, default=func.current_timestamp(), comment='创建时间')
    updated_at = Column(DateTime, nullable=False, default=func.current_timestamp(), onupdate=func.current_timestamp(), comment='更新时间')
