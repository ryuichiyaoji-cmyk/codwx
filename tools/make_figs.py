#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配图模板生成器（冷灰科技蓝 #3D5A80 统一风格）

4 类版式固化成模板，写稿时只给数据，不用每次现写 matplotlib。
输出 1080px 宽 PNG，可直接被 md2wx 渲染并随稿推送。

用法：
    python3 tools/make_figs.py 信息 -t "论文基本信息" -s "来源：arXiv" -o assets/a.png \
        -k "标题::DeepSeek Elastic Compute（DSec）" -k "分类::cs.DC 分布式计算"

    python3 tools/make_figs.py 对照 -t "同一天，两种手段" -s "2026-09-21" -o assets/b.png \
        -c "加州::州长纽森::签 7 项法案::改规则::成本自己承担" \
        -c "得州::州长阿博特::停发许可::关闸门::审计没完先不开工"

    python3 tools/make_figs.py 清单 -t "Agent 作弊与事故" -s "来源：论文第 6 节" -o assets/c.png \
        -i "覆盖 /bin/bash::把命令注入后续 shell 会话"

    python3 tools/make_figs.py 柱状 -t "镜像读取比例" -s "来源：论文 Table 3" -o assets/d.png \
        -d "Go:13.3:4.1GB" -d "Java:9.2:12.1GB" --unit "%"

字段分隔符统一用 :: （对照/清单的列内用 :: 分隔，最多 5 / 3 段）
"""
import argparse, os, sys

BLUE, DARK, GREY, LIGHT, WHITE, ACCENT, GREEN = (
    (61, 90, 128), (34, 48, 60), (122, 135, 148),
    (244, 246, 248), (255, 255, 255), (224, 122, 95), (91, 140, 90))
HEX = {"BLUE": "#3D5A80", "DARK": "#22303C", "GREY": "#7A8794", "LIGHT": "#F4F6F8",
       "WHITE": "#FFFFFF", "ACCENT": "#E07A5F", "GREEN": "#5B8C5A"}
FONT_BOLD = "/System/Library/Fonts/STHeiti Medium.ttc"
FONT_REG = "/System/Library/Fonts/Hiragino Sans GB.ttc"
FONT_LAT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    return plt, fm


def split(s, n, pad=""):
    """把 "a::b::c" 拆成 n 段，不足补 pad"""
    parts = [x.strip() for x in s.split("::")]
    return (parts + [pad] * n)[:n]


class Fig:
    def __init__(self, w, h, title, sub=None):
        plt, fm = _plt()
        self.plt = plt
        self.F_BOLD = fm.FontProperties(fname=FONT_BOLD)
        self.F_REG = fm.FontProperties(fname=FONT_REG)
        self.F_LAT = fm.FontProperties(fname=FONT_LAT)
        self.fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
        self.ax = self.fig.add_axes([0, 0, 1, 1]); self.ax.axis("off")
        self.ax.set_xlim(0, w); self.ax.set_ylim(0, h)
        self.ax.add_patch(self.plt.Rectangle((0, 0), w, h, color=HEX["LIGHT"], zorder=0))
        self.ax.text(56, h - 62, title, fontproperties=self.F_BOLD, fontsize=23,
                     color=HEX["DARK"], va="center")
        self.ax.add_patch(self.plt.Rectangle((56, h - 88), 74, 5, color=HEX["BLUE"], zorder=2))
        if sub:
            self.ax.text(56, h - 116, sub, fontproperties=self.F_REG, fontsize=13,
                         color=HEX["GREY"], va="center")
        self.w, self.h = w, h

    def card(self, x, y, w, h, edge=None):
        self.ax.add_patch(self.plt.matplotlib.patches.FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0,rounding_size=14", linewidth=1.4,
            edgecolor=edge or "#E1E6EB", facecolor=HEX["WHITE"], zorder=1))

    def save(self, out):
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        self.fig.savefig(out, facecolor=HEX["LIGHT"]); self.plt.close(self.fig)
        return out


def fig_info(title, sub, rows, out):
    h = 250 + len(rows) * 66
    f = Fig(1080, h, title, sub)
    top = h - 176
    for i, (k, v) in enumerate(rows):
        y = top - i * 66
        f.card(56, y - 50, 968, 54, edge="#E8EDF2")
        f.ax.text(92, y - 23, k, fontproperties=f.F_BOLD, fontsize=15, color=HEX["BLUE"], va="center")
        f.ax.text(300, y - 23, v, fontproperties=f.F_REG, fontsize=17, color=HEX["DARK"], va="center")
    return f.save(out)


def fig_compare(title, sub, cols, out):
    n = len(cols)
    cw = int((968 - (n - 1) * 22) / n)
    h = 560
    f = Fig(1080, h, title, sub)
    palette = [HEX["BLUE"], HEX["ACCENT"], HEX["GREEN"], "#7A6C9B"]
    for i, c in enumerate(cols):
        head, sec, mid, tag, note = split(c, 5)
        col = palette[i % 4]
        x = 56 + i * (cw + 22); y = 92; ch = 336
        f.card(x, y, cw, ch, edge=col)
        f.ax.text(x + 26, y + ch - 44, head, fontproperties=f.F_BOLD, fontsize=25, color=col, va="center")
        if sec:
            f.ax.text(x + 26, y + ch - 88, sec, fontproperties=f.F_REG, fontsize=13.5,
                      color=HEX["GREY"], va="center")
        if mid:
            f.ax.text(x + 26, y + ch - 150, mid, fontproperties=f.F_BOLD, fontsize=17,
                      color=HEX["DARK"], va="center")
        if tag:
            tw = min(cw - 60, 132)
            f.ax.add_patch(f.plt.matplotlib.patches.FancyBboxPatch(
                (x + 26, y + 56), tw, 50, boxstyle="round,pad=0,rounding_size=12",
                linewidth=0, facecolor=col, zorder=3))
            f.ax.text(x + 26 + tw / 2, y + 81, tag, fontproperties=f.F_BOLD, fontsize=18,
                      color=HEX["WHITE"], va="center", ha="center", zorder=4)
        if note:
            f.ax.text(x + 26, y + 30, note, fontproperties=f.F_REG, fontsize=12.5,
                      color=HEX["GREY"], va="center")
    return f.save(out)


def fig_list(title, sub, items, out, numbered=True):
    h = 180 + len(items) * 92 + 20
    f = Fig(1080, h, title, sub)
    top = h - 176
    for i, it in enumerate(items):
        left, main, right = split(it, 3)
        y = top - i * 92
        f.card(56, y - 74, 968, 78, edge="#E8EDF2")
        if numbered:
            # 编号式：两段 = 主文本::副说明（左段字段在编号式里不参与）
            main, right = split(it, 2)
            tm = main
            f.ax.add_patch(f.plt.matplotlib.patches.FancyBboxPatch(
                (76, y - 40), 30, 30, boxstyle="round,pad=0,rounding_size=8",
                linewidth=0, facecolor=HEX["BLUE"] if i < len(items) / 2 else HEX["ACCENT"], zorder=3))
            f.ax.text(91, y - 25, str(i + 1), fontproperties=f.F_LAT, fontsize=14,
                      color=HEX["WHITE"], ha="center", va="center", zorder=4)
            f.ax.text(132, y - 25, tm, fontproperties=f.F_BOLD, fontsize=17, color=HEX["DARK"], va="center")
            if right:
                f.ax.text(132, y - 58, right, fontproperties=f.F_REG, fontsize=13.5,
                          color=HEX["GREY"], va="center")
        else:
            f.ax.text(86, y - 25, left, fontproperties=f.F_LAT, fontsize=17, color=HEX["BLUE"], va="center")
            f.ax.text(232, y - 25, main, fontproperties=f.F_BOLD, fontsize=16, color=HEX["DARK"], va="center")
            if right:
                f.ax.text(452, y - 25, right, fontproperties=f.F_LAT, fontsize=12, color=HEX["GREY"], va="center")
    return f.save(out)


def fig_bar(title, sub, data, out, unit="", baseline_label="", highlight_below=None):
    h = 620
    f = Fig(1080, h, title, sub)
    ax2 = f.fig.add_axes([0.07, 0.16, 0.88, 0.56]); ax2.axis("off")
    ax2.set_xlim(0, 10); ax2.set_ylim(0, 10)
    vals = [d[1] for d in data]
    mx = max(vals) or 1
    step = 10 / max(len(data), 1)
    for i, (label, val, note) in enumerate(data):
        x = 0.4 + i * step
        bw = step * 0.62
        hgt = val / (mx * 1.25) * 8.2
        col = HEX["ACCENT"] if (highlight_below is not None and val < highlight_below) else HEX["BLUE"]
        ax2.add_patch(f.plt.Rectangle((x, 0.7), bw, hgt, facecolor=col, zorder=2))
        ax2.text(x + bw / 2, 0.7 + hgt + 0.4, f"{val}{unit}", fontsize=18, color=HEX["DARK"],
                 ha="center", fontproperties=f.F_BOLD, zorder=3)
        lab = label + (f"  {note}" if note else "")
        ax2.text(x + bw / 2, 0.16, lab, fontsize=11.5, color=HEX["GREY"], ha="center",
                 fontproperties=f.F_LAT)
    if baseline_label:
        ax2.text(0.4, 9.6, baseline_label, fontsize=13, color=HEX["GREY"], fontproperties=f.F_REG)
    return f.save(out)


def main():
    ap = argparse.ArgumentParser(description="配图模板生成器（冷灰科技蓝统一风格）")
    ap.add_argument("type", choices=["信息", "对照", "清单", "条目", "柱状"], help="版式类型")
    ap.add_argument("-t", "--title", required=True)
    ap.add_argument("-s", "--sub", default=None, help="副标题/来源行")
    ap.add_argument("-o", "--out", required=True, help="输出 png 路径")
    ap.add_argument("-k", "--kv", action="append", default=[], help="信息：键::值")
    ap.add_argument("-c", "--col", action="append", default=[], help="对照：头::副::主体::标签::备注")
    ap.add_argument("-i", "--item", action="append", default=[], help="清单：左::主::右")
    ap.add_argument("-d", "--data", action="append", default=[], help="柱状：标签:值:副标签")
    ap.add_argument("--unit", default="", help="柱状单位，如 %%")
    ap.add_argument("--baseline-label", default="", help="柱状左侧说明")
    ap.add_argument("--highlight-below", type=float, default=None,
                    help="柱状：低于该值的柱子用橙色标出（不传则全部蓝色）")
    a = ap.parse_args()

    if a.type == "信息":
        if not a.kv: sys.exit("信息卡至少一个 -k")
        rows = [split(k, 2) for k in a.kv]
        out = fig_info(a.title, a.sub, rows, a.out)
    elif a.type == "对照":
        if len(a.col) < 2: sys.exit("对照至少两个 -c")
        out = fig_compare(a.title, a.sub, a.col, a.out)
    elif a.type == "清单":
        if not a.item: sys.exit("清单至少一个 -i")
        out = fig_list(a.title, a.sub, a.item, a.out, numbered=True)
    elif a.type == "条目":
        if not a.item: sys.exit("条目至少一个 -i")
        out = fig_list(a.title, a.sub, a.item, a.out, numbered=False)
    else:
        if not a.data: sys.exit("柱状至少一个 -d")
        data = []
        for d in a.data:
            parts = [x.strip() for x in d.split(":")]
            label = parts[0]; val = float(parts[1]); note = parts[2] if len(parts) > 2 else ""
            data.append((label, val, note))
        out = fig_bar(a.title, a.sub, data, a.out, a.unit, a.baseline_label, a.highlight_below)

    from PIL import Image
    w, h = Image.open(out).size
    print(f"✅ {a.type} → {out}（{w}×{h}）")


if __name__ == "__main__":
    main()
