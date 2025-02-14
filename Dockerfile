FROM python:3.11-slim

# 设置工作目录
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
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# 设置时区
ENV TZ=Asia/Shanghai

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 创建所有必要的目录结构
RUN mkdir -p /app/logs && \
    mkdir -p /app/download

# 复制.env文件和应用代码
COPY . .

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 6011

# 启动命令
CMD ["python", "main.py"]