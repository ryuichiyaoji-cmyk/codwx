#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公众号一键发布（渲染 → 封面 → 配图 → 推草稿箱）

把发布总闸、草稿箱体检与推送链路固化成一条命令。

用法：
    python3 tools/wx_publish.py formatted/xxx-排版稿.md --form 资讯
    python3 tools/wx_publish.py formatted/xxx-排版稿.md --form 资讯 --tag 论文深度解读
    python3 tools/wx_publish.py formatted/xxx-排版稿.md --form 资讯 --dry-run
    python3 tools/wx_publish.py formatted/xxx-排版稿.md --form 资讯 --replace <旧草稿media_id>

前置：~/.workbuddy/.env 里有 WX_APPID / WX_APPSECRET（不打印、不回显）
退出码：0 = 草稿已成功推送（或 dry-run 通过）；非 0 = 卡在某一步
"""
import argparse, html as ihtml, json, os, re, subprocess, sys, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 四个本机路径都可用环境变量覆盖，默认值只是作者本机的约定。
# 换成你自己的环境时，export 这四个变量即可，不用改代码：
#   WXPYTHON        渲染器用的 python（默认：当前解释器）
#   MD2WX           markdown → 微信 HTML 的渲染脚本
#   WX_ENV_FILE     存放 WX_APPID / WX_APPSECRET 的文件
#   PUBLISH_LOG_DIR 发布日志目录
WXPY = Path(os.environ.get("WXPYTHON", sys.executable))
MD2WX = Path(os.environ.get("MD2WX", Path.home() / ".workbuddy/skills/ai-news-xiaobian/md2wx.py"))
ENV = Path(os.environ.get("WX_ENV_FILE", Path.home() / ".workbuddy/.env"))
MEM = Path(os.environ.get("PUBLISH_LOG_DIR", Path.home() / ".workbuddy/memory"))
# 你的公众号名称：封面署名与草稿 author 字段。留空则只在封面显示栏目语。
# 这是唯一需要填自己号名的地方，用环境变量给，不写进代码。
ACCOUNT_NAME = os.environ.get("ACCOUNT_NAME", "")
FONT_BOLD = "/System/Library/Fonts/STHeiti Medium.ttc"
BLUE, DARK, GREY, LIGHT, WHITE = (61,90,128),(34,48,60),(122,135,148),(244,246,248),(255,255,255)
API = "https://api.weixin.qq.com/cgi-bin"
FORMS = ("实测", "教程", "资讯", "批判")
PERF_HEADER = ("| 日期 | 形态 | 标题 | media_id | 发布状态 | 24h 阅读 | 48h 阅读 | 新增关注 | 搜一搜占比 | 回填状态 |\n"
               "|---|---|---|---|---|---|---|---|---|---|\n")


def die(msg, code=1):
    print(f"❌ {msg}", file=sys.stderr); sys.exit(code)


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def curl_json(args, data_file=None, form=None):
    """统一走 curl（系统 python 的 SSL 链对微信 API 不可用）"""
    cmd = ["curl", "-s", "--max-time", "30"] + args
    if data_file: cmd += ["--data-binary", f"@{data_file}"]
    for f in (form or []): cmd += ["-F", f]
    r = sh(cmd)
    if r.returncode != 0: die(f"curl 失败：{r.stderr[:120]}")
    try: return json.loads(r.stdout)
    except Exception: die(f"接口返回非 JSON：{r.stdout[:160]}")


def run_publish_gate(src, form, account_status, perf_log):
    r = sh([sys.executable, str(REPO / "tools/publish_gate.py"), str(src),
            "--form", form, "--account-status", str(account_status), "--perf-log", str(perf_log)])
    if r.returncode != 0:
        die("发布总闸未通过，禁止推送：\n" + r.stdout.strip()[-1800:])
    print("Ⓐ 发布总闸 ✅ 账号健康度四查 + 形态配比通过")


def draftbox_check(T, title, replace=None):
    """推送前草稿箱体检：列出现有草稿，拦截同标题重复推送。"""
    probe = Path("/tmp/wx_draft_batchget.json")
    probe.write_text(json.dumps({"offset": 0, "count": 20, "no_content": 1}), encoding="utf-8")
    res = curl_json(["-X", "POST", "-H", "Content-Type: application/json",
                     f"{API}/draft/batchget?access_token={T}", "--data-binary", f"@{probe}"])
    if res.get("errcode") not in (None, 0):
        die(f"草稿箱体检失败：{json.dumps(res, ensure_ascii=False)[:220]}")
    items = res.get("item") or []
    total = res.get("total_count", len(items))
    print(f"Ⓑ 草稿箱体检 ✅ 共 {total} 条，列出最近 {len(items[:20])} 条")
    matches = []
    for i, it in enumerate(items[:20], 1):
        news = (it.get("news_item") or [{}])[0]
        item_title = news.get("title", "")
        upd = it.get("update_time") or news.get("update_time") or ""
        stamp = ""
        if upd:
            try: stamp = datetime.datetime.fromtimestamp(int(upd)).strftime("%m-%d %H:%M")
            except Exception: stamp = str(upd)
        print(f"   {i}. [{stamp}] {item_title}｜{it.get('media_id', '')}")
        if item_title.strip() == title.strip():
            matches.append(it.get("media_id", ""))
    if matches:
        if replace and matches == [replace]:
            print("   ⚠️  已发现同标题旧草稿；已授权用 --replace 先推后删")
        else:
            die("草稿箱已有同标题草稿：" + "、".join(matches) +
                "；确认是同一篇旧稿时用 --replace <media_id> 重推，避免留下重复草稿")
    print("   ⚠️  只发布本次 media_id；其它条目只做辨认，不要顺手发布")


def append_perf_log(path, form, title, mid):
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 发布流水账\n\n" + PERF_HEADER, encoding="utf-8")
    elif "| 日期 | 形态 |" not in path.read_text(encoding="utf-8", errors="ignore"):
        with path.open("a", encoding="utf-8") as fh:
            fh.write("\n" + PERF_HEADER)
    row = (f"| {datetime.date.today().isoformat()} | {form} | {title} | {mid} | "
           "待后台手动发布 |  |  |  |  | 待 24–48h 回填 |\n")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(row)


# ---------- 解析 md ----------
def strip_frontmatter(text):
    return re.sub(r"^\s*---\s*\n.*?\n---\s*\n?", "", text, count=1, flags=re.S)


def parse(md_text):
    md_text = strip_frontmatter(md_text)
    title = next((l.strip() for l in md_text.splitlines() if l.strip()), "")
    title = re.sub(r"^#+\s*", "", title).strip()
    imgs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md_text)
    return title, imgs


def char_check(md_text, html_text):
    m = strip_frontmatter(md_text)
    m = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", m)
    m = re.sub(r"[#*`\[\]()>]", "", m)
    h = re.sub(r"<br\s*/?>", "\n", html_text)
    h = re.sub(r"<img[^>]*>", "", h)
    h = ihtml.unescape(re.sub(r"<[^>]+>", "", h))
    for name, pat in [("中文", r"[\u4e00-\u9fff]"), ("字母数字", r"[A-Za-z0-9]"),
                      ("emoji", r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2b00-\u2bff]")]:
        a, b = re.findall(pat, m), re.findall(pat, h)
        if a != b:
            i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            die(f"字符级核验失败（{name}）：位置 {i}，md={a[i:i+1]} html={b[i:i+1]}")
    return "中文/字母数字/emoji 三段一致"


# ---------- 封面 ----------
def make_cover(title, out, tag):
    from PIL import Image, ImageDraw, ImageFont
    W, H = 900, 383
    img = Image.new("RGB", (W, H), LIGHT); d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 10], fill=BLUE); d.rectangle([0, 0, 10, H], fill=BLUE)
    for i in range(3):
        x = 796 + i * 34
        d.rounded_rectangle([x, 150, x + 20, 318], radius=10, outline=(223,229,236), width=2)
    f_tag = ImageFont.truetype(FONT_BOLD, 22)
    f_brand = ImageFont.truetype(FONT_BOLD, 20)
    # 标题字号自适应 + 自动折行（中文按字宽，英文按 0.55 宽估）
    clean = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2b00-\u2bff\ufe0f]", "", title).strip()
    for size in (46, 42, 38, 34, 30):
        f = ImageFont.truetype(FONT_BOLD, size)
        lines, cur = [], ""
        for ch in clean:
            w = (size if ord(ch) > 0x2E80 else size * 0.55)
            if d.textlength(cur, font=f) + w > 700:
                lines.append(cur); cur = ch
            else:
                cur += ch
        if cur: lines.append(cur)
        if len(lines) <= 3: break
    d.rounded_rectangle([54, 46, 54 + max(150, len(tag)*22 + 34), 90], radius=22, fill=BLUE)
    d.text((76, 68), tag, font=f_tag, fill=WHITE, anchor="lm")
    y = 150 if len(lines) <= 2 else 132
    for i, ln in enumerate(lines):
        d.text((54, y + i * (size + 12)), ln, font=f, fill=DARK)
    if ACCOUNT_NAME:
        d.text((54, 318), ACCOUNT_NAME, font=f_brand, fill=BLUE)
        d.text((54 + max(90, len(ACCOUNT_NAME) * 20) + 24, 320),
               "｜ AI 领域资讯与实测", font=f_brand, fill=GREY)
    else:
        d.text((54, 318), "AI 领域资讯与实测", font=f_brand, fill=BLUE)
    img.save(out)
    return len(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("--title", default=None, help="覆盖标题（默认取 md 第一行）")
    ap.add_argument("--form", required=True, choices=FORMS, help="本篇形态：实测/教程/资讯/批判（发布总闸强制）")
    ap.add_argument("--account-status", default=str(REPO / "account-status.md"), help="账号状态块路径")
    ap.add_argument("--perf-log", default=str(REPO / "perf-log.md"), help="发布流水账路径")
    ap.add_argument("--tag", default="深度解读", help="封面左上角标签")
    ap.add_argument("--digest", default=None, help="摘要，默认取导语")
    ap.add_argument("--dry-run", action="store_true", help="跑 preflight + 发布总闸 + 本地渲染，不联网")
    ap.add_argument("--replace", default=None, help="重推时先删掉这个旧草稿 media_id")
    ap.add_argument("--no-log", action="store_true", help="不写每日发布日志")
    a = ap.parse_args()

    src = Path(a.md)
    if not src.exists(): die(f"找不到稿件：{src}")
    md_text = src.read_text(encoding="utf-8")
    title, imgs = parse(md_text)
    if a.title: title = a.title
    slug = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "-", src.stem).strip("-")[:40]
    outdir = REPO / "outputs"; outdir.mkdir(exist_ok=True)

    # --- 0. preflight（硬门槛）---
    r = sh([sys.executable, str(REPO / "tools/preflight.py"), str(src)])
    tail = r.stdout.strip().splitlines()[-2:]
    if r.returncode != 0:
        die("preflight 未通过，禁止发布：\n" + "\n".join(r.stdout.strip().splitlines()[-14:]))
    print(f"① preflight ✅ {tail[-2].split('：')[-1] if len(tail)>1 else ''}".rstrip())

    # --- 0b. 发布总闸（账号健康度四查 + 形态配比）---
    run_publish_gate(src, a.form, Path(a.account_status), Path(a.perf_log))

    # --- 1. 渲染 ---
    # 核验用一份 --no-tail 版本：外置尾部由渲染器注入，md 侧没有，
    # 直接拿带 tail 的 HTML 做字符比对会把固定引流语误报成“渲染改了字”。
    md_copy = outdir / f"{slug}.md"
    html_check = outdir / f"{slug}.check.html"
    html_out = outdir / f"{slug}.html"
    md_copy.write_text(md_text, encoding="utf-8")
    r = sh([str(WXPY), str(MD2WX), str(md_copy), str(html_check), "--no-tail"])
    if r.returncode != 0 or not html_check.exists():
        die(f"md2wx 核验渲染失败（--no-tail）：{r.stdout[-200:]}{r.stderr[-200:]}")
    r = sh([str(WXPY), str(MD2WX), str(md_copy), str(html_out)])
    if r.returncode != 0 or not html_out.exists(): die(f"md2wx 渲染失败：{r.stdout[-200:]}{r.stderr[-200:]}")
    print(f"② 渲染 ✅ {html_out.name}（{len(html_out.read_text(encoding='utf-8'))} 字符）")

    # --- 2. 封面 ---
    cover = outdir / f"cover_{slug}.png"
    nlines = make_cover(title, cover, a.tag)
    print(f"③ 封面 ✅ {cover.name}（900×383，{nlines} 行标题）")

    # --- 3. 字符级核验（对比 --no-tail 版本，尾部单独由渲染器负责）---
    html_text = html_out.read_text(encoding="utf-8")
    print(f"④ 字符核验 ✅ {char_check(md_text, html_check.read_text(encoding='utf-8'))}")

    if a.dry_run:
        print("\n🧪 dry-run 完成（preflight + 发布总闸 + 本地渲染全过，未联网、未推送）")
        print("⚠️  草稿箱体检需在正式推送时联网执行。")
        return 0

    # --- 4. 凭据 ---
    if not ENV.exists(): die(f"找不到 {ENV}")
    env = {}
    for line in ENV.read_text().splitlines():
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
        if m: env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    appid, secret = env.get("WX_APPID"), env.get("WX_APPSECRET")
    if not appid or not secret: die("WX_APPID / WX_APPSECRET 缺失")
    tok = curl_json([f"{API}/token?grant_type=client_credential&appid={appid}&secret={secret}"])
    if "access_token" not in tok:
        code = tok.get("errcode")
        hint = {40164: "出口 IP 不在白名单（先加 IP，换 secret 无用）",
                40125: "AppSecret 已重置，需要新值"}.get(code, "")
        die(f"取 token 失败 {code} {tok.get('errmsg','')} {hint}")
    T = tok["access_token"]
    print(f"⑤ token ✅（有效期 {tok.get('expires_in')} 秒）")

    # --- 5. 草稿箱体检（必须在推草稿之前）---
    draftbox_check(T, title, a.replace)

    # --- 6. 上传封面 + 配图 ---
    thumb = curl_json(["-X","POST",f"{API}/material/add_material?access_token={T}&type=thumb",
                       "-F",f"media=@{cover}"])
    if "media_id" not in thumb: die(f"封面上传失败：{json.dumps(thumb,ensure_ascii=False)[:200]}")
    n = 0
    for p in imgs:
        local = (REPO / p) if not os.path.isabs(p) else Path(p)
        if not local.exists(): die(f"配图不存在：{local}")
        up = curl_json(["-X","POST",f"{API}/material/add_material?access_token={T}&type=image",
                        "-F",f"media=@{local}"])
        if "url" not in up: die(f"配图上传失败 {local.name}：{json.dumps(up,ensure_ascii=False)[:160]}")
        html_text = html_text.replace(p, up["url"]); n += 1
    left = re.findall(r'(?:\.\./)?assets/[^"\']*', html_text)
    if left: die(f"配图路径替换后有残留：{left[:3]}")
    print(f"⑥ 素材 ✅ 封面 1 张 + 配图 {n} 张（本地路径零残留）")

    html_out.write_text(html_text, encoding="utf-8")

    # --- 6. 推草稿 ---
    digest = a.digest
    if not digest:
        m = re.search(r"【导语】(.+?)(?:\n|$)", md_text)
        digest = (m.group(1).strip() if m else md_text.strip().splitlines()[0])[:120]
    payload = {"articles": [{"title": title, "content": html_text, "thumb_media_id": thumb["media_id"],
                             "digest": digest, "author": ACCOUNT_NAME, "content_source_url": "",
                             "need_open_comment": 0, "only_fans_can_comment": 0}]}
    pf = Path("/tmp/wx_draft_payload.json"); pf.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    res = curl_json(["-X","POST","-H","Content-Type: application/json",f"{API}/draft/add?access_token={T}",
                     "--data-binary", f"@{pf}"])
    # ⚠️ 成功时微信不返回 errcode，直接给 media_id
    if "media_id" not in res:
        die(f"推草稿失败：{json.dumps(res,ensure_ascii=False)[:220]}")
    mid = res["media_id"]
    print(f"⑦ 推草稿 ✅ media_id={mid}")

    # --- 6b. 重推的收尾：新草稿上手后再删旧的（先推后删，中途失败不丢草稿）---
    if a.replace:
        df = Path("/tmp/wx_draft_del.json")
        df.write_text(json.dumps({"media_id": a.replace}), encoding="utf-8")
        d = curl_json(["-X","POST","-H","Content-Type: application/json",
                       f"{API}/draft/delete?access_token={T}","--data-binary", f"@{df}"])
        print(f"⑦b 旧草稿删除 {'✅' if d.get('errcode')==0 else '⚠️ ' + json.dumps(d,ensure_ascii=False)[:120]}")

    # --- 8. 回查 ---
    gf = Path("/tmp/wx_draft_get.json"); gf.write_text(json.dumps({"media_id": mid}), encoding="utf-8")
    ver = curl_json(["-X","POST","-H","Content-Type: application/json",f"{API}/draft/get?access_token={T}",
                     "--data-binary", f"@{gf}"])
    item = (ver.get("news_item") or [{}])[0]
    print(f"⑧ 回查 ✅ 标题「{item.get('title','')}」｜正文图 {len(re.findall('<img', item.get('content','')))} 张"
          f"｜本地残留 {len(re.findall('assets/', item.get('content','')))} 处")

    # --- 9. 日志 ---
    if not a.no_log:
        MEM.mkdir(parents=True, exist_ok=True)
        day = datetime.date.today().isoformat()
        f = MEM / f"{day}.md"
        head = "" if f.exists() else f"# {day} 发布日志\n\n"
        with f.open("a", encoding="utf-8") as fh:
            fh.write(f"{head}## {datetime.datetime.now():%H:%M} 发布 · {title}\n\n"
                     f"- 稿件：`{src}`｜形态：**{a.form}**\n"
                     f"- 渲染：`{html_out}`｜封面：`{cover}`（配图 {n} 张）\n"
                     f"- 草稿 media_id：`{mid}`\n- 状态：✅ 已推草稿箱，**待用户在后台手动发布**\n\n")
        print(f"⑨ 日志 ✅ {f}")

    # --- 10. 发布流水账（perf-log 由脚本自动追加）---
    append_perf_log(a.perf_log, a.form, title, mid)
    print(f"⑩ 流水账 ✅ {a.perf_log}（形态 {a.form}，待 24–48h 回填）")

    print(f"\n🎉 完成。本次只发这一条：\n   ✅ 可发：{title}（media_id={mid}）\n"
          f"   ⚠️ 草稿箱其它条目只做辨认，不要顺手发布。\n"
          f"   去后台确认排版与封面，再手动点「发布」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
