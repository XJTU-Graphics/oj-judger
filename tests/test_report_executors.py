import json
import pytest  # noqa: F401
from judger.manager.models import Executor


def test_empty_request(manager_client):
    """测试空请求体返回400错误"""
    response = manager_client.post(
        '/api/judge/executors',
        headers={'Content-Type': 'application/json'}
    )
    assert response.status_code == 400
    assert b"Invalid JSON data" in response.data


def test_invalid_json(manager_client):
    """测试无效JSON返回400错误"""
    response = manager_client.post(
        '/api/judge/executors',
        data="{ invalid json",  # 发送无效JSON数据
        headers={'Content-Type': 'application/json'}
    )
    assert response.status_code == 400
    # 验证返回JSON错误消息
    error_data = json.loads(response.data)
    assert "error" in error_data
    assert "Invalid JSON data" in error_data["error"]


def test_valid_status_submission(manager_client):
    """测试有效状态提交"""
    status_data = {
        "hostname": "node-01",
        "cpu_model_name": "Intel Xeon",
        "n_cpus": 8,
        "memory_mib": 16384,
        "is_alive": True
    }
    
    response = manager_client.post(
        '/api/judge/executors',
        json=status_data
    )
    assert response.status_code == 200
    
    # 验证数据库记录
    record = Executor.query.first()
    assert record is not None
    stored_data = json.loads(record.data)
    assert stored_data == status_data


def test_continuous_status_update(manager_client):
    """测试连续状态更新"""
    # 首次提交：服务未启动
    response1 = manager_client.post('/api/judge/executors', json={
        "hostname": "node-01",
        "is_alive": False
    })
    assert response1.status_code == 200
    
    # 二次提交：服务已启动
    response2 = manager_client.post('/api/judge/executors', json={
        "hostname": "node-01", 
        "is_alive": True
    })
    assert response2.status_code == 200
    
    # 验证数据库只有1条记录且状态更新
    records = Executor.query.all()
    assert len(records) == 1
    stored_data = json.loads(records[0].data)
    assert stored_data["is_alive"] is True
