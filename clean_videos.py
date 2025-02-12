#!/usr/bin/env python3
import argparse
from datetime import datetime, timedelta
import os
from pathlib import Path
import shutil
from app.services.logger import get_logger

logger = get_logger()


def parse_date(date_str):
    """解析日期字符串，支持YYYY-MM-DD格式"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"无效的日期格式: {date_str}，请使用YYYY-MM-DD格式"
        )


def get_directory_date(dir_path):
    """从目录路径中提取日期"""
    try:
        year = int(dir_path.parent.parent.parent.name)
        month = int(dir_path.parent.parent.name)
        day = int(dir_path.parent.name)
        return datetime(year, month, day)
    except (ValueError, AttributeError):
        return None


def should_delete(dir_date, start_date, end_date):
    """判断目录是否在删除日期范围内"""
    if not dir_date:
        return False
    return start_date <= dir_date <= end_date


def clean_videos(start_date, end_date):
    """清理指定日期范围内的视频文件"""
    download_dir = Path.cwd() / "download"
    if not download_dir.exists():
        logger.warning(f"下载目录不存在: {download_dir}")
        return

    deleted_count = 0
    total_size = 0

    # 遍历年份目录
    for year_dir in download_dir.iterdir():
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue

        # 遍历月份目录
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir() or not month_dir.name.isdigit():
                continue

            # 遍历日期目录
            for day_dir in month_dir.iterdir():
                if not day_dir.is_dir() or not day_dir.name.isdigit():
                    continue

                # 遍历任务ID目录
                for task_dir in day_dir.iterdir():
                    if not task_dir.is_dir():
                        continue

                    dir_date = get_directory_date(task_dir)
                    if should_delete(dir_date, start_date, end_date):
                        try:
                            # 计算目录大小
                            dir_size = sum(
                                f.stat().st_size
                                for f in task_dir.rglob("*")
                                if f.is_file()
                            )
                            total_size += dir_size

                            # 删除目录
                            shutil.rmtree(task_dir)
                            deleted_count += 1
                            logger.info(f"已删除目录: {task_dir}")
                        except Exception as e:
                            logger.error(f"删除目录失败 {task_dir}: {str(e)}")

    # 转换总大小为MB
    total_size_mb = total_size / (1024 * 1024)
    logger.info(
        f"清理完成: 删除了 {deleted_count} 个目录，释放了 {total_size_mb:.2f}MB 空间"
    )


def main():
    parser = argparse.ArgumentParser(description="清理缓存视频文件")
    parser.add_argument("--start", type=parse_date, help="开始日期 (YYYY-MM-DD格式)")
    parser.add_argument("--end", type=parse_date, help="结束日期 (YYYY-MM-DD格式)")

    args = parser.parse_args()

    # 如果没有指定日期，默认清理7天前的文件
    if not args.start and not args.end:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
    else:
        if not args.start or not args.end:
            parser.error("start和end参数必须同时提供")
        start_date = args.start
        end_date = args.end

    logger.info(
        f'开始清理 {start_date.strftime("%Y-%m-%d")} 到 {end_date.strftime("%Y-%m-%d")} 期间的视频文件'
    )
    clean_videos(start_date, end_date)


if __name__ == "__main__":
    main()
