"""
    Redis数据结构设计
        # 任务队列（List类型）
        task_queue -> List类型，存储待处理的任务ID

        # 任务详情（Hash类型）
        task_info:{taskId} -> Hash类型，存储任务详情
            - url: 视频URL
            - status: 任务状态
            - retry_count: 重试次数
            - created_at: 创建时间

        # 失败任务队列（List类型）
        task_queue_failed -> List类型，存储处理失败的任务ID

        # 任务锁（String类型）
        task_queue_lock:{taskId} -> String类型，任务处理锁，防止重复处理
"""

"""
    1、接收来自api请求的参数（task_createAPI接口的参数）
    2、将任务写入MySQL
    3、将任务写入Redis
    4、返回状态
    注意事项：
        1、写入MySQL和Redis时，需要开启事务
        2、写入Redis时，保证写入队列和写入任务详情的原子性
"""
import time
from app.services.logger import get_logger
from typing import Dict, Any
from redis import Redis
from sqlalchemy.orm import Session
from app.models.task import Task
from app.db.session import SessionLocal
from app.db.redis import get_redis_client

# 配置日志记录器
logger = get_logger()


class Producer:
    def __init__(self):
        self.db = SessionLocal()
        self.redis = get_redis_client()
        self.redis.select(1)  # 切换到Redis 1号数据库

    async def dispatch(self, task_id: str, task_data: Dict[Any, Any]) -> bool:
        """创建视频处理任务"""
        start_time = time.time()
        try:
            uid = task_data.get("uid", "")
            logger.info(
                f"【Producer】- 开始创建任务: {task_id}, 参数: url={task_data['url']}, platform={task_data['platform']}, uid={uid}"
            )

            # 1. 创建MySQL任务记录
            task = Task(
                task_id=task_id,
                uid=uid,
                url=task_data["url"],
                platform=task_data["platform"],
                status="pending",
                message=None,
                tags=None,
                processed_start=None,
                processed_end=None,
            )

            # 开启MySQL事务
            self.db.begin()
            self.db.add(task)
            self.db.flush()
            self.db.commit()

            # 2. Redis原子性操作
            pipeline = self.redis.pipeline()
            try:
                # 写入任务详情
                pipeline.hset(
                    f"task_info:{task_id}",
                    mapping={
                        "url": task_data["url"],
                        "uid": uid,
                        "platform": task_data["platform"],
                        "material_id": task_data["material_id"],
                        "status": "pending",
                        "retry_count": "0",
                        "created_at": str(int(time.time())),
                    },
                )
                # 写入任务队列
                pipeline.lpush("task_queue", task_id)
                # 执行Redis事务
                pipeline.execute()

                elapsed_time = round(time.time() - start_time, 3)
                logger.info(
                    f"【Producer】- 任务创建完成: task_id={task_id}, 耗时={elapsed_time}秒"
                )
                return True

            except Exception as e:
                pipeline.reset()
                self.db.rollback()
                logger.error(
                    f"【Producer】- Redis操作失败: task_id={task_id}, 错误信息={str(e)}"
                )
                raise Exception(f"Redis操作失败: {str(e)}")

        except Exception as e:
            self.db.rollback()
            elapsed_time = round(time.time() - start_time, 3)
            logger.error(
                f"【Producer】- MySQL操作失败: task_id={task_id}, 错误信息={str(e)}, 耗时={elapsed_time}秒"
            )
            return False
