#!/usr/bin/env bash
# 工作数据备份（不经 git）
#
# 背景：稿件、选题存档、配图、视频工程等「写稿产出」含个人内容，
# 已从 git 仓库中排除（见 .gitignore）。它们不走版本控制，
# 但仍然需要异地备份 —— 本脚本用 rsync 直接同步到 iCloud。
#
# 用法：
#   bash tools/backup_work.sh              # 增量同步（不删备份里的旧文件）
#   bash tools/backup_work.sh --dry-run    # 只看会同步什么
#   bash tools/backup_work.sh --mirror     # 严格镜像（本地删了的，备份里也删）注：有风险
set -euo pipefail
cd "$(dirname "$0")/.."

DEST_ROOT="${WORK_BACKUP_DIR:-$HOME/Library/Mobile Documents/com~apple~CloudDocs/backups/codwx-work}"
# 工作数据清单：直接问 git「哪些被忽略了」——不硬编码任何文件名。
# 用 while-read 而非 mapfile：macOS 自带 bash 3.2 没有 mapfile。
ITEM_LIST="$(git -c core.quotepath=false ls-files --others --ignored --exclude-standard --directory \
             | grep -v '^\.privacy-local\.txt$' || true)"
if [ -z "$ITEM_LIST" ]; then
  echo "⚠️  没有发现被忽略的工作数据，检查 .gitignore"
  exit 1
fi

RSYNC_OPTS=(-a --human-readable)
for a in "$@"; do
  case "$a" in
    --dry-run) RSYNC_OPTS+=(--dry-run) ;;
    --mirror)  RSYNC_OPTS+=(--delete) ;;
  esac
done

mkdir -p "$DEST_ROOT"
n=0
while IFS= read -r item; do
  [ -n "$item" ] || continue
  # ⚠️ 必须去掉尾斜杠：rsync 源路径带 / 会拷贝「目录内容」而不是「目录本身」，
  #    会把所有文件拍平到备份根目录（已踩过）
  item="${item%/}"
  [ -e "$item" ] || continue
  rsync "${RSYNC_OPTS[@]}" -- "$item" "$DEST_ROOT/" >/dev/null
  n=$((n+1))
done <<< "$ITEM_LIST"

echo "✅ 已同步 $n 项 → $DEST_ROOT"
du -sh "$DEST_ROOT" 2>/dev/null | awk '{print "   备份体积：" $1}'
echo "   说明：默认增量同步、不删旧文件；加 --mirror 可做严格镜像"
