"""
AI提示词模块
"""

import os
from pathlib import Path


def get_prompt_path(os_type: str = "windows") -> Path:
    """获取提示词文件路径"""
    prompts_dir = Path(__file__).parent
    filename = "macos.txt" if os_type.lower() == "darwin" else "windows.txt"
    return prompts_dir / filename


def load_prompt(os_type: str = "windows") -> str:
    """加载提示词内容"""
    prompt_path = get_prompt_path(os_type)
    if prompt_path.exists():
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""
