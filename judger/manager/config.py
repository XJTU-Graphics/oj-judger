import os


class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get('SQLALCHEMY_DATABASE_URI') or 'sqlite:///judger.db'
    WEB_SERVER_IP = os.environ.get('WEB_SERVER_IP') or '127.0.0.1'
    WEB_SERVER_PORT = os.environ.get('WEB_SERVER_PORT') or '8000'
    # Account and password for login to the Web backend
    WEB_ACCOUNT = os.environ.get('WEB_ACCOUNT')
    WEB_PASSWORD = os.environ.get('WEB_PASSWORD')
    EXECUTOR_PORT = os.environ.get('EXECUTOR_PORT') or '10011'
