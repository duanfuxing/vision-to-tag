import os
from jinja2 import Environment, FileSystemLoader, Template
from typing import Dict
from app.services.logger import get_logger

# 日志
logger = get_logger()

"""
提示词管理器
通过 jinja2 实现
"""
class PromptManager:
    def __init__(self, prompt_dir=None):
        if prompt_dir is None:
            # 获取当前文件所在目录的上一级目录-prompts
            base_dir = os.path.dirname(os.path.abspath(__file__))
            prompt_dir = os.path.join(base_dir, "prompt-v3-modules")  # 确保是绝对路径

        prompt_dir = os.path.abspath(prompt_dir)  # 进一步确保路径为绝对路径

        if not os.path.exists(prompt_dir):
            logger.error(f"【prompt-manager】- 未找到提示词目录: {prompt_dir}")
            raise Exception(f"未找到提示词目录: {prompt_dir}")

        self.env = Environment(
            loader=FileSystemLoader(prompt_dir),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True
        )
        self.templates: Dict[str, Template] = {}
        self._preload_templates()

    def _preload_templates(self):
        """预加载所有模板结构"""
        for root, _, files in os.walk(self.env.loader.searchpath[0]):
            rel_path = os.path.relpath(root, self.env.loader.searchpath[0])
            for f in files:
                if f.endswith('.jinja'):
                    template_path = os.path.join(rel_path, f).replace('\\', '/')
                    # 只存储路径，实际使用时再加载模板
                    self.templates[template_path] = None

    def get_prompt(self, template_name: str, **kwargs) -> str:
        """
        获取渲染后的提示词
        :param template_name: 模板文件名（不带后缀或带.jinja后缀均可）
        :param kwargs: 模板参数
        :return: 渲染后的提示词文本
        """
        # 确保 template_name 有效
        if template_name not in [
            "vision",
            "audio",
            "content-semantics",
            "commercial-value",
        ]:
            logger.info(f"【prompt-manager】- 提示词非法{template_name}")
            raise Exception(f"提示词非法: {template_name}")
        # 确保模板名称有.jinja后缀
        if not template_name.endswith('.jinja'):
            # prompt-v3-前缀
            template_name = f"prompt-v3-{template_name}.jinja"
        try:
            template = self.env.get_template(template_name)
            return template.render(**kwargs)
        except Exception as e:
            logger.error(f"【prompt-manager】- 提示词加载错误: {template_name}, 错误: {str(e)}")
            raise Exception(f"提示词加载错误: {template_name}, 错误: {str(e)}")

# 单例实例
prompt_manager = PromptManager()