from typing import Optional, Dict, Union, List
import requests
from judger.utils.token_manager import TokenManager


class APIRequestError(Exception):
    """API请求异常类

    :ivar str message: 错误描述信息
    """
    pass


class APIClient:
    """封装Web服务端API请求的工具类

    :param token_manager: TokenManager实例，用于获取JWT令牌
    """

    def __init__(self, token_manager: TokenManager):
        """初始化APIClient

        :param token_manager: TokenManager实例
        """
        self.token_manager = token_manager

    def _get_headers(self) -> Dict[str, str]:
        """获取带有JWT的请求头

        :return: 包含Authorization头的字典
        """
        return {
            'Authorization': f'Bearer {self.token_manager.get_access_token()}'
        }

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """发送请求的核心方法

        :param method: HTTP方法（GET/POST等）
        :param endpoint: API端点路径
        :param kwargs: 请求参数
        :return: 原始响应对象
        :raises APIRequestError: 当请求失败时抛出
        """
        url = f'{self.token_manager.get_web_base_url()}{endpoint}'
        headers = self._get_headers()

        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                timeout=5,
                **kwargs
            )
            if response.status_code == 401:
                self.token_manager.refresh_tokens()
                headers = self._get_headers()
                response = requests.request(
                    method,
                    url,
                    headers=headers,
                    timeout=5,
                    **kwargs
                )
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            raise APIRequestError(f'{method} request to {endpoint} failed: {str(e)}')

    def get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        parse_json: bool = True,
        **kwargs
    ) -> List | Dict | requests.Response:
        """发送GET请求

        :param endpoint: API端点路径
        :param params: 查询参数字典
        :param parse_json: 是否解析为JSON
        :param kwargs: 额外请求参数(如stream=True)
        :return: 如果请求的是文件且请求成功，则返回原始响应对象，其余情况返回解析 JSON 响应体得到的字典或列表
        :raises APIRequestError: 当请求失败时抛出
        """
        response = self._request('GET', endpoint, params=params, **kwargs)
        return response.json() if parse_json else response

    def post(
        self,
        endpoint: str,
        data: Optional[Dict] = None,
        parse_json: bool = True,
        **kwargs
    ) -> Union[Dict, requests.Response]:
        """发送POST请求

        :param endpoint: API端点路径
        :param data: 请求体数据字典
        :param parse_json: 是否解析为JSON
        :param kwargs: 额外请求参数
        :return: 响应数据或原始响应对象
        :raises APIRequestError: 当请求失败时抛出
        """
        response = self._request('POST', endpoint, json=data, **kwargs)
        return response.json() if parse_json else response
