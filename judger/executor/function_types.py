"""
函数类型定义模块

该模块定义了函数提取功能所需的数据结构。
"""

from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class FunctionParameter:
    """函数参数"""
    name: str
    type: str


@dataclass
class FunctionSignature:
    """函数签名"""
    return_type: str
    name: str
    parameters: List[FunctionParameter]


@dataclass
class FunctionRequirement:
    """函数需求"""
    id: int
    problem_id: int
    source_file_path: str
    function_signature: FunctionSignature


def parse_function_signature(signature_data: Dict[str, Any]) -> FunctionSignature:
    """
    从字典数据解析函数签名

    :param signature_data: 包含函数签名信息的字典
    :return: 解析后的函数签名对象
    :raises RuntimeError: 如果缺少必要的字段
    """
    return_type = signature_data.get('return_type')
    name = signature_data.get('name')

    if return_type is None:
        raise RuntimeError("函数签名中缺少 'return_type' 字段")

    if name is None:
        raise RuntimeError("函数签名中缺少 'name' 字段")

    parameters_data = signature_data.get('parameters', [])

    parameters = []
    for param in parameters_data:
        param_name = param.get('name')
        param_type = param.get('type')

        if param_name is None:
            raise RuntimeError("函数参数中缺少 'name' 字段")

        if param_type is None:
            raise RuntimeError("函数参数中缺少 'type' 字段")

        parameters.append(FunctionParameter(param_name, param_type))

    return FunctionSignature(return_type, name, parameters)


def parse_function_requirement(requirement_data: Dict[str, Any]) -> FunctionRequirement:
    """
    从字典数据解析函数需求

    :param requirement_data: 包含函数需求信息的字典
    :return: 解析后的函数需求对象
    """
    requirement_id = requirement_data.get('id', 0)
    problem_id = requirement_data.get('problem_id', 0)
    source_file_path = requirement_data.get('source_file_path', '')
    signature_data = requirement_data.get('function_signature', {})

    function_signature = parse_function_signature(signature_data)

    return FunctionRequirement(
        requirement_id,
        problem_id,
        source_file_path,
        function_signature
    )
