#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""选题扫描的信源抓取器

把 skill 里说的"三层扫描"变成一条命令：抓 RSS → 过滤 AI 相关 → 归档 JSON。

用法：
    python3 tools/scan_feeds.py                    # 抓最近 48 小时，输出到 topic-scans/
    python3 tools/scan_feeds.py --hours 72
    python3 tools/scan_feeds.py --all              # 不做 AI 关键词过滤

口径：只抓标题+链接+时间；正文核验是下一步（官方文件 > 媒体报道）。
"""
import argparse, json, re, ssl, sys, urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124 Safari/537.36"}

# 三层信源：第一层官方/大厂，第二层争议/监管，第三层数据/研究。合计 <=20。
FEEDS = [
    # --- 第一层：官方发布与重磅融资（国内）---
    ("IT之家",      "https://www.ithome.com/rss/"),
    ("量子位",      "https://www.qbitai.com/feed"),
    ("钛媒体",      "https://www.tmtpost.com/rss"),
    # --- 第一层：官方发布与重磅融资（海外）---
    ("TechCrunch",  "https://techcrunch.com/feed/"),
    ("VentureBeat", "https://venturebeat.com/feed/"),
    # --- 第二层：争议与政策监管 ---
    ("Ars Technica","https://feeds.arstechnica.com/arstechnica/index"),
    ("The Verge",   "https://www.theverge.com/rss/index.xml"),
    ("cnBeta",      "https://www.cnbeta.com.tw/backend.php"),
    # --- 第三层：深度分析与产业数据 ---
    ("机器之心",    "https://www.jiqizhixin.com/rss"),
    ("Engadget",    "https://www.engadget.com/rss.xml"),
    ("HuggingFace Papers", "https://huggingface.co/papers/rss"),
]

# AI 相关性过滤：命中任一即入选
AI_KW = ["AI", "A.I.", "人工智能", "大模型", "模型", "智能体", "Agent", "LLM", "GPT", "Claude",
         "Gemini", "OpenAI", "Anthropic", "DeepSeek", "Qwen", "通义", "豆包", "文心", "Kimi",
         "智谱", "GLM", "MiniMax", "月之暗面", "阶跃", "Suno", "Sora", "Midjourney", "Stable",
         "算力", "数据中心", "GPU", "英伟达", "NVIDIA", "芯片", "推理", "训练", "多模态",
         "机器人", "自动驾驶", "生成式", "AIGC", "开源", "版权", "监管", "融资", "音乐", "视频"]
# 明显无关的板块直接扔掉
NOISE = ["世界杯", "NBA", "欧冠", "足球", "天气", "台风", "彩票", "星座", "张雪峰", "涨粉"]


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=20, context=CTX).read()


def parse_date(s):
    if not s:
        return None
    try:
        return parsedate_to_datetime(s)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def strip_tag(t):
    return t.split("}")[-1].lower() if t and "}" in t else (t or "").lower()


def items_from_xml(raw, src):
    out = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return out
    for node in root.iter():
        if strip_tag(node.tag) not in ("item", "entry"):
            continue
        title = link = date = ""
        for child in node:
            tag = strip_tag(child.tag)
            if tag == "title" and not title:
                title = (child.text or "").strip()
            elif tag == "link" and not link:
                link = (child.get("href") or child.text or "").strip()
            elif tag in ("pubdate", "published", "updated", "date") and not date:
                date = (child.text or "").strip()
        if title:
            out.append({"src": src, "title": re.sub(r"\s+", " ", title), "url": link, "date": date})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=48, help="只保留最近 N 小时（默认 48）")
    ap.add_argument("--all", action="store_true", help="不做 AI 关键词过滤")
    ap.add_argument("--out", default=None, help="输出 JSON 路径")
    a = ap.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=a.hours)
    rows, failures = [], []
    for src, url in FEEDS:
        try:
            raw = fetch(url)
            got = items_from_xml(raw, src)
            if not got:
                failures.append((src, "RSS 解析为空"))
                continue
            kept = []
            for it in got:
                dt = parse_date(it["date"])
                if dt is None or dt >= cutoff:
                    kept.append(it)
            rows += kept
            print(f"  [{src}] {len(got)} 条 → 窗口内 {len(kept)} 条", file=sys.stderr)
        except Exception as e:
            failures.append((src, f"{type(e).__name__}: {str(e)[:60]}"))
            print(f"  [{src}] ❌ {type(e).__name__}", file=sys.stderr)

    if not a.all:
        keep = []
        for it in rows:
            t = it["title"]
            if any(n in t for n in NOISE):
                continue
            if any(k.lower() in t.lower() for k in AI_KW):
                keep.append(it)
        rows = keep

    seen, uniq = set(), []
    for it in rows:
        key = it["title"]
        if key in seen:
            continue
        seen.add(key); uniq.append(it)

    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    out = Path(a.out) if a.out else Path("topic-scans") / f"{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(uniq, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n合计 {len(uniq)} 条 AI 相关线索 → {out}")
    if failures:
        print("抓取失败：" + "、".join(f"{s}({w})" for s, w in failures))
    return 0


if __name__ == "__main__":
    sys.exit(main())
