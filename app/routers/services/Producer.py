"""
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
from typing import Dict, Any
from redis import Redis
from sqlalchemy.orm import Session
from app.models.task import Task
from app.core.config import settings


class Producer:
    def __init__(self, db: Session, redis: Redis):
        self.db = db
        self.redis = redis
        self.redis.select(1)  # 切换到Redis 1号数据库

    async def dispatch(self, task_id: str, task_data: Dict[Any, Any]) -> bool:
        """
        创建视频处理任务
        :param task_id: 任务ID，由上层调用者生成
        :param task_data: 包含任务信息的字典，需要包含：
            - url: 视频URL
            - uid: 用户ID（可选）
            - platform: 平台来源
            - material_id: 素材ID
        :return: 任务创建状态
        """
        try:
            # 使用传入的task_id
            uid = task_data.get("uid", "")

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
                    f"video:task:{task_id}",
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
                pipeline.lpush("video:task:queue", task_id)
                # 执行Redis事务
                pipeline.execute()

                return True

            except Exception as e:
                pipeline.reset()
                # Redis操作失败，回滚MySQL事务
                self.db.rollback()
                raise Exception(f"Redis操作失败: {str(e)}")

        except Exception as e:
            # MySQL操作失败
            self.db.rollback()
            return False
