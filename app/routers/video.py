from fastapi import APIRouter, HTTPException, Request
from app.config.data_dict import VideoRequest, BaseResponse
from app.services.google_vision import GoogleVisionService, GoogleTagGenerationError
from app.services.video_service import VideoService
from app.services.logger import get_logger
from config import Settings
from functools import wraps
import uuid
import aiohttp
import json
import time

router = APIRouter(prefix="/vision_to_tag", tags=["Video"])
logger = get_logger()

def handle_google_errors(func):
    """处理Google服务相关的异常装饰器"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except json.JSONDecodeError:
            logger.error("模型响应格式错误，无法解析为JSON")
            return BaseResponse[dict](
                status="error", message="模型响应格式错误"
            )
        except GoogleTagGenerationError as e:
            # 这些错误已经经过重试机制处理，可以直接返回错误
            logger.error(f"Google服务错误: {str(e)}")
            return BaseResponse[dict](
                status="error", message=str(e)
            )
        except (ConnectionError, TimeoutError) as e:
            # 网络相关错误，让内层重试机制处理
            raise
        except Exception as e:
            logger.error(f"未预期的错误: {str(e)}")
            return BaseResponse[dict](
                status="error", message="服务器内部错误，请稍后重试"
            )
    return wrapper

# 单接口无状态同步版
@router.post("/google", response_model=BaseResponse[dict])
@handle_google_errors
async def generate_video_tags(request: Request):
    try:
        # 解析请求体
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return BaseResponse[dict](
                status="error", message="请求体必须是有效的JSON格式"
            )

        # 验证视频地址参数
        if not body or "url" not in body:
            return BaseResponse[dict](
                status="error", message="缺少必填参数'url'"
            )
        # 验证视频打标签的提示词维度参数
        if not body or "dimensions" not in body or body["dimensions"] not in Settings.VIDEO_DIMENSIONS + ["all"]:
            return BaseResponse[dict](
                status="error", message="缺少必填参数'dimensions'或值不合法"
            )
        
        try:
            video_request = VideoRequest(**body)
        except ValueError as e:
            error_msg = str(e)
            if "url" in error_msg.lower():
                if "not a valid url" in error_msg.lower():
                    return BaseResponse[dict](
                        status="error",
                        message="请提供有效的视频URL地址",
                        task_id="",
                        data=None,
                    )
                return BaseResponse[dict](
                    status="error", message="视频URL格式不正确"
                )
            return BaseResponse[dict](
                status="error", message=f"请求参数验证失败: {str(e)}"
            )

        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 验证视频URL和格式
        try:
            video_service = VideoService()
            await video_service.validate_video(str(video_request.url))
        except HTTPException as e:
            return BaseResponse[dict](
                status="error", message="视频无法访问或视频格式错误"
            )

        # 下载视频
        try:
            video_path = await video_service.download_video(
                str(video_request.url), task_id
            )
        except Exception as e:
            logger.error(f"视频下载失败: {str(e)}")
            return BaseResponse[dict](
                status="error",
                message="视频下载失败，请检查URL是否可访问",
                task_id="",
                data=None,
            )

        # 调用 Google 服务生成标签
        google_file = None
        try:
            # 实例化 GoogleVisionService 服务
            vision_service = GoogleVisionService()
            # 上传文件
            google_file = vision_service.upload_file(video_path)
            logger.info(f"【video-router】上传文件成功:{video_path}")
            dimensions = body["dimensions"]
            # 全部维度的标签生成
            if dimensions == "all":
                # 按顺序处理四个维度的标签生成
                dimension_list = Settings.VIDEO_DIMENSIONS
                merged_tags = {}
                
                for dim in dimension_list:
                    dim_start = time.time()
                    response = vision_service.generate_tag(google_file, dim)
                    dim_time = round(time.time() - dim_start, 3)
                    logger.info(f"【video-router】- {dim} 维度处理完成，耗时={dim_time}秒")
                    
                    if not isinstance(response, str):
                        response = str(response)
                    merged_tags[dim] = json.loads(response.strip())
                
                vision_response = json.dumps(merged_tags)
            else:
                # 单一维度的标签生成
                vision_response = vision_service.generate_tag(google_file, dimensions)
                if not isinstance(vision_response, str):
                    vision_response = str(vision_response)

            # 解析响应为JSON格式
            if not isinstance(vision_response, str):
                vision_response = str(vision_response)

            # 移除首尾空白字符
            response_data = json.loads(vision_response.strip())

            return BaseResponse[dict](
                status="success", message="成功", task_id=task_id, data=response_data
            )
        except json.JSONDecodeError:
            logger.error("模型响应格式错误，无法解析为JSON")
            return BaseResponse[dict](
                status="error", message="模型响应格式错误"
            )
        except GoogleTagGenerationError as e:
            # 这些错误已经经过重试机制处理，可以直接返回错误
            logger.error(f"Google服务错误: {str(e)}")
            return BaseResponse[dict](
                status="error", message=str(e)
            )
        except (ConnectionError, TimeoutError) as e:
            # 网络相关错误，让内层重试机制处理
            raise
        # 清理文件
        finally:
            if google_file:  # 确保 google_file 已成功赋值
                vision_service.delete_google_file(google_file=google_file)
            # 测试时关闭
            # 删除本地临时文件
            vision_service.delete_local_file(file_path=video_path)

    except HTTPException as e:
        logger.error(f"HTTP错误: {str(e)}")
        return BaseResponse[dict](
            code=e.status_code, message=e.detail
        )
    except aiohttp.ClientError as e:
        logger.error(f"网络请求错误: {str(e)}")
        return BaseResponse[dict](
            status="error", message="视频处理失败，请检查网络连接"
        )
    except Exception as e:
        logger.error(f"未知错误: {str(e)}")
        return BaseResponse[dict](
            status="error", message="服务器内部错误"
        )
