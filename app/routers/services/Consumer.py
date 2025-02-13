"""
Redis数据结构设计
    # 任务队列（List类型）
    video:task:queue -> List类型，存储待处理的任务ID

    # 任务详情（Hash类型）
    video:task:{taskId} -> Hash类型，存储任务详情
        - url: 视频URL
        - status: 任务状态
        - retry_count: 重试次数
        - created_at: 创建时间

    # 失败任务队列（List类型）
    video:task:failed -> List类型，存储处理失败的任务ID

    # 任务锁（String类型）
    video:task:lock:{taskId} -> String类型，任务处理锁，防止重复处理
"""

"""
消费者逻辑
    1. 从Redis获取任务（原子操作）
    2. 获取任务锁
    3. 更新任务状态为处理中
    4. 获取任务信息
    5. 下载视频
    6. 调用Google视频标签服务
    7. 更新MySQL中的标签
    8. 调用ES入库服务
    9. 清理处理队列
    10. 更新任务状态为完成
    注意事项：
        错误处理：重试或进入死信队列
        资源释放：关闭数据库连接、清理临时文件
        使用 Supervisor 管理多进程
        日志记录关键操作（下载、标签服务调用、错误）
"""
