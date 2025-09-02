import shutil
import subprocess
import requests
import logging
import argparse
import json
from pathlib import Path
from typing import Optional
from judger.executor.config import Config
from judger.executor.function_extractor import extract_function_implementation
from judger.executor.function_types import (
    FunctionRequirement, FunctionSignature, FunctionParameter
)


logger = logging.getLogger('validate')


def submit_result(judgment_id: int, result: str, log: str):
    """
    提交评测结果到管理节点

    :param judgment_id: 评测 ID
    :param result: 评测结果，必须是以下三者之一：
        - passed ，表示评测通过
        - failed ，表示评测未通过
        - error ，表示服务端执行评测过程中出错，但不是因为提交的代码本身有问题
    :param log: 当评测结果是 failed 或 error 时，用于返回失败命令的输出内容
    """
    url = f'http://{Config.MANAGER_IP}:{Config.MANAGER_PORT}/api/judge/{judgment_id}/result'
    payload = {'result': result, 'log': log}

    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            logger.info(f'评测记录 {judgment_id} 结果上报成功')
        else:
            logger.error(f'结果上报失败: {response.status_code}')
    except requests.exceptions.RequestException as e:
        logger.error(f'请求管理节点失败: {str(e)}')


def compile_project(template_dir: Path, n_proc: int) -> tuple[bool, str]:
    """编译Dandelion项目"""
    build_dir = template_dir / 'build'

    # 1. 创建build目录
    build_dir.mkdir(parents=True, exist_ok=True)
    print('directory build/ re-created')

    # 2. 执行cmake配置
    cmake_process = subprocess.run(
        ['cmake', '-S', str(template_dir), '-B', str(build_dir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        text=True
    )
    print('CMake project configured')

    if cmake_process.returncode != 0:
        return False, cmake_process.stdout

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
    print('successfully compiled project')

    if build_process.returncode != 0:
        return False, build_process.stdout

    return True, ''


def run_tests(template_dir: Path, n_proc: int, unit_test_name: str) -> tuple[bool, str]:
    """执行单元测试"""
    test_build_dir = template_dir / 'test' / 'build'

    try:
        # 1. 创建测试build目录
        test_build_dir.mkdir(parents=True, exist_ok=True)
        print('directory test/build/ created')

        # 2. 执行cmake配置
        cmake_process = subprocess.run(
            ['cmake', '-S', str(template_dir / 'test'), '-B', str(test_build_dir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            text=True
        )
        print('CMake test project configured')

        if cmake_process.returncode != 0:
            return False, cmake_process.stdout

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
        print('test program compiled')

        if build_process.returncode != 0:
            return False, build_process.stdout

        # 4. 执行测试
        test_process = subprocess.run(
            [str(test_build_dir / 'test'), unit_test_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            text=True
        )
        print('test executed')

        if test_process.returncode != 0:
            return False, test_process.stdout

        return True, ''

    except Exception as e:
        return False, str(e)


def extract_and_log_functions(
    template_dir: Path,
    function_requirements_json: Optional[str] = None
) -> bool:
    """
    提取并记录函数实现

    :param template_dir: 模板目录路径
    :param problem_id: 题目ID
    :param function_requirements_json: 函数需求信息的JSON字符串
    :return: 是否所有函数都成功提取
    :raises RuntimeError: 当提取流程出现错误时抛出
    """
    try:
        # 如果有函数需求信息的JSON字符串，直接解析使用
        if function_requirements_json:
            requirements_data = json.loads(function_requirements_json)

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
                    req_data['problem_id'],
                    req_data['source_file_path'],
                    function_signature
                )
                function_requirements.append(requirement)

            logger.info(f'从命令行参数解析得到 {len(function_requirements)} 个函数需求')
        else:
            # 如果没有提供函数需求信息的JSON字符串，说明没有函数需求需要提取
            logger.info('没有提供函数需求信息，跳过函数提取')
            return True

        # 提取每个函数的实现
        build_dir = template_dir / 'build'
        for requirement in function_requirements:
            source_file_path = template_dir / requirement.source_file_path
            logger.info(f'从 {source_file_path} 中提取函数 {requirement.function_signature.name}')

            if not source_file_path.exists():
                logger.error(f'源文件不存在: {source_file_path}')
                return False

            try:
                # 提取函数实现
                implementation = extract_function_implementation(
                    source_file_path,
                    requirement.function_signature,
                    build_dir
                )

                if implementation is None:
                    logger.error(
                        f'提取函数 {requirement.function_signature.name} 实现失败'
                    )
                    return False
                else:
                    # 输出函数实现到日志
                    logger.info(f'函数 {requirement.function_signature.name} 实现提取成功:')
                    logger.info(f'--- impl start ---\n{implementation}')
                    logger.info('---  impl end  ---')
            except RuntimeError as e:
                # 重新抛出 RuntimeError
                logger.error(f'提取函数 {requirement.function_signature.name} 实现时发生流程错误: {str(e)}')
                raise

        return True

    except RuntimeError:
        # 重新抛出 RuntimeError
        raise
    except Exception as e:
        # 其他异常转换为 RuntimeError 并抛出
        logger.error(f'提取函数实现时发生未知错误: {str(e)}')
        raise RuntimeError(f'提取函数实现失败: {str(e)}') from e


def main(
    judgment_id: int,
    temp_dir_path: str,
    unit_test_name: Optional[str] = None,
    problem_id: Optional[int] = None,
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

        # 提取函数实现（如果提供了problem_id）
        if problem_id is not None:
            extraction_success = extract_and_log_functions(
                template_dir,
                function_requirements_json
            )
            if not extraction_success:
                return submit_result(judgment_id, 'failed', '函数提取失败')

        # 全部成功
        submit_result(judgment_id, 'passed', '')

    except Exception as e:
        # 捕获所有异常，返回error状态
        submit_result(judgment_id, 'error', str(e))

    finally:
        # 清理整个临时目录
        if template_dir.exists():
            shutil.rmtree(template_dir, ignore_errors=True)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s][%(name)s][%(asctime)s] %(message)s'
    )

    # 使用argparse解析命令行参数
    parser = argparse.ArgumentParser(description='执行Dandelion项目验证')
    parser.add_argument('--judgment-id', type=int, required=True, help='评测ID')
    parser.add_argument('--temp-dir', type=str, required=True, help='临时目录路径')
    parser.add_argument('--unit-test', type=str, help='单元测试名称')
    parser.add_argument('--problem-id', type=int, help='题目ID')
    parser.add_argument('--function-requirements', type=str, help='函数需求信息的JSON字符串')

    args = parser.parse_args()

    main(
        args.judgment_id,
        args.temp_dir,
        args.unit_test,
        args.problem_id,
        args.function_requirements
    )
