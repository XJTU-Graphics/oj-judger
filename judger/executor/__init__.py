from typing import Optional, Dict
from flask import Flask, Blueprint, current_app, jsonify
from judger.utils.token_manager import TokenManager
from judger.utils.api_client import APIRequestError, APIClient
from judger.executor.config import Config
import os
import shutil
import logging
from logging import Formatter


bp = Blueprint('judge', __name__, url_prefix='/api/judge')


@bp.route('/<int:judgment_id>', methods=['POST'])
def judge_judgment(judgment_id):
    '''处理评测请求

    1. 通过judgment_id获取submission_id
    2. 获取源代码附件并解压到Dandelion项目目录
    3. 返回202表示评测已开始
    '''
    try:
        # 获取配置和API客户端
        dandelion_path = current_app.config['DANDELION_TEMPLATE']
        api_client = APIClient(current_app.token_manager)

        # 通过judgment_id获取submission_id
        judgment_info = api_client.get(f'/api/judgments/{judgment_id}')
        submission_id = judgment_info['submission_id']
        current_app.logger.info(f'submission ID {submission_id} obtained')

        # 获取题目信息
        submission_info = api_client.get(f'/api/submissions/{submission_id}')
        problem_info = api_client.get(f'/api/problems/{submission_info["problem_id"]}')
        has_autograder = problem_info.get('has_autograder', False)
        unit_test_name = problem_info.get('unit_test_name', '') if has_autograder else None
        current_app.logger.info(f'problem info obtained: has_autograder={has_autograder}')

        # 获取源代码附件ID
        code_info = api_client.get(f'/api/submissions/{submission_id}/code')
        attachment_id = code_info['attachment_id']
        current_app.logger.info(f'source code attachment ID {attachment_id} obtained')

        # 下载ZIP文件
        zip_path = f'/tmp/submission_{submission_id}.zip'
        response = api_client.get(
            f'/api/submissions/attachments/{attachment_id}',
            parse_json=False,
            stream=True
        )

        # 保存ZIP文件
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        current_app.logger.info('source code file saved')

        # 准备临时目录
        temp_dir = f'{current_app.config["TMP_DIR"]}/dandelion-template'
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        shutil.copytree(dandelion_path, temp_dir)
        
        # 解压到临时目录
        shutil.unpack_archive(
            filename=zip_path, extract_dir=temp_dir, format='zip'
        )
        os.remove(zip_path)
        current_app.logger.info(f'ZIP unpacked to {temp_dir}')

        # 异步启动验证脚本
        import subprocess
        import sys
        validator_path = os.path.join(os.path.dirname(__file__), 'validate.py')
        args = [sys.executable, validator_path, str(judgment_id)]
        if unit_test_name:
            args.append(unit_test_name)
        subprocess.Popen(args)
        current_app.logger.info('validator started')

        return jsonify(''), 202

    except APIRequestError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        current_app.logger.error(f'Judge submission error: {str(e)}')
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500


def create_app(test_config: Optional[Dict] = None) -> Flask:
    app = Flask(__name__)
    app.token_manager = TokenManager('executor')
    app.config.from_object(Config)
    if test_config is not None:
        app.config.from_mapping(test_config)
    
    # Configure logging format
    formatter = Formatter('[%(levelname)s][%(name)s][%(asctime)s] %(message)s')
    for handler in app.logger.handlers:
        handler.setFormatter(formatter)
    app.logger.setLevel(logging.INFO)

    @app.get('/alive')
    def is_alive():
        return '', 200

    # 注册评测路由
    app.register_blueprint(bp)

    return app
