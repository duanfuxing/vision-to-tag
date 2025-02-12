from fastapi import APIRouter, HTTPException, Request
from app.config.data_dict import VideoRequest, BaseResponse
from datetime import datetime
from app.services.google_vision import GoogleVisionService
from app.services.video_service import VideoService
from app.services.logger import get_logger
import uuid
import sys
import aiohttp
import json

router = APIRouter(prefix="/vision_to_tag", tags=["Video"])
logger = get_logger()


@router.post("/google", response_model=BaseResponse[dict])
async def generate_video_tags(request: Request):
    try:
        # 解析请求体
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return BaseResponse[dict](
                code=400, message="请求体必须是有效的JSON格式", task_id="", data=None
            )

        # 验证必填参数
        if not body or "url" not in body:
            return BaseResponse[dict](
                code=400, message="缺少必填参数'url'", task_id="", data=None
            )

        try:
            video_request = VideoRequest(**body)
        except ValueError as e:
            error_msg = str(e)
            if "url" in error_msg.lower():
                if "not a valid url" in error_msg.lower():
                    return BaseResponse[dict](
                        code=400,
                        message="请提供有效的视频URL地址",
                        task_id="",
                        data=None,
                    )
                return BaseResponse[dict](
                    code=400, message="视频URL格式不正确", task_id="", data=None
                )
            return BaseResponse[dict](
                code=400, message=f"请求参数验证失败: {str(e)}", task_id="", data=None
            )

        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 验证视频URL和格式
        try:
            video_service = VideoService()
            await video_service.validate_video_url(str(video_request.url))
        except HTTPException as e:
            return BaseResponse[dict](
                code=500, message="视频无法访问或视频格式错误", task_id="", data=None
            )

        # 下载视频
        try:
            video_path = await video_service.download_video(
                str(video_request.url), task_id
            )
        except Exception as e:
            logger.error(f"视频下载失败: {str(e)}")
            return BaseResponse[dict](
                code=500,
                message="视频下载失败，请检查URL是否可访问",
                task_id="",
                data=None,
            )

        # 调用Google服务生成标签
        try:
            vision_service = GoogleVisionService()
            # 读取prompt文件内容
            with open("app/config/prompt.txt", "r") as f:
                prompt = f.read()
            vision_response = vision_service.generate_tag(video_path, prompt)

            logger.info(f"模型响应类型: {type(vision_response)}")
            logger.info(f"模型响应内容: {vision_response}")

            # 解析响应为JSON格式
            if not isinstance(vision_response, str):
                vision_response = str(vision_response)

            # 移除首尾空白字符
            response_data = json.loads(vision_response.strip())

            return BaseResponse[dict](
                code=200, message="成功", task_id=task_id, data=response_data
            )
        except json.JSONDecodeError:
            logger.error("模型响应格式错误，无法解析为JSON")
            return BaseResponse[dict](
                code=500, message="模型响应格式错误", task_id="", data=None
            )
        except Exception as e:
            logger.error(f"标签生成失败: {str(e)}")
            return BaseResponse[dict](
                code=500, message="视频标签生成失败，请稍后重试", task_id="", data=None
            )

    except HTTPException as e:
        logger.error(f"HTTP错误: {str(e)}")
        return BaseResponse[dict](
            code=e.status_code, message=e.detail, task_id="", data=None
        )
    except aiohttp.ClientError as e:
        logger.error(f"网络请求错误: {str(e)}")
        return BaseResponse[dict](
            code=500, message="视频处理失败，请检查网络连接", task_id="", data=None
        )
    except Exception as e:
        logger.error(f"未知错误: {str(e)}")
        return BaseResponse[dict](
            code=500, message="服务器内部错误", task_id="", data=None
        )
