import json
from typing import Optional, Dict
from flask import Flask, request, jsonify, current_app
from judger.utils.token_manager import TokenManager
from judger.utils.api_client import APIClient
from judger.manager.config import Config
from judger.manager.models import db, Executor, Task
from logging import Formatter


def create_app(test_config: Optional[Dict] = None) -> Flask:
    app = Flask(__name__)
    app.token_manager = TokenManager('manager')
    app.config.from_object(Config)
    if test_config is not None:
        app.config.from_mapping(test_config)
    
    # Configure logging format
    formatter = Formatter('[%(levelname)s][%(name)s][%(asctime)s] %(message)s')
    for handler in app.logger.handlers:
        handler.setFormatter(formatter)

    @app.route('/api/judge/<int:judgment_id>', methods=['POST'])
    def judge_submission(judgment_id: int) -> tuple[str, int]:
        '''接收评测任务请求

        将提交ID加入数据库任务队列并返回202状态码。

        :param judgment_id: 需要处理的评测记录 ID
        :return: 空字符串和HTTP 202状态码
        '''
        # 创建新任务并存入数据库
        new_task = Task(judgment_id=judgment_id)
        db.session.add(new_task)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

        return '', 202

    # 初始化数据库
    db.init_app(app)
    with app.app_context():
        db.create_all()

        # 清空所有表数据（新增）
        meta = db.metadata
        for table in reversed(meta.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()

    @app.route('/api/judge/<int:judgment_id>/result', methods=['POST'])
    def receive_judgment_result(judgment_id: int) -> tuple[str, int]:
        '''接收评测结果，重置执行节点空闲状态，并将结果转发给Web服务端

        由执行节点在完成任务后调用
        '''
        ip = request.remote_addr
        executor = Executor.query.filter_by(ip=ip).first()

        if executor:
            executor.idle = True
            try:
                db.session.commit()

                # 获取请求体中的评测结果
                result_data = request.get_json()
                if result_data is None:
                    return jsonify({'error': 'Missing result data'}), 400

                # 创建 API 客户端实例
                api_client = APIClient(current_app.token_manager)

                try:
                    # 将评测结果转发给Web服务端
                    api_client.post(f'/api/judgments/{judgment_id}/result', data=result_data)
                except Exception as api_error:
                    # 记录错误但继续执行
                    current_app.logger.error(f'更新评测结果失败: {str(api_error)}')

                return '', 200
            except Exception as e:
                db.session.rollback()
                return jsonify({'error': str(e)}), 500
        return jsonify({'error': 'Executor not found'}), 404

    @app.route('/api/judge/executors', methods=['POST'])
    def update_executor_status():
        ip = request.remote_addr
        data = request.get_json(silent=True)

        if data is None:
            return jsonify({'error': 'Invalid JSON data'}), 400

        try:
            json_data = json.dumps(data)
        except TypeError:
            return jsonify({'error': 'Invalid JSON format'}), 400

        executor = Executor.query.filter_by(ip=ip).first()
        if not executor:
            executor = Executor(ip=ip, data=json_data)
            db.session.add(executor)
        else:
            executor.data = json_data

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

        return '', 200

    return app
