#!/bin/bash

# 确保在出错时停止执行
set -e

echo "🚀 开始打包流程..."

# 1. 确保安装了打包工具
if ! python3 -m pip show build > /dev/null 2>&1; then
    echo "📦 正在安装 build 工具..."
    python3 -m pip install build --quiet
fi

# 2. 清理旧的构建产物
echo "🧹 清理旧的构建文件 (dist/, build/, *.egg-info/)..."
rm -rf dist/
rm -rf build/
rm -rf *.egg-info/

# 3. 执行构建
echo "🏗️ 正在构建项目..."
python3 -m build

# 4. 完成
echo "✅ 打包完成！"
echo "--------------------------------------------------"
echo "产物路径: $(pwd)/dist/"
ls -l dist/
echo "--------------------------------------------------"
echo "💡 提示：可以使用 'pip install dist/*.whl' 进行本地安装测试。"
