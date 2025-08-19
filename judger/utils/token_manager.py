from pathlib import Path
import json
import requests
from filelock import FileLock
from flask import current_app
from typing import Optional, Dict


class TokenManager:
    """JWT令牌管理器，用于管理节点与Web服务端的认证"""

    def __init__(self, node_type: str):
        self.node_type = node_type
        self.token_file = Path(f'/tmp/oj_judger_{node_type}_tokens.json')
        self.lock = FileLock(f'{self.token_file}.lock')

    def get_web_base_url(self) -> str:
        """获取Web服务端基础URL"""
        config = current_app.config
        return f'http://{config["WEB_SERVER_IP"]}:{config["WEB_SERVER_PORT"]}'

    def _load_tokens(self) -> Optional[Dict]:
        """从文件加载令牌(带文件锁)"""
        try:
            with self.lock:
                if self.token_file.exists():
                    return json.loads(self.token_file.read_text())
        except (json.JSONDecodeError, IOError):
            return None
        return None

    def _save_tokens(self, tokens: Dict):
        """保存令牌到文件(带文件锁)"""
        with self.lock:
            self.token_file.write_text(json.dumps(tokens))

    def _login(self) -> Dict:
        """初始登录获取令牌"""
        login_url = f'{self.get_web_base_url()}/login'
        response = requests.post(
            login_url,
            json={
                'account': current_app.config['WEB_ACCOUNT'],
                'password': current_app.config['WEB_PASSWORD']
            }
        )
        response.raise_for_status()
        tokens = response.json()
        self._save_tokens(tokens)
        return tokens

    def refresh_tokens(self):
        """刷新JWT令牌并保存结果"""
        tokens = self._load_tokens()
        if not tokens or 'refresh_token' not in tokens:
            self._login()
            return

        refresh_url = f'{self.get_web_base_url()}/refresh'
        try:
            response = requests.post(
                refresh_url,
                headers={'Authorization': f'Bearer {tokens["refresh_token"]}'}
            )
            response.raise_for_status()
            self._save_tokens(response.json())
        except requests.RequestException:
            # 刷新失败时尝试重新登录
            self._login()

    def get_access_token(self) -> str:
        """获取有效的access_token"""
        tokens = self._load_tokens() or self._login()
        return tokens['access_token']

    def get_refresh_token(self) -> str:
        tokens = self._load_tokens() or self._login()
        return tokens['refresh_token']
