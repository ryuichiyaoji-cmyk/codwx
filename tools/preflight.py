#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布前自检脚本（V6 体系）

覆盖：禁用词 / 标题规范 / 核心判断开篇 / V6 六模块结构 / 存疑表述 / 合规声明 / 字数 / 亲历式表述 / 拼盘信号 / 占位符 / **公众号排版六项**
口径：字数只统计正文，标题备选、编辑器备注、自查记录、自检清单均不计入。

口径说明：字数只统计正文，标题备选、编辑器备注、自查记录、自检清单均不计入。

设计原则：
- 只读：不修改稿件，只输出报告
- 离线：不联网、不调用模型
- 确定性：同一份稿子永远给同一个结果，不依赖"模型自觉"

用法：
    python3 tools/preflight.py <稿件.md>
    python3 tools/preflight.py <稿件.md> --json

退出码：0 = 全部通过（可能有 WARN）；1 = 有 FAIL（不可发布）
"""
import argparse
import json
import re
import sys
from pathlib import Path

# ---- 规则表 ----
BANNED_WORDS = ["背叛", "狂裁", "炸场", "出走", "怒", "惨", "秒杀", "吊打"]
# 风格卡硬规则（2026-09-23 定稿）：不用自称、不用套话
STYLE_BANNED = {
    "小编": "自称禁用——旧稿的“小编锐评/小编一句话”正是被判 AI 化的那批",
    "笔者": "自称禁用——风格卡规定不用自称",
    "咱们明天见": "收尾套话禁用",
    "点个关注不迷路": "收尾套话禁用",
    "今天我们来聊聊": "报到式开场禁用",
}
TITLE_LIMIT = 25
MIN_CHARS = 1200
MAX_CHARS = 1800   # V4.1 上参考线上限
TITLE_SIGNAL = re.compile(r"(实测|对比|体验)")
EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\u2b00-\u2bff\ufe0f]"
)
# 无素材却像亲历的表述（编造高危信号）
FAKE_EXPERIENCE = [
    r"我测了", r"小编测了", r"实测了\s*\d", r"试了\s*\d+\s*(天|小时|分钟|次)",
    r"花了\s*\d+\s*(小时|分钟|天)", r"大概花了", r"亲测\s*\d",
    r"踩了.{0,6}坑", r"上手.{0,4}(感觉|体验)",
]
# 拼盘信号（多个"另外/此外/还有"式并列）
PATCHWORK = [r"此外", r"另外", r"与此同时", r"还有一个", r"顺便说", r"值得一提"]
PLACEHOLDER = [r"【待[^】]*】", r"TODO", r"TBD", r"待补", r"待回填", r"待定"]

# --- V6 体系：六模块结构（功能点，不要求标题逐字一致）---
SIX_MODULES = {
    "① 核心判断开篇": [r"核心判断", r"先说判断", r"小编觉得", r"我的判断", r"一句话(说清|结论)", r"换挡", r"不再", r"第一次", r"真正.{0,8}(是|在于)"],
    "② 事件背景":     [r"事件", r"背景", r"发生了什么", r"起因"],
    "③ 分层拆解":     [r"拆解", r"扒数据", r"怎么运作", r"机制", r"原理", r"技术细节", r"▍"],  # ▍= 排版稿小标题，出现即视为已完成分层
    "④ 行业对照":     [r"对比", r"对照", r"横评", r"两条路", r"同行"],
    "⑤ 深层变化":     [r"深层", r"结构性", r"改变了什么", r"影响", r"意味着", r"关咱啥事"],
    "⑥ 结论":         [r"结论", r"总结", r"最后", r"说到底", r"回到开头"],
}

# --- 移植自 ai-news-xiaobian 版：序号泄漏 / 素材状态 / 双源 / 时间词 / 同质化 ---
INDEX_LEAK = re.compile(r"(国内|国外)\s*[0-9一二三四五六七八九十]\s*[、,.．]")
NO_TEST_DECL = ["本文未做实测", "未做实测", "没有做实测", "未进行实测", "本文不含实测"]
TEST_CLAIM = re.compile(r"(小编实测|实测了|亲测|我试了|跑了一遍|装上试)")
FRESH_WORDS = ["今天", "昨天", "凌晨", "刚刚", "本周", "昨日", "今日"]
NUM_PATTERNS = [
    re.compile(r"\d+(?:\.\d+)?\s*%"),
    re.compile(r"[¥$￥]\s*\d+(?:\.\d+)?"),
    re.compile(r"\d[\d,]{2,}\s*(?:万|亿|百万|千万)?"),
    re.compile(r"v?\d+\.\d+(?:\.\d+)?"),
    re.compile(r"\d+(?:\.\d+)?\s*(?:秒|分钟|小时|天|ms|GB|MB|TB)"),
]
SOURCE_SIGN = re.compile(
    r"(官方|据\s*[\u4e00-\u9fff]{2,10}(?:报|网|社|台|志)|"
    r"量子位|机器之心|36氪|财联社|IT之家|钛媒体|品玩|澎湃|新华|央视|"
    r"TechCrunch|The Information|路透|彭博|官网|公告|博客|报告|白皮书|"
    r"arXiv|Hacker News|GitHub|Hugging Face|HF|LICENSE)")


# 六模块的固定功能名：它们是结构常量，不是"创意写法"，不参与同质化对比
FIXED_MODULES = {"关咱啥事", "今日挖宝", "合规声明", "事件简述", "小编锐评", "结论",
                 "核心判断", "排版交接单", "核心数字清单", "建议配图位", "金句",
                 "数据来源", "商业关系", "事件背景", "分层拆解", "行业对照", "深层变化"}


def load_recent_headings(path="module-log.md", n=5, draft="", exclude_self=True):
    """从 module-log.md 最近 n 篇里提取「创意小标题」用于同质化去重。

    两个必须的过滤（否则必然误报）：
      1. 掉固定模块名（关咱啥事 / 今日挖宝 …）——它们是结构常量
      2. 跳过本稿自己的那一行——否则拿自己和自己比，永远命中
    """
    try:
        lines = [l for l in open(path, encoding="utf-8") if l.count("|") >= 5]
    except Exception:
        return []
    out = []
    for line in lines[-n:]:
        if exclude_self and draft:
            # 从稿件名里取"核心词"：去掉 草稿/排版稿/分析型/未实测 这类通用词，只留能识别选题的中文串
            noise = ("草稿", "排版稿", "分析型", "实测", "降级", "初版", "终稿", "版", "稿")
            core = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", " ", draft)
            toks = [t for t in core.split() if len(t) >= 2 and t not in noise]
            # 英文名（如 Apple-Reference-Image）也要能自排除：补拉丁/数字词
            toks += [t.lower() for t in re.findall(r"[A-Za-z0-9]{4,}", draft) if not t.isdigit()]
            row = re.sub(r"[\s]", "", line).lower()
            if toks and any(t.lower() in row for t in toks):
                continue    # 这是本稿自己那一行，跳过
        for cell in line.split("|"):
            for seg in re.split(r"[→>]", cell):
                seg = re.sub(r"[\s*]", "", seg)
                seg = re.sub(r"[（(].*?[)）]", "", seg)
                if seg in FIXED_MODULES:
                    continue
                if 5 <= len(seg) <= 24 and re.search(r"[\u4e00-\u9fff]{4,}", seg):
                    out.append(seg)
    return sorted(set(out))

# 存疑表述（低信息量判定里的“引用存疑数据/言论”）
DUBIOUS = [r"据说", r"据了解", r"有消息称", r"网传", r"传闻", r"业内普遍认为",
           r"知情人士", r"内部消息", r"听说"]
REFERENCE_LEAK = r"\[reference:\s*\d+\]"


def cjk_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def display_len(text: str) -> int:
    """标题长度：中文字数 + 英文数字连续段的个数（近似'字'）"""
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z0-9]+(?:\.[0-9]+)?", text))
    return cjk + latin


META_HEADING = re.compile(
    r"^#{2,4}\s*[^\n]*(标题|编辑器备注|编辑备注|编辑提示|自查记录|自检清单|发布说明|元数据)[^\n]*$", re.M
)


def strip_meta_sections(text: str) -> str:
    """去掉不属于正文的区块：标题备选区、编辑器备注、自查记录、自检清单等。

    这些区块是给编辑看的，不能算进正文字数——否则字数检查会误报。
    """
    out, skip = [], False
    for line in text.splitlines():
        if re.match(r"^#{2,4}\s", line):
            skip = bool(META_HEADING.match(line))
        if not skip:
            out.append(line)
    return "\n".join(out)


def strip_md(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)          # 代码块
    text = re.sub(r"^\s*>.*$", "", text, flags=re.M)           # 引用块
    text = re.sub(r"^\s*\|.*$", "", text, flags=re.M)          # 表格
    text = re.sub(r"[#*`_\[\]()>]", "", text)
    return text


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, name, detail):
        self.items.append({"level": level, "item": name, "detail": detail})

    def ok(self, name, detail=""):
        self.add("PASS", name, detail)

    def warn(self, name, detail):
        self.add("WARN", name, detail)

    def fail(self, name, detail):
        self.add("FAIL", name, detail)

    @property
    def failed(self):
        return [i for i in self.items if i["level"] == "FAIL"]

    def render(self):
        icon = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}
        lines = []
        for i in self.items:
            lines.append(f"{icon[i['level']]} [{i['level']:4}] {i['item']}")
            if i["detail"]:
                lines.append(f"          {i['detail']}")
        n = {lv: sum(1 for i in self.items if i["level"] == lv) for lv in ("PASS", "WARN", "FAIL")}
        lines.append("")
        lines.append(f"合计：PASS {n['PASS']} · WARN {n['WARN']} · FAIL {n['FAIL']}")
        lines.append("结论：" + ("❌ 不可发布，先修 FAIL 项" if n["FAIL"] else
                                ("⚠️  可发布，但请人工确认 WARN 项" if n["WARN"] else "✅ 全部通过")))
        return "\n".join(lines)


def title_section(text: str) -> str:
    """只取「标题」模块的正文，避免把阅读收益里的 ✅ 条目误判成标题"""
    m = re.search(r"^#{2,4}\s*\d*\.?\s*标题\s*$", text, re.M)
    if not m:
        return ""
    rest = text[m.end():]
    nxt = re.search(r"^#{2,4}\s", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def find_titles(text: str):
    """抓候选标题。两种格式都认：
    - 草稿格式：有「## 标题」模块 → 取模块内的主推与备选
    - 排版稿格式：无标题模块 → 只取正文第一行非空行（公众号稿的约定），
      避免把关咱啥事/互动问题里的 emoji 小标题误判成文章标题
    """
    sec = title_section(text)
    if not sec:
        first = next((l.strip() for l in text.splitlines() if l.strip()), "")
        return [first] if first and len(first) <= 60 else []
    titles = []
    for raw_line in sec.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(">") or line.startswith("|"):
            continue
        # 去掉列表符号 / 加粗符号 / 序号
        line = re.sub(r"^[-*\d.]+\s*", "", line)
        line = re.sub(r"^\*\*(主推|备选)\*\*\s*", "", line)
        line = line.strip("* ").strip()
        if 4 <= display_len(line) <= 60 and EMOJI.search(line):
            titles.append(line)
    seen, out = set(), []
    for t in titles:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def check(path: Path) -> Report:
    raw = path.read_text(encoding="utf-8")
    body = strip_md(raw)
    r = Report()

    # 1 禁用词
    hits = [w for w in BANNED_WORDS if w in raw]
    if hits:
        r.fail("禁用词", f"命中：{'、'.join(hits)}")
    else:
        r.ok("禁用词", f"未命中 {len(BANNED_WORDS)} 个禁用词")

    # 1.5 风格卡硬规则（自称与套话）
    style_hits = [(w, why) for w, why in STYLE_BANNED.items() if w in raw]
    if style_hits:
        r.fail("风格卡·自称与套话",
               "命中：" + "、".join(f"{w}（{why}）" for w, why in style_hits))
    else:
        r.ok("风格卡·自称与套话", f"未命中 {len(STYLE_BANNED)} 条禁忌（不用自称/不用套话）")

    # 2 标题
    titles = find_titles(raw)
    if not titles:
        r.warn("标题检测", "没识别到标题行（需要标题带 Emoji）")
    for t in titles[:6]:
        n = display_len(t)
        problems = []
        if n > TITLE_LIMIT:
            problems.append(f"{n}字 > {TITLE_LIMIT}字")
        if not re.search(r"\d", t) and not TITLE_SIGNAL.search(t):
            problems.append("既无具体数字，也无'实测/对比/体验'")
        if not EMOJI.search(t):
            problems.append("无 Emoji")
        if problems:
            r.fail(f"标题「{t[:18]}…」", "；".join(problems))
        else:
            r.ok(f"标题「{t[:18]}…」", f"{n}字，含数字/信号词 + Emoji")

    # 3 核心判断开篇（V6 取代 V4 的“阅读收益前置”与“锐评前置”）
    plain = strip_md(raw)
    head = plain[: max(200, int(len(plain) * 0.35))]
    if re.search(r"(小编觉得|我的判断|核心判断|先说判断|换句话|说到底|真正.{0,8}是|不是.{0,12}而是)", head):
        r.ok("核心判断开篇", "正文前部检测到明确判断句")
    else:
        r.fail("核心判断开篇", "正文前 35% 内未见明确判断（V6 要求先给判断）")

    # 4 关咱啥事 / 挖宝 / 引导
    for name, keys in [
        ("关咱啥事", ["关咱啥事"]),
        ("今日挖宝", ["今日挖宝", "🎁"]),
    ]:
        if any(k in raw for k in keys):
            r.ok(name, "模块存在")
        else:
            r.fail(name, "模块缺失")

    # 5 文末引导 + 互动
    has_cta = ("关注" in raw) and ("评论" in raw or "聊聊" in raw)
    if has_cta:
        r.ok("文末引导 + 互动问题", "检测到关注引导与互动提问")
    else:
        r.fail("文末引导 + 互动问题", "缺少关注引导或互动问题")

    # 6 合规声明三件套
    ai_mark = ("AI 辅助生成" in raw) or ("AI辅助生成" in raw) or ("AI生成内容标识" in raw)
    src_mark = "数据来源" in raw or "来源：" in raw
    biz_mark = "商业关系" in raw or "商业合作" in raw
    missing = [n for n, ok in [("AI生成标识", ai_mark), ("数据来源", src_mark), ("商业披露", biz_mark)] if not ok]
    if missing:
        r.fail("合规声明", "缺少：" + "、".join(missing))
    else:
        r.ok("合规声明", "AI标识 + 数据来源 + 商业关系 齐全")

    # 6.5 V6 六模块结构
    missing = []
    for name, pats in SIX_MODULES.items():
        if not any(re.search(pt, raw) for pt in pats):
            missing.append(name)
    if len(missing) >= 3:
        r.fail("V6 六模块结构", f"缺 {len(missing)} 个功能点：{'、'.join(missing)}")
    elif missing:
        r.warn("V6 六模块结构", f"疑似缺：{'、'.join(missing)}（标题措辞可不同，功能点要在）")
    else:
        r.ok("V6 六模块结构", "六个功能点全部命中")

    # 6.6 存疑表述（低信息量）
    hit = []
    for pt in DUBIOUS:
        for m in re.finditer(pt, raw):
            hit.append(m.group(0))
    if hit:
        r.fail("存疑表述", f"命中 {len(hit)} 处：{'、'.join(sorted(set(hit)))}（低信息量判定的高危词）")
    else:
        r.ok("存疑表述", "未出现据传/网传/业内人士等无源表述")

    # 7 引用标记残留
    leak = re.findall(REFERENCE_LEAK, raw)
    if leak:
        r.fail("引用标记残留", f"发现 {len(leak)} 处：{leak[:3]}")
    else:
        r.ok("引用标记残留", "未发现 [reference:n]")

    # 8 字数（排除引用块/表格/代码块，并排除标题/备注/自查等非正文区块）
    n = cjk_count(strip_md(strip_meta_sections(raw)))
    if n < MIN_CHARS:
        r.fail("字数", f"{n} 字 < {MIN_CHARS}（差 {MIN_CHARS - n} 字）")
    elif n > MAX_CHARS:
        r.warn("字数", f"{n} 字 > {MAX_CHARS}（超 {n - MAX_CHARS} 字；上限是参考线，但超太多会拖完读率）")
    else:
        r.ok("字数", f"{n} 字（{MIN_CHARS}–{MAX_CHARS} 区间内）")

    # 9 占位符（降级稿预期会有）
    ph = re.findall("|".join(PLACEHOLDER), raw)
    if ph:
        r.warn("未完成占位符", f"发现 {len(ph)} 处（降级稿正常，终稿必须清零）：{'、'.join(sorted(set(ph))[:6])}")
    else:
        r.ok("未完成占位符", "无残留")

    # 10 编造高危：无素材却像亲历
    fake = []
    for p in FAKE_EXPERIENCE:
        for m in re.finditer(p, raw):
            fake.append(m.group(0))
    if fake:
        r.warn("亲历式表述", f"检测到 {len(fake)} 处可能被读成亲测的表述：{'、'.join(fake[:5])}（若尚未实测，需改为条件句）")
    else:
        r.ok("亲历式表述", "未检测到无素材的亲历式表达")

    # 11 拼盘信号
    pw = sum(len(re.findall(p, raw)) for p in PATCHWORK)
    if pw >= 4:
        r.warn("拼盘信号", f"并列转折词出现 {pw} 次，注意是否在堆事件（规则：一篇文章只写一件事）")
    else:
        r.ok("拼盘信号", f"并列转折词 {pw} 次，密度正常")

    # --- 排版检查（公众号移动端）---
    # 12a 单段超长（手机 ≈15-17 字/行 → 4 行 ≈ 65 字）
    paras = [x.strip() for x in re.split(r"\n\s*\n", raw) if x.strip()]
    body_paras = [x for x in paras if not re.match(r"^\s*(#|\||>|```|【配图|-{2,}|—)", x)]
    over = sorted(((cjk_count(x), x) for x in body_paras if cjk_count(x) > 65), reverse=True)
    if over:
        n, t = over[0]
        r.fail("排版·单段超长", f"{len(over)} 段超过 65 字（手机约 4 行）；最长 {n} 字：{t[:26]}…")
    else:
        r.ok("排版·单段超长", f"{len(body_paras)} 个正文段落全部 ≤65 字")

    # 12b 加粗密度（公众号编辑器不认 Markdown 星号，这里只做密度体检）
    bold = "".join(re.findall(r"\*\*(.+?)\*\*", raw, re.S))
    total = cjk_count(strip_md(raw))
    dens = (cjk_count(bold) / total * 100) if total else 0.0
    if dens > 8:
        r.fail("排版·加粗密度", f"{dens:.1f}% > 8%——加粗用多了等于没重点，只留数字与结论词")
    elif dens > 0:
        r.warn("排版·加粗密度", f"{dens:.1f}%（≤8% 达标）。注意：公众号编辑器不识别 **，需按操作清单手动加粗")
    else:
        r.ok("排版·加粗密度", "未使用加粗")

    # 12c 小标题间距（▍为公众号小标题写法）
    heads = list(re.finditer(r"^\s*##\s*[一二三四五六七八九十]", raw, re.M))
    if heads:
        gaps = []
        for i in range(len(heads) - 1):
            seg = raw[heads[i].end():heads[i+1].start()]
            gaps.append(cjk_count(seg))
        tail = cjk_count(raw[heads[-1].end():])
        gaps.append(tail)
        bad = [g for g in gaps if g > 600]
        if bad:
            r.fail("排版·小标题间距", f"{len(bad)} 个小节超过 600 字（最长 {max(bad)} 字）——读者会失去位置感")
        else:
            r.ok("排版·小标题间距", f"{len(heads)} 个小标题，各节 {min(gaps)}–{max(gaps)} 字")
    else:
        r.warn("排版·小标题间距", "未检测到「## 一、xxx」格式的小标题——md2wx 靠这个渲染成胶囊，不要用其它花式符号")

    # 12d 配图位
    pics = re.findall(r"!\[[^\]]*\]\([^)]+\)", raw)
    n_body = cjk_count(strip_md(raw))
    expect = max(1, n_body // 500)
    ph = re.findall(r"【配图|此处放|插图|配图\s*\d+", raw)
    if ph:
        r.fail("排版·配图提示", f"发现 {len(ph)} 处配图占位文字（{ph[0]}…）——红线禁止，md2wx 会渲染成正文")
    elif len(pics) == 0:
        r.warn("排版·配图", f"正文 {n_body} 字但没有图片（建议每 350–500 字一张，约需 {expect} 张）")
    elif len(pics) < expect:
        r.warn("排版·配图", f"正文 {n_body} 字只有 {len(pics)} 张图，建议 ≥{expect} 张")
    else:
        r.ok("排版·配图", f"{len(pics)} 张图，正文 {n_body} 字")

    # 12e 分隔符混用 / 感叹号
    seps = set()
    for pat, name in [(r"^\s*—\s*—\s*—", "— — —"), (r"^\s*\*\s*\*\s*\*", "* * *"),
                      (r"^\s*-{3,}\s*$", "---"), (r"^\s*={3,}\s*$", "===")]:
        if re.search(pat, raw, re.M):
            seps.add(name)
    if len(seps) > 1:
        r.fail("排版·分隔符混用", "同时出现：" + "、".join(sorted(seps)) + "——全篇只用一种")
    else:
        r.ok("排版·分隔符", "未混用（" + ("、".join(seps) if seps else "未使用") + "）")
    # ⚠️ 先剥掉 Markdown 图片语法 ![...](...)：那 4 类括号里的 `!` 不是排版上的感叹号，
    #    否则只要配图超过 3 张就必然误报（本号规范是每 350–500 字一张图）。
    _no_img = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", raw)
    bangs = _no_img.count("！") + _no_img.count("!")
    if bangs > 3:
        r.warn("排版·感叹号", f"{bangs} 个（建议 ≤3）")
    else:
        r.ok("排版·感叹号", f"{bangs} 个")

    # --- 移植项：序号泄漏 / 素材状态 / 双源 / 时间词 / 同质化 ---
    leak = INDEX_LEAK.findall(raw)
    if leak:
        r.fail("序号泄漏", f"出现「{leak[0][0]}N、」式序号泄漏 {len(leak)} 处——草稿序号不许进正文")
    else:
        r.ok("序号泄漏", "无草稿序号残留")

    has_claim = bool(TEST_CLAIM.search(raw))
    has_decl = any(k in raw for k in NO_TEST_DECL)
    if has_claim and not has_decl:
        r.warn("素材状态", "出现实测式表述——请确认素材状态确为 A（有真素材），否则必须改写成脚本")
    elif not has_claim and not has_decl:
        r.warn("素材状态", "未见素材状态声明。状态 B（无素材）必须在文末写明「本文未做实测」")
    else:
        r.ok("素材状态", "已声明未做实测")

    nums = []
    for pat in NUM_PATTERNS:
        nums += pat.findall(raw)
    uniq = list(dict.fromkeys(nums))
    sents = re.split(r"[。！？\n]", raw)
    with_src = sum(1 for x in sents if SOURCE_SIGN.search(x) and any(c.isdigit() for c in x))
    if uniq and with_src == 0:
        r.warn("双源", f"检出 {len(uniq)} 个数字，但没有一句同时含来源信号，核对双源")
    elif uniq:
        r.ok("双源", f"{len(uniq)} 个数字、{with_src} 句含来源（关键数字仍需人工确认双源）")
    else:
        r.warn("双源", "全文未见具体数字，数据驱动不足")

    fw = [w for w in FRESH_WORDS if w in raw]
    if fw:
        r.warn("时间词新鲜度", f"出现 {fw}——需确认有对应日期的信源支撑")
    else:
        r.ok("时间词新鲜度", "无绝对时间词")

    used = load_recent_headings("module-log.md", 5, draft=path.name)
    if not used:
        r.warn("同质化", "读不到 module-log.md 的历史写法，跳过小标题去重")
    else:
        hits = [u for u in used if u in raw]
        if hits:
            r.fail("同质化", f"命中最近 5 篇用过的小标题写法：{hits[:3]}——必须换写法")
        else:
            r.ok("同质化", f"未命中最近 5 篇的 {len(used)} 条写法")

    # 12 过渡钩子
    hooks = len(re.findall(r"(好家伙|说实话|但真正|小编带着|不过话说|这里有个)", raw))
    if hooks >= 1:
        r.ok("过渡钩子", f"检测到 {hooks} 处过渡句（人工确认非模板复用）")
    else:
        r.warn("过渡钩子", "未检测到过渡句")

    return r


def main():
    ap = argparse.ArgumentParser(description="发布前自检")
    ap.add_argument("file", help="稿件 markdown 路径")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"找不到文件：{path}", file=sys.stderr)
        return 2

    rep = check(path)
    if args.json:
        print(json.dumps({"file": str(path), "items": rep.items}, ensure_ascii=False, indent=2))
    else:
        print(f"自检报告：{path.name}")
        print("=" * 56)
        print(rep.render())
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
