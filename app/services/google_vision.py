from google import genai
from google.genai import types
from pathlib import Path
import json
import logging
import time
from datetime import datetime
from typing import List, Dict
from .GoogleAccount import GoogleAccount
from .logger import get_logger
import os

# 初始化logger
logger = get_logger()


class GoogleVisionService:
    def __init__(self):
        # 初始化账号管理器
        # self.account_manager = GoogleAccount()

        # 初始化Google Vision API客户端
        self.client = None
        self.api_key = os.getenv("API_KEY", "")
        self._init_client()

    def _init_client(self):
        """初始化Google API客户端"""
        try:
            # 获取可用账号
            # account = self.account_manager.get_available_account()
            # 检查是否有可用的API密钥
            # if not account or not account["api_key"]:
            #     logger.error("【Google】- 没有可用的API密钥")
            #     raise Exception("【Google】- 没有可用的API密钥")

            if self.api_key == "":
                logger.error("【Google】- 没有可用的API密钥")
                raise Exception("【Google】- 没有可用的API密钥")

            # 创建客户端
            # self.client = genai.Client(api_key=account["api_key"])
            self.client = genai.Client(api_key=self.api_key)
            logger.info(
                f"【Google】- 成功初始化Google API客户端，使用付费API密钥：{self.api_key}"
            )

        except Exception as e:
            logger.error(f"【Google】- 初始化Google API客户端失败: {str(e)}")
            raise

    def generate_tag(self, file_path: str, prompt: str) -> str:
        """处理文件并获取模型响应

        Args:
            file_path: 要处理的文件路径
            prompt: 可选的提示词

        Returns:
            str: 模型的响应文本
        """

        # 处理文件
        try:
            # 设置状态检查参数
            max_retries = 30  # 最大重试次数
            retry_interval = 1  # 重试间隔（秒）
            retries = 0

            # 上传文件
            video_file = self.client.files.upload(file=file_path)
            time.sleep(retry_interval)

            while retries < max_retries:
                try:
                    video_file = self.client.files.get(name=video_file.name)

                    # 检查文件状态
                    if video_file.state.name == "ACTIVE":
                        logger.info(f"【Google】- 文件上传成功：{video_file.name}")
                        break

                    # 增加重试计数并等待
                    retries += 1
                    if retries < max_retries:
                        logger.info(
                            f"【Google】- 文件状态为 {video_file.state.name}，等待 {retry_interval} 秒后重试"
                        )
                        time.sleep(retry_interval)

                except Exception as e:
                    logger.error(f"【Google】- 检查文件状态时发生错误：{str(e)}")
                    # 增加重试计数并等待
                    retries += 1
                    if retries < max_retries:
                        logger.info(
                            f"【Google】- 将在 {retry_interval} 秒后进行第 {retries + 1} 次重试"
                        )
                        time.sleep(retry_interval)
                    else:
                        raise

            if retries >= max_retries:
                logger.error(f"【Google】- 文件处理超时：{video_file.name}")
                raise TimeoutError(f"【Google】- 文件处理超时，已重试 {max_retries} 次")

        except Exception as e:
            logger.error(f"【Google】- 处理文件失败: {str(e)}")
            raise

        # 请求模型
        try:
            response = self.client.models.generate_content(
                # model="gemini-2.0-pro-exp-02-05",
                model="gemini-2.0-flash",
                contents=[video_file, "对视频内容进行理解，并按照规则生成标签"],
                config=types.GenerateContentConfig(
                    system_instruction=prompt,
                    top_p=0.95,
                    temperature=1,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                ),
            )

            return response.text

        except Exception as e:
            error_message = str(e)
            # if "RESOURCE_EXHAUSTED" in error_message:
            #     # 获取当前使用的账号
            #     current_account = self.account_manager.get_available_account()
            #     if current_account:
            #         # 标记账号为不可用
            #         self.account_manager.disable_account(current_account)
            #         logger.warning(
            #             f"【Google】- API密钥 {current_account['api_key'][-5:]} 已超出配额限制，已标记为不可用"
            #         )
            logger.error(f"【Google】- 模型请求失败: {error_message}")
            raise
        finally:
            # 清理文件
            self.client.files.delete(name=video_file.name)
            logger.info(f"【Google】- 已清理临时文件：{video_file.name}")
