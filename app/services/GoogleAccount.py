from datetime import datetime
import threading
import redis
import os
from .logger import Logger


class GoogleAccount:
    """Google账号管理类
    负责从Redis获取可用的Google API账号，并管理其使用情况
    包含分钟级滑动窗口限流和日使用量统计
    """

    def __init__(self):
        """初始化账号管理器
        设置Redis连接和线程锁
        """
        self.logger = Logger().logger
        redis_password = os.getenv("REDIS_PASSWORD", "123456")
        self.redis_client = redis.from_url(
            f"redis://:{redis_password}@{os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6379')}/0"
        )
        self.account_lock = threading.Lock()
        self.logger.info("【Google】- 初始化Google账号管理器")

    def get_available_account(self):
        """获取一个可用的账号
        使用轮询方式遍历所有账号，返回第一个可用的账号信息

        Returns:
            dict: 包含账号信息的字典，如果没有可用账号则返回None
        """
        # 检查是否处于导入锁定状态
        if self.redis_client.get("google_account:import_lock_str"):
            self.logger.warning("【Google】- 账号池处于导入锁定状态，暂时无法获取账号")
            return None

        with self.account_lock:
            # 获取所有账号
            phones = self.redis_client.smembers("google_account:phones_set")
            if not phones:
                self.logger.warning("【Google】- Redis中没有找到任何账号信息")
                return None

            now = datetime.now()
            today = now.date().isoformat()
            current_timestamp = now.timestamp()
            minute_ago = current_timestamp - 60

            # 遍历所有账号，查找可用账号
            for phone in phones:
                phone = phone.decode("utf-8")
                account_info = self.redis_client.hgetall(
                    f"google_account:info_hash:{phone}"
                )
                if not account_info:
                    continue

                # 解码账号信息
                account_info = {
                    k.decode("utf-8"): v.decode("utf-8")
                    for k, v in account_info.items()
                }
                quota_daily = int(account_info.get("quota_daily", 1200))
                minute_limit = int(account_info.get("minute_limit", 8))

                # 检查账号状态
                if account_info.get("status") != "active":
                    continue

                # 检查每日使用量
                used_today = int(
                    self.redis_client.hget(f"google_account:daily_hash:{phone}", today)
                    or 0
                )
                if used_today >= quota_daily:
                    continue

                # 检查分钟级限制（滑动窗口）
                self.redis_client.zremrangebyscore(
                    f"google_account:minute_window_zset:{phone}", 0, minute_ago
                )
                minute_requests = self.redis_client.zcount(
                    f"google_account:minute_window_zset:{phone}",
                    minute_ago,
                    current_timestamp,
                )
                if minute_requests >= minute_limit:
                    continue

                # 更新使用量统计
                self.redis_client.hincrby(
                    f"google_account:daily_hash:{phone}", today, 1
                )
                self.redis_client.zadd(
                    f"google_account:minute_window_zset:{phone}",
                    {str(current_timestamp): current_timestamp},
                )

                # 设置过期时间
                self.redis_client.expire(
                    f"google_account:daily_hash:{phone}", 86400 * 2
                )  # 2天后过期
                self.redis_client.expire(
                    f"google_account:minute_window_zset:{phone}", 120
                )  # 2分钟后过期

                self.logger.info(
                    f"【Google】- 获取到可用账号，API密钥：{account_info['api_key'][-5:]}，今日已使用：{used_today + 1}次"
                )
                return account_info

            self.logger.warning("【Google】- 没有找到可用的账号")
            return None

    def disable_account(self, account_info):
        """将账号标记为不可用状态

        Args:
            account_info: 包含账号信息的字典
        """
        if not account_info or "phone" not in account_info:
            self.logger.error("【Google】- 无效的账号信息")
            return

        try:
            phone = account_info["phone"]
            # 更新账号状态为不可用
            self.redis_client.hset(
                f"google_account:info_hash:{phone}", "status", "disabled"
            )
            self.logger.info(
                f"【Google】- 已将账号 {account_info['api_key'][-5:]} 标记为不可用"
            )
        except Exception as e:
            self.logger.error(f"【Google】- 禁用账号失败: {str(e)}")
