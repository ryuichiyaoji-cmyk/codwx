#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""选题的搜索需求验证：调用公开搜索建议接口，判断一个主题有没有真实长尾需求。

背景：微信公众号搜一搜的下拉词是金标准，但只能人工代抄（模型访问不了）。
本脚本用 Bing / Google / 百度 的公开建议接口做**可自动化的替代验证**——
它们反映的是真实搜索行为，足够判断"这个词有没有人在搜、搜的是不是具体问题"。

用法：
    python3 tools/search_demand.py "Suno 版权"
    python3 tools/search_demand.py "Kimi 上下文" --json

输出：各引擎建议词 + 评分建议（0-3）+ 判定理由。**这是选题评分里"搜索价值"维度的依据。**
"""
import argparse, json, re, ssl, sys, urllib.parse, urllib.request

CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124 Safari/537.36"}

def _get(url, timeout=12):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout, context=CTX).read()

def bing(q):
    raw = _get("https://api.bing.com/osjson.aspx?query=" + urllib.parse.quote(q)).decode("utf-8", "ignore")
    return json.loads(raw)[1]

def google(q):
    raw = _get("https://suggestqueries.google.com/complete/search?client=firefox&hl=zh-CN&q="
               + urllib.parse.quote(q)).decode("utf-8", "ignore")
    return json.loads(raw)[1]

def baidu(q):
    raw = _get("https://suggestion.baidu.com/su?wd=" + urllib.parse.quote(q)).decode("gb18030", "ignore")
    m = re.search(r's:\[(.*?)\]', raw, re.S)
    if not m:
        return []
    return [x.strip().strip('"') for x in m.group(1).split(",") if x.strip()]

def normalize(s):
    return re.sub(r"[\s　]+", "", s).lower()

def judge(base, all_sugs):
    """判定搜索需求强度：0（无） / 1-2（只有泛核心词） / 3（有明确长尾）。"""
    nb = normalize(base)
    uniq = sorted({s for s in all_sugs if s.strip()})
    # 与基础词归一化后相同、或仅大小写/空格差异的，算"泛核心词"
    generic = [s for s in uniq if normalize(s) == nb]
    longtail = [s for s in uniq if normalize(s) != nb and nb in normalize(s) or normalize(s) != nb and nb[:2] in normalize(s)]
    # 只保留确实含核心语义的建议词
    longtail = [s for s in uniq if normalize(s) != nb and (nb[:2] in normalize(s) or any(t in normalize(s) for t in base.split()))]
    if len(uniq) == 0:
        return 0, "三个引擎都没有返回建议词——这个词没有人搜，或表述不成立", uniq, generic, longtail
    if len(longtail) >= 2:
        return 3, f"有 {len(longtail)} 个具体长尾词，说明用户在搜的是具体问题（不是泛泛了解）", uniq, generic, longtail
    if len(uniq) >= 3:
        return 1, "只有泛核心词的变体，没有具体长尾——读者可能只是泛泛了解，转化价值低", uniq, generic, longtail
    return 1, "建议词很少，搜索需求偏弱", uniq, generic, longtail

def main():
    ap = argparse.ArgumentParser(description="选题搜索需求验证")
    ap.add_argument("keyword")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    res = {}
    for name, fn in [("bing", bing), ("google", google), ("baidu", baidu)]:
        try:
            res[name] = fn(a.keyword)
        except Exception as e:
            res[name] = {"error": f"{type(e).__name__}: {str(e)[:60]}"}

    all_sugs = []
    for v in res.values():
        if isinstance(v, list):
            all_sugs += v
    score, why, uniq, generic, longtail = judge(a.keyword, all_sugs)

    if a.json:
        print(json.dumps({"keyword": a.keyword, "score": score, "reason": why,
                          "suggestions": uniq, "longtail": longtail, "by_engine": res},
                         ensure_ascii=False, indent=1))
        return 0

    print(f"关键词：{a.keyword}")
    for name, v in res.items():
        if isinstance(v, dict) and "error" in v:
            print(f"  [{name}] ❌ {v['error']}")
        else:
            print(f"  [{name}] {len(v)} 条：" + "、".join(v[:8]))
    print(f"\n搜索价值评分建议：**{score}/3**")
    print(f"理由：{why}")
    if longtail:
        print(f"可用的长尾词（写标题时优先用这些）：{'、'.join(longtail[:6])}")
    print("\n注：这是 Bing/Google/百度 的替代验证；微信公众号搜一搜的下拉词仍是金标准，"
          "有条件时人工代抄一次以校准。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
