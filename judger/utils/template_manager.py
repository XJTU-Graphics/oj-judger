from pathlib import Path
from typing import Dict
import shutil
from datetime import datetime
from judger.utils.api_client import APIClient
from judger.executor.config import Config


class TemplateManager:
    """管理模板缓存和下载的类"""

    def __init__(self, api_client: APIClient):
        """初始化模板管理器

        :param api_client: APIClient实例
        """
        self.api_client = api_client
        self.cache_dir = Path(Config.TMP_DIR) / 'templates'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # 模板缓存字典 {template_id: {'updated_at': str, 'path': Path}}
        self.template_cache: Dict[int, Dict] = {}

    def get_template(self, template_id: int) -> Dict[str, any]:
        """获取模板信息，必要时下载最新版本

        :param template_id: 模板ID
        :return: 包含模板信息的字典 {'path': Path, 'dir_name': str}
        :raises APIRequestError: 当获取模板失败时抛出
        """
        # 获取模板信息
        template_info = self.api_client.get(f'/api/templates/{template_id}')
        updated_at = template_info['updated_at']

        # 检查缓存
        cache_entry = self.template_cache.get(template_id)
        if cache_entry:
            # 将时间字符串转换为datetime对象进行比较
            cache_time = datetime.fromisoformat(cache_entry['updated_at'])
            new_time = datetime.fromisoformat(updated_at)
            if cache_time >= new_time:
                return {
                    'path': cache_entry['path'],
                    'dir_name': cache_entry['dir_name']
                }

        # 需要下载新模板
        self._download_template(template_id, updated_at)
        cache_entry = self.template_cache.get(template_id)
        return {
            'path': cache_entry['path'],
            'dir_name': cache_entry['dir_name']
        }

    def _download_template(self, template_id: int, updated_at: str) -> Path:
        """下载并解压模板

        :param template_id: 模板ID
        :param updated_at: 模板更新时间
        :return: 解压后的模板目录路径
        """
        # 准备目录
        template_dir = self.cache_dir / str(template_id)
        if template_dir.exists():
            shutil.rmtree(template_dir)
        template_dir.mkdir()

        # 下载模板zip文件
        zip_path = template_dir / 'template.zip'
        response = self.api_client.get(
            f'/api/templates/{template_id}/download',
            parse_json=False,
            stream=True
        )

        # 将响应内容写入文件
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # 解压模板到唯一目录
        extracted_dir = template_dir
        shutil.unpack_archive(str(zip_path), str(extracted_dir))
        zip_path.unlink()
        contents = list(extracted_dir.iterdir())
        if len(contents) > 1:
            raise RuntimeError(
                f'a template can only contain one directory, but {contents} are found'
            )
        content_dir = contents[0]
        content_dir_name = content_dir.stem

        # 更新缓存
        self.template_cache[template_id] = {
            'updated_at': updated_at,
            'path': content_dir,
            'dir_name': content_dir_name
        }

        return extracted_dir

    def clear_cache(self):
        """清空所有模板缓存"""
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
        self.cache_dir.mkdir()
        self.template_cache.clear()
