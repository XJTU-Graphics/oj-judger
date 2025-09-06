import shutil
import subprocess
import requests
import logging
import argparse
import json
from pathlib import Path
from typing import Optional, List
from judger.executor.config import Config
from judger.executor.function_extractor import extract_function_implementation
from judger.executor.function_types import (
    FunctionRequirement, FunctionSignature, FunctionParameter
)


logger = logging.getLogger('validate')


def submit_result(
    judgment_id: int, result: str, log: str,
    function_impls: Optional[List[str]] = None
):
    """
    提交评测结果到管理节点

    :param judgment_id: 评测 ID
    :param result: 评测结果，必须是以下三者之一：
        - passed ，表示评测通过
        - failed ，表示评测未通过
        - error ，表示服务端执行评测过程中出错，但不是因为提交的代码本身有问题
    :param function_impls: 提取到的函数实现
    :param log: 当评测结果是 failed 或 error 时，用于返回失败命令的输出内容
    """
    url = f'http://{Config.MANAGER_IP}:{Config.MANAGER_PORT}/api/judge/{judgment_id}/result'
    payload = {'result': result, 'log': log}
    if result == 'passed' and function_impls is not None:
        payload['function_impls'] = function_impls
    logger.info(f'result to submit: {result}')

    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            logger.info(f'result of judgment {judgment_id} submitted')
        else:
            logger.error(f'failed to submit judgment result: {response.status_code}')
    except requests.exceptions.RequestException as e:
        logger.error(f'cannot connect to the manager node: {type(e)}: {str(e)}')


def compile_project(template_dir: Path, n_proc: int) -> tuple[bool, str]:
    """编译Dandelion项目"""
    build_dir = template_dir / 'build'

    # 1. 创建build目录
    build_dir.mkdir(parents=True, exist_ok=True)
    logger.info('directory build/ re-created')

    # 2. 执行cmake配置
    cmake_process = subprocess.run(
        ['cmake', '-S', str(template_dir), '-B', str(build_dir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        text=True
    )
    if cmake_process.returncode != 0:
        logger.warning('failed to configure CMake project')
        return False, cmake_process.stdout
    logger.info('CMake project configured')

    # 3. 执行编译
    build_process = subprocess.run(
        ['cmake', '--build', str(build_dir),
         '--config', 'Release',
         '--target', 'dandelion',
         '--parallel', str(n_proc)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        text=True
    )
    if build_process.returncode != 0:
        logger.warning('failed to compile the project')
        return False, build_process.stdout
    logger.info('successfully compiled project')

    return True, ''


def run_tests(template_dir: Path, n_proc: int, unit_test_name: str) -> tuple[bool, str]:
    """执行单元测试"""
    test_build_dir = template_dir / 'test' / 'build'

    try:
        # 1. 创建测试build目录
        test_build_dir.mkdir(parents=True, exist_ok=True)
        logger.info('directory test/build/ created')

        # 2. 执行cmake配置
        cmake_process = subprocess.run(
            ['cmake', '-S', str(template_dir / 'test'), '-B', str(test_build_dir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            text=True
        )
        if cmake_process.returncode != 0:
            logger.warning('failed to configure CMake test target')
            return False, cmake_process.stdout
        logger.info('CMake test target configured')

        # 3. 编译测试程序
        build_process = subprocess.run(
            ['cmake', '--build', str(test_build_dir),
             '--config', 'Release',
             '--target', 'test',
             '--parallel', str(n_proc)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            text=True
        )
        if build_process.returncode != 0:
            logger.warning('failed to compile test program')
            return False, build_process.stdout
        logger.info('test program compiled')

        # 4. 执行测试
        test_process = subprocess.run(
            [str(test_build_dir / 'test'), unit_test_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            text=True
        )

        if test_process.returncode != 0:
            logger.warning('unit test failed')
            return False, test_process.stdout
        logger.info('unit test passed')

        return True, ''

    except Exception as e:
        return False, str(e)


def extract_and_log_functions(
    template_dir: Path,
    function_requirements_json: str
) -> Optional[List[str]]:
    """
    提取并记录函数实现

    :param template_dir: 模板目录路径
    :param function_requirements_json: 函数需求信息的JSON字符串
    :return: 如果提取成功，返回所有函数实现组成的列表，未找到任何一个指定的函数实现则返回 `None`
    :raises RuntimeError: 当提取流程出现错误时抛出
    """
    try:
        requirements_data = json.loads(function_requirements_json)
        function_impls = []

        # 将字典数据转换为函数需求对象
        function_requirements = []
        for req_data in requirements_data:
            # 解析函数签名
            sig_data = req_data['function_signature']
            parameters = [
                FunctionParameter(param['name'], param['type'])
                for param in sig_data['parameters']
            ]
            function_signature = FunctionSignature(
                sig_data['return_type'],
                sig_data['name'],
                parameters
            )

            # 创建函数需求对象
            requirement = FunctionRequirement(
                req_data['id'],
                req_data['source_file_path'],
                function_signature
            )
            function_requirements.append(requirement)

        logger.info(
            f'{len(function_requirements)} function requirements parsed form command-line arg'
        )

        # 提取每个函数的实现
        build_dir = template_dir / 'build'
        for requirement in function_requirements:
            source_file_path = template_dir / requirement.source_file_path
            logger.info(
                f'try to extract {requirement.function_signature.name} from {source_file_path}'
            )

            if not source_file_path.exists():
                raise RuntimeError(f'source file {source_file_path} not found')

            try:
                # 提取函数实现
                implementation = extract_function_implementation(
                    source_file_path,
                    requirement.function_signature,
                    build_dir
                )

                if implementation is None:
                    logger.warning(
                        f'implementation of {requirement.function_signature.name} not found'
                    )
                    return None
                else:
                    # 输出函数实现到日志
                    logger.info(f'found implementation of {requirement.function_signature.name}')
                    function_impls.append(implementation)
            except RuntimeError as e:
                # 重新抛出 RuntimeError
                logger.error(
                    'unexpected error occurred when extracting '
                    f'{requirement.function_signature.name}: {type(e)}: {str(e)}'
                )
                raise

        return function_impls

    except RuntimeError:
        # 重新抛出 RuntimeError
        raise
    except Exception as e:
        # 其他异常转换为 RuntimeError 并抛出
        logger.error(f'unexpected error occurred during extraction: {type(e)}: {str(e)}')
        raise RuntimeError('failed to extract function implementation')


def main(
    judgment_id: int,
    temp_dir_path: str,
    unit_test_name: Optional[str] = None,
    function_requirements_json: Optional[str] = None
):
    """执行Dandelion项目验证并提交结果"""
    # 使用传入的临时目录路径
    template_dir = Path(temp_dir_path)
    n_proc = Config.PARALLEL_BUILD

    try:
        # 执行项目编译
        compile_success, compile_log = compile_project(template_dir, n_proc)
        if not compile_success:
            return submit_result(judgment_id, 'failed', compile_log)

        # 执行单元测试（如果提供测试名称）
        if unit_test_name:
            test_success, test_log = run_tests(template_dir, n_proc, unit_test_name)
            if not test_success:
                return submit_result(judgment_id, 'failed', test_log)

        # 提取函数实现（如果提供了描述需求的 JSON）
        function_impls = None
        if function_requirements_json is not None:
            function_impls = extract_and_log_functions(
                template_dir,
                function_requirements_json
            )
            if function_impls is None:
                return submit_result(judgment_id, 'failed', '未找到题目要求的所有函数实现')

        # 全部成功
        submit_result(judgment_id, 'passed', '', function_impls)

    except Exception as e:
        logger.warning(f'unexpected error occurred: {type(e)}: {str(e)}')
        # 捕获所有异常，返回error状态
        submit_result(judgment_id, 'error', str(e))

    finally:
        # 清理整个临时目录
        if template_dir.exists():
            shutil.rmtree(template_dir, ignore_errors=True)
        logger.info(f'judgment {judgment_id} done')


if __name__ == '__main__':
    # 使用argparse解析命令行参数
    parser = argparse.ArgumentParser(description='执行Dandelion项目验证')
    parser.add_argument('--judgment-id', type=int, required=True, help='评测ID')
    parser.add_argument('--temp-dir', type=str, required=True, help='临时目录路径')
    parser.add_argument('--unit-test', type=str, help='单元测试名称')
    parser.add_argument('--function-requirements', type=str, help='函数需求信息的JSON字符串')

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG,
        format=Config.LOG_FORMAT,
        filename=Path(Config.LOG_DIR) / f'{args.judgment_id}.log'
    )

    main(
        args.judgment_id,
        args.temp_dir,
        args.unit_test,
        args.function_requirements
    )
