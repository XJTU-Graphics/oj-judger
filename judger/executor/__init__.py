from typing import Optional, Dict, Any
from flask import Flask, Blueprint, current_app, jsonify
from judger.utils.token_manager import TokenManager
from judger.utils.api_client import APIRequestError, APIClient
from judger.utils.template_manager import TemplateManager
from judger.executor.config import Config
import shutil
import logging
from logging import Formatter
from pathlib import Path


bp = Blueprint('judge', __name__, url_prefix='/api/judge')


@bp.route('/<int:judgment_id>', methods=['POST'])
def judge_judgment(judgment_id):
    """处理评测请求

    1. 通过judgment_id获取submission_id
    2. 获取源代码附件并解压到Dandelion项目目录
    3. 返回202表示评测已开始
    """
    try:
        # 获取API客户端和模板管理器
        api_client = APIClient(current_app.token_manager)
        template_manager = TemplateManager(api_client)

        # 通过judgment_id获取submission_id
        judgment_info = api_client.get(f'/api/judgments/{judgment_id}')
        submission_id = judgment_info['submission_id']
        current_app.logger.info(f'submission ID {submission_id} obtained')

        # 获取题目信息
        submission_info: Dict[str, Any] = api_client.get(f'/api/submissions/{submission_id}')
        problem_info: Dict[str, Any] = api_client.get(
            f'/api/problems/{submission_info["problem_id"]}'
        )
        has_autograder = problem_info.get('has_autograder', False)
        unit_test_name = problem_info.get('unit_test_name', '') if has_autograder else None
        current_app.logger.info(f'problem info obtained: has_autograder={has_autograder}')

        # 获取源代码附件ID
        code_info = api_client.get(f'/api/submissions/{submission_id}/code')
        attachment_id = code_info['attachment_id']
        current_app.logger.info(f'source code attachment ID {attachment_id} obtained')

        # 下载ZIP文件
        tmp_dir = Path(current_app.config["TMP_DIR"])
        zip_path = tmp_dir / f'submission_{submission_id}.zip'
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
        temp_dir = tmp_dir / f'judgement_for_{judgment_id}'
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

        # 获取远程模板
        template_info = template_manager.get_template(problem_info['template_id'])
        template_dir = template_info['path']
        template_dir_name = template_info['dir_name']
        shutil.copytree(template_dir, temp_dir)

        # 解压到临时目录的模板中
        shutil.unpack_archive(
            filename=zip_path, extract_dir=temp_dir / template_dir_name, format='zip'
        )
        zip_path.unlink()
        current_app.logger.info(f'{zip_path} unpacked to {temp_dir}')

        # 异步启动验证脚本
        import subprocess
        import sys
        validator_path = Path(__file__).parent / 'validate.py'
        args = [sys.executable, validator_path, str(judgment_id), str(temp_dir / template_dir_name)]
        if unit_test_name:
            args.append(unit_test_name)
        subprocess.Popen(args)
        current_app.logger.info('validator started')

        return jsonify(''), 202

    except APIRequestError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        current_app.logger.error(f'Judge submission error: {str(e)}')
        return jsonify({'error_message': f'Unexpected error: {str(e)}'}), 500


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
