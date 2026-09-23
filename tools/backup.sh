#!/usr/bin/env bash
# 一键备份：隐私审计 → 提交 → 推送到所有远程（GitHub + iCloud）
#
# ⚠️ 推送前强制跑隐私审计。仓库已公开，一旦推上去带隐私的提交，
#    GitHub 会立刻可被抓取，事后改历史也追不回已抓走的副本 —— 所以这里设卡。
#
# 用法：
#   bash tools/backup.sh "改了什么"           # 正常：先审计，再提交推送
#   bash tools/backup.sh "说明" --no-audit    # 跳过审计（仅在确认误报时用，风险自负）
set -e
cd "$(dirname "$0")/.."

MSG="${1:-备份 $(date '+%Y-%m-%d %H:%M')}"
NO_AUDIT=0
for a in "$@"; do [ "$a" = "--no-audit" ] && NO_AUDIT=1; done

# ── 1. 先暂存，让新增文件也进入审计范围 ──────────────────────
HAS_CHANGES=0
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  HAS_CHANGES=1
  git add -A
fi

# ── 2. 隐私审计（硬门槛）────────────────────────────────────
if [ "$NO_AUDIT" = "1" ]; then
  echo "⚠️  已跳过隐私审计（--no-audit）。仓库是公开的，请确认你清楚后果。"
else
  echo "🔍 推送前隐私审计…"
  if ! python3 tools/privacy_audit.py --history; then
    echo
    echo "❌ 隐私审计未通过，已拒绝推送。"
    echo "   改动仍在暂存区，修完再跑一次即可：bash tools/backup.sh \"说明\""
    echo "   确认是误报才用 --no-audit 跳过。"
    exit 1
  fi
  echo "✅ 审计通过"
fi

# ── 3. 提交 ────────────────────────────────────────────────
if [ "$HAS_CHANGES" = "1" ]; then
  git commit -q -m "$MSG"
  echo "✅ 已提交：$MSG"
else
  echo "ℹ️  工作区干净，无新改动"
fi

# ── 4. 推送 ───────────────────────────────────────────────
if [ -z "$(git remote)" ]; then echo "❌ 没有配置任何远程"; exit 1; fi
BRANCH="$(git branch --show-current)"
for r in $(git remote); do
  if git push --quiet "$r" "$BRANCH" 2>/dev/null; then
    echo "✅ 已推送 → $r"
  else
    echo "⚠️  推送失败 → $r（凭据或网络问题）"
  fi
done
git log --oneline -1
