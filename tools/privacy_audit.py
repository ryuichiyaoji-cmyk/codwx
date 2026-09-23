#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""隐私审计：推送前逐一排查可能泄露本人身份或数据的内容

设计原则：**工具本身不含你的任何私人词**。
  - 通用检测器：账号数字 / 本机路径 / 凭据 / 联系方式 / 个人主页链接（硬编码在这里）
  - 私有关键词：放在 `.privacy-local.txt`（已 gitignore，不进仓库），一行一个词

用法：
    python3 tools/privacy_audit.py              # 扫 git 跟踪的文件（工作区）
    python3 tools/privacy_audit.py --all-files  # 连未跟踪文件一起扫
    python3 tools/privacy_audit.py --history    # 连全部 git 历史一起扫
    python3 tools/privacy_audit.py --json

退出码：0 = 无高危发现；1 = 有 HIGH/CRITICAL；2 = 有 MEDIUM
"""
import argparse, json, os, re, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOCAL_TERMS = REPO / ".privacy-local.txt"
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".ttf", ".otf", ".woff", ".woff2",
            ".mp3", ".mp4", ".wav", ".mov", ".zip", ".gz", ".ico", ".icns", ".dylib", ".node", ".wasm"}

# 忽略清单（仓库内可提交，因为只含路径不含隐私）：第三方/vendored 文件
IGNORE_FILE = REPO / ".privacy-ignore"
DEFAULT_IGNORE = ("video/bin/", "node_modules/", "public/fonts/", "package-lock.json",
                  "assets/", "outputs/")

# ---------------- 通用检测器 ----------------
# (类别, 严重度, 正则, 说明)
RULES = [
    ("凭据", "CRITICAL",
     re.compile(r"(?i)(appsecret|app_secret|client_secret)\s*[:=]\s*[\"']?[A-Za-z0-9]{16,}"),
     "疑似明文密钥"),
    ("凭据", "CRITICAL",
     re.compile(r"\b(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
     "疑似 API / 访问令牌"),
    ("凭据", "CRITICAL",
     re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
     "私钥内容"),
    ("凭据", "HIGH",
     re.compile(r"(?i)access_token[\"']?\s*[:=]\s*[\"'][A-Za-z0-9_\-]{20,}"),
     "疑似 access_token 实值"),

    ("本机环境", "HIGH",
     re.compile(r"/Users/[A-Za-z0-9._\-]+"),
     "绝对家目录路径（含用户名）"),
    ("本机环境", "MEDIUM",
     re.compile(r"/(?:home|Users)/[A-Za-z0-9._\-]+/[A-Za-z0-9._\-/]+"),
     "本机专属路径片段"),

    ("联系方式", "HIGH",
     re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
     "邮箱地址"),
    ("联系方式", "HIGH",
     re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
     "疑似手机号"),

    ("账号数据", "HIGH",
     re.compile(r"(粉丝数|粉丝|关注数|订阅数|累计原创|原创文章|日均收入|月均收入|广告收入|阅读量|涨粉|eCPM)"
                r"\s*[:：|]?\s*[¥￥$]?\s*\d[\d,.]*\s*(万|亿|元|人|篇|次)?"),
     "账号运营数据"),
    ("账号数据", "MEDIUM",
     re.compile(r"(单篇涨粉率|搜一搜占比|周新增粉丝|总曝光量)\s*[:：|]?\s*[¥￥$]?\s*\d"),
     "账号指标"),

    ("个人主页", "MEDIUM",
     re.compile(r"https?://(?:www\.)?(?:github\.com|x\.com|twitter\.com|weibo\.com|zhihu\.com|"
                r"xiaohongshu\.com|juejin\.cn|bilibili\.com)/[A-Za-z0-9_.\-%]+/?[\"'\s)]"),
     "指向个人主页的链接"),
]

SEV_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}

# 逐行豁免：某行含这个标记就跳过该项（用于已人工确认的误报，如第三方许可证里的邮箱）
# ⚠️ 对 CRITICAL（凭据类）不生效——见 scan_text 里的判断
WAIVER = "privacy-audit:ok"


def load_ignore():
    pats = list(DEFAULT_IGNORE)
    if IGNORE_FILE.exists():
        for line in IGNORE_FILE.read_text(encoding="utf-8").splitlines():
            t = line.split("#", 1)[0].strip()          # 支持行内注释
            if t:
                pats.append(t)
    return pats


def is_ignored(path, pats):
    return any(p in path for p in pats)


def is_binary(path):
    """含 NUL 字节即视为二进制——比靠后缀可靠"""
    p = REPO / path
    try:
        with open(p, "rb") as f:
            return b"\0" in f.read(8192)
    except Exception:
        return True


def load_local_terms():
    """私有关键词：一行一个，支持 # 注释"""
    if not LOCAL_TERMS.exists():
        return []
    out = []
    for line in LOCAL_TERMS.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if t and not t.startswith("#"):
            out.append(t)
    return out


def tracked_files(include_untracked=False):
    # -c core.quotepath=false：否则 git 会把非 ASCII 文件名转义成 "\344\270..."，
    # 按转义名去读文件必然失败 → 中文名文件被静默跳过（曾导致审计漏报）
    cmd = ["git", "-c", "core.quotepath=false", "ls-files"] + \
          (["--cached", "--others", "--exclude-standard"] if include_untracked else [])
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    return [f for f in r.stdout.splitlines() if f]


def read_text(path, ignore=()):
    p = REPO / path
    if not p.is_file() or p.suffix.lower() in SKIP_EXT:
        return None
    if is_ignored(path, ignore) or is_binary(path):
        return None
    if p.stat().st_size > 2_000_000:
        return None
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def _waived(text, pos):
    """该命中所在行是否有豁免标记"""
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    line = text[start:end if end != -1 else len(text)]
    return WAIVER in line


def scan_text(text, where, findings, terms):
    for cat, sev, rx, why in RULES:
        for m in rx.finditer(text):
            # ⚠️ 豁免标记对 CRITICAL（凭据类）无效——否则一句注释就能放行真密钥
            if sev != "CRITICAL" and _waived(text, m.start()):
                continue
            line_no = text[:m.start()].count("\n") + 1
            findings.append({"where": where, "line": line_no, "category": cat,
                             "severity": sev, "why": why, "hit": m.group(0)[:60]})
    for t in terms:
        for m in re.finditer(re.escape(t), text):
            if _waived(text, m.start()):
                continue
            line_no = text[:m.start()].count("\n") + 1
            findings.append({"where": where, "line": line_no, "category": "私有关键词",
                             "severity": "HIGH", "why": "命中 .privacy-local.txt 中的词",
                             "hit": m.group(0)[:60]})


def scan_worktree(all_files, terms):
    findings = []
    ignore = load_ignore()
    for f in tracked_files(include_untracked=all_files):
        if is_ignored(f, ignore):
            continue
        t = read_text(f, ignore)
        if t:
            scan_text(t, f, findings, terms)
    return findings


def scan_history(terms):
    """逐个提交扫全部 blob（比 git log -S 更彻底）"""
    findings = []
    ignore = load_ignore()
    r = subprocess.run(["git", "rev-list", "--all"], cwd=REPO, capture_output=True, text=True)
    for commit in r.stdout.split():
        br = subprocess.run(["git", "-c", "core.quotepath=false", "ls-tree", "-r", "--name-only", commit],
                            cwd=REPO, capture_output=True, text=True)
        for f in br.stdout.splitlines():
            if Path(f).suffix.lower() in SKIP_EXT or is_ignored(f, ignore):
                continue
            sr = subprocess.run(["git", "-c", "core.quotepath=false", "show", f"{commit}:{f}"], cwd=REPO,
                                capture_output=True, text=True, errors="ignore")
            if sr.returncode or not sr.stdout or "\0" in sr.stdout[:8192]:
                continue
            scan_text(sr.stdout, f"{commit[:7]}:{f}", findings, terms)
    return findings


def scan_git_metadata(terms):
    """git 元数据泄露面：提交作者/提交者、提交信息。
    这两处最容易被忽略——内容擦干净了，作者名还挂在每个 commit 上。"""
    findings = []

    # ① 作者与提交者
    r = subprocess.run(["git", "log", "--all", "--format=%h%x1f%an%x1f%ae%x1f%cn%x1f%ce"],
                       cwd=REPO, capture_output=True, text=True)
    seen = set()
    for line in r.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) < 5:
            continue
        h, an, ae, cn, ce = parts
        for kind, name, mail in (("作者", an, ae), ("提交者", cn, ce)):
            key = (kind, name, mail)
            if key in seen:
                continue
            seen.add(key)
            bad = [t for t in terms if t.lower() in (name + " " + mail).lower()]
            local_domain = bool(re.search(r"@(?:localhost|.*\.local)\b", mail, re.I))
            if bad or local_domain:
                findings.append({
                    "where": f"git {kind}", "line": 0, "category": "Git 元数据",
                    "severity": "HIGH",
                    "why": "作者信息含私人标识" if bad else "邮箱是本地域名",
                    "hit": f"{name} <{mail}>"})

    # ② 提交信息
    r = subprocess.run(["git", "log", "--all", "--format=%h%x1f%B%x1e"],
                       cwd=REPO, capture_output=True, text=True)
    for chunk in r.stdout.split("\x1e"):
        if "\x1f" not in chunk:
            continue
        h, msg = chunk.split("\x1f", 1)
        h = h.strip()
        for t in terms:
            if t in msg:
                line_no = msg[:msg.index(t)].count("\n") + 1
                findings.append({
                    "where": f"git 提交信息 {h}", "line": line_no, "category": "Git 元数据",
                    "severity": "MEDIUM", "why": "提交信息含私有关键词", "hit": t})
    return findings


def sanity_check():
    """护栏：中文名文件必须能被读到，否则说明路径处理有问题（曾静默漏报）"""
    files = tracked_files()
    cn = [f for f in files if any(ord(ch) > 0x2E80 for ch in f)]
    if cn and not any(read_text(f) for f in cn[:20]):
        print("🔴 自检失败：中文名文件无法读取，审计结果不可信（路径转义问题）", file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-files", action="store_true", help="连未跟踪文件一起扫")
    ap.add_argument("--history", action="store_true", help="连 git 全历史一起扫（慢）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-per-rule", type=int, default=8)
    ap.add_argument("--show-waived", action="store_true", help="显示被 privacy-audit:ok 豁免的项")
    a = ap.parse_args()

    if not sanity_check():
        return 3
    terms = load_local_terms()
    findings = scan_worktree(a.all_files, terms)
    findings += scan_git_metadata(terms)          # git 元数据永远扫
    if a.history:
        findings += scan_history(terms)

    # 去重 + 截断
    seen, uniq = set(), []
    for f in findings:
        k = (f["where"], f["line"], f["category"], f["hit"])
        if k in seen: continue
        seen.add(k); uniq.append(f)
    uniq.sort(key=lambda x: (SEV_RANK[x["severity"]], x["category"], x["where"]))

    if a.json:
        print(json.dumps(uniq, ensure_ascii=False, indent=1)); return 0

    print("=" * 64)
    print(f"隐私审计｜扫描范围：工作区{' + 未跟踪' if a.all_files else ''}{' + 全历史' if a.history else ''}")
    print(f"私有关键词表：{LOCAL_TERMS.name}"
          f"（{len(terms)} 个词{'，未创建' if not terms else ''}）")
    print("=" * 64)
    if not uniq:
        print("✅ 未发现任何隐私风险项")
        return 0

    buckets = {}
    for f in uniq: buckets.setdefault((f["severity"], f["category"]), []).append(f)
    for (sev, cat), items in sorted(buckets.items(), key=lambda kv: SEV_RANK[kv[0][0]]):
        icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡"}[sev]
        print(f"\n{icon} [{sev}] {cat}（{len(items)} 处）")
        for f in items[:a.max_per_rule]:
            print(f"   {f['where']}:{f['line']}  {f['why']}")
            print(f"      → {f['hit'].strip()[:70]}")
        if len(items) > a.max_per_rule:
            print(f"   …另有 {len(items)-a.max_per_rule} 处同类")

    n = {s: sum(1 for f in uniq if f["severity"] == s) for s in ("CRITICAL", "HIGH", "MEDIUM")}
    print(f"\n合计：CRITICAL {n['CRITICAL']} · HIGH {n['HIGH']} · MEDIUM {n['MEDIUM']}")
    print("结论：" + ("🔴 有 CRITICAL，禁止推送" if n["CRITICAL"] else
                     ("🟠 有 HIGH，必须处理后才能推送" if n["HIGH"] else
                      "🟡 仅有 MEDIUM，人工确认后再推送")))
    return 1 if n["CRITICAL"] or n["HIGH"] else 2


if __name__ == "__main__":
    sys.exit(main())
