#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""选题扫描一键跑（抓源 → 自动聚类 → 搜索验证 → 归档）

把 ai-topic-scout 的机械部分全做掉，把判断力留给模型：
一次命令输出「今天有哪些候选选题簇 + 每簇的搜索需求分」，不用再把 100+ 条标题逐条读一遍。

用法：
    python3 tools/topic_scan.py                          # 抓 48h + 自动聚类，输出 Top 12 簇
    python3 tools/topic_scan.py --hours 24 --top 15
    python3 tools/topic_scan.py --demand "GPT-6" "Agent 沙盒"    # 额外跑搜索需求验证
    python3 tools/topic_scan.py --topic "OpenAI 降价|GPT-6,Opus 5.5"   # 指定簇，看它命中了哪些线索
    python3 tools/topic_scan.py --no-fetch --from topic-scans/xxx.json  # 不联网，复用已有 JSON

归档：topic-scans/YYYY-MM-DD-HHMM.md（含全部匹配线索与信源链接）
"""
import argparse, json, re, subprocess, sys, datetime
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import scan_feeds
except ImportError:
    scan_feeds = None

REPO = Path(__file__).resolve().parent.parent

# 自动聚类用的实体词表：命中即作为一簇的锚点
ENTITIES = [
    "GPT-6", "GPT-5", "Opus 5.5", "Claude", "OpenAI", "Anthropic", "Google", "Gemini",
    "Meta", "Muse", "DeepSeek", "Qwen", "通义", "阿里", "百度", "文心", "字节", "豆包",
    "腾讯", "混元", "华为", "盘古", "小米", "MiMo", "Kimi", "月之暗面", "智谱", "GLM",
    "MiniMax", "阶跃", "讯飞", "蚂蚁", "百灵", "Ming", "英伟达", "NVIDIA", "黄仁勋",
    "台积电", "高通", "骁龙", "三星", "苹果", "Apple", "微软", "Microsoft", "xAI", "Grok",
    "机器人", "具身", "智能体", "Agent", "算力", "数据中心", "芯片", "世界模型",
    "Suno", "Sora", "PixVerse", "视频模型", "音乐", "版权", "融资", "上市", "监管",
    "安全", "漏洞", "越狱", "反垄断", "备案", "开源", "论文", "RSI",
]


def rel(path):
    """相对仓库显示，仓库外则原样显示"""
    try:
        return str(Path(path).resolve().relative_to(REPO))
    except Exception:
        return str(path)


def load_items(args):
    if args.from_json:
        return json.loads(Path(args.from_json).read_text(encoding="utf-8")), {}
    if scan_feeds is None:
        sys.exit("找不到 tools/scan_feeds.py，无法抓源")
    if args.no_fetch:
        sys.exit("--no-fetch 需要配合 --from 指定已有 JSON")
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=args.hours)
    rows, fails, stats = [], [], {}
    for src, url in scan_feeds.FEEDS:
        try:
            got = scan_feeds.items_from_xml(scan_feeds.fetch(url), src)
            if not got:
                fails.append(src); continue
            kept = [it for it in got
                    if (scan_feeds.parse_date(it["date"]) is None
                        or scan_feeds.parse_date(it["date"]) >= cutoff)]
            stats[src] = (len(got), len(kept)); rows += kept
        except Exception as e:
            fails.append(f"{src}({type(e).__name__})")
    keep = []
    for it in rows:
        t = it["title"]
        if any(n in t for n in scan_feeds.NOISE):
            continue
        if any(k.lower() in t.lower() for k in scan_feeds.AI_KW):
            keep.append(it)
    seen, uniq = set(), []
    for it in keep:
        if it["title"] in seen: continue
        seen.add(it["title"]); uniq.append(it)
    return uniq, {"stats": stats, "fails": fails}


def fmt_time(raw):
    """把各种日期格式统一成 MM-DD HH:MM（本地时区），取不到则回退原串"""
    if not raw:
        return "??-?? ??:??"
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(raw)
    except Exception:
        try:
            dt = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return raw[:16]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone().strftime("%m-%d %H:%M")


def cluster(items):
    """按实体词把标题聚成簇；一条线索可落进多个簇"""
    groups = defaultdict(list)
    for it in items:
        t = it["title"]
        hit = [e for e in ENTITIES if e.lower() in t.lower()]
        for e in hit:
            groups[e].append(it)
    # 只留成簇的（>=2 条），按条数排序
    return sorted(((k, v) for k, v in groups.items() if len(v) >= 2),
                  key=lambda kv: -len(kv[1]))


def demand(kw):
    """跑 search_demand.py，返回 (分数, 理由, 前 6 个长尾词)

    ⚠️ 无网络时三个引擎都会返回 error，此时 search_demand 会给出 score=0，
    那会被误读成「大家不搜这个词」。所以这里先判联网状态，失败返回 None。
    """
    r = subprocess.run([sys.executable, str(REPO / "tools/search_demand.py"), kw, "--json"],
                       capture_output=True, text=True)
    if r.returncode != 0: return None
    try:
        d = json.loads(r.stdout)
    except Exception:
        return None
    eng = d.get("by_engine") or {}
    ok = [v for v in eng.values() if isinstance(v, list)]
    if not ok:
        return None                      # 三个引擎全挂 = 联网失败，不是没需求
    return d.get("score"), d.get("reason", ""), d.get("longtail", [])[:6]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=48)
    ap.add_argument("--top", type=int, default=12, help="输出前 N 个簇")
    ap.add_argument("--demand", nargs="*", default=[], help="要跑搜索需求验证的核心词")
    ap.add_argument("--topic", action="append", default=[],
                    help='指定簇，格式 "名称|关键词1,关键词2"')
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--from", dest="from_json", default=None, help="复用已有扫描 JSON")
    ap.add_argument("--out", default=None)
    ap.add_argument("--quiet", action="store_true", help="只打汇总，不列簇内标题")
    a = ap.parse_args()

    items, meta = load_items(a)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")

    # 归档原始 JSON（走 --from 时不再重复写）
    if not a.from_json:
        jp = (REPO / "topic-scans" / f"{stamp}.json").resolve()
        jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        jp = Path(a.from_json).resolve()

    clusters = cluster(items)
    print(f"📡 线索 {len(items)} 条｜{len(clusters)} 个候选簇｜原始：{rel(jp)}")
    if meta.get("fails"):
        print(f"   ⚠️ 抓取失败：{'、'.join(meta['fails'])}")

    lines = [f"# 选题扫描 · {datetime.date.today().isoformat()}", "",
             "> 每条线索前缀为该条**发布时间**（本机时区）。写选题卡时，`事件` 字段必须标注实际发生时间。", "",
             f"线索 **{len(items)}** 条｜候选簇 **{len(clusters)}** 个｜原始 JSON：`{rel(jp)}`", ""]
    if meta.get("stats"):
        lines += ["## 信源覆盖", "", "| 信源 | 抓取 | 窗口内 |", "|---|---|---|"]
        for s, (g, k) in meta["stats"].items():
            lines.append(f"| {s} | {g} | {k} |")
        lines += ["", f"失败源：{'、'.join(meta['fails']) or '无'}", ""]

    # 自动簇
    lines += ["## 自动聚类（按线索条数排序）", ""]
    for name, its in clusters[:a.top]:
        lines.append(f"### {name}（{len(its)} 条）")
        for it in its[:6]:
            lines.append(f"- `{fmt_time(it.get('date'))}` [{it['src']}] {it['title']}")
        lines.append("")
        if not a.quiet:
            print(f"\n▸ {name}（{len(its)} 条）")
            for it in its[:3]:
                print(f"   · [{it['src']} {fmt_time(it.get('date'))}] {it['title'][:60]}")

    # 指定簇
    if a.topic:
        print("\n🎯 指定簇命中情况：")
        lines += ["## 指定簇明细", ""]
        for spec in a.topic:
            parts = [x.strip() for x in spec.split("|")]
            name, kws = parts[0], [x.strip() for x in (parts[1].split(",") if len(parts) > 1 else parts[0].split())]
            hit = [it for it in items if any(k.lower() in it["title"].lower() for k in kws)]
            print(f"   ▸ {name}：{len(hit)} 条")
            lines += [f"### {name}（{len(hit)} 条）", f"关键词：{'、'.join(kws)}", ""]
            for it in hit[:10]:
                lines += [f"- `{fmt_time(it.get('date'))}` [{it['src']}] {it['title']}｜{it['url']}"]
            lines.append("")

    # 搜索需求验证
    if a.demand:
        print("\n🔎 搜索需求验证：")
        lines += ["## 搜索需求验证（`search_demand.py`）", "",
                  "| 核心词 | 得分 | 可用长尾词 |", "|---|---|---|"]
        for kw in a.demand:
            r = demand(kw)
            if not r:
                print(f"   ▸ {kw}：⚠️ 联网失败，未取得结果（不代表没有搜索需求）")
                lines.append(f"| {kw} | ⚠️ 联网失败 | — |")
                continue
            sc, why, lt = r
            print(f"   ▸ {kw}：{sc}/3" + (f"｜{'、'.join(lt[:4])}" if lt else ""))
            lines.append(f"| {kw} | {sc}/3 | {'、'.join(lt) or '—'} |")
        lines.append("")

    # 未归类线索（最多 30 条，兜底不漏）
    intitles = {it["title"] for _, its in clusters for it in its}
    rest = [it for it in items if it["title"] not in intitles]
    if rest:
        lines += ["## 未归入任何簇的线索（前 30 条）", ""]
        for it in rest[:30]:
            lines.append(f"- `{fmt_time(it.get('date'))}` [{it['src']}] {it['title']}")

    out = Path(a.out) if a.out else REPO / "topic-scans" / f"{datetime.date.today().isoformat()}-{stamp[-4:]}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n📝 归档：{rel(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
