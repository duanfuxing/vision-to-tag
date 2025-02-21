from functools import wraps
from typing import Optional, Type, Union, Any, Callable
from redis.exceptions import (
    ConnectionError,
    TimeoutError,
    RedisError,
    ResponseError,
    BusyLoadingError,
    ReadOnlyError,
    OutOfMemoryError,
)
from app.services.logger import get_logger
from redis import Redis
import os

# 从环境变量获取Redis连接信息
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_DB = int(os.getenv("REDIS_DB", "0"))


def get_redis_client() -> Redis:
    """获取Redis客户端连接"""
    return Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        db=REDIS_DB,
        decode_responses=True,  # 自动将字节解码为字符串
    )


import time
import random

logger = get_logger()


class RetryableRedisError(Exception):
    """自定义可重试的Redis异常"""

    pass


def retry_on_redis_error(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 5.0,
    exponential_backoff: bool = True,
    jitter: bool = True,
    retryable_errors: Optional[tuple[Type[Exception], ...]] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
    db_number: int = 0,
) -> Callable:
    """
    Redis操作重试装饰器

    Args:
        max_retries: 最大重试次数
        base_delay: 基础重试延迟时间（秒）
        max_delay: 最大重试延迟时间（秒）
        exponential_backoff: 是否使用指数退避策略
        jitter: 是否添加随机抖动
        retryable_errors: 可重试的异常类型元组
        on_retry: 重试回调函数
        db_number: Redis数据库号码
    """
    if retryable_errors is None:
        retryable_errors = (
            ConnectionError,
            TimeoutError,
            BusyLoadingError,
            ReadOnlyError,
            RetryableRedisError,
            ResponseError,  # 某些ResponseError也可能需要重试
        )

    def calculate_delay(attempt: int) -> float:
        """计算重试延迟时间"""
        if exponential_backoff:
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
        else:
            delay = base_delay

        if jitter:
            delay *= 0.5 + random.random()

        return min(delay, max_delay)

    def get_connection_error_config() -> dict[str, bool]:
        """获取连接错误的配置数据

        Returns:
            dict: 错误消息映射表，值表示是否需要重试
        """
        return {
            "connection refused": True,
            "connection timed out": True,
            "connection reset": True,
            "broken pipe": True,
            "connection lost": True,
            "connection closed": True,
            "connection error": True,
            "max number of clients reached": True,
            "oom command not allowed": True,  # 内存不足
            "readonly": True,  # 主从复制只读错误
            "busy loading": True,  # Redis正在加载数据
            "max retries exceeded": False,  # 已超过最大重试次数
            "authentication required": False,  # 认证错误，不需要重试
            "invalid password": False,  # 密码错误，不需要重试
        }

    def is_connection_error(error: Exception) -> bool:
        """判断是否为需要重试的错误"""
        error_msg = str(error).lower()
        error_config = get_connection_error_config()

        # 检查是否是已知的错误类型
        for msg, should_retry in error_config.items():
            if msg in error_msg:
                return should_retry

        # 特殊处理某些Redis错误
        if isinstance(error, OutOfMemoryError):
            return True
        if isinstance(error, ResponseError) and "LOADING" in str(error):
            return True
        if isinstance(error, ReadOnlyError):
            return True

        # 对于ConnectionError和TimeoutError，默认重试
        if isinstance(error, (ConnectionError, TimeoutError)):
            return True

        return False

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            retries = 0
            last_error = None

            while retries <= max_retries:
                try:
                    # 重置Redis连接（如果适用）
                    if args and hasattr(args[0], "redis"):
                        try:
                            if hasattr(args[0].redis, "close"):
                                args[0].redis.close()
                            if hasattr(args[0].redis, "connection_pool"):
                                args[0].redis.connection_pool.disconnect()
                        except Exception as e:
                            logger.warning(f"关闭Redis连接失败: {e}")
                        finally:
                            try:
                                args[0].redis = get_redis_client()
                                if db_number != 0:
                                    args[0].redis.select(db_number)
                            except Exception as e:
                                logger.error(f"创建新Redis连接失败: {e}")
                                raise

                    return func(*args, **kwargs)

                except retryable_errors as e:
                    if not is_connection_error(e):
                        logger.error(f"Redis操作失败，非可重试错误: {str(e)}")
                        raise

                    last_error = e
                    retries += 1

                    if retries <= max_retries:
                        delay = calculate_delay(retries)
                        logger.warning(
                            f"Redis操作错误，正在进行第{retries}次重试。"
                            f"等待{delay:.2f}秒。错误信息: {str(e)}"
                        )

                        # 执行重试回调
                        if on_retry:
                            try:
                                on_retry(e, retries)
                            except Exception as callback_error:
                                logger.error(f"重试回调执行失败: {callback_error}")

                        time.sleep(delay)
                    else:
                        logger.error(
                            f"Redis操作失败，已达到最大重试次数({max_retries})。"
                            f"错误信息: {str(e)}"
                        )
                        raise last_error

                except Exception as e:
                    logger.error(f"Redis操作发生未预期的错误: {str(e)}", exc_info=True)
                    raise

            return None

        return wrapper

    return decorator
