"""
命令行接口模块

提供管理节点（manager）和执行节点（executor）的命令行启动功能。
"""

import argparse
import sys
import subprocess
import threading

from judger.manager import create_app as create_manager_app
from judger.executor import create_app as create_executor_app


def run_distribute_script():
    """运行分发脚本"""
    # 导入并运行分发脚本
    from judger.manager.distribute import distribute_tasks
    distribute_tasks()


def run_reporter_script():
    """运行上报脚本"""
    # 导入并运行上报脚本
    from judger.executor.reporter import StatusReporter
    reporter = StatusReporter()
    reporter.start()


def manager() -> None:
    """启动管理节点（Flask 应用 + 分发脚本）"""
    parser = argparse.ArgumentParser(description='启动 OJ 评测系统管理节点')
    parser.add_argument('--host', default='127.0.0.1', help='监听地址 (默认: %(default)s)')
    parser.add_argument('--port', type=int, default=10010, help='监听端口 (默认: %(default)s)')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    parser.add_argument('--workers', type=int, default=1, help='工作进程数 (默认: %(default)s)')

    args = parser.parse_args()

    app = create_manager_app()

    # 在调试模式下，直接运行 Flask 应用和分发脚本
    if args.debug:
        # 创建并启动分发脚本线程
        distribute_thread = threading.Thread(target=run_distribute_script)
        distribute_thread.daemon = True
        distribute_thread.start()

        # 运行 Flask 应用
        app.run(host=args.host, port=args.port, debug=True)
    else:
        # 在生产模式下，使用 gunicorn 运行 Flask 应用，并在子进程中运行分发脚本
        # 启动分发脚本子进程
        distribute_process = subprocess.Popen([
            sys.executable, '-c',
            'from judger.manager.distribute import distribute_tasks; distribute_tasks()'
        ])

        try:
            # 运行 Flask 应用
            import gunicorn.app.base

            class StandaloneApplication(gunicorn.app.base.BaseApplication):
                def __init__(self, app, options=None):
                    self.options = options or {}
                    self.application = app
                    super().__init__()

                def load_config(self):
                    config = {
                        key: value for key, value in self.options.items()
                        if key in self.cfg.settings and value is not None
                    }
                    for key, value in config.items():
                        self.cfg.set(key.lower(), value)

                def load(self):
                    return self.application

            options = {
                'bind': f'{args.host}:{args.port}',
                'workers': args.workers,
                'worker_class': 'sync',
                'timeout': 120,
            }
            StandaloneApplication(app, options).run()
        finally:
            # 确保 Flask 应用关闭时，分发脚本子进程也被终止
            distribute_process.terminate()
            distribute_process.wait()


def executor() -> None:
    """启动执行节点（Flask 应用 + 上报脚本）"""
    parser = argparse.ArgumentParser(description='启动 OJ 评测系统执行节点')
    parser.add_argument('--host', default='127.0.0.1', help='监听地址 (默认: %(default)s)')
    parser.add_argument('--port', type=int, default=10011, help='监听端口 (默认: %(default)s)')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    parser.add_argument('--workers', type=int, default=1, help='工作进程数 (默认: %(default)s)')

    args = parser.parse_args()

    app = create_executor_app()

    # 在调试模式下，直接运行 Flask 应用和上报脚本
    if args.debug:
        # 创建并启动上报脚本线程
        reporter_thread = threading.Thread(target=run_reporter_script)
        reporter_thread.daemon = True
        reporter_thread.start()

        # 运行 Flask 应用
        app.run(host=args.host, port=args.port, debug=True)
    else:
        # 在生产模式下，使用 gunicorn 运行 Flask 应用，并在子进程中运行上报脚本
        # 启动上报脚本子进程
        reporter_process = subprocess.Popen([
            sys.executable, '-c',
            'from judger.executor.reporter import StatusReporter; '
            'reporter = StatusReporter(); reporter.start()'
        ])

        try:
            # 运行 Flask 应用
            import gunicorn.app.base

            class StandaloneApplication(gunicorn.app.base.BaseApplication):
                def __init__(self, app, options=None):
                    self.options = options or {}
                    self.application = app
                    super().__init__()

                def load_config(self):
                    config = {
                        key: value for key, value in self.options.items()
                        if key in self.cfg.settings and value is not None
                    }
                    for key, value in config.items():
                        self.cfg.set(key.lower(), value)

                def load(self):
                    return self.application

            options = {
                'bind': f'{args.host}:{args.port}',
                'workers': args.workers,
                'worker_class': 'sync',
                'timeout': 120,
            }
            StandaloneApplication(app, options).run()
        finally:
            # 确保 Flask 应用关闭时，上报脚本子进程也被终止
            reporter_process.terminate()
            reporter_process.wait()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('请指定要启动的节点类型: manager 或 executor')
        sys.exit(1)

    node_type = sys.argv[1]
    if node_type == 'manager':
        manager()
    elif node_type == 'executor':
        executor()
    else:
        print(f'未知的节点类型: {node_type}')
        sys.exit(1)
