from pathlib import Path
import aiohttp
from fastapi import HTTPException
import ssl
import os
from config import Settings
from datetime import datetime
from app.config.data_dict import VideoValidation
from app.services.logger import get_logger

logger = get_logger()

class VideoService:
    def __init__(self):
        self.validation = VideoValidation()
        # 创建一次SSL上下文以供重用
        self.ssl_context = self._create_ssl_context()

    @staticmethod
    def _create_ssl_context() -> ssl.SSLContext:
        """创建SSL上下文"""
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    async def _create_session(self) -> aiohttp.ClientSession:
        """创建HTTP会话"""
        return aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=self.ssl_context)
        )

    async def validate_video(self, url: str) -> None:
        """
        验证视频
        1、URL是否有效
        2、视频大小
        3、视频格式
        """
        async with await self._create_session() as session:
            try:
                async with session.head(url) as response:
                    if response.status != 200:
                        raise HTTPException(status_code=400, detail="视频URL无效")

                    # 验证视频大小和格式
                    await self._validate_video_size(response)
                    await self._validate_video_format(response)
            except aiohttp.ClientError as e:
                logger.error(f"验证视频时发生错误: {e}")
                raise HTTPException(status_code=400, detail=f"视频URL访问失败: {str(e)}")

    async def get_video_size(self, url: str) -> int:
        """获取视频文件大小"""
        async with await self._create_session() as session:
            try:
                async with session.head(url) as response:
                    if response.status == 200:
                        return int(response.headers.get("content-length", 0))
                    raise HTTPException(status_code=400, detail="无法获取视频大小")
            except aiohttp.ClientError as e:
                logger.error(f"获取视频大小时发生错误: {e}")
                raise HTTPException(status_code=400, detail=f"获取视频大小失败: {str(e)}")

    async def _validate_video_size(self, response) -> None:
        """验证视频大小"""
        content_length = response.headers.get("content-length")
        if not content_length:
            logger.warning("响应头中没有content-length字段")
            return

        size_mb = int(content_length) / (1024 * 1024)
        max_size = float(self.validation.max_size_mb)
        if size_mb > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"视频大小超过{self.validation.max_size_mb}MB限制",
            )

    async def _validate_video_format(self, response) -> None:
        """验证视频格式"""
        content_type = response.headers.get("content-type", "").lower()
        if not any(fmt in content_type for fmt in self.validation.allowed_formats):
            raise HTTPException(
                status_code=400,
                detail=f"不支持的视频格式。支持的格式: {', '.join(self.validation.allowed_formats)}",
            )

    async def download_video(self, url: str, task_id: str) -> Path:
        """下载视频到指定目录"""
        video_dir = self._create_video_directory(task_id)
        filename = self._get_valid_filename(url, task_id)
        video_path = os.path.join(video_dir, filename)

        try:
            await self._download_file(url, video_path)
            logger.info(f"成功下载视频: {url} 到 {video_path}")
            return video_path
        except Exception as e:
            logger.error(f"下载视频失败: {e}")
            if video_path.exists():
                os.remove(video_path)
            raise HTTPException(status_code=500, detail=f"下载视频失败: {str(e)}")

    def _get_valid_filename(self, url: str, task_id: str) -> str:
        """从URL获取有效的文件名"""
        try:
            original_filename = url.split("/")[-1].split("?")[0]
            file_ext = original_filename.lower().split(".")[-1]
            
            if original_filename and file_ext in self.validation.allowed_formats:
                return original_filename
        except Exception as e:
            logger.warning(f"无法从URL获取有效文件名: {e}")
        
        # 默认使用task_id作为文件名
        return f"{task_id}.mp4"

    def _create_video_directory(self, task_id: str) -> Path:
        """创建视频存储目录"""
        now = datetime.now()
        video_dir = os.path.join(Settings.DOWNLOAD_DIR, now.strftime("%Y/%m"), task_id)
        os.makedirs(str(video_dir), exist_ok=True)
        return video_dir

    async def _download_file(self, url: str, file_path: Path) -> None:
        """下载文件到指定路径"""
        async with await self._create_session() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise HTTPException(status_code=400, detail=f"下载视频失败，状态码: {response.status}")
                
                with open(file_path, "wb") as f:
                    chunk_size = 8192
                    # total_size = int(response.headers.get("content-length", 0))
                    downloaded = 0

                    async for chunk in response.content.iter_chunked(chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # 每下载50%记录一次日志
                            # if total_size > 0 and downloaded % (total_size // 2) < chunk_size:
                            #     progress = (downloaded / total_size) * 100
                            #     logger.debug(f"下载进度: {progress:.1f}%")