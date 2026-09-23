#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公众号一键发布（渲染 → 封面 → 配图 → 推草稿箱）

把 ai-wechat-publish 的 6 个手工步骤固化成一条命令，输出压缩到 10 行以内。

用法：
    python3 tools/wx_publish.py formatted/xxx-排版稿.md
    python3 tools/wx_publish.py formatted/xxx-排版稿.md --tag 论文深度解读
    python3 tools/wx_publish.py formatted/xxx-排版稿.md --dry-run     # 只跑本地三步，不联网
    python3 tools/wx_publish.py formatted/xxx-排版稿.md --replace <旧草稿media_id>

前置：~/.workbuddy/.env 里有 WX_APPID / WX_APPSECRET（不打印、不回显）
退出码：0 = 草稿已成功推送（或 dry-run 通过）；非 0 = 卡在某一步
"""
import argparse, html as ihtml, json, os, re, subprocess, sys, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WXPY = Path.home() / ".workbuddy/binaries/python/versions/3.13.12/bin/python3"
MD2WX = Path.home() / ".workbuddy/skills/ai-news-xiaobian/md2wx.py"
ENV = Path.home() / ".workbuddy/.env"
MEM = Path.home() / ".workbuddy/memory"
FONT_BOLD = "/System/Library/Fonts/STHeiti Medium.ttc"
BLUE, DARK, GREY, LIGHT, WHITE = (61,90,128),(34,48,60),(122,135,148),(244,246,248),(255,255,255)
API = "https://api.weixin.qq.com/cgi-bin"


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


# ---------- 解析 md ----------
def parse(md_text):
    title = next((l.strip() for l in md_text.splitlines() if l.strip()), "")
    title = re.sub(r"^#+\s*", "", title).strip()
    imgs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md_text)
    return title, imgs


def char_check(md_text, html_text):
    m = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md_text)
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
    d.text((54, 318), "本号", font=f_brand, fill=BLUE)
    d.text((168, 320), "｜ AI 领域资讯与实测", font=f_brand, fill=GREY)
    img.save(out)
    return len(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("--title", default=None, help="覆盖标题（默认取 md 第一行）")
    ap.add_argument("--tag", default="深度解读", help="封面左上角标签")
    ap.add_argument("--digest", default=None, help="摘要，默认取导语")
    ap.add_argument("--dry-run", action="store_true", help="只跑本地三步，不联网")
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

    # --- 1. 渲染 ---
    md_copy = outdir / f"{slug}.md"; html_out = outdir / f"{slug}.html"
    md_copy.write_text(md_text, encoding="utf-8")
    r = sh([str(WXPY), str(MD2WX), str(md_copy), str(html_out)])
    if r.returncode != 0 or not html_out.exists(): die(f"md2wx 渲染失败：{r.stdout[-200:]}{r.stderr[-200:]}")
    print(f"② 渲染 ✅ {html_out.name}（{len(html_out.read_text(encoding='utf-8'))} 字符）")

    # --- 2. 封面 ---
    cover = outdir / f"cover_{slug}.png"
    nlines = make_cover(title, cover, a.tag)
    print(f"③ 封面 ✅ {cover.name}（900×383，{nlines} 行标题）")

    # --- 3. 字符级核验 ---
    html_text = html_out.read_text(encoding="utf-8")
    print(f"④ 字符核验 ✅ {char_check(md_text, html_text)}")

    if a.dry_run:
        print("\n🧪 dry-run 完成（本地三步全过，未联网、未推送）")
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

    # --- 5. 上传封面 + 配图 ---
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
                             "digest": digest, "author": "本号", "content_source_url": "",
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
                     f"- 稿件：`{src}`\n- 渲染：`{html_out}`｜封面：`{cover}`（配图 {n} 张）\n"
                     f"- 草稿 media_id：`{mid}`\n- 状态：✅ 已推草稿箱，**待用户在后台手动发布**\n\n")
        print(f"⑨ 日志 ✅ {f}")

    print(f"\n🎉 完成。去公众号后台确认排版与封面，然后手动点「发布」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
