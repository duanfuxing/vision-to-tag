from functools import wraps
from typing import Optional, Type, Union, Any
from sqlalchemy.exc import OperationalError, StatementError, SQLAlchemyError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import QueuePool
from app.services.logger import get_logger
import time
import random
import os

logger = get_logger()

# 从环境变量获取数据库连接信息
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "123456")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_DATABASE = os.getenv("DB_DATABASE", "vision_to_tag")

# 构建数据库URL
DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_DATABASE}"
)

# 创建数据库引擎
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    pool_pre_ping=True,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建Base类
Base = declarative_base()


class RetryableDBError(Exception):
    """自定义可重试的数据库异常"""

    pass


def retry_on_db_error(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 5.0,
    exponential_backoff: bool = True,
    jitter: bool = True,
    retryable_errors: Optional[tuple[Type[Exception], ...]] = None,
):
    """
    数据库操作重试装饰器

    Args:
        max_retries: 最大重试次数
        base_delay: 基础重试延迟时间（秒）
        max_delay: 最大重试延迟时间（秒）
        exponential_backoff: 是否使用指数退避策略
        jitter: 是否添加随机抖动
        retryable_errors: 可重试的异常类型元组
    """
    if retryable_errors is None:
        retryable_errors = (OperationalError, StatementError, RetryableDBError)

    def calculate_delay(attempt: int) -> float:
        """计算重试延迟时间"""
        if exponential_backoff:
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
        else:
            delay = base_delay

        if jitter:
            delay *= 0.5 + random.random()

        return min(delay, max_delay)

    def get_connection_error_config() -> tuple[set[str], set[int]]:
        """获取连接错误的配置数据

        Returns:
            tuple: (错误消息集合, 错误代码集合)
        """
        connection_error_messages = {
            "lost connection",
            "connection refused",
            "connection timed out",
            "broken pipe",
            "connection reset",
            "too many connections",
            "lock wait timeout",
        }

        connection_error_codes = {
            2006,  # MySQL server has gone away
            2013,  # Lost connection to MySQL server during query
            2014,  # Commands out of sync
            2024,  # Connection attempt failed
            2055,  # Lost connection to MySQL server
            1205,  # Lock wait timeout exceeded
            1213,  # Deadlock found
        }

        return connection_error_messages, connection_error_codes

    def is_connection_error(error: Union[OperationalError, StatementError]) -> bool:
        """判断是否为连接相关错误"""
        error_msg = str(error).lower()
        error_code = getattr(error, "orig", None)
        error_code = getattr(error_code, "args", [None])[0] if error_code else None

        connection_error_messages, connection_error_codes = (
            get_connection_error_config()
        )

        return (
            any(msg in error_msg for msg in connection_error_messages)
            or error_code in connection_error_codes
        )

    def decorator(func):
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            retries = 0
            last_error = None

            while retries <= max_retries:
                try:
                    # 重置数据库会话（如果适用）
                    if args and hasattr(args[0], "db"):
                        try:
                            args[0].db.close()
                        except Exception as e:
                            logger.warning(f"关闭数据库会话失败: {e}")
                        finally:
                            args[0].db = SessionLocal()

                    return func(*args, **kwargs)

                except retryable_errors as e:
                    if isinstance(
                        e, (OperationalError, StatementError)
                    ) and not is_connection_error(e):
                        logger.error(f"数据库操作失败，非连接错误: {str(e)}")
                        raise

                    last_error = e
                    retries += 1

                    if retries <= max_retries:
                        delay = calculate_delay(retries)
                        logger.warning(
                            f"数据库连接错误，正在进行第{retries}次重试。"
                            f"等待{delay:.2f}秒。错误信息: {str(e)}"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"数据库操作失败，已达到最大重试次数({max_retries})。"
                            f"错误信息: {str(e)}"
                        )
                        raise last_error

                except Exception as e:
                    logger.error(f"数据库操作发生未预期的错误: {str(e)}")
                    raise

            return None

        return wrapper

    return decorator
