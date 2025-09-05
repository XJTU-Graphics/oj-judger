#!/bin/bash

# Judger 项目构建脚本
# 用于构建项目的分发包

set -e  # 遇到错误立即退出

echo "开始构建 Judger 项目..."

# 检查是否在虚拟环境中
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "警告: 未检测到虚拟环境。建议在虚拟环境中运行此脚本。"
    echo "是否继续? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        echo "构建已取消。"
        exit 1
    fi
fi

# 检查 Python 版本
python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "错误: 需要 Python 3.8 或更高版本，当前版本为 $python_version"
    exit 1
fi

# 安装构建工具
echo "安装构建工具..."
pip install build

# 清理之前的构建
echo "清理之前的构建..."
rm -rf dist/ build/ *.egg-info/

# 构建项目
echo "构建项目..."
python -m build

# 显示构建结果
echo "构建完成！生成的文件:"
ls -hl dist/

echo "构建脚本执行完成。"