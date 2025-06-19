import os


class Config:
    MANAGER_IP = os.environ.get('MANAGER_IP') or '127.0.0.1'
    MANAGER_PORT = os.environ.get('MANAGER_PORT') or '10010'
    # Interval between two keep alive reports (in minute)
    KEEP_ALIVE_INTERVAL = os.environ.get('KEEP_ALIVE_INTERVAL') or 1
    # Path to Dandelion template (removing src/ from the project)
    DANDELION_TEMPLATE = os.environ.get('DANDELION_TEMPLATE') or 'dandelion-template'
    WEB_SERVER_IP = os.environ.get('WEB_SERVER_IP') or '127.0.0.1'
    WEB_SERVER_PORT = os.environ.get('WEB_SERVER_PORT') or '8000'
    # Account and password for login to the Web backend
    WEB_ACCOUNT = os.environ.get('WEB_ACCOUNT')
    WEB_PASSWORD = os.environ.get('WEB_PASSWORD')
    # Number of parallel build processes (default: CPU count or 4)
    PARALLEL_BUILD = os.environ.get('PARALLEL_BUILD') or os.cpu_count() or 4
