import time
import subprocess
import socket
import requests
import logging
from typing import Dict, Any
from judger.executor.config import Config

logger = logging.getLogger('reporter')
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s][%(name)s][%(asctime)s] %(message)s'
)


class StatusReporter:
    def __init__(self):
        self.manager_url = f'http://{Config.MANAGER_IP}:{Config.MANAGER_PORT}/api/judge/executors'

    def get_cpu_info(self) -> Dict[str, str]:
        """获取CPU信息"""
        try:
            result = subprocess.run(
                ['lscpu', '-p=cpu,modelname'],
                capture_output=True, text=True, check=True
            )
            output = result.stdout

            # Format example: 19,Intel Core i5 xxxx
            last_line = output.splitlines()[-1].split(',')

            return {
                'cpu_model_name': last_line[1],
                'n_cpus': int(last_line[0]) + 1
            }
        except Exception as e:
            logger.error(f'Failed to get CPU info: {e}')
            return {
                'cpu_model_name': 'unknown',
                'n_cpus': 0
            }

    def get_memory_info(self) -> int:
        """获取内存信息（单位：MiB）"""
        try:
            result = subprocess.run(['free', '-m'], capture_output=True, text=True, check=True)
            output = result.stdout.splitlines()[1]
            return int(output.split()[1])
        except Exception as e:
            logger.error(f'Failed to get memory info: {e}')
            return 0

    def check_service_alive(self) -> bool:
        """检查本地Flask服务是否存活"""
        try:
            response = requests.get('http://127.0.0.1:10011/alive', timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f'Service alive check failed: {e}')
            return False

    def collect_status(self) -> Dict[str, Any]:
        """收集所有状态信息"""
        cpu_info = self.get_cpu_info()
        return {
            'hostname': socket.gethostname(),
            'cpu_model_name': cpu_info['cpu_model_name'],
            'n_cpus': cpu_info['n_cpus'],
            'memory_mib': self.get_memory_info(),
            'is_alive': self.check_service_alive()
        }

    def report(self):
        """上报状态到管理节点"""
        status = self.collect_status()
        try:
            response = requests.post(
                self.manager_url,
                json=status,
                timeout=10
            )
            response.raise_for_status()
            logger.info(f'Status reported successfully: {status}')
        except Exception as e:
            logger.error(f'Failed to report status: {e}')

    def start(self):
        """启动定时上报"""
        logger.info('Starting status reporter')
        while True:
            self.report()
            time.sleep(Config.KEEP_ALIVE_INTERVAL * 60)


if __name__ == '__main__':
    reporter = StatusReporter()
    reporter.start()
