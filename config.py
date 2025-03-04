import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

class Settings:
    # 服务配置
    API_PORT = int(os.getenv("API_PORT", 8000))
    API_HOST = os.getenv("API_HOST", "0.0.0.0")

    # Redis配置
    REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
    REDIS_PORT = int(os.getenv("REDIS_PORT"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

    # MySQL配置
    DB_CONNECTION = os.getenv("DB_CONNECTION", "mysql")
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = int(os.getenv("DB_PORT"))
    DB_DATABASE = os.getenv("DB_DATABASE")
    DB_USERNAME = os.getenv("DB_USERNAME")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_ROOT_PASSWORD = os.getenv("DB_ROOT_PASSWORD")

    # 日志配置
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR = os.getenv("LOG_DIR")

    # 文件存储配置
    DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR")

    # API配置
    API_KEYS_FILE = os.getenv("API_KEYS_FILE")

    # 视频处理配置
    MAX_VIDEO_SIZE_MB = int(os.getenv("MAX_VIDEO_SIZE_MB", 100))
    ALLOWED_VIDEO_FORMATS = eval(os.getenv("ALLOWED_VIDEO_FORMATS", '["mp4","avi","mov", "wav"]'))

    # API Key
    API_KEY = os.getenv("API_KEY")

settings = Settings()