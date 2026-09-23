#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写稿提速套件（开稿前情报包 / 完稿体检 / 交接单骨架）

把 ai-article-writer 里机械的部分固化成三条命令，省掉反复读文件与逐项核对。

用法：
    python3 tools/draft_kit.py brief                # 开稿前：一屏读完所有硬约束与去重清单
    python3 tools/draft_kit.py check topics/xx.md   # 完稿：preflight + 文风体检合并成一屏
    python3 tools/draft_kit.py handoff topics/xx.md # 从稿件抽核心数字，生成排版交接单骨架
    python3 tools/draft_kit.py handoff topics/xx.md --append   # 直接追加到稿件末尾
"""
import argparse, datetime, re, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
try:
    import preflight as pf
except Exception:
    pf = None

C = {"g": "\033[32m", "y": "\033[33m", "r": "\033[31m", "d": "\033[2m", "0": "\033[0m"}
def c(s, k): return f"{C[k]}{s}{C['0']}"


# ---------------- brief ----------------
def brief():
    print(c("━" * 62, "d"))
    print(c("开稿前情报包", "g"))
    print(c("━" * 62, "d"))

    # 1 账号状态新鲜度
    acc = (REPO / "account-status.md")
    if acc.exists():
        t = acc.read_text(encoding="utf-8")
        m = re.search(r"状态更新日期：\s*([0-9-]+)", t)
        if m:
            d = datetime.date.fromisoformat(m.group(1))
            age = (datetime.date.today() - d).days
            flag = c(f"⚠️  已 {age} 天未更新，引用粉丝/收入前先让用户更新", "y") if age > 7 \
                   else c(f"✅ {age} 天前更新", "g")
            print(f"\n【账号状态】更新于 {m.group(1)}　{flag}")
            for k in ("粉丝数", "当前阶段", "本阶段核心目标"):
                r = re.search(rf"{k}：(.*)", t)
                if r: print(f"   {k}：{r.group(1).strip()}")

    # 2 风格卡硬约束
    sc = (REPO / "voice/风格卡.md")
    if sc.exists():
        t = sc.read_text(encoding="utf-8")
        print(f"\n【风格卡硬约束】{c('卡里写「不用」的一处都不许出现', 'y')}")
        sec = re.search(r"### 盲测得出的三条硬规则.*?\n(.*?)\n\n", t, re.S)
        if sec:
            for line in sec.group(1).strip().splitlines():
                if line.strip(): print("   " + line.strip())
        for key, pat in [("人称", r"\*\*人称\*\* \| (.*)"), ("标点习惯", r"\*\*标点习惯\*\* \| (.*)"),
                         ("典型段长", r"\*\*典型段长\*\* \| (.*)"), ("口语词表", r"\*\*口语词表\*\* \| (.*)")]:
            m = re.search(pat, t)
            if m: print(f"   · {key}：{m.group(1).strip()[:88]}")

    # 3 最近 5 篇的去重清单
    ml = (REPO / "module-log.md")
    if ml.exists():
        t = ml.read_text(encoding="utf-8")
        rows = [l for l in t.splitlines() if l.count("|") >= 5 and re.search(r"\d{4}-\d{2}-\d{2}", l)]
        print(f"\n【近 5 篇已用写法】{c('这些小标题写法本篇不得复用', 'y')}")
        for r in rows[-5:]:
            cells = [x.strip() for x in r.split("|") if x.strip()]
            if len(cells) >= 5:
                print(f"   · {cells[1]}：{cells[4][:96]}")
        used = re.search(r"## 已用过的写法（避免重复）\n(.*?)\n##", t, re.S)
        if used:
            flat = [x.strip() for x in used.group(1).strip().splitlines() if x.strip()]
            print(f"   累计已用 {len(flat)} 条短语（脚本会自动查）")
        todo = re.search(r"## 待写的三条.*?\n(.*?)$", t, re.S)
        if todo:
            print(f"\n【待写储备】")
            for line in todo.group(1).strip().splitlines():
                if line.startswith("|") and "---" not in line:
                    cells = [x.strip() for x in line.split("|") if x.strip()]
                    if len(cells) >= 2 and cells[0] != "选题": print(f"   · {cells[0]}")

    # 4 规格与红线
    print(f"\n【写作规格】")
    print(f"   · 字数 {pf.MIN_CHARS}–{pf.MAX_CHARS} 字（preflight 实算，不靠估）")
    print(f"   · 单段 ≤65 字｜加粗 ≤8%｜小标题间距 ≤600 字")
    print(f"   · 标题 16–25 字，带 Emoji，含具体数字或「实测/对比/体验」")
    print(f"   · 禁用词（{len(pf.BANNED_WORDS)} 个）：{'、'.join(pf.BANNED_WORDS)}")
    print(f"   · 禁：引用标记 [reference:n]｜配图提示｜序号泄漏｜匿名信源｜亲历式编造")
    print(f"   · 必出：合规三件套（AI 标识 + 数据来源 + 商业关系）")
    print(c("\n提示：题材状态 B（无实测素材）必须文末写「本文未做实测」", "y"))
    print(c("━" * 62, "d"))


# ---------------- check ----------------
def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def check(path, json_out=False):
    p = Path(path)
    if not p.exists(): sys.exit(f"找不到稿件：{p}")
    print(c("━" * 62, "d"))
    print(c(f"完稿体检 · {p.name}", "g"))
    print(c("━" * 62, "d"))

    r = run([sys.executable, str(REPO / "tools/preflight.py"), str(p)])
    fails = [l for l in r.stdout.splitlines() if "[FAIL]" in l or "[WARN]" in l]
    print(f"\n【preflight】退出码 {c(str(r.returncode), 'g' if r.returncode == 0 else 'r')}")
    if fails:
        for i, l in enumerate(fails):
            lv = "r" if "[FAIL]" in l else "y"
            print("   " + c(l.strip(), lv))
    else:
        print("   " + c("全部 PASS，无 FAIL/WARN", "g"))
    # 把 FAIL 的详情行也带出来
    lines = r.stdout.splitlines()
    for i, l in enumerate(lines):
        if "[FAIL]" in l and i + 1 < len(lines) and lines[i + 1].startswith("          "):
            print("      " + lines[i + 1].strip())

    base = REPO / "voice/基线.json"
    if base.exists():
        v = run([sys.executable, str(REPO / "tools/voice_check.py"), str(p), "--baseline", str(base)])
        print(f"\n【文风体检】对照 voice/基线.json")
        for l in v.stdout.splitlines():
            if ("✅" in l or "⚠️" in l or "❌" in l) and "判定" not in l:
                print("   " + l.strip())
    print(c("━" * 62, "d"))
    return r.returncode


# ---------------- handoff ----------------
def handoff(path, append=False):
    p = Path(path)
    if not p.exists(): sys.exit(f"找不到稿件：{p}")
    raw = p.read_text(encoding="utf-8")

    # 正文范围：砍掉标题模块、合规声明、已有的交接单
    body = raw
    for stop in ("## 合规声明", "## 排版交接单", "## 标题"):
        i = body.find(stop)
        if i > 0: body = body[:i]
    # 去掉 URL 与 arXiv 编号——它们含数字但不是"核心数字"
    body = re.sub(r"https?://\S+", " ", body)
    body = re.sub(r"arXiv[:\s]*\d{4}\.\d{4,5}", " ", body)
    body = re.sub(r"arxiv\.org/abs/\S+", " ", body)
    body = re.sub(r"\d{4}-\d{2}-\d{2}", " ", body)          # 日期

    # 值得做成图/大字的数字：带单位、百分比、倍数，或 3 位以上（排除年份）
    DATA_NUM = re.compile(
        r"\d+(?:\.\d+)?\s*(?:%|％|万|亿|倍|千|GB|TB|MB|KB|ms|毫秒|秒|分钟|小时|天|个|人|"
        r"节点|台|核|次|条|项|页|元|美元)")
    BARE = re.compile(r"\b\d{3,}\b")

    nums, seen = [], set()
    for s in re.split(r"(?<=[。！？；\n])", body):
        if not s.strip(): continue
        found = DATA_NUM.findall(s) or [
            m.group(0) for m in BARE.finditer(s)
            if not re.fullmatch(r"(?:19|20)\d{2}", m.group(0))
        ]
        found = [f.strip() for f in found if f.strip()]
        if not found: continue
        key = tuple(found)
        if key in seen: continue
        seen.add(key)
        ctx = re.sub(r"\s+", " ", re.sub(r"[*`>#\[\]]", "", s)).strip()
        nums.append(("、".join(found[:3]), ctx[:64]))

    # 引用块（金句 / 官方原话候选），排除合规声明里的行
    quotes = [q.strip() for q in re.findall(r"^>\s*(.+)$", body, re.M)
              if not re.search(r"内容说明|本文未做实测|数据来源|商业关系", q)]

    print(c("━" * 62, "d"))
    print(c(f"排版交接单骨架 · {p.name}", "g"))
    print(c("━" * 62, "d"))
    if not nums:
        print(c("⚠️  没扫到明显的核心数字——确认关键数据是否写进了正文", "y"))
    else:
        print(f"\n扫到 {len(nums)} 组候选数字（含义与出处请人工补全、去重）：\n")
        print("| 数字 | 含义 | 出处 |")
        print("|---|---|---|")
        for n, _ in nums[:10]:
            print(f"| {n} |  |  |")
        print(c("\n   原始上下文（帮你回忆每个数字指什么）：", "d"))
        for n, ctx in nums[:10]:
            print(c(f"   · {n} ← {ctx}", "d"))
    if quotes:
        print(f"\n【引用块】{len(quotes)} 条（金句 / 官方原话候选）")
        for q in quotes[:3]:
            print(f"   · {q[:78]}")
    print(f"\n【建议配图位】每 350–500 字一张，正文约需 "
          f"{max(1, pf.cjk_count(pf.strip_md(body)) // 450)} 张")
    print(c("━" * 62, "d"))

    if append:
        block = ["\n## 排版交接单", "", "核心数字清单：", "",
                 "| 数字 | 含义 | 出处 |", "|---|---|---|"]
        for n, _ in nums[:8]:
            block.append(f"| {n} |  |  | ")
        block += ["", "建议配图位：", ""]
        for i in range(1, max(1, pf.cjk_count(pf.strip_md(body)) // 450) + 1):
            block += [f"{i}. 第 __ 段后：", ""]
        block += ["金句：", ""]
        with p.open("a", encoding="utf-8") as f:
            f.write("\n".join(block) + "\n")
        print(c(f"✅ 已追加空的交接单骨架到 {p.name}（填空即可）", "g"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["brief", "check", "handoff"])
    ap.add_argument("path", nargs="?")
    ap.add_argument("--append", action="store_true", help="handoff：直接追加到稿件末尾")
    a = ap.parse_args()
    if pf is None: sys.exit("无法导入 tools/preflight.py")
    if a.cmd == "brief": brief(); return 0
    if not a.path: sys.exit(f"{a.cmd} 需要指定稿件路径")
    if a.cmd == "check": return check(a.path)
    handoff(a.path, a.append); return 0


if __name__ == "__main__":
    sys.exit(main())
