import os
import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler


class Logger:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._initialized = True
            self._setup_logger()

    def _setup_logger(self):
        # 创建基础日志目录
        base_log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs"
        )

        # 获取当前年月
        current_date = datetime.now()
        year_dir = str(current_date.year)
        month_dir = f"{current_date.month:02d}"

        # 创建年月目录
        log_dir = os.path.join(base_log_dir, year_dir, month_dir)
        os.makedirs(log_dir, exist_ok=True)

        # 设置日志文件路径
        log_file = os.path.join(log_dir, "app.log")

        # 创建logger
        self.logger = logging.getLogger("VisionToTag")
        # 设置全局日志级别为 DEBUG
        self.logger.setLevel(logging.DEBUG)

        # 创建TimedRotatingFileHandler
        file_handler = TimedRotatingFileHandler(
            filename=log_file,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)

        # 设置日志格式
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s"
        )
        file_handler.setFormatter(formatter)

        # 添加处理器
        if not self.logger.handlers:
            self.logger.addHandler(file_handler)

            # 添加控制台输出
            console_handler = logging.StreamHandler()
            # 控制台 Handler 设置为 INFO 级别
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

    def debug(self, message):
        self.logger.debug(message, stacklevel=2)

    def info(self, message):
        self.logger.info(message, stacklevel=2)

    def warning(self, message):
        self.logger.warning(message, stacklevel=2)

    def error(self, message):
        self.logger.error(message, stacklevel=2)

    def critical(self, message):
        self.logger.critical(message, stacklevel=2)


# 创建全局logger实例
def get_logger():
    return Logger()