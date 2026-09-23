#!/usr/bin/env bash
# 启用仓库勾子：把 core.hooksPath 指向 .githooks/
#
# 为什么需要这一步：git 出于安全考虑不跟踪 .git/hooks/，
# 所以勾子放在受版本控制的 .githooks/ 里，再让 git 去那里找。
# core.hooksPath 是本机配置，clone 后每人跑一次即可。
set -e
cd "$(dirname "$0")/.."

chmod +x .githooks/* 2>/dev/null || true
git config core.hooksPath .githooks

echo "✅ 已启用仓库勾子"
echo "   core.hooksPath = $(git config core.hooksPath)"
echo "   生效的勾子："
for f in .githooks/*; do
  [ -f "$f" ] && echo "     - $(basename "$f")"
done
echo
echo "   验证：git push 会先跑隐私审计，不通过则拒绝"
echo "   跳过：git push --no-verify（不推荐）"
