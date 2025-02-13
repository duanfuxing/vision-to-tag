CREATE TABLE `video_tasks` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `task_id` varchar(100) NOT NULL COMMENT '任务ID',
    `uid` varchar(100) NOT NULL COMMENT '用户ID',
    `url` varchar(512) NOT NULL COMMENT '视频URL',
    `platform` varchar(20) NOT NULL COMMENT '平台来源 rpa,miaobi',
    `status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT '任务状态 pending:待处理, processing:处理中, completed:已完成, failed:失败',
    `message` text COMMENT '错误信息',
    `tags` json DEFAULT NULL COMMENT '视频标签',
    `processed_start` timestamp NULL DEFAULT NULL COMMENT '处理完成时间',
    `processed_end` timestamp NULL DEFAULT NULL COMMENT '处理完成时间',
    `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_task_id` (`task_id`),
    KEY `idx_status_created` (`status`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='视频任务表';