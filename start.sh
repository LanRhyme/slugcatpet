#!/bin/bash
# 进入脚本所在目录
cd "$(dirname "$0")"

# 检查虚拟环境是否存在
if [ -d "venv_sys" ]; then
    PYTHON_BIN="./venv_sys/bin/python"
elif [ -d "venv" ]; then
    PYTHON_BIN="./venv/bin/python"
else
    PYTHON_BIN="python"
fi

# 启动桌宠
exec "$PYTHON_BIN" run_slugcatpet.py
