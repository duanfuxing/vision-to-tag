from functools import wraps
from sqlalchemy.exc import OperationalError, StatementError
from app.services.logger import get_logger
from app.db.session import SessionLocal
import time

logger = get_logger()


def retry_on_connection_error(max_retries=3, delay=1):
    """
    数据库操作重试装饰器
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
                    # 如果第一个参数是self且包含db属性，则重置其db会话
                    if args and hasattr(args[0], "db"):
                        # 每次尝试前都重置会话，确保连接状态
                        try:
                            args[0].db.close()
                        except:
                            pass
                        args[0].db = SessionLocal()

                    return func(*args, **kwargs)

                except (OperationalError, StatementError) as e:
                    error_msg = str(e).lower()
                    error_code = getattr(e, "orig", None)
                    error_code = (
                        getattr(error_code, "args", [None])[0] if error_code else None
                    )

                    # 检查MySQL特定错误码或连接错误消息
                    is_connection_error = any(
                        msg in error_msg
                        for msg in [
                            "lost connection",
                            "connection refused",
                            "connection timed out",
                            "broken pipe",
                            "connection reset",
                        ]
                    ) or error_code in [
                        2006,
                        2013,
                    ]  # MySQL error codes for connection issues

                    if is_connection_error:
                        last_error = e
                        retries += 1

                        if retries <= max_retries:
                            logger.warning(
                                f"数据库连接错误，正在进行第{retries}次重试。错误信息: {str(e)}"
                            )
                            time.sleep(delay)
                        else:
                            logger.error(
                                f"数据库操作失败，已达到最大重试次数({max_retries})。错误信息: {str(e)}"
                            )
                            raise last_error
                    else:
                        # 对于非连接错误，直接抛出异常
                        logger.error(f"数据库操作失败，非连接错误: {str(e)}")
                        raise e

            return None

        return wrapper

    return decorator
