import os


class Config:
    MANAGER_IP = os.environ.get('MANAGER_IP') or '127.0.0.1'
    MANAGER_PORT = os.environ.get('MANAGER_PORT') or '10010'
    # Interval between two keep alive reports (in minute)
    KEEP_ALIVE_INTERVAL = os.environ.get('KEEP_ALIVE_INTERVAL') or 1
    WEB_SERVER_IP = os.environ.get('WEB_SERVER_IP') or '127.0.0.1'
    WEB_SERVER_PORT = os.environ.get('WEB_SERVER_PORT') or '8000'
    # Account and password for login to the Web backend
    WEB_ACCOUNT = os.environ.get('WEB_ACCOUNT')
    WEB_PASSWORD = os.environ.get('WEB_PASSWORD')
    # Number of parallel build processes (default: CPU count or 4)
    PARALLEL_BUILD = os.environ.get('PARALLEL_BUILD') or os.cpu_count() or 4
    TMP_DIR = os.environ.get('TMP_DIR') or '/tmp'
    LOG_FORMAT = '[%(levelname)s][%(name)s][%(asctime)s] %(message)s'
    LOG_DIR = os.environ.get('LOG_DIR') or '/var/log/judgment'
