import os
import tempfile
import pytest
from judger.manager import create_app as create_manager_app
from judger.manager.models import db as manager_db


@pytest.fixture(scope='module')
def manager_app():
    """创建manager测试应用"""
    fd, path = tempfile.mkstemp()
    app = create_manager_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False
    })
    
    with app.app_context():
        manager_db.create_all()
        yield app
        manager_db.session.remove()
        manager_db.drop_all()
    
    os.close(fd)
    os.unlink(path)


@pytest.fixture
def manager_client(manager_app):
    """manager测试客户端"""
    return manager_app.test_client()
