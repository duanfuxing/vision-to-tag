from pathlib import Path
import aiohttp
from fastapi import HTTPException
from datetime import datetime
import logging
from app.config.data_dict import VideoValidation
import ssl
import os
from app.services.logger import get_logger

logger = get_logger()


class VideoService:
    def __init__(self):
        self.validation = VideoValidation()

    async def validate_video_url(self, url: str) -> None:
        """验证视频URL是否有效"""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=ssl_context)
        ) as session:
            async with session.head(str(url)) as response:
                if response.status != 200:
                    raise HTTPException(status_code=400, detail="视频URL无效")

                await self._validate_video_size(response)
                await self._validate_video_format(response)

    async def _validate_video_size(self, response) -> None:
        """验证视频大小"""
        content_length = response.headers.get("content-length")
        if content_length:
            size_mb = int(content_length) / (1024 * 1024)
            if size_mb > self.validation.max_size_mb:
                raise HTTPException(
                    status_code=400,
                    detail=f"视频大小超过{self.validation.max_size_mb}MB限制",
                )

    async def _validate_video_format(self, response) -> None:
        """验证视频格式"""
        content_type = response.headers.get("content-type", "")
        if not any(
            fmt in content_type.lower() for fmt in self.validation.allowed_formats
        ):
            raise HTTPException(
                status_code=400,
                detail=f"不支持的视频格式。支持的格式: {self.validation.allowed_formats}",
            )

    async def download_video(self, url: str, task_id: str) -> Path:
        """下载视频到指定目录"""
        video_dir = self._create_video_directory(task_id)

        # 从URL中提取原始文件名
        original_filename = url.split("/")[-1].split("?")[0]
        if (
            not original_filename
            or original_filename.lower().split(".")[-1]
            not in self.validation.allowed_formats
        ):
            # 如果无法获取有效的文件名，使用任务ID作为文件名
            original_filename = f"{task_id}.mp4"

        video_path = video_dir / original_filename
        await self._download_file(url, video_path)
        return video_path

    def _create_video_directory(self, task_id: str) -> Path:
        """创建视频存储目录"""
        year = datetime.now().strftime("%Y")
        month = datetime.now().strftime("%m")
        day = datetime.now().strftime("%d")
        video_dir = Path.cwd() / "download" / year / month / day / task_id
        os.makedirs(str(video_dir), exist_ok=True)
        return video_dir

    async def _download_file(self, url: str, file_path: Path) -> None:
        """下载文件到指定路径"""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=ssl_context)
        ) as session:
            async with session.get(str(url)) as response:
                with open(file_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
