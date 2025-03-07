from google import genai
from google.api_core import retry
from google.genai import types
import time
import os
from app.services.logger import get_logger
from config import Settings
from app.prompts.prompt_manager import PromptManager

# 初始化logger
logger = get_logger()

class GoogleTagGenerationError(Exception):
    """Google标签生成异常"""
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class GoogleVisionService:
    def __init__(self):
        # 初始化Google Vision API客户端
        self.client = None
        self.api_key = Settings.API_KEY
        self._init_client()
        self.max_retries = 10  # 最大重试次数
        self.retry_interval = 1  # 重试间隔（秒）
    
    # 可重试装饰器
    def is_retryable(e) -> bool:
        # 出现暂时错误时重试
        if retry.if_transient_error(e):
            logger.info(f"[Service-Retry] - 出现暂时错误时重试")
            return True
        # 客户端错误且错误码为429时重试
        elif (isinstance(e, genai.errors.ClientError) and e.code == 429):
            logger.info(f"[Service-Retry] - 客户端错误且错误码为429时重试")
            return True
        # 服务端错误且错误码为503时重试
        elif (isinstance(e, genai.errors.ServerError) and e.code == 503):
            logger.info(f"[Service-Retry] - 服务端错误且错误码为503时重试")
            return True
        # 打标签返回结果不是完整json时重试
        elif (isinstance(e, GoogleTagGenerationError)):
            logger.info(f"[Service-Retry] - 打标签返回结果不是完整json时重试")
            return True
        # 触发服务的请求限流时重试
        # elif (isinstance(e, Exception)):
            return True
        # 连接失败或请求超时时重试
        elif (isinstance(e, (ConnectionError, TimeoutError))):
            logger.info(f"[Service-Retry] - 连接失败或请求超时时重试")
            return True
        else:
            return False
        
    def _init_client(self):
        """初始化客户端"""
        try:
            # 创建客户端
            self.client = genai.Client(
                api_key=Settings.API_KEY,
            )
            logger.info(
                f"【Google】- 成功初始化Google API客户端，使用付费API密钥：{self.api_key}"
            )
        except Exception as e:
            err_msg = f"【Google】- 初始化Google API客户端失败: {str(e)}"
            logger.error(err_msg)
            raise Exception(err_msg)
        
    def delete_local_file(self, file_path: str):
        """删除本地文件"""
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

    def get_system_prompt_by_dim(self, dim: str) -> str:
        """根据场景获取系统提示词"""
        try:
            # 提示词管理器
            pm = PromptManager()
            return pm.get_prompt(dim)
        except Exception as e:
            err_msg = f"【prompt-manager】- 根据场景获取系统提示词错误: {str(e)}"
            logger.info(err_msg)
            raise Exception(err_msg)
    
    def _wait_for_file_active(self, file_name: str, timeout: int = 60) -> bool:
        """
        等待文件状态变为 ACTIVE
        Args:
            file_name: 文件名
            timeout: 超时时间（秒）
        Returns:
            bool: 文件是否激活
        """
        start_time = time.time()
        while True:
            try:
                file_info = self.client.files.get(name=file_name)
                if file_info.state.name == "ACTIVE":
                    return True
                
                # 检查是否超时
                if time.time() - start_time > timeout:
                    logger.error(f"【Google】- 等待文件激活超时：{file_name}")
                    return False
                
                # 等待一段时间后重试
                time.sleep(self.retry_interval)
                
            except Exception as e:
                logger.error(f"【Google】- 检查文件状态失败：{str(e)}")
                return False

    @retry.Retry(predicate=is_retryable)
    def upload_file(self, file_path: str):
        """上传文件"""
        try:
            # 上传文件
            video_file = self.client.files.upload(file=file_path)
            # 等待一段时间后重试
            time.sleep(self.retry_interval * 3)
            # 等待文件状态变为 ACTIVE
            if not self._wait_for_file_active(video_file.name):
                err_msg = f"【Google】- 文件未能激活：{video_file.name}"
                logger.error(err_msg)
                raise Exception(err_msg)

            return video_file
        except Exception as e:
            err_msg = f"【Google】- 文件上传失败：{str(e)}"
            logger.error(err_msg)
            raise Exception(err_msg)
            
    @retry.Retry(predicate=is_retryable)
    def delete_google_file(self, google_file):
        """删除 google 文件"""
        try:
            self.client.files.delete(name=google_file.name)
            logger.info(f"【Google】- 已删除谷歌文件: {google_file.name}")
        except Exception as e:
            err_msg = f"【Google】- 删除文件失败: {str(e)}"
            logger.error(err_msg)
            raise Exception(err_msg)
        
    @retry.Retry(predicate=is_retryable)
    def generate_tag(self, google_file, dim: str, user_prompt: str = "对视频内容进行理解，并按照规则生成标签") -> str:
        """生成标签"""
        # 根据场景获取提示词
        # if dim == 'content':
        #     raise Exception("content维度故意失败")
        try:
            system_prompt = self.get_system_prompt_by_dim(dim)
        except Exception as e:
            logger.error(e)
            raise Exception(e)

        try:
            # 生成内容
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[google_file, system_prompt + user_prompt],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    top_p=0.95,
                    temperature=1,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                )
            )
        except Exception as e:
            err_msg = f"【Google】- 生成标签失败：{str(e)}"
            logger.error(err_msg)
            raise Exception(err_msg)

        # 检查响应是否为空
        try:
            if not response or not response.text:
                err_msg = "生成的响应为空"
                logger.error(f"【Google】- {err_msg}")
                raise GoogleTagGenerationError(err_msg)
        except GoogleTagGenerationError as e:
            raise GoogleTagGenerationError(e)
        
        # 检查响应是否为有效的 JSON 格式
        try:
            import json
            json.loads(response.text)
        except (GoogleTagGenerationError, json.JSONDecodeError) as e:
            err_msg = f"生成的响应不是有效的 JSON 格式: {str(e)}"
            logger.error(f"【Google】- {err_msg}")
            raise GoogleTagGenerationError(err_msg)

        return response.text
        
# 测试开启      
if __name__ == "__main__":
    
    google_file = None
    try:
        test = GoogleVisionService()
        start_time = time.time()
        file_path = "/home/eleven/vision-to-tag/test/test-2.mp4"
        google_file = test.upload_file(file_path)
        
        result = test.generate_tag(google_file=google_file, dim="vision")
        print(result)
        result = test.generate_tag(google_file=google_file, dim="audio")
        print(result)
        result = test.generate_tag(google_file=google_file, dim="content")
        print(result)
        result = test.generate_tag(google_file=google_file, dim="business")
        print(result)
        
        # 记录程序结束时间
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"程序执行时长: {execution_time:.2f} 秒")
    except Exception as e:
        print(str(e))
    finally:
        if google_file:
            test.delete_google_file(google_file=google_file)