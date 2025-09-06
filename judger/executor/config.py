import os


class Config:
    MANAGER_IP = os.environ.get('MANAGER_IP') or '127.0.0.1'
    MANAGER_PORT = os.environ.get('MANAGER_PORT') or '10010'
    # 向管理节点上报状态的时间间隔（以分钟计），如果网络环境稳定可以适当增大
    KEEP_ALIVE_INTERVAL = os.environ.get('KEEP_ALIVE_INTERVAL') or 1
    WEB_SERVER_IP = os.environ.get('WEB_SERVER_IP') or '127.0.0.1'
    WEB_SERVER_PORT = os.environ.get('WEB_SERVER_PORT') or '8000'
    # 登录 Web 服务端的账号和密码
    WEB_ACCOUNT = os.environ.get('WEB_ACCOUNT')
    WEB_PASSWORD = os.environ.get('WEB_PASSWORD')
    # 编译项目时启动的线程数，默认等于 CPU 核数，若获取不到核数则为 4
    PARALLEL_BUILD = os.environ.get('PARALLEL_BUILD') or os.cpu_count() or 4
    # 临时存放解压后的模板和提交内容
    TMP_DIR = os.environ.get('TMP_DIR') or '/tmp'
    LOG_FORMAT = '[%(levelname)s][%(name)s][%(asctime)s] %(message)s'
    # 存放每个评测的日志信息
    LOG_DIR = os.environ.get('LOG_DIR') or '/var/log/judgment'
