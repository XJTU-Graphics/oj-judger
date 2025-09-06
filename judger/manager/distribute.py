import json
import sqlite3
import time
import requests
import logging
from judger.manager.config import Config


logger = logging.getLogger('distribute')
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s][%(name)s][%(asctime)s] %(message)s'
)


def distribute_tasks():
    # 获取数据库路径
    db_path = Config.SQLALCHEMY_DATABASE_URI.split('///')[1]

    while True:
        # 每5秒检查一次
        time.sleep(5)
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 检查任务
            cursor.execute('SELECT id, judgment_id FROM tasks ORDER BY id ASC LIMIT 1')
            task = cursor.fetchone()

            if task is None:
                logger.info('task queue is empty')
                continue
            task_id, judgment_id = task

            # 获取所有空闲节点及其状态数据
            cursor.execute('SELECT id, ip, data FROM executors WHERE idle=1')
            idle_executors = cursor.fetchall()

            chosen_executor = None
            for executor in idle_executors:
                executor_id, executor_ip, data_json = executor
                try:
                    # 解析 data 字段的 JSON
                    data = json.loads(data_json)
                    # 检查 is_alive 属性，找到第一个在线的执行节点
                    if data.get('is_alive', False):
                        chosen_executor = (executor_id, executor_ip)
                        break
                except json.JSONDecodeError:
                    logger.error(f'cannot parse \"data\" field of executor {executor_id}')
                    continue

            if chosen_executor is None:
                logger.warning('no alive executor node')
                continue
            executor_id, executor_ip = chosen_executor

            try:
                # 发送请求（5秒超时）
                url = f'http://{executor_ip}:{Config.EXECUTOR_PORT}' \
                    + f'/api/judge/{judgment_id}'
                response = requests.post(url, timeout=5)

                if response.status_code == 202:
                    # 标记节点忙碌
                    cursor.execute('UPDATE executors SET idle=0 WHERE id=?', (executor_id,))
                    # 删除任务
                    cursor.execute('DELETE FROM tasks WHERE id=?', (task_id,))
                    conn.commit()
                    logger.info(
                        f'task (judgment ID: {judgment_id}) assigned to '
                        f'executor {executor_id} at {executor_ip}'
                    )
                else:
                    # 评测节点返回异常状态码，无法执行评测
                    logger.warning(
                        f'response from executor {executor_id} (at {executor_ip}): '
                        f'{response.status_code} {response.content}'
                    )
                    handle_failed_executor(cursor, conn, executor_id)
            except requests.exceptions.Timeout:
                # 评测请求超时则认为该执行节点已经失联，清除数据库记录
                logger.warning(f'executor {executor_id} timeout')
                handle_failed_executor(cursor, conn, executor_id)
            except requests.exceptions.RequestException as e:
                logger.warning(f'RequestException: {str(e)}')
                handle_failed_executor(cursor, conn, executor_id)

            conn.close()
        except sqlite3.Error as e:
            logger.error(f'database error: {str(e)}')


def handle_failed_executor(cursor, conn, executor_id):
    """处理失败节点"""
    # 删除节点
    cursor.execute('DELETE FROM executors WHERE id=?', (executor_id,))
    conn.commit()
    logger.warning(f'executor {executor_id} has been removed')


if __name__ == '__main__':
    distribute_tasks()
