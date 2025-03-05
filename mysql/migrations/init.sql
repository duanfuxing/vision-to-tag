CREATE TABLE `video_tasks` (
  `id` int unsigned NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `task_id` varchar(100) NOT NULL DEFAULT '' COMMENT '任务ID',
  `uid` varchar(100) NOT NULL DEFAULT '' COMMENT '用户ID',
  `url` varchar(512) NOT NULL DEFAULT '' COMMENT '视频URL',
  `platform` varchar(20) NOT NULL DEFAULT '' COMMENT '平台-rpa,miaobi',
  `status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT '任务状态 pending:待处理, processing:处理中, completed:已完成, failed:失败',
  `dimensions` varchar(30) NOT NULL DEFAULT 'all' COMMENT '提取维度all-全部， vision-视觉，audio-音频，content-semantics-内容语义，commercial-value-商业价值',
  `message` json DEFAULT NULL COMMENT '附加信息',
  `tags` json DEFAULT NULL COMMENT '视频标签',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx-task_id` (`task_id`),
  KEY `idx-status` (`status`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='视频任务表';