import time
import asyncio
from typing import Dict, Any, Optional
from redis import Redis
from sqlalchemy.orm import Session
from app.db.db_decorators import SessionLocal, retry_on_db_error
from app.db.redis_decorators import get_redis_client, retry_on_redis_error
from app.models.task import Task
from app.services.video_service import VideoService
from app.services.google_vision import GoogleVisionService
from app.services.logger import get_logger
import json
import os
import requests

logger = get_logger()


class RpaConsumer:
    def __init__(self, db: Session, redis: Redis):
        self.db = db
        self.redis = redis
        self.redis.select(1)  # 切换到Redis 1号数据库
        self.video_service = VideoService()  # 初始化视频服务
        self.max_retries = 30  # 最大重试次数
        self.lock_timeout = 300  # 任务锁超时时间（秒）
        self.platform = "rpa"  # 平台标识

    @retry_on_redis_error(max_retries=3, base_delay=1, db_number=1)
    async def get_task(self) -> Optional[str]:
        """从Redis队列中获取任务"""
        return self.redis.rpop(f"{self.platform}:task_queue")

    @retry_on_redis_error(max_retries=3, base_delay=1, db_number=1)
    async def acquire_lock(self, task_id: str) -> bool:
        """获取任务锁"""
        lock_key = f"{self.platform}:task_queue_lock:{task_id}"
        return bool(self.redis.set(lock_key, "1", ex=self.lock_timeout, nx=True))

    @retry_on_redis_error(max_retries=3, base_delay=1, db_number=1)
    async def release_lock(self, task_id: str):
        """释放任务锁"""
        lock_key = f"{self.platform}:task_queue_lock:{task_id}"
        self.redis.delete(lock_key)

    @retry_on_db_error(max_retries=3, base_delay=1)
    async def update_task_status(self, task_id: str, status: str, message: str = None):
        """更新任务状态"""
        try:
            # 更新Redis中的任务状态
            self.redis.hset(f"{self.platform}:task_info:{task_id}", "status", status)
            if message:
                self.redis.hset(
                    f"{self.platform}:task_info:{task_id}", "message", message
                )

            # 更新MySQL中的任务状态
            task = self.db.query(Task).filter(Task.task_id == task_id).first()
            if task:
                task.status = status
                task.message = message
                if status == "processing":
                    task.processed_start = time.strftime("%Y-%m-%d %H:%M:%S")
                elif status in ["completed", "failed"]:
                    task.processed_end = time.strftime("%Y-%m-%d %H:%M:%S")
                self.db.commit()
        except Exception as e:
            logger.error(f"【RpaConsumer】- 更新任务状态失败 {task_id}: {str(e)}")
            raise

    @retry_on_redis_error(max_retries=3, base_delay=1, db_number=1)
    async def increment_retry_count(self, task_id: str) -> int:
        """增加重试次数"""
        retry_key = f"{self.platform}:task_info:{task_id}"
        return int(self.redis.hincrby(retry_key, "retry_count", 1))

    @retry_on_redis_error(max_retries=3, base_delay=1, db_number=1)
    async def move_to_failed_queue(self, task_id: str):
        """将任务移动到失败队列"""
        self.redis.lpush(f"{self.platform}:task_queue_failed", task_id)

    # 下载视频
    async def download_video(self, task_id: str, url: str) -> str:
        """下载视频文件"""
        download_start = time.time()
        video_path = await self.video_service.download_video(url, task_id)
        if not video_path:
            error_msg = f"【RpaConsumer】- 视频下载失败: task_id={task_id}, url={url}"
            logger.error(error_msg)
            # 更新任务状态为错误
            await self.update_task_status(task_id, "failed", error_msg)
            raise Exception(error_msg)
        download_time = round(time.time() - download_start, 3)
        logger.info(
            f"【RpaConsumer】- 视频下载成功: {video_path}, 耗时={download_time}秒"
        )
        return video_path

    async def generate_video_tags(self, task_id: str, video_path: str) -> dict:
        """生成视频标签"""
        logger.info(f"【RpaConsumer】- 解析视频标签开始: task_id={task_id}")
        with open("app/config/prompt.txt", "r") as f:
            prompt = f.read()

        vision_start = time.time()
        try:
            google_vision_service = GoogleVisionService()  # 初始化Google视频标签服务
            vision_response = google_vision_service.generate_tag(video_path, prompt)
            if not isinstance(vision_response, str):
                vision_response = str(vision_response)
        except Exception as e:
            error_msg = (
                f"【RpaConsumer】- 生成视频标签失败: task_id={task_id}, error={str(e)}"
            )
            logger.error(error_msg)
            raise Exception(error_msg)
        vision_time = round(time.time() - vision_start, 3)
        logger.info(
            f"【RpaConsumer】- 获取视频标签成功: task_id={task_id}, 耗时={vision_time}秒"
        )

        return json.loads(vision_response.strip())

    async def sync_tags_to_es(self, task_id: str, task_info: str, tags: dict) -> None:
        """同步标签到ES服务"""
        sync_start = time.time()
        logger.info(f"【RpaConsumer】- 开始同步标签到ES: task_info={task_info}")
        try:
            # 验证tags数据格式
            if not isinstance(tags, dict):
                error_msg = f"【RpaConsumer】- 标签数据格式错误，期望dict类型: task_id={task_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            if not tags:
                error_msg = f"【RpaConsumer】- 标签数据为空: task_id={task_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # 根据task_info['env']选择ES API URL
            if task_info.get("env") == "production":
                es_api_url = os.getenv("ES_API_URL_PROD")
            else:
                es_api_url = os.getenv("ES_API_URL_DEVE")

            if not es_api_url:
                error_msg = f"【RpaConsumer】- ES_API_URL环境变量未配置，请检查.env文件: task_id={task_id}"
                logger.error(error_msg)
                raise Exception(error_msg)

            # 构造请求数据
            material_ids = (
                json.loads(task_info["material_id"]) if task_info["material_id"] else []
            )
            if not isinstance(material_ids, list):
                material_ids = [material_ids]

            request_data = {
                "material_ids": material_ids,
                "tags": tags,
            }

            response = requests.request(
                "POST",
                es_api_url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(request_data),
                timeout=300,
            )
            response.raise_for_status()

            resp_data = response.json()
            if resp_data.get("code") != 10000:
                error_msg = (
                    f"ES入库失败: task_id={task_id}, message={resp_data.get('message')}"
                )
                logger.error(error_msg)
                raise Exception(error_msg)

            sync_time = round(time.time() - sync_start, 3)
            logger.info(
                f"【RpaConsumer】- 同步标签到ES成功: task_id={task_id}, 耗时={sync_time}秒"
            )

        except requests.exceptions.Timeout:
            error_msg = f"【RpaConsumer】- ES入库服务请求超时: task_id={task_id}"
            logger.error(error_msg)
            raise Exception(error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = f"【RpaConsumer】- ES入库服务请求异常: task_id={task_id}, error={str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)
        except ValueError as e:
            error_msg = f"【RpaConsumer】- ES入库服务响应解析失败: task_id={task_id}, error={str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    @retry_on_db_error(max_retries=3, base_delay=1)
    async def update_mysql_tags(self, task_id: str, tags: dict) -> None:
        """更新MySQL中的标签"""
        update_start = time.time()
        task = self.db.query(Task).filter(Task.task_id == task_id).first()
        if task:
            try:
                task.tags = tags
                self.db.commit()
                update_time = round(time.time() - update_start, 3)
                logger.info(
                    f"【RpaConsumer】- DB更新标签成功: task_id={task_id}, 耗时={update_time}秒"
                )
            except Exception as e:
                error_msg = f"【RpaConsumer】- 更新MySQL标签失败: task_id={task_id}, error={str(e)}"
                logger.error(error_msg)
                raise Exception(error_msg)

    async def process_task(self, task_id: str):
        """处理单个任务"""
        video_path = None
        start_time = time.time()
        try:
            # 获取任务信息
            task_info = None
            retry_count = 0
            while retry_count < 3:
                try:
                    task_info = self.redis.hgetall(
                        f"{self.platform}:task_info:{task_id}"
                    )
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count == 3:
                        raise
                    logger.warning(
                        f"【RpaConsumer】- 获取任务信息重试 {retry_count}/3: {str(e)}"
                    )
                    await asyncio.sleep(1)

            if not task_info:
                logger.error(f"【RpaConsumer】- 任务 {task_id} 不存在")
                return

            # 更新任务状态为处理中
            await self.update_task_status(task_id, "processing")
            logger.info(
                f"【RpaConsumer】- 开始处理任务: {task_id}, 视频URL: {task_info.get('url')}"
            )

            try:
                # 下载视频
                video_path = await self.download_video(task_id, task_info["url"])

                # 生成视频标签
                tags = await self.generate_video_tags(task_id, video_path)
                logger.info(f"【RpaConsumer】- 生成视频标签成功: {tags}")

                # 同步标签到ES
                await self.sync_tags_to_es(task_id, task_info, tags)

                # 更新MySQL中的标签
                await self.update_mysql_tags(task_id, tags)

                # 更新任务状态为完成
                await self.update_task_status(task_id, "completed", "success")
                total_time = round(time.time() - start_time, 3)
                logger.info(
                    f"【RpaConsumer】- 任务处理完成: task_id={task_id}, 总耗时={total_time}秒"
                )

                # 删除Redis中的任务信息
                self.redis.delete(f"{self.platform}:task_info:{task_id}")

            except Exception as e:
                logger.error(f"【RpaConsumer】- 处理任务 {task_id} 失败: {str(e)}")
                retry_count = await self.increment_retry_count(task_id)

                if retry_count >= self.max_retries:
                    await self.move_to_failed_queue(task_id)
                    await self.update_task_status(task_id, "failed", str(e))
                    logger.error(
                        f"【RpaConsumer】- 任务 {task_id} 达到最大重试次数({self.max_retries})，移入失败队列"
                    )
                else:
                    # 重新加入队列
                    self.redis.lpush(f"{self.platform}:task_queue", task_id)
                    logger.warning(
                        f"【RpaConsumer】- 任务 {task_id} 重试次数: {retry_count}/{self.max_retries}"
                    )
                raise

        except Exception as e:
            logger.error(f"【RpaConsumer】- 处理任务 {task_id} 时发生错误: {str(e)}")
            await self.update_task_status(task_id, "failed", str(e))

        finally:
            # 清理临时文件
            if video_path and os.path.exists(video_path):
                try:
                    os.remove(video_path)
                    logger.info(f"【RpaConsumer】- 清理临时文件成功: {video_path}")
                except Exception as e:
                    logger.error(f"清理临时文件失败 {video_path}: {str(e)}")
            # 释放任务锁
            await self.release_lock(task_id)

    async def run(self):
        """启动消费者服务"""
        logger.info("【RpaConsumer】- 启动视频标签处理消费者服务")
        while True:
            try:
                # 获取任务
                task_id = await self.get_task()
                if not task_id:
                    # 队列为空，等待一段时间
                    await asyncio.sleep(1)
                    continue

                # 获取任务锁
                if not await self.acquire_lock(task_id):
                    logger.warning(
                        f"【RpaConsumer】- 任务 {task_id} 正在被其他进程处理"
                    )
                    continue

                # 处理任务
                await self.process_task(task_id)

            except Exception as e:
                logger.error(f"【RpaConsumer】- 消费者服务发生错误: {str(e)}")
                await asyncio.sleep(1)

    @classmethod
    async def main(cls):
        """主入口函数"""
        db = None
        redis_client = None
        try:
            # 创建数据库会话和Redis客户端
            db = SessionLocal()
            redis_client = get_redis_client()

            # 创建消费者实例
            consumer = cls(db, redis_client)

            # 运行异步任务
            await consumer.run()
        except Exception as e:
            logger.error(f"【RpaConsumer】- 启动消费者失败: {str(e)}")
            raise
        finally:
            # 关闭数据库连接
            if db:
                db.close()


if __name__ == "__main__":
    asyncio.run(RpaConsumer.main())
