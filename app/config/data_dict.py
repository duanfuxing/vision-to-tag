from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List, TypeVar, Generic
from config import Settings

T = TypeVar("T")

class BaseResponse(BaseModel, Generic[T]):
    """基础响应模型"""
    status: str = Field(default="error", description="状态 error-错误 success-成功")
    message: str = Field(default="success", description="响应消息 status=error时表示错误信息")
    task_id: Optional[str] = Field(default=None, description="任务ID")
    data: Optional[T] = Field(default=None, description="响应数据")

class VideoRequest(BaseModel):
    """视频处理请求参数"""
    url: HttpUrl

class VideoValidation(BaseModel):
    """视频验证参数"""
    # 最大文件大小（MB）
    max_size_mb: int = Settings.MAX_VIDEO_SIZE_MB
    # 支持的视频格式
    allowed_formats: List[str] = Settings.ALLOWED_VIDEO_FORMATS
