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
                        if retries > 0:  # 只在重试时重置会话
                            try:
                                args[0].db.close()
                            except:
                                pass
                            args[0].db = SessionLocal()

                    return func(*args, **kwargs)

                except (OperationalError, StatementError) as e:
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

            return None

        return wrapper

    return decorator
