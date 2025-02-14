from functools import wraps
from redis.exceptions import ConnectionError, TimeoutError
from app.services.logger import get_logger
from app.db.redis import get_redis_client
import time

logger = get_logger()


def retry_on_redis_error(max_retries=3, delay=1):
    """
    Redis操作重试装饰器
    :param max_retries: 最大重试次数
    :param delay: 重试间隔（秒）
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            last_error = None

            while retries <= max_retries:
                try:
                    # 如果第一个参数是self且包含redis属性，则重置其redis连接
                    if args and hasattr(args[0], "redis"):
                        try:
                            args[0].redis.close()
                        except:
                            pass
                        args[0].redis = get_redis_client()
                        args[0].redis.select(1)  # 切换到Redis 1号数据库

                    return func(*args, **kwargs)

                except (ConnectionError, TimeoutError) as e:
                    error_msg = str(e).lower()
                    # 只对特定的连接错误进行重试
                    if any(
                        msg in error_msg
                        for msg in [
                            "connection refused",
                            "connection timed out",
                            "connection reset",
                            "broken pipe",
                            "connection lost",
                        ]
                    ):
                        last_error = e
                        retries += 1

                        if retries <= max_retries:
                            logger.warning(
                                f"Redis连接错误，正在进行第{retries}次重试。错误信息: {str(e)}"
                            )
                            time.sleep(delay)
                        else:
                            logger.error(
                                f"Redis操作失败，已达到最大重试次数({max_retries})。错误信息: {str(e)}"
                            )
                            raise last_error
                    else:
                        # 对于非连接错误，直接抛出异常
                        logger.error(f"Redis操作失败，非连接错误: {str(e)}")
                        raise e

            return None

        return wrapper

    return decorator
