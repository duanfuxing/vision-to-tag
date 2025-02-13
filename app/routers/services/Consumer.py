import time
from typing import Dict, Any, Optional
from redis import Redis
from sqlalchemy.orm import Session
from app.models.task import Task
from app.core.config import settings
from app.services.video_service import VideoService
from app.services.google_vision import GoogleVisionService
from app.services.logger import get_logger
import json
import os

logger = get_logger()

class Consumer:
    def __init__(self, db: Session, redis: Redis):
        self.db = db
        self.redis = redis
        self.redis.select(1)  # 切换到Redis 1号数据库
        self.video_service = VideoService()
        self.vision_service = GoogleVisionService()
        self.max_retries = 3
        self.lock_timeout = 300  # 任务锁超时时间（秒）

    async def get_task(self) -> Optional[str]:
        """从Redis队列中获取任务"""
        return self.redis.rpop('video:task:queue')

    async def acquire_lock(self, task_id: str) -> bool:
        """获取任务锁"""
        lock_key = f'video:task:lock:{task_id}'
        return bool(self.redis.set(lock_key, '1', ex=self.lock_timeout, nx=True))

    async def release_lock(self, task_id: str):
        """释放任务锁"""
        lock_key = f'video:task:lock:{task_id}'
        self.redis.delete(lock_key)

    async def update_task_status(self, task_id: str, status: str, message: str = None):
        """更新任务状态"""
        # 更新Redis中的任务状态
        self.redis.hset(f'video:task:{task_id}', 'status', status)
        if message:
            self.redis.hset(f'video:task:{task_id}', 'message', message)

        # 更新MySQL中的任务状态
        task = self.db.query(Task).filter(Task.task_id == task_id).first()
        if task:
            task.status = status
            task.message = message
            if status == 'processing':
                task.processed_start = time.strftime('%Y-%m-%d %H:%M:%S')
            elif status in ['completed', 'failed']:
                task.processed_end = time.strftime('%Y-%m-%d %H:%M:%S')
            self.db.commit()

    async def increment_retry_count(self, task_id: str) -> int:
        """增加重试次数"""
        retry_key = f'video:task:{task_id}'
        return int(self.redis.hincrby(retry_key, 'retry_count', 1))

    async def move_to_failed_queue(self, task_id: str):
        """将任务移动到失败队列"""
        self.redis.lpush('video:task:failed', task_id)

    async def process_task(self, task_id: str):
        """处理单个任务"""
        try:
            # 获取任务信息
            task_info = self.redis.hgetall(f'video:task:{task_id}')
            if not task_info:
                logger.error(f'任务 {task_id} 不存在')
                return

            # 更新任务状态为处理中
            await self.update_task_status(task_id, 'processing')

            # 下载视频
            video_path = await self.video_service.download_video(task_info['url'], task_id)
            if not video_path:
                raise Exception('视频下载失败')

            try:
                # 读取prompt文件内容
                with open('app/config/prompt.txt', 'r') as f:
                    prompt = f.read()

                # 调用Google视频标签服务
                vision_response = self.vision_service.generate_tag(video_path, prompt)
                if not isinstance(vision_response, str):
                    vision_response = str(vision_response)

                # 解析响应
                tags = json.loads(vision_response.strip())

                # 更新MySQL中的标签
                task = self.db.query(Task).filter(Task.task_id == task_id).first()
                if task:
                    task.tags = tags
                    self.db.commit()

                # 更新任务状态为完成
                await self.update_task_status(task_id, 'completed')

                # 清理临时文件
                if os.path.exists(video_path):
                    os.remove(video_path)

            except Exception as e:
                logger.error(f'处理任务 {task_id} 失败: {str(e)}')
                retry_count = await self.increment_retry_count(task_id)

                if retry_count >= self.max_retries:
                    await self.move_to_failed_queue(task_id)
                    await self.update_task_status(task_id, 'failed', str(e))
                else:
                    # 重新加入队列
                    self.redis.lpush('video:task:queue', task_id)

                # 清理临时文件
                if os.path.exists(video_path):
                    os.remove(video_path)

        except Exception as e:
            logger.error(f'处理任务 {task_id} 时发生错误: {str(e)}')
            await self.update_task_status(task_id, 'failed', str(e))

        finally:
            # 释放任务锁
            await self.release_lock(task_id)

    async def run(self):
        """启动消费者服务"""
        logger.info('启动视频标签处理消费者服务')
        while True:
            try:
                # 获取任务
                task_id = await self.get_task()
                if not task_id:
                    # 队列为空，等待一段时间
                    time.sleep(1)
                    continue

                # 获取任务锁
                if not await self.acquire_lock(task_id):
                    logger.warning(f'任务 {task_id} 正在被其他进程处理')
                    continue

                # 处理任务
                await self.process_task(task_id)

            except Exception as e:
                logger.error(f'消费者服务发生错误: {str(e)}')
                time.sleep(1)
Redis数据结构设计
    # 任务队列（List类型）
    video:task:queue -> List类型，存储待处理的任务ID

    # 任务详情（Hash类型）
    video:task:{taskId} -> Hash类型，存储任务详情
        - url: 视频URL
        - status: 任务状态
        - retry_count: 重试次数
        - created_at: 创建时间

    # 失败任务队列（List类型）
    video:task:failed -> List类型，存储处理失败的任务ID

    # 任务锁（String类型）
    video:task:lock:{taskId} -> String类型，任务处理锁，防止重复处理
import time
from typing import Dict, Any, Optional
from redis import Redis
from sqlalchemy.orm import Session
from app.models.task import Task
from app.core.config import settings
from app.services.video_service import VideoService
from app.services.google_vision import GoogleVisionService
from app.services.logger import get_logger
import json
import os

logger = get_logger()

class Consumer:
    def __init__(self, db: Session, redis: Redis):
        self.db = db
        self.redis = redis
        self.redis.select(1)  # 切换到Redis 1号数据库
        self.video_service = VideoService()
        self.vision_service = GoogleVisionService()
        self.max_retries = 3
        self.lock_timeout = 300  # 任务锁超时时间（秒）

    async def get_task(self) -> Optional[str]:
        """从Redis队列中获取任务"""
        return self.redis.rpop('video:task:queue')

    async def acquire_lock(self, task_id: str) -> bool:
        """获取任务锁"""
        lock_key = f'video:task:lock:{task_id}'
        return bool(self.redis.set(lock_key, '1', ex=self.lock_timeout, nx=True))

    async def release_lock(self, task_id: str):
        """释放任务锁"""
        lock_key = f'video:task:lock:{task_id}'
        self.redis.delete(lock_key)

    async def update_task_status(self, task_id: str, status: str, message: str = None):
        """更新任务状态"""
        # 更新Redis中的任务状态
        self.redis.hset(f'video:task:{task_id}', 'status', status)
        if message:
            self.redis.hset(f'video:task:{task_id}', 'message', message)

        # 更新MySQL中的任务状态
        task = self.db.query(Task).filter(Task.task_id == task_id).first()
        if task:
            task.status = status
            task.message = message
            if status == 'processing':
                task.processed_start = time.strftime('%Y-%m-%d %H:%M:%S')
            elif status in ['completed', 'failed']:
                task.processed_end = time.strftime('%Y-%m-%d %H:%M:%S')
            self.db.commit()

    async def increment_retry_count(self, task_id: str) -> int:
        """增加重试次数"""
        retry_key = f'video:task:{task_id}'
        return int(self.redis.hincrby(retry_key, 'retry_count', 1))

    async def move_to_failed_queue(self, task_id: str):
        """将任务移动到失败队列"""
        self.redis.lpush('video:task:failed', task_id)

    async def process_task(self, task_id: str):
        """处理单个任务"""
        try:
            # 获取任务信息
            task_info = self.redis.hgetall(f'video:task:{task_id}')
            if not task_info:
                logger.error(f'任务 {task_id} 不存在')
                return

            # 更新任务状态为处理中
            await self.update_task_status(task_id, 'processing')

            # 下载视频
            video_path = await self.video_service.download_video(task_info['url'], task_id)
            if not video_path:
                raise Exception('视频下载失败')

            try:
                # 读取prompt文件内容
                with open('app/config/prompt.txt', 'r') as f:
                    prompt = f.read()

                # 调用Google视频标签服务
                vision_response = self.vision_service.generate_tag(video_path, prompt)
                if not isinstance(vision_response, str):
                    vision_response = str(vision_response)

                # 解析响应
                tags = json.loads(vision_response.strip())

                # 更新MySQL中的标签
                task = self.db.query(Task).filter(Task.task_id == task_id).first()
                if task:
                    task.tags = tags
                    self.db.commit()

                # 更新任务状态为完成
                await self.update_task_status(task_id, 'completed')

                # 清理临时文件
                if os.path.exists(video_path):
                    os.remove(video_path)

            except Exception as e:
                logger.error(f'处理任务 {task_id} 失败: {str(e)}')
                retry_count = await self.increment_retry_count(task_id)

                if retry_count >= self.max_retries:
                    await self.move_to_failed_queue(task_id)
                    await self.update_task_status(task_id, 'failed', str(e))
                else:
                    # 重新加入队列
                    self.redis.lpush('video:task:queue', task_id)

                # 清理临时文件
                if os.path.exists(video_path):
                    os.remove(video_path)

        except Exception as e:
            logger.error(f'处理任务 {task_id} 时发生错误: {str(e)}')
            await self.update_task_status(task_id, 'failed', str(e))

        finally:
            # 释放任务锁
            await self.release_lock(task_id)

    async def run(self):
        """启动消费者服务"""
        logger.info('启动视频标签处理消费者服务')
        while True:
            try:
                # 获取任务
                task_id = await self.get_task()
                if not task_id:
                    # 队列为空，等待一段时间
                    time.sleep(1)
                    continue

                # 获取任务锁
                if not await self.acquire_lock(task_id):
                    logger.warning(f'任务 {task_id} 正在被其他进程处理')
                    continue

                # 处理任务
                await self.process_task(task_id)

            except Exception as e:
                logger.error(f'消费者服务发生错误: {str(e)}')
                time.sleep(1)

import time
from typing import Dict, Any, Optional
from redis import Redis
from sqlalchemy.orm import Session
from app.models.task import Task
from app.core.config import settings
from app.services.video_service import VideoService
from app.services.google_vision import GoogleVisionService
from app.services.logger import get_logger
import json
import os

logger = get_logger()

class Consumer:
    def __init__(self, db: Session, redis: Redis):
        self.db = db
        self.redis = redis
        self.redis.select(1)  # 切换到Redis 1号数据库
        self.video_service = VideoService()
        self.vision_service = GoogleVisionService()
        self.max_retries = 3
        self.lock_timeout = 300  # 任务锁超时时间（秒）

    async def get_task(self) -> Optional[str]:
        """从Redis队列中获取任务"""
        return self.redis.rpop('video:task:queue')

    async def acquire_lock(self, task_id: str) -> bool:
        """获取任务锁"""
        lock_key = f'video:task:lock:{task_id}'
        return bool(self.redis.set(lock_key, '1', ex=self.lock_timeout, nx=True))

    async def release_lock(self, task_id: str):
        """释放任务锁"""
        lock_key = f'video:task:lock:{task_id}'
        self.redis.delete(lock_key)

    async def update_task_status(self, task_id: str, status: str, message: str = None):
        """更新任务状态"""
        # 更新Redis中的任务状态
        self.redis.hset(f'video:task:{task_id}', 'status', status)
        if message:
            self.redis.hset(f'video:task:{task_id}', 'message', message)

        # 更新MySQL中的任务状态
        task = self.db.query(Task).filter(Task.task_id == task_id).first()
        if task:
            task.status = status
            task.message = message
            if status == 'processing':
                task.processed_start = time.strftime('%Y-%m-%d %H:%M:%S')
            elif status in ['completed', 'failed']:
                task.processed_end = time.strftime('%Y-%m-%d %H:%M:%S')
            self.db.commit()

    async def increment_retry_count(self, task_id: str) -> int:
        """增加重试次数"""
        retry_key = f'video:task:{task_id}'
        return int(self.redis.hincrby(retry_key, 'retry_count', 1))

    async def move_to_failed_queue(self, task_id: str):
        """将任务移动到失败队列"""
        self.redis.lpush('video:task:failed', task_id)

    async def process_task(self, task_id: str):
        """处理单个任务"""
        try:
            # 获取任务信息
            task_info = self.redis.hgetall(f'video:task:{task_id}')
            if not task_info:
                logger.error(f'任务 {task_id} 不存在')
                return

            # 更新任务状态为处理中
            await self.update_task_status(task_id, 'processing')

            # 下载视频
            video_path = await self.video_service.download_video(task_info['url'], task_id)
            if not video_path:
                raise Exception('视频下载失败')

            try:
                # 读取prompt文件内容
                with open('app/config/prompt.txt', 'r') as f:
                    prompt = f.read()

                # 调用Google视频标签服务
                vision_response = self.vision_service.generate_tag(video_path, prompt)
                if not isinstance(vision_response, str):
                    vision_response = str(vision_response)

                # 解析响应
                tags = json.loads(vision_response.strip())

                # 更新MySQL中的标签
                task = self.db.query(Task).filter(Task.task_id == task_id).first()
                if task:
                    task.tags = tags
                    self.db.commit()

                # 更新任务状态为完成
                await self.update_task_status(task_id, 'completed')

                # 清理临时文件
                if os.path.exists(video_path):
                    os.remove(video_path)

            except Exception as e:
                logger.error(f'处理任务 {task_id} 失败: {str(e)}')
                retry_count = await self.increment_retry_count(task_id)

                if retry_count >= self.max_retries:
                    await self.move_to_failed_queue(task_id)
                    await self.update_task_status(task_id, 'failed', str(e))
                else:
                    # 重新加入队列
                    self.redis.lpush('video:task:queue', task_id)

                # 清理临时文件
                if os.path.exists(video_path):
                    os.remove(video_path)

        except Exception as e:
            logger.error(f'处理任务 {task_id} 时发生错误: {str(e)}')
            await self.update_task_status(task_id, 'failed', str(e))

        finally:
            # 释放任务锁
            await self.release_lock(task_id)

    async def run(self):
        """启动消费者服务"""
        logger.info('启动视频标签处理消费者服务')
        while True:
            try:
                # 获取任务
                task_id = await self.get_task()
                if not task_id:
                    # 队列为空，等待一段时间
                    time.sleep(1)
                    continue

                # 获取任务锁
                if not await self.acquire_lock(task_id):
                    logger.warning(f'任务 {task_id} 正在被其他进程处理')
                    continue

                # 处理任务
                await self.process_task(task_id)

            except Exception as e:
                logger.error(f'消费者服务发生错误: {str(e)}')
                time.sleep(1)
消费者逻辑
    1. 从Redis获取任务（原子操作）
    2. 获取任务锁
    3. 更新任务状态为处理中
    4. 获取任务信息
    5. 下载视频
    6. 调用Google视频标签服务
    7. 更新MySQL中的标签
    8. 调用ES入库服务
    9. 清理处理队列
    10. 更新任务状态为完成
    注意事项：
        错误处理：重试或进入死信队列
        资源释放：关闭数据库连接、清理临时文件
        使用 Supervisor 管理多进程
        日志记录关键操作（下载、标签服务调用、错误）
import time
from typing import Dict, Any, Optional
from redis import Redis
from sqlalchemy.orm import Session
from app.models.task import Task
from app.core.config import settings
from app.services.video_service import VideoService
from app.services.google_vision import GoogleVisionService
from app.services.logger import get_logger
import json
import os

logger = get_logger()

class Consumer:
    def __init__(self, db: Session, redis: Redis):
        self.db = db
        self.redis = redis
        self.redis.select(1)  # 切换到Redis 1号数据库
        self.video_service = VideoService()
        self.vision_service = GoogleVisionService()
        self.max_retries = 3
        self.lock_timeout = 300  # 任务锁超时时间（秒）

    async def get_task(self) -> Optional[str]:
        """从Redis队列中获取任务"""
        return self.redis.rpop('video:task:queue')

    async def acquire_lock(self, task_id: str) -> bool:
        """获取任务锁"""
        lock_key = f'video:task:lock:{task_id}'
        return bool(self.redis.set(lock_key, '1', ex=self.lock_timeout, nx=True))

    async def release_lock(self, task_id: str):
        """释放任务锁"""
        lock_key = f'video:task:lock:{task_id}'
        self.redis.delete(lock_key)

    async def update_task_status(self, task_id: str, status: str, message: str = None):
        """更新任务状态"""
        # 更新Redis中的任务状态
        self.redis.hset(f'video:task:{task_id}', 'status', status)
        if message:
            self.redis.hset(f'video:task:{task_id}', 'message', message)

        # 更新MySQL中的任务状态
        task = self.db.query(Task).filter(Task.task_id == task_id).first()
        if task:
            task.status = status
            task.message = message
            if status == 'processing':
                task.processed_start = time.strftime('%Y-%m-%d %H:%M:%S')
            elif status in ['completed', 'failed']:
                task.processed_end = time.strftime('%Y-%m-%d %H:%M:%S')
            self.db.commit()

    async def increment_retry_count(self, task_id: str) -> int:
        """增加重试次数"""
        retry_key = f'video:task:{task_id}'
        return int(self.redis.hincrby(retry_key, 'retry_count', 1))

    async def move_to_failed_queue(self, task_id: str):
        """将任务移动到失败队列"""
        self.redis.lpush('video:task:failed', task_id)

    async def process_task(self, task_id: str):
        """处理单个任务"""
        try:
            # 获取任务信息
            task_info = self.redis.hgetall(f'video:task:{task_id}')
            if not task_info:
                logger.error(f'任务 {task_id} 不存在')
                return

            # 更新任务状态为处理中
            await self.update_task_status(task_id, 'processing')

            # 下载视频
            video_path = await self.video_service.download_video(task_info['url'], task_id)
            if not video_path:
                raise Exception('视频下载失败')

            try:
                # 读取prompt文件内容
                with open('app/config/prompt.txt', 'r') as f:
                    prompt = f.read()

                # 调用Google视频标签服务
                vision_response = self.vision_service.generate_tag(video_path, prompt)
                if not isinstance(vision_response, str):
                    vision_response = str(vision_response)

                # 解析响应
                tags = json.loads(vision_response.strip())

                # 更新MySQL中的标签
                task = self.db.query(Task).filter(Task.task_id == task_id).first()
                if task:
                    task.tags = tags
                    self.db.commit()

                # 更新任务状态为完成
                await self.update_task_status(task_id, 'completed')

                # 清理临时文件
                if os.path.exists(video_path):
                    os.remove(video_path)

            except Exception as e:
                logger.error(f'处理任务 {task_id} 失败: {str(e)}')
                retry_count = await self.increment_retry_count(task_id)

                if retry_count >= self.max_retries:
                    await self.move_to_failed_queue(task_id)
                    await self.update_task_status(task_id, 'failed', str(e))
                else:
                    # 重新加入队列
                    self.redis.lpush('video:task:queue', task_id)

                # 清理临时文件
                if os.path.exists(video_path):
                    os.remove(video_path)

        except Exception as e:
            logger.error(f'处理任务 {task_id} 时发生错误: {str(e)}')
            await self.update_task_status(task_id, 'failed', str(e))

        finally:
            # 释放任务锁
            await self.release_lock(task_id)

    async def run(self):
        """启动消费者服务"""
        logger.info('启动视频标签处理消费者服务')
        while True:
            try:
                # 获取任务
                task_id = await self.get_task()
                if not task_id:
                    # 队列为空，等待一段时间
                    time.sleep(1)
                    continue

                # 获取任务锁
                if not await self.acquire_lock(task_id):
                    logger.warning(f'任务 {task_id} 正在被其他进程处理')
                    continue

                # 处理任务
                await self.process_task(task_id)

            except Exception as e:
                logger.error(f'消费者服务发生错误: {str(e)}')
                time.sleep(1)
