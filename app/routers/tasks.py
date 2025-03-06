from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, HttpUrl
from enum import Enum
from app.config.data_dict import BaseResponse
from app.services.video_service import VideoService
from app.services.logger import get_logger
from app.services.Producer import Producer
from app.db.db_decorators import SessionLocal, retry_on_db_error
from app.models.task import Task

import uuid
import aiohttp
import json

# 定义枚举类型来限制参数值
class Platform(str, Enum):
    # 归属 RpaConsumer
    FILE = "files"
    RPA = "rpa"
    # 归属 MiaobiConsumer
    MIAOBI = "user"

class Dimension(str, Enum):
    VISION = "vision"
    AUDIO = "audio"
    CONTENT = "content"
    BUSINESS = "business"
    ALL = "all"

# 请求模型
class TaskCreateRequest(BaseModel):
    url: HttpUrl
    platform: Platform
    dimensions: Dimension

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
    
@retry_on_db_error(max_retries=3)
@router.get("/get/{task_id}", response_model=BaseResponse[dict])
async def get_task(task_id: str):
    """获取任务详情"""
    # 验证 task_id 是否传递
    if not task_id:
        return create_error_response("error", "任务ID不能为空", None)

    # 验证 task_id 是否为有效的 UUID
    try:
        uuid.UUID(task_id)
    except ValueError:
        return create_error_response("error", "无效的任务ID格式", task_id)
    try:
        # 查询任务
        db = SessionLocal()
        task = db.query(Task).filter(Task.task_id == task_id).first()
        
        if not task:
            return create_error_response("error", f"未找到任务ID: {task_id}", task_id)
        
        # 获取所有非成功状态的消息
        error_messages = []
        if task.message:
            for dim, msg_info in task.message.items():
                if msg_info.get("status") != "success":
                    error_message = msg_info.get("message", "")
                    if error_message:
                        error_messages.append(f"{dim}: {error_message}")
        
        # 如果有错误消息，则拼接；否则使用默认成功消息
        response_message = "; ".join(error_messages) if error_messages else "success"
        
        return BaseResponse[dict](
            status=task.status,
            message=response_message,
            task_id=task_id,
            data=task.tags
        )
        
    except Exception as e:
        logger.error(f"获取任务详情失败, task_id: {task_id}, error: {str(e)}")
        return create_error_response("error", "获取任务详情失败", task_id)
