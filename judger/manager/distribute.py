import json
import sqlite3
import time
import requests
import logging
from judger.manager.config import Config


logger = logging.getLogger('distribute')


def distribute_tasks():
    # 获取数据库路径
    db_path = Config.SQLALCHEMY_DATABASE_URI.split('///')[1]

    while True:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 检查任务
            cursor.execute('SELECT id, judgment_id FROM tasks ORDER BY id ASC LIMIT 1')
            task = cursor.fetchone()

            if task:
                task_id, judgment_id = task

                # 获取所有空闲节点及其状态数据
                cursor.execute('SELECT id, ip, data FROM executors WHERE idle=1')
                idle_executors = cursor.fetchall()

                chosen_executor = None
                for executor in idle_executors:
                    executor_id, executor_ip, data_json = executor
                    try:
                        # 解析data字段的JSON
                        data = json.loads(data_json)
                        # 检查is_alive属性
                        if data.get('is_alive', False):
                            chosen_executor = (executor_id, executor_ip)
                            break
                    except json.JSONDecodeError:
                        logger.error(f'执行节点 {executor_id} 的data字段解析失败')
                        continue

                if chosen_executor:
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
                            logger.info(f'任务 {task_id} 已分配给 {executor_ip}')
                        else:
                            # 处理失败节点
                            handle_failed_executor(cursor, conn, executor_id)
                    except requests.exceptions.Timeout:
                        # 超时处理
                        handle_failed_executor(cursor, conn, executor_id)
                    except requests.exceptions.RequestException as e:
                        print(f'请求异常: {str(e)}')
                        handle_failed_executor(cursor, conn, executor_id)
                else:
                    logger.warning('没有可用执行节点')
            else:
                logger.info('任务队列为空')

            conn.close()
        except sqlite3.Error as e:
            logger.error(f'数据库错误: {str(e)}')

        # 每5秒检查一次
        time.sleep(5)


def handle_failed_executor(cursor, conn, executor_id):
    '''处理失败节点'''
    # 删除节点
    cursor.execute('DELETE FROM executors WHERE id=?', (executor_id,))
    conn.commit()
    logger.warning(f'执行节点 {executor_id} 因响应超时已被移除')


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s][%(name)s][%(asctime)s] %(message)s'
    )
    distribute_tasks()
