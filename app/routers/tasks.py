from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, HttpUrl
from enum import Enum
from app.config.data_dict import BaseResponse
from app.services.video_service import VideoService
from app.services.logger import get_logger
from app.services.Producer import Producer

import uuid
import aiohttp
import json
from typing import Tuple, Dict, Any

# 定义枚举类型来限制参数值
class Platform(str, Enum):
    RPA = "rpa"
    MIAOBI = "miaobi"

class Environment(str, Enum):
    DEVELOP = "develop"
    PRODUCTION = "production"

class Dimension(str, Enum):
    VISION = "vision"
    AUDIO = "audio"
    CONTENT_SEMANTICS = "content-semantics"
    COMMERCIAL_VALUE = "commercial-value"
    ALL = "all"

# 请求模型
class TaskCreateRequest(BaseModel):
    url: HttpUrl
    platform: Platform
    env: Environment
    dismensions: Dimension

router = APIRouter(prefix="/task", tags=["Video"])
logger = get_logger()

def create_error_response(status: str, message: str, task_id: str) -> BaseResponse:
    """统一的错误响应创建函数"""
    return BaseResponse[dict](
        status=status,
        message=message,
        task_id=task_id,
        data=None
    )

@router.post("/create", response_model=BaseResponse[dict])
async def task_create(request: Request):
    """创建视频标签队列任务"""
    task_id = str(uuid.uuid4())
    
    try:
        # 解析并验证请求体
        try:
            params = await request.json()
            task_request = TaskCreateRequest(**params)
        except json.JSONDecodeError:
            return create_error_response("error", "请求体必须是有效的JSON格式", task_id)
        except ValueError as e:
            return create_error_response("error", f"参数验证错误: {str(e)}", task_id)

        # 验证视频有效性
        try:
            video_service = VideoService()
            await video_service.validate_video(str(task_request.url))
        except HTTPException as e:
            return create_error_response("error", e.detail, task_id)
        except Exception as e:
            logger.error(f"视频验证失败: {str(e)}")
            return create_error_response("error", "视频验证失败", task_id)

        # 创建队列任务
        logger.info(f"开始创建任务, params:{params}")

        producer = Producer()
        result = await producer.dispatch(task_id, task_request.dict())

        if not result:
            return create_error_response("error", "任务创建失败", task_id)

        return BaseResponse[dict](
            status="success",
            message="success",
            task_id=task_id,
            data=None
        )

    except aiohttp.ClientError as e:
        err_msg = f"网络请求错误, error: {str(e), params: {params}}"
        logger.error(err_msg)
        return create_error_response("error", err_msg, task_id)
    except Exception as e:
        err_msg = f"系统错误, error:{str(e)}, params: {params}"
        logger.error(err_msg)
        return create_error_response("error", err_msg, task_id)
