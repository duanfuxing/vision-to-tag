import time
from app.services.logger import get_logger
from typing import Dict, Any
from app.models.task import Task
from app.db.db_decorators import SessionLocal, retry_on_db_error
from app.db.redis_decorators import get_redis_client
import json

# 配置日志记录器
logger = get_logger()


class Producer:
    def __init__(self):
        self.db = SessionLocal()
        self.redis = get_redis_client()
        self.redis.select(1)  # 切换到Redis 1号数据库

    @retry_on_db_error(max_retries=3, base_delay=1)
    async def dispatch(self, task_id: str, task_data: Dict[Any, Any]) -> bool:
        """创建视频处理任务"""
        start_time = time.time()
        try:
            uid = task_data.get("uid", "")
            material_ids = json.dumps(task_data["material_id"])
            logger.info(
                f"【Producer-{task_data['platform']}】- 开始创建任务: {task_id}, 参数: {task_data}"
            )

            # 1. 创建MySQL任务记录
            task = Task(
                task_id=task_id,
                uid=uid,
                url=task_data["url"],
                platform=task_data["platform"],
                env=task_data["env"],
                status="pending",
                dismensions=task_data["dismensions"],
                message=None,
                tags=None,
                material_id=material_ids
            )

            # 开启MySQL事务
            self.db.begin()
            self.db.add(task)
            self.db.flush()
            self.db.commit()

            # 2. Redis原子性操作
            pipeline = self.redis.pipeline()
            try:
                # 获取平台前缀
                platform = task_data["platform"]
                # 写入任务详情
                pipeline.hset(
                    f"{platform}:task_info:{task_id}",
                    mapping={
                        "url": task_data["url"],
                        "uid": uid,
                        "platform": task_data["platform"],
                        "env": task_data["env"],
                        "material_id": material_ids,
                        "status": "pending",
                        "dismensions":task_data["dismensions"],
                        "retry_count": "0",
                        "created_at": str(int(time.time())),
                    },
                )
                # 写入任务队列
                pipeline.lpush(f"{platform}:task_queue", task_id)
                # 执行Redis事务
                pipeline.execute()

                elapsed_time = round(time.time() - start_time, 3)
                logger.info(
                    f"【Producer-{platform}】- 任务创建完成: task_id={task_id}, 耗时={elapsed_time}秒"
                )
                return True

            except Exception as e:
                pipeline.reset()
                self.db.rollback()
                logger.error(
                    f"【Producer-{platform}】- Redis操作失败: task_id={task_id}, 错误信息={str(e)}"
                )
                raise Exception(f"Redis操作失败: {str(e)}")

        except Exception as e:
            self.db.rollback()
            elapsed_time = round(time.time() - start_time, 3)
            logger.error(
                f"【Producer-{task_data['platform']}】- MySQL操作失败: task_id={task_id}, 错误信息={str(e)}, 耗时={elapsed_time}秒"
            )
            return False
