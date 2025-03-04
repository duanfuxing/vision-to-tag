# Vision-to-tag 视频标签生成服务

## 项目介绍
Vision-to-tag是一个基于Google的 gemini-2.0-flash 模型实现的视频标签生成服务 

该服务能够自动分析视频内容，提取关键场景，并生成相应的标签描述 


## 系统架构
[API Server] → [MySQL] ↔ [Redis]
      ↑               ↓
      └─[Consumer] → [Google 标签服务]
                     → [ES 服务]
                     → [文件存储]

### 核心组件
1. **智能账号池管理系统**
   - 多账号轮询调度
   - 自动负载均衡
   - 实时配额监控
   - 分钟级限流控制
   - 故障自动转移

2. **视频处理服务**
   - 视频格式验证
   - 视频下载管理
   - 视频帧提取
   - 标签生成处理
   - 缓存自动清理

3. **队列管理服务**
   - 任务调度管理
   - 任务状态监控
   - 任务重试机制
   - 任务超时处理
   - 任务失败处理

### Google账号-Redis数据结构
1. **账号基本信息 (Hash)**
   - 键名格式：`google_account:{api_key}:info`
   - 字段说明：
     - api_key: API密钥
     - quota_daily: 每日配额限制
     - status: 账号状态(active/inactive)
     - username: 账号用户名
     - password: 账号密码
     - phone: 手机号码
     - email: 电子邮箱

2. **账号集合 (Set)**
   - 键名：`google_accounts:keys`
   - 用途：存储所有可用的API密钥

3. **每日使用量 (Hash)**
   - 键名格式：`google_account:{api_key}:daily`
   - 字段说明：
     - {date}: 当日使用次数
   - 过期时间：2天

4. **分钟级请求窗口 (Sorted Set)**
   - 键名格式：`google_account:{api_key}:minute_window`
   - 成员：请求时间戳
   - 分数：请求时间戳
   - 过期时间：2分钟

5. **导入锁 (String)**
   - 键名：`google_accounts:import_lock`
   - 用途：防止导入过程中的并发访问


### Redis数据结构设计
1. **任务队列（List）**
   - 键名：`task_queue`
   - 类型：List
   - 用途：存储待处理的任务ID
   - 数据示例：["task-001", "task-002", ...]

2. **任务详情（Hash）**
   - 键名格式：`task_info:{taskId}`
   - 类型：Hash
   - 字段说明：
     - url: 视频URL
     - status: 任务状态（pending/processing/completed/failed）
     - retry_count: 重试次数
     - created_at: 创建时间戳
   - 过期时间：7天

3. **失败任务队列（List）**
   - 键名：`task_queue_failed`
   - 类型：List
   - 用途：存储处理失败的任务ID
   - 数据示例：["failed-task-001", "failed-task-002", ...]

4. **任务锁（String）**
   - 键名格式：`task_queue_lock:{taskId}`
   - 类型：String
   - 用途：任务处理锁，防止重复处理
   - 过期时间：5分钟

## 配置说明

### 环境变量配置
1. 复制`.env.example`为`.env`
2. 配置必要的环境变量

### Google API密钥配置
1. 在`app/config`目录下创建`google_account.json`文件
2. 按以下格式配置API密钥：
```json
[
  {
    "api_key": "your-google-api-key",
    "daily_limit": 1500,
    "minute_limit": 10,
    "username": "your-username",
    "password": "your-password",
    "phone": "your-phone-number",
    "email": "your-email@example.com"
  }
]
```

### Google 账号导入说明
1. 准备包含账号信息的JSON文件，确保包含以下必填字段：
   - api_key: Google API密钥
   - daily_limit: 每日请求配额限制
   - minute_limit: 每分钟请求限制
   - username: 账号用户名
   - password: 账号密码
   - phone: 手机号码
   - email: 电子邮箱

2. 使用导入工具导入账号：
```bash
python import_accounts.py --file google_accounts.json
```



## 部署说明

### MiniConda 管理环境
```bash
# 下载 MiniConda
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
# 安装 MiniConda
bash Miniconda3-latest-Linux-x86_64.sh
# 一路 enter
# 生效 .bashrc
source ~/.bashrc
# 验证安装
conda --version
# 创建虚拟环境
conda create -n vision-to-tag python=3.11
# 激活环境
conda activate vision-to-tag
# 退出环境
conda deactivate
```

### Supervisor 守护进程
```bash
# 安装 supervisor
sudo apt install supervisor
# 更新配置文件
```

### 本地部署
```bash
# 安装依赖
pip install -r requirements.txt

# 启动API服务
python main.py

# 启动队列消费服务
python app/services/consumer.py
```

## API使用说明

### 创建任务API
```http
POST /api/v1/task/create

请求参数
{
    "url": "http://example.com/video.mp4", // 必填参数，视频URL
    "uid": 123, // 可选参数，uid
    "platform": "rpa", // 必填参数 rpa, miaobi
    "dismensions": "all", // 拆分维度 all-全部 vision-视觉
    "env": "develop" // 环境
}

成功响应
{
   "code": 200,
   "message": "success",
   "task_id": "550e8400-e29b-41d4-a716-446655440000",
   "data":{

   }
}

错误响应
{
   "code": 400,
   "message": "Invalid video URL",
   "task_id": null,
   "data":{

   }
}
```

### 视频标签生成API
```http
POST /api/v1/vision_to_tag/google

请求参数:
{
    "url": "https://example.com/video.mp4"
}

响应:
{
    "code": 200,
    "message": "成功",
    "task_id": "uuid",
    "data": {
        "tags": ["tag1", "tag2", "tag3"]
    }
}
```

## 限制说明
1. 视频格式支持：mp4、avi、mov、wav、3gpp、x-flv
2. 视频大小限制：50MB

## 缓存管理
系统提供自动化的视频缓存清理功能：

### 清理工具
```bash
# 清理指定日期范围的缓存文件
python clean_videos.py --start 2024-01-01 --end 2024-01-31

# 默认清理7天前的缓存文件
python clean_videos.py
```

### 清理策略
- 默认保留最近7天的缓存文件
- 支持自定义清理日期范围
- 自动计算释放的存储空间
- 异常处理和日志记录

### 自动清理配置
系统默认每天凌晨3点自动执行缓存清理任务，清理7天前的视频文件。此功能在Docker环境中已配置，无需额外设置。如需调整清理时间或策略，可修改docker-compose.yml中的定时任务配置。

```bash
# 手动触发清理（Docker环境）
docker exec vision_tag python clean_videos.py
