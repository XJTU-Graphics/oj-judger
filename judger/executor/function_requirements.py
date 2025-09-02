"""
函数需求获取模块

该模块负责从 Web 服务端获取函数需求列表。
"""

from typing import List, Optional
import logging
from judger.utils.api_client import APIClient, APIRequestError
from judger.executor.function_types import FunctionRequirement, parse_function_requirement


logger = logging.getLogger('function_requirements')


def get_function_requirements(api_client: APIClient, problem_id: int) -> List[FunctionRequirement]:
    """
    从 Web 服务端获取函数需求列表

    :param api_client: API客户端实例
    :param problem_id: 题目ID
    :return: 函数需求列表
    :raises APIRequestError: 当API请求失败时抛出
    """
    try:
        # 调用Web服务端API获取函数需求列表
        response = api_client.get(f'/api/problems/{problem_id}/functions')

        # 解析响应数据
        requirements_data = response if isinstance(response, list) else []

        # 转换为函数需求对象列表
        function_requirements = [
            parse_function_requirement(req_data)
            for req_data in requirements_data
        ]

        logger.info(f'成功获取题目 {problem_id} 的函数需求列表，共 {len(function_requirements)} 个函数')
        return function_requirements

    except APIRequestError as e:
        logger.error(f'获取题目 {problem_id} 的函数需求列表失败: {str(e)}')
        raise


def get_function_requirement_by_id(
    api_client: APIClient,
    problem_id: int,
    requirement_id: int
) -> Optional[FunctionRequirement]:
    """
    根据需求ID获取特定函数需求

    :param api_client: API客户端实例
    :param problem_id: 题目ID
    :param requirement_id: 函数需求ID
    :return: 函数需求对象，如果未找到则返回None
    :raises APIRequestError: 当API请求失败时抛出
    """
    try:
        # 获取所有函数需求
        all_requirements = get_function_requirements(api_client, problem_id)

        # 查找指定ID的函数需求
        for requirement in all_requirements:
            if requirement.id == requirement_id:
                logger.info(
                    f'找到题目 {problem_id} 的函数需求 {requirement_id}: '
                    f'{requirement.function_signature.name}'
                )
                return requirement

        logger.warning(f'未找到题目 {problem_id} 的函数需求 {requirement_id}')
        return None

    except APIRequestError as e:
        logger.error(f'获取题目 {problem_id} 的函数需求 {requirement_id} 失败: {str(e)}')
        raise
