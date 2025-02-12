#!/usr/bin/env python3
import argparse
import json
import redis
import os
from pathlib import Path
from datetime import datetime
from app.services.logger import Logger


class AccountImporter:
    """Google账号导入器
    用于将JSON格式的Google账号信息导入到Redis数据库中
    包含导入锁机制，确保导入过程的安全性
    """

    REQUIRED_FIELDS = [
        "api_key",
        "daily_limit",
        "minute_limit",
        "username",
        "password",
        "phone",
        "email",
    ]

    def __init__(self):
        """初始化账号导入器
        设置日志记录器和Redis连接
        """
        self.logger = Logger().logger
        redis_password = os.getenv("REDIS_PASSWORD", "123456")
        self.redis_client = redis.from_url(
            f"redis://:{redis_password}@{os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6379')}/0"
        )

    def validate_account_data(self, account):
        """验证账号数据是否包含所有必填字段

        Args:
            account (dict): 账号数据字典

        Returns:
            tuple: (是否有效, 错误信息)
        """
        missing_fields = [
            field for field in self.REQUIRED_FIELDS if not account.get(field)
        ]
        if missing_fields:
            return False, f"缺少必填字段：{', '.join(missing_fields)}"
        return True, ""

    def import_accounts(self, file_path):
        """从JSON文件导入Google账号信息到Redis

        Args:
            file_path (str): JSON文件的路径

        Returns:
            int: 成功导入的账号数量

        Raises:
            Exception: 当导入过程发生错误时抛出异常
        """
        try:
            # 设置导入锁，防止其他程序访问账号数据
            self.redis_client.set("google_account:import_lock_str", "true")
            self.logger.info("已启用账号导入锁，开始导入账号信息")

            # 清除所有旧的账号数据
            phones = self.redis_client.smembers("google_account:phones_set")
            if phones:
                for phone in phones:
                    phone = phone.decode("utf-8")
                    # 删除账号基本信息
                    self.redis_client.delete(f"google_account:info_hash:{phone}")
                    # 删除每日使用计数
                    self.redis_client.delete(f"google_account:daily_hash:{phone}")
                    # 删除分钟级请求窗口
                    self.redis_client.delete(
                        f"google_account:minute_window_zset:{phone}"
                    )
            # 清除手机号集合
            self.redis_client.delete("google_account:phones_set")
            self.logger.info("已清除所有旧账号数据")

            with open(file_path, "r", encoding="utf-8") as f:
                accounts_data = json.load(f)

            imported_count = 0
            for account in accounts_data:
                # 验证账号数据
                is_valid, error_msg = self.validate_account_data(account)
                if not is_valid:
                    self.logger.warning(f"跳过无效账号数据：{error_msg}")
                    continue

                # 存储账号基本信息到Hash
                account_info = {
                    "api_key": account["api_key"],
                    "quota_daily": account["daily_limit"],
                    "minute_limit": account["minute_limit"],
                    "status": "active",
                    "username": account["username"],
                    "password": account["password"],
                    "phone": account["phone"],
                    "email": account["email"],
                }
                for field, value in account_info.items():
                    self.redis_client.hset(
                        f"google_account:info_hash:{account['phone']}", field, value
                    )

                # 将手机号添加到账号集合
                self.redis_client.sadd("google_account:phones_set", account["phone"])

                # 初始化每日使用计数
                today = datetime.now().date().isoformat()
                self.redis_client.hsetnx(
                    f"google_account:daily_hash:{account['phone']}", today, 0
                )

                # 初始化分钟级请求窗口
                self.redis_client.delete(
                    f"google_account:minute_window_zset:{account['phone']}"
                )

                imported_count += 1
                self.logger.info(f"成功导入账号，API密钥：{account['api_key'][-5:]}")

            # 导入完成后解除导入锁
            self.redis_client.delete("google_account:import_lock_str")
            self.logger.info("账号导入完成，已解除导入锁")

            return imported_count

        except Exception as e:
            # 发生错误时确保解除导入锁
            self.redis_client.delete("google_account:import_lock_str")
            self.logger.error(f"导入账号失败：{str(e)}")
            raise


def main():
    """主函数
    处理命令行参数并执行账号导入操作
    """
    parser = argparse.ArgumentParser(description="导入Google账号信息到Redis")
    parser.add_argument("--file", required=True, help="包含账号信息的JSON文件路径")
    args = parser.parse_args()

    importer = AccountImporter()
    try:
        count = importer.import_accounts(args.file)
        print(f"成功导入 {count} 个账号")
    except Exception as e:
        print(f"错误：{str(e)}")
        exit(1)


if __name__ == "__main__":
    main()
