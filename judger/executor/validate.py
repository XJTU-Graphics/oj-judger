import sys
import shutil
import subprocess
import requests
import logging
from pathlib import Path
from typing import Optional
from judger.executor.config import Config


logger = logging.getLogger('validate')


def submit_result(judgment_id: int, result: str, log: str):
    '''提交评测结果到管理节点'''
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


def compile_project(dandelion_template: Path, n_proc: int) -> tuple[bool, str]:
    '''编译Dandelion项目'''
    build_dir = dandelion_template / 'build'
    
    # 1. 创建build目录
    build_dir.mkdir(parents=True, exist_ok=True)
    print('directory build/ re-created')

    # 2. 执行cmake配置
    cmake_process = subprocess.run(
        ['cmake', '-S', str(dandelion_template), '-B', str(build_dir)],
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


def run_tests(dandelion_template: Path, n_proc: int, unit_test_name: str) -> tuple[bool, str]:
    '''执行单元测试'''
    test_build_dir = dandelion_template / 'test' / 'build'
    
    try:
        # 1. 创建测试build目录
        test_build_dir.mkdir(parents=True, exist_ok=True)
        print('directory test/build/ created')

        # 2. 执行cmake配置
        cmake_process = subprocess.run(
            ['cmake', '-S', str(dandelion_template / 'test'), '-B', str(test_build_dir)],
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


def main(judgment_id: int, unit_test_name: Optional[str] = None):
    '''执行Dandelion项目验证并提交结果'''
    dandelion_template = Path(f'{Config.TMP_DIR}/dandelion-template')
    n_proc = Config.PARALLEL_BUILD
    
    try:
        # 执行项目编译
        compile_success, compile_log = compile_project(dandelion_template, n_proc)
        if not compile_success:
            return submit_result(judgment_id, 'failed', compile_log)

        # 执行单元测试（如果提供测试名称）
        if unit_test_name:
            test_success, test_log = run_tests(dandelion_template, n_proc, unit_test_name)
            if not test_success:
                return submit_result(judgment_id, 'failed', test_log)

        # 全部成功
        submit_result(judgment_id, 'passed', '')

    except Exception as e:
        # 捕获所有异常，返回error状态
        submit_result(judgment_id, 'error', str(e))

    finally:
        # 清理整个临时目录
        if dandelion_template.exists():
            shutil.rmtree(dandelion_template, ignore_errors=True)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s][%(name)s][%(asctime)s] %(message)s'
    )
    
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        logger.error('Usage: python validate.py <judgment_id> [unit_test_name]')
        sys.exit(1)

    judgment_id = int(sys.argv[1])
    unit_test_name = sys.argv[2] if len(sys.argv) >= 3 else None
    main(judgment_id, unit_test_name)
