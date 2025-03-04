from google import genai
from google.genai import types
import time
from app.services.logger import get_logger
from app.services.rate_limiter import RateLimiter
from app.prompts.prompt_manager import PromptManager
from requests.exceptions import ConnectionError
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
        self.max_retries = 10  # 最大重试次数
        self.retry_interval = 1  # 重试间隔（秒）

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
            self.client = genai.Client(
                api_key=self.api_key,
                # http_options=types.HttpOptions(timeout="30")
            )
            logger.info(
                f"【Google】- 成功初始化Google API客户端，使用付费API密钥：{self.api_key}"
            )

        except Exception as e:
            logger.error(f"【Google】- 初始化Google API客户端失败: {str(e)}")
            raise
    
    def _retry_api_call(self, func, caller_name: str, *args, **kwargs):
        """统一的API调用重试机制
        
        Args:
            func: 要执行的函数
            caller_name: 调用者名称，用于日志追踪
            *args: 函数的位置参数
            **kwargs: 函数的关键字参数
            
        Returns:
            函数执行的结果
        """
        retries = 0
        while retries < self.max_retries:
            try:
                return func(*args, **kwargs)
            except ConnectionError:
                logger.error(f"【Google】- {caller_name} - 网络连接错误，请检查网络或API地址")
                raise
            except Exception as e:
                logger.error(f"【Google】- {caller_name} - API调用失败: {str(e)}")
                retries += 1
                if retries < self.max_retries:
                    logger.info(f"【Google】- {caller_name} - 将在 {self.retry_interval} 秒后进行第 {retries + 1} 次重试")
                    time.sleep(self.retry_interval)
                else:
                    raise
        raise TimeoutError(f"【Google】- {caller_name} - API调用超时，已重试 {self.max_retries} 次")

    # 上传文件
    def upload_file(self, file_path: str):
        """上传文件到Google Vision API
        
        Args:
            file_path: 文件路径
            
        Returns:
            上传后的文件对象
        """
        video_file = self.client.files.upload(file=file_path)
        time.sleep(self.retry_interval)

        def check_file_status():
            file = self.client.files.get(name=video_file.name)
            if file.state.name != "ACTIVE":
                raise Exception(f"文件状态为 {file.state.name}")
            return video_file

        return self._retry_api_call(check_file_status, caller_name="文件上传")
    
    # 删除 google 文件
    def delete_google_file(self, google_file):
        # 删除 google 文件
        if google_file:
            try:
                if 'google_file' in locals():
                    self.client.files.delete(name=google_file.name)
                    logger.info(f"【Google】- 已清理临时文件：{google_file.name}")
            except Exception as e:
                logger.error(f"【Google】- 删除文件失败：{str(e)}")
    
    # 删除本地文件
    def delete_local_file(self, file_path: str):
        if os.path.exists(file_path):
            # 删除文件
            os.remove(file_path)
            logger.info(f"【本地】- 已清理本地文件：{file_path}")

            # 获取文件所在目录
            dir_path = os.path.dirname(file_path)

            # 删除上层目录
            try:
                os.rmdir(dir_path)  # 尝试删除目录
                logger.info(f"【本地】- 已清理上层目录：{dir_path}")
            except OSError as e:
                if e.errno == 39:  # 39 表示目录不为空
                    logger.info(f"【本地】- 上层目录不为空，无法删除：{dir_path}")
                else:
                    logger.error(f"【本地】- 删除上层目录时出错：{e}")
        else:
            logger.warning(f"【本地】- 文件不存在，无法删除：{file_path}")

    # 根据场景获取系统提示词
    def get_system_prompt_by_dimensions(self, dismensions: str) -> str:
        try:
            # 提示词管理器
            pm = PromptManager()
            return pm.get_prompt(dismensions)
        except Exception as e:
            logger.info(f"【prompt-manager】- 根据场景获取系统提示词错误: {str(e)}")
            raise Exception(f"根据场景获取系统提示词错误: {str(e)}")

    # 生成标签
    def generate_tag(self, google_file, dismensions: str, user_prompt: str = "对视频内容进行理解，并按照规则生成标签") -> str:
        """处理文件并获取模型响应

        Args:
            file_path: 要处理的文件路径
            prompt: 可选的提示词

        Returns:
            str: 模型的响应文本
        """

        # 处理文件
        try:
            # 根据场景获取提示词
            system_prompt = self.get_system_prompt_by_dimensions(dismensions)

            # 生成内容
            response = self._retry_api_call(
                self.client.models.generate_content,
                caller_name="标签生成",
                model="gemini-2.0-flash",
                contents=[google_file, system_prompt + user_prompt],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    top_p=0.95,
                    temperature=1,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                ),
            )
            # 获取本次 token 消耗量
            token_count = None
            try:
                if response is not None and hasattr(response, 'usage_metadata') and hasattr(response.usage_metadata, 'total_token_count'):
                    token_count = response.usage_metadata.total_token_count
                    logger.info(f"【Google】 - 本次消耗 token: {token_count}")
                else:
                    logger.warning("【Google】 - 无法获取 token 消耗信息，response 数据结构错误或缺失必要字段")
            except Exception as e:
                    logger.error(f"【Google】 - 获取 token 消耗信息时发生错误: {e}")

            # TODO: 将token数量添加到rateLimiter中
            # limiter = RateLimiter()
            # try:
            #     start_time = time.monotonic()
            #     limiter.acquire(response.usage_metadata.total_token_count)
            #     end_time = time.monotonic()
            #     print(f"请求完成 - tokens: {response.usage_metadata.total_token_count}, 耗时: {end_time - start_time:.2f}秒")
            # except ValueError as e:
            #     print(f"错误: {e}")
            
            # self.rate_limiter.add_tokens(token_count)
            return response.text

            return response.usage_metadata.total_token_count

        except Exception as e:
            logger.error(f"【Google】- 处理失败: {str(e)}")
            raise

# 测试
if __name__ == "__main__":
    google_file = None
    try:
        test = GoogleVisionService()
        start_time = time.time()
        file_path = "/home/eleven/vision-to-tag/test/test-2.mp4"
        google_file = test.upload_file(file_path)
        print(google_file)
        result = test.generate_tag(google_file=google_file,dismensions="prompt-v3-vision")
        print(result)
        result = test.generate_tag(google_file=google_file,dismensions="prompt-v3-audio")
        print(result)
        result = test.generate_tag(google_file=google_file,dismensions="prompt-v3-content-semantics")
        print(result)
        result = test.generate_tag(google_file=google_file,dismensions="prompt-v3-commercial-value")
        print(result)
        # 记录程序结束时间
        end_time = time.time()

        # 计算并输出程序执行时长
        execution_time = end_time - start_time
        print(f"程序执行时长: {execution_time:.2f} 秒")
    except Exception as e:
        print(str(e))
    finally:
        if google_file:  # 确保 google_file 已成功赋值
            test.delete_google_file(google_file=google_file)
        # 测试时关闭
        #test.delete_local_file(file_path=file_path)
