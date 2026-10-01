#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布总闸：账号健康度四查 + 形态配比 + 产出结构。

这是 `preflight.py` 之外的**运营侧闸门**。preflight 管稿件本身；
本脚本管“账号现在适不适合推这篇”。

用法：
    python3 tools/publish_gate.py formatted/xx-排版稿.md --form 资讯
    python3 tools/publish_gate.py formatted/xx-排版稿.md --form 教程 --json

退出码：0 = 无红灯（可能有 WARN）；1 = 有 FAIL，禁止推送草稿箱。
本脚本只读，不联网，不修改稿件。
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FORMS = ("实测", "教程", "资讯", "批判")
TAKEAWAY_FORMS = ("实测", "教程")
RISK_FORMS = ("资讯", "批判")
FORM_RE = re.compile(r"(?:形态(?:标注)?|form)\s*[:：]\s*(实测|教程|资讯|批判)(?!\s*[/／])", re.I)

BAD_STATUS = ("异常", "低创作度", "受限", "不正常", "未通过", "黄牌", "红牌")


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, item, detail=""):
        self.items.append({"level": level, "item": item, "detail": detail})

    def ok(self, item, detail=""):
        self.add("PASS", item, detail)

    def warn(self, item, detail=""):
        self.add("WARN", item, detail)

    def fail(self, item, detail=""):
        self.add("FAIL", item, detail)

    @property
    def failed(self):
        return any(x["level"] == "FAIL" for x in self.items)

    def render(self):
        icon = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}
        lines = ["发布总闸报告", "=" * 56]
        for x in self.items:
            lines.append(f"{icon[x['level']]} [{x['level']:4}] {x['item']}")
            if x["detail"]:
                lines.append("          " + x["detail"])
        n = {k: sum(1 for x in self.items if x["level"] == k) for k in ("PASS", "WARN", "FAIL")}
        lines += ["", f"合计：PASS {n['PASS']} · WARN {n['WARN']} · FAIL {n['FAIL']}"]
        lines.append("结论：" + ("❌ 有红灯，禁止推送草稿箱" if n["FAIL"] else
                                ("⚠️ 可推送，但请人工确认 WARN" if n["WARN"] else "✅ 四查通过，可进入推送")))
        return "\n".join(lines)


def field(text, key):
    m = re.search(rf"{re.escape(key)}\s*[:：]\s*(.+)", text)
    return m.group(1).strip() if m else ""


def parse_iso(value):
    m = re.search(r"\d{4}-\d{2}-\d{2}", value or "")
    if not m:
        return None
    try:
        return dt.date.fromisoformat(m.group(0))
    except ValueError:
        return None


def parse_int(value):
    m = re.search(r"\d+", value or "")
    return int(m.group(0)) if m else None


def read_status(path):
    if not path.exists():
        return None, "找不到账号状态文件"
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text, ""


def parse_perf_rows(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[0]):
            continue
        form = cells[1]
        if form not in FORMS:
            continue
        rows.append({"date": cells[0], "form": form, "title": cells[2]})
    return rows


def check(file_arg, form, status_path, perf_path, max_status_age=7, max_gap_days=2):
    r = Report()
    src = Path(file_arg)
    if not src.exists():
        r.fail("稿件文件", f"找不到：{src}")
        return r
    if form not in FORMS:
        r.fail("形态标注", f"未知形态：{form}")
    else:
        manuscript = src.read_text(encoding="utf-8", errors="ignore")
        hit = FORM_RE.search(manuscript)
        if not hit:
            r.fail("形态标注", "稿件里没有可机读的形态标注；排版稿请在 YAML frontmatter 写 form: 资讯")
        elif hit.group(1) != form:
            r.fail("形态标注", f"参数是 {form}，稿件标注是 {hit.group(1)}；两处必须一致")
        else:
            r.ok("形态标注", f"本篇形态：{form}")

    text, err = read_status(status_path)
    if text is None:
        r.fail("账号状态", err + f"：{status_path}")
        text = ""

    # ⓪ 状态块新鲜度
    status_date = parse_iso(field(text, "状态更新日期"))
    if status_date is None:
        r.fail("账号状态新鲜度", "缺少状态更新日期")
    else:
        age = (dt.date.today() - status_date).days
        (r.ok if age <= max_status_age else r.fail)(
            "账号状态新鲜度", f"更新于 {status_date}（{age} 天前）"
        )

    # ① 账号检测
    detect = field(text, "账号检测结果")
    detect_date = parse_iso(field(text, "账号检测更新日期"))
    if not detect or "待填" in detect:
        r.fail("账号健康① 账号检测", "账号检测结果未填；先更新后台账号检测快照")
    elif any(k in detect for k in BAD_STATUS):
        r.fail("账号健康① 账号检测", f"检测结果含异常信号：{detect}")
    elif detect_date is None:
        r.warn("账号健康① 账号检测", f"结果已填（{detect}）但缺更新日期")
    else:
        age = (dt.date.today() - detect_date).days
        (r.ok if age <= max_status_age else r.fail)(
            "账号健康① 账号检测",
            f"{detect}；快照 {detect_date}（{age} 天前）",
        )

    # ② 产出结构
    structure = field(text, "产出结构（近30天）") or field(text, "产出结构")
    m = re.search(r"本流程\s*(\d+)\s*篇.*?直发\s*(\d+)\s*篇", structure)
    if not structure or "待填" in structure or not m:
        r.fail("账号健康② 产出结构", "产出结构未填；格式：本流程 X 篇 / 直发 Y 篇")
    else:
        made, direct = int(m.group(1)), int(m.group(2))
        total = made + direct
        ratio = direct / total if total else 0
        if total == 0:
            r.fail("账号健康② 产出结构", "近 30 天产出为 0")
        elif direct == 0:
            r.ok("账号健康② 产出结构", f"本流程 {made} 篇 / 直发 0 篇")
        elif ratio > 0.5:
            r.warn("账号健康② 产出结构", f"直发 {direct} 篇，占比 {ratio:.0%}；账号画像风险偏高")
        else:
            r.ok("账号健康② 产出结构", f"本流程 {made} 篇 / 直发 {direct} 篇（{ratio:.0%}）")

    # ③ 断更
    rows = parse_perf_rows(perf_path)
    last_date = parse_iso(field(text, "最近一次成稿日期"))
    if not last_date and rows:
        last_date = parse_iso(rows[-1]["date"])
    gap_field = parse_int(field(text, "断更时长"))
    if last_date:
        gap = (dt.date.today() - last_date).days
        if gap > max_gap_days:
            r.fail("账号健康③ 断更", f"最近成稿 {last_date}，距今 {gap} 天（> {max_gap_days} 天）")
        else:
            r.ok("账号健康③ 断更", f"最近成稿 {last_date}，距今 {gap} 天")
    elif gap_field is not None:
        if gap_field > max_gap_days:
            r.fail("账号健康③ 断更", f"状态块记录断更 {gap_field} 天（> {max_gap_days} 天）")
        else:
            r.ok("账号健康③ 断更", f"状态块记录断更 {gap_field} 天")
    else:
        r.fail("账号健康③ 断更", "缺少最近成稿日期或断更时长")

    # ④ 形态配比
    if not rows:
        r.fail("账号健康④ 形态配比", f"读不到 {perf_path.name} 的形态记录；先建立发布流水账")
    else:
        recent = rows[-6:]
        recent3 = rows[-3:]
        take = sum(1 for x in recent if x["form"] in TAKEAWAY_FORMS)
        if len(recent3) == 3 and all(x["form"] in RISK_FORMS for x in recent3):
            r.fail("账号健康④ 形态配比", "连续 3 篇都是资讯/批判；下一篇必须先做实测或教程")
        elif len(recent) >= 6 and take / len(recent) < 0.5:
            r.warn("账号健康④ 形态配比", f"最近 {len(recent)} 篇里“能拿走”型只有 {take} 篇（<50%）")
        else:
            r.ok("账号健康④ 形态配比", f"最近 {len(recent)} 篇中实测/教程 {take} 篇")
    return r


def main():
    ap = argparse.ArgumentParser(description="发布总闸：账号健康度四查 + 形态配比")
    ap.add_argument("file", help="排版稿路径")
    ap.add_argument("--form", required=True, choices=FORMS, help="本篇形态")
    ap.add_argument("--account-status", default=str(REPO / "account-status.md"))
    ap.add_argument("--perf-log", default=str(REPO / "perf-log.md"))
    ap.add_argument("--max-status-age", type=int, default=7, help="账号检测快照最长有效期（天）")
    ap.add_argument("--max-gap-days", type=int, default=2, help="允许断更天数")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rep = check(args.file, args.form, Path(args.account_status), Path(args.perf_log),
                args.max_status_age, args.max_gap_days)
    if args.json:
        print(json.dumps({"file": args.file, "form": args.form, "items": rep.items},
                         ensure_ascii=False, indent=2))
    else:
        print(rep.render())
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
