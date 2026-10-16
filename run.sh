#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# 启动智能阅卷助手
"$DIR/.venv/bin/python" AutoGrader.py "$@"
