FROM python:3.11-slim

WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    cron \
    vim \ 
    git \
    wget \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制.env文件和应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p ${LOG_DIR:-/app/logs} ${DOWNLOAD_DIR:-/app/download}

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE ${API_PORT:-8000}

# 启动命令
CMD ["python", "main.py"]