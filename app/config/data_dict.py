from pydantic import BaseModel, HttpUrl
from typing import Optional, List, TypeVar, Generic
from datetime import datetime

T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    """基础响应模型"""

    code: int = 200  # HTTP状态码
    message: str = "Success"  # 响应消息
    task_id: str = ""  # 任务ID
    data: Optional[T] = []  # 响应数据


class VideoRequest(BaseModel):
    """视频处理请求参数"""

    url: HttpUrl


class VideoValidation(BaseModel):
    """视频验证参数"""

    max_size_mb: int = 50  # 最大文件大小（MB）
    allowed_formats: List[str] = [
        "mp4",
        "avi",
        "mov",
        "wav",
        "3gpp",
        "x-flv",
    ]  # 支持的视频格式
