# Judger

图形学专用在线评测系统（OJ）的评测服务端组件。评测服务端应该运行在内网环境下，只有 Web 服务端能直接访问到评测服务。

## 功能

- 管理节点（manager）：负责与 Web 服务端交互并管理评测任务
- 执行节点（executor）：负责实际执行评测任务

## 安装

建议安装前创建虚拟环境进行隔离。首先安装 `requirements.txt` 中的依赖并执行 `build.sh` 构建 `judger` 包，然后在各节点上用 `pip` 安装构建出的包即可。

## 部署

完整的评测服务端包含一个管理节点和至少一个执行节点。其中执行节点的 IP 无需固定，但管理节点的 IP 必须固定以保证执行节点始终能够访问到管理节点。`judger` 包同时包含了管理节点和执行节点的代码，所以各节点安装的包没有区别。

### 管理节点

在管理节点上，首先确认自己的 IP 地址，然后设置[管理节点配置文件](judger/manager/config.py)中用到的环境变量，再启动服务：
```bash
# 使用 /path/to/judger.db 作为 SQLite 数据库文件
export SQLALCHEMY_DATABASE_URI="sqlite:////path/to/judger.db"
export WEB_SERVER_IP="your Web server IP"       # 默认为 127.0.0.1，即 Web 服务端在本地
export WEB_SERVER_PORT="your Web service port"  # 默认为 8000，与 Web 服务端默认端口相同
export WEB_ACCOUNT="user ID for manager node"   # 需要先在 Web 服务端创建好用户
export WEB_PASSWORD="password of the user"
export EXECUTOR_PORT="executor service port"    # 所有执行节点须使用同一端口号
judger-manager
```

如果以下两个条件满足其一，那么管理节点启动时要加 `--host 0.0.0.0`（或你需要指定的网段）来允许 Web 服务端和执行节点访问它。
- 管理节点和执行节点不在同一台机器上
- 管理节点和 Web 服务端不在同一台机器上

### 执行节点

受到 Dandelion 的限制，执行节点必须拥有图形环境、连接到显示器，启动执行节点的 shell 也必须是从图形界面启动的，不能是 SSH 远程连接的 login shell。执行节点需要具备编译 Dandelion 所需的环境，可以参考 Dandelion 开发者文档加以配置。

另外，建议执行节点安装与 Python `libclang` 包版本接近的 clang 编译器（`libclang` 版本见 pyproject.toml 配置文件），并将其配置为 CMake 的编译器以确保 AST 解析正常。

参考[执行节点配置文件](judger/executor/config.py)设置环境变量，并启动执行节点：
```bash
export CC=clang
export CXX=clang++
export MANAGER_IP="manager node IP"
export MANAGER_PORT="manager service port"
export WEB_SERVER_IP="your web server IP"
export WEB_SERVER_PORT="your Web service port"
export WEB_ACCOUNT="user ID for this executor node"  # 最好是每个执行节点各有一个用户
export WEB_PASSWORD="password for the user"
# 其他配置都可以用环境变量覆盖，详见配置文件
judger-executor
```

如果管理节点和执行节点不在同一台机器上，那么执行节点启动时也要加 `--host 0.0.0.0`（或管理节点 IP）来允许管理节点访问它。

## 数据和日志

在每个节点上，都有不止一个服务进程运行，因此管理节点用一个 SQLite 数据库来实现 IPC。所有的题目、提交、模板等信息都是从 Web 服务端获取的，评测服务端不会在自己的数据库中保存任何持久化数据。

执行节点每执行完一次评测任务，会将对应的评测日志输出到 `LOG_DIR` 下的 `[judgment-id].log` 文件中，以便后续查看。启动执行节点服务的用户需要有读写该目录的权限，否则服务会因为不能写入日志而退出。