from fastapi import APIRouter, HTTPException, Request
from app.config.data_dict import VideoRequest, BaseResponse
from datetime import datetime
from app.services.google_vision import GoogleVisionService
from app.services.video_service import VideoService
from app.services.logger import get_logger
from app.services.Producer import Producer

import uuid
import sys
import aiohttp
import json
from typing import Tuple, Dict, Any

router = APIRouter(prefix="/task", tags=["Video"])
logger = get_logger()


async def parse_request_body(request: Request) -> Tuple[int, str, Dict[str, Any]]:
    """解析请求体"""
    try:
        params = await request.json()
        return 200, "", params
    except json.JSONDecodeError:
        return 400, "请求体必须是有效的JSON格式", {}


def validate_required_fields(params: dict) -> Tuple[int, str]:
    """验证必填参数"""
    required_fields = ["url", "platform", "material_id"]
    missing_fields = [field for field in required_fields if field not in params]
    if missing_fields:
        return 400, f"缺少必填参数: {', '.join(missing_fields)}"

    if params.get("platform") not in ["rpa", "miaobi"]:
        return 400, "platform 参数值必须是 'rpa' 或 'miaobi'"

    return 200, ""


async def validate_video(url: str) -> Tuple[int, str]:
    """验证视频的有效性、大小和格式"""
    try:
        video_service = VideoService()
        await video_service.validate_video(url)
        return 200, ""
    except HTTPException as e:
        return 400, e.detail
    except Exception as e:
        logger.error(f"视频验证失败: {str(e)}")
        return 400, "视频验证失败"


@router.post("/create", response_model=BaseResponse[dict])
async def task_create(request: Request):
    """创建视频标签队列任务"""
    task_id = str(uuid.uuid4())

    try:
        # 解析请求体
        code, message, params = await parse_request_body(request)
        if code != 200:
            return BaseResponse[dict](
                code=code, message=message, task_id=task_id, data=None
            )

        # 验证必填参数
        code, message = validate_required_fields(params)
        if code != 200:
            return BaseResponse[dict](
                code=code, message=message, task_id=task_id, data=None
            )

        # 验证视频有效性、大小、格式
        code, message = await validate_video(params["url"])
        if code != 200:
            return BaseResponse[dict](
                code=code, message=message, task_id=task_id, data=None
            )

        # 调用Producer.py，创建队列任务
        producer = Producer(request.app.state.db, request.app.state.redis)
        result = await producer.dispatch(task_id, params)

        if not result:
            return BaseResponse[dict](
                code=400, message="任务创建失败", task_id=task_id, data=None
            )

        return BaseResponse[dict](
            code=200, message="任务创建成功", task_id=task_id, data=None
        )

    except HTTPException as e:
        logger.error(f"HTTP错误: {str(e)}")
        return BaseResponse[dict](
            code=400,
            message=f"HTTP请求错误: {str(e.detail)}",
            task_id=task_id,
            data=None,
        )
    except aiohttp.ClientError as e:
        logger.error(f"网络请求错误: {str(e)}")
        return BaseResponse[dict](
            code=400, message="网络连接错误", task_id=task_id, data=None
        )
    except Exception as e:
        logger.error(f"未知错误: {str(e)}")
        return BaseResponse[dict](
            code=400, message="服务器内部错误", task_id=task_id, data=None
        )
