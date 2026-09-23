#!/usr/bin/env bash
# 一键备份：提交改动 → 推送到所有远程（iCloud 异地 + 其它已配置远程）
# 用法：bash tools/backup.sh "提交说明"     不传说明则用时间戳
set -e
cd "$(dirname "$0")/.."
MSG="${1:-备份 $(date '+%Y-%m-%d %H:%M')}"
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  git add -A
  git commit -q -m "$MSG"
  echo "✅ 已提交：$MSG"
else
  echo "ℹ️  工作区干净，无新改动"
fi
if [ -z "$(git remote)" ]; then echo "❌ 没有配置任何远程"; exit 1; fi
for r in $(git remote); do
  if git push --quiet "$r" "$(git branch --show-current)" 2>/dev/null; then
    echo "✅ 已推送 → $r"
  else
    echo "⚠️  推送失败 → $r（凭据或网络问题）"
  fi
done
git log --oneline -1
