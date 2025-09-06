import json
from typing import Optional, Dict, List, Any
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
        """接收评测任务请求

        将提交ID加入数据库任务队列并返回202状态码。

        :param judgment_id: 需要处理的评测记录 ID
        :return: 空字符串和HTTP 202状态码
        """
        # 创建新任务并存入数据库
        new_task = Task(judgment_id=judgment_id)
        db.session.add(new_task)

        try:
            db.session.commit()
            current_app.logger.info(
                f'task {new_task.id} (judgment {judgment_id}) added to task queue'
            )
        except Exception as e:
            current_app.logger.error(f'cannot add new task to queue: {type(e)}: {str(e)}')
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

        return '', 202

    # 初始化数据库
    db.init_app(app)
    with app.app_context():
        db.create_all()

        # 管理节点的数据库只用来实现 IPC，上次运行留下的数据都没有意义
        meta = db.metadata
        for table in reversed(meta.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()

    @app.route('/api/judge/<int:judgment_id>/result', methods=['POST'])
    def receive_judgment_result(judgment_id: int):
        """
        接收评测结果，重置执行节点空闲状态，并将结果转发给 Web 服务端。

        该 API 由执行节点在完成任务后调用，返回 200 表示管理节点成功收到了执行节点的反馈。
        """
        ip = request.remote_addr
        executor = Executor.query.filter_by(ip=ip).first()
        if executor is None:
            return jsonify({'error': 'Executor not found'}), 404

        # 执行节点回报结果，说明它此时已经空闲
        executor.idle = True
        try:
            db.session.commit()

            # 获取请求体中的评测结果
            result_data: Dict[str, Any] = request.get_json()
            if result_data is None:
                return jsonify({'error': 'Missing result data'}), 400
            judgment_result = {
                'result': result_data['result'],
                'log': result_data['log']
            }
            function_impls: List[str] | None = result_data.get('function_impls', None)

            api_client = APIClient(current_app.token_manager)
            judgment: Dict[str, Any] = api_client.get(f'/api/judgments/{judgment_id}')
            submission_id = judgment['submission_id']

            try:
                # 将评测结果转发给Web服务端
                api_client.post(f'/api/judgments/{judgment_id}/result', data=judgment_result)
                if function_impls is not None:
                    for function_impl in function_impls:
                        response = api_client.post(
                            f'/api/submissions/{submission_id}/function_impls',
                            data={'code': function_impl}
                        )
                        function_impl_id = response['function_impl_id']
                        current_app.logger.info(
                            f'function implementation sent to Web server, ID: {function_impl_id}'
                        )
            except Exception as api_error:
                # 更新 Web 服务端信息失败，但这和执行节点没有关系
                current_app.logger.error(
                    f'failed to update judgment result: {type(api_error)}: {str(api_error)}'
                )

            return '', 200
        except Exception as e:
            current_app.logger.error(
                f'failed to receive judgment result: {type(e)}: {str(e)}'
            )
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/judge/executors', methods=['POST'])
    def update_executor_status():
        """
        接收执行节点上报的状态。如果该执行节点存在，则更新对应执行节点的信息；
        如果执行节点不存在，则在数据库中创建新的执行节点记录。
        """
        ip = request.remote_addr
        data = request.get_json(silent=True)
        current_app.logger.info(f'receive executor status reported from {ip}')

        if data is None:
            current_app.logger.warning('no status data')
            return jsonify({'error': 'invalid JSON data'}), 400

        try:
            json_data = json.dumps(data)
        except TypeError:
            return jsonify({'error': 'invalid JSON format'}), 400

        executor = Executor.query.filter_by(ip=ip).first()
        if not executor:
            current_app.logger.info('create a new executor node')
            executor = Executor(ip=ip, data=json_data)
            db.session.add(executor)
        else:
            executor.data = json_data
            current_app.logger.info(f'update executor to {executor}')

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(
                f'unexpected error occurred when updating executor: {type(e)}: {str(e)}'
            )
            return jsonify({'error': str(e)}), 500

        return '', 200

    return app
