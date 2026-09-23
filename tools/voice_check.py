#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写作风格体检：把"太AI化"变成可量化的指标，并与你自己的风格基线对比。

两种用法：
  1) 建基线（从你的真实语料）：
       python3 tools/voice_check.py --corpus voice/语料 --save voice/基线.json
  2) 体检一篇文章（可选与基线对比）：
       python3 tools/voice_check.py 草稿.md --baseline voice/基线.json

指标分两类：
  · 越多越像 AI —— 公式化过渡 / 抽象大词 / 对仗模板 / 空转过渡
  · 越多越像人 —— 第一人称密度 / 口语词 / 情绪自嘲 / 破折号省略号 / 短句占比
"""
import argparse, glob, json, os, re, statistics as st, sys

# ---- AI 腔词表 ----
AI_PATTERNS = {
    "公式化过渡": r"(值得(注意|一提)的?是?|需要指出的是|不可否认|众所周知|不难发现|毋庸置疑)",
    "抽象大词":   r"(真正的|本质上|标志着|意味着|核心在于|深刻地|关键在于|从根本上|深层次)",
    "对仗模板":   r"(不是[^。]{1,20}而是|不仅[^。]{0,15}而且|既[^。]{0,12}又|越[^。]{0,8}越[^。]{0,8})",
    "空转过渡":   r"(那么[，、]|接下来|综上所述|总而言之|让我们|下面我们|首先[，、]|其次[，、])",
}
# ---- 人味特征 ----
HUMAN_PATTERNS = {
    "第一人称": r"我(?![们方]|方)|我们",
    "第二人称": r"你(?![们])",
    "口语词":   r"(挺[^。]{0,6}|其实|说白了|反正|居然|竟然|倒是|有点|压根|干脆|好家伙|谁懂|离谱|真的[^。]{0,4})",
    "情绪自嘲": r"(翻车|踩坑|无语|尴尬|打脸|真香|哭笑不得|绷不住|服了)",
    "破折号":   r"——",
    "省略号":   r"……",
    "括号OS":   r"（[^）]{2,30}）",
}

def cjk(t): return len(re.findall(r"[\u4e00-\u9fff]", t))

def plain(text):
    t = re.sub(r"```.*?```", " ", text, flags=re.S)
    t = "\n".join(l for l in t.splitlines() if not l.startswith(("#", "|", ">", "```")))
    return t

def analyze(text):
    body = plain(text)
    n = max(1, cjk(body))
    paras = [p for p in re.split(r"\n\s*\n|\n", body) if cjk(p) >= 6]
    plens = [cjk(p) for p in paras] or [0]
    sents = [x.strip() for x in re.split(r"[。！？；\n]", body) if cjk(x.strip()) >= 2]
    slens = [cjk(x) for x in sents] or [0]
    m = {"字数": n, "段落数": len(paras)}
    for k, p in AI_PATTERNS.items():
        m[k] = round(len(re.findall(p, body)) / n * 1000, 2)      # 每千字
    for k, p in HUMAN_PATTERNS.items():
        m[k] = round(len(re.findall(p, body)) / n * 1000, 2)
    m["句长均值"] = round(st.mean(slens), 1)
    m["句长标准差"] = round(st.pstdev(slens), 1)
    m["短句占比"] = round(sum(1 for x in slens if x < 15) / len(slens) * 100, 1)   # <15 字算短句
    m["逗号密度"] = round(body.count("，") / n * 1000, 1)
    ends = len(re.findall(r"[。！？]", body)) or 1
    m["意合度"] = round(body.count("，") / ends, 2)   # 逗号÷句号：越高越"一逗到底"
    m["段长均值"] = round(st.mean(plens), 1)
    m["段长最长"] = max(plens)
    return m

def load_corpus(d):
    files = []
    for ext in ("*.md", "*.txt"):
        files += glob.glob(os.path.join(d, ext))
    if not files:
        raise SystemExit(f"{d} 里没有 .md / .txt 语料")
    ms = [analyze(open(f, encoding="utf-8").read()) for f in files]
    keys = ms[0].keys()
    base = {k: round(st.mean([x[k] for x in ms]), 2) for k in keys}
    base["_语料文件数"] = len(files)
    base["_语料文件"] = [os.path.basename(f) for f in files]
    return base

# 判定：AI 腔指标越低越好；人味指标越高越好
AI_KEYS = list(AI_PATTERNS.keys())
HUMAN_KEYS = ["第一人称", "第二人称", "口语词", "情绪自嘲", "破折号", "省略号", "括号OS"]

def verdict(key, val, base):
    if base is None:
        return ""
    b = base.get(key)
    if b is None:
        return "（基线无此项）"
    if key in AI_KEYS:
        return "✅ 与你的风格一致" if val <= max(b * 1.5, b + 0.5) else f"⚠️ 比你的习惯多 {val - b:.1f}/千字"
    if key in HUMAN_KEYS:
        return "✅ 与你的风格一致" if val >= b * 0.6 else f"⚠️ 比你的习惯少 {b - val:.1f}/千字"
    return f"基线 {b}"

def main():
    ap = argparse.ArgumentParser(description="写作风格体检")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--corpus")
    ap.add_argument("--save")
    ap.add_argument("--baseline")
    a = ap.parse_args()

    if a.corpus:
        base = load_corpus(a.corpus)
        if a.save:
            os.makedirs(os.path.dirname(a.save) or ".", exist_ok=True)
            json.dump(base, open(a.save, "w"), ensure_ascii=False, indent=1)
            print(f"✓ 基线已存 {a.save}（来自 {base['_语料文件数']} 个文件）")
        else:
            print(json.dumps(base, ensure_ascii=False, indent=1))
        return 0

    if not a.file:
        ap.error("要么给 --corpus 建基线，要么给一篇文章做体检")

    base = json.load(open(a.baseline)) if a.baseline and os.path.exists(a.baseline) else None
    m = analyze(open(a.file, encoding="utf-8").read())

    print(f"风格体检：{os.path.basename(a.file)}" + (f"（对照基线：{os.path.basename(a.baseline)}）" if base else "（无基线）"))
    print("=" * 74)
    print(f"{'指标':<12}{'本文':>10}{'基线':>10}   判定")
    print("-" * 74)
    print("— AI 腔（越低越好）—")
    for k in AI_KEYS:
        b = base.get(k) if base else None
        print(f"{k:<12}{m[k]:>10}{('' if b is None else b):>10}   {verdict(k, m[k], base)}")
    print("— 人味（越高越像人）—")
    for k in HUMAN_KEYS:
        b = base.get(k) if base else None
        print(f"{k:<12}{m[k]:>10}{('' if b is None else b):>10}   {verdict(k, m[k], base)}")
    print("— 结构 —")
    for k in ["句长均值", "句长标准差", "短句占比", "段长均值", "段长最长", "逗号密度", "意合度", "字数"]:
        b = base.get(k) if base else None
        print(f"{k:<12}{m[k]:>10}{('' if b is None else b):>10}")

    ai_total = sum(m[k] for k in AI_KEYS)
    print("-" * 74)
    print(f"AI 腔词合计：{ai_total:.1f}/千字" + ("  ⚠️ 偏高" if ai_total > 6 else "  ✅ 可接受"))
    if not base:
        print("\n提示：还没建基线。把 3–5 段你自己写的文字放进 voice/语料/，跑")
        print("      python3 tools/voice_check.py --corpus voice/语料 --save voice/基线.json")
    return 0

if __name__ == "__main__":
    sys.exit(main())
