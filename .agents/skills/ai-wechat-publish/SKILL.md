---
name: ai-wechat-publish
description: "把公众号稿件渲染并推送到微信公众号草稿箱。当用户说'发布草稿箱''推送到草稿箱''发布''渲染'时使用。不用于写稿、排版内容层（走 ai-article-formatter）。"
---

# 微信草稿箱发布链路

**默认走一条命令，不要手工分步执行**（手工 8 步会烧掉大量词元，且容易漏步骤）。

## 一、一键发布（主路径）

```bash
python3 tools/wx_publish.py formatted/<稿件>-排版稿.md --tag <封面标签>
```

脚本内部按顺序做完 9 件事，输出压缩到 10 行以内：

| # | 动作 | 失败即中止 |
|---|---|---|
| ① | `preflight.py` 自检 | ✅ 退出码非 0 直接退出，不许绕过 |
| ② | 渲染 HTML | 调 `$MD2WX` 指定的渲染器（见下方「可配置路径」） |
| ③ | PIL 自画封面 900×383 | 标题自动折行 + 字号自适应 |
| ④ | 字符级核验（中文/字母数字/emoji 三段序列） | 不一致即中止 |
| ⑤ | 取 access_token | 40164/40125 带人话提示 |
| ⑥ | 上传封面（thumb）+ 配图（image），替换为永久 URL | 校验本地路径零残留 |
| ⑦ | 推送草稿（`articles` 数组） | — |
| ⑦b | 若带 `--replace`，新草稿上手后删旧稿 | 先推后删，中途失败不丢稿 |
| ⑧ | 回查草稿箱确认 | 打印标题/图数/残留数 |
| ⑨ | 追加每日发布日志 | `$PUBLISH_LOG_DIR/YYYY-MM-DD.md` |

**常用参数**

| 参数 | 用途 |
|---|---|
| `--dry-run` | 只跑 ①②③④，不联网、不推送。改版式后先跑这个 |
| `--replace <media_id>` | 重推同一篇，避免留下重复草稿 |
| `--tag 论文深度解读` | 封面左上角标签（默认「深度解读」） |
| `--title` / `--digest` | 覆盖标题 / 摘要（默认取 md 第一行与【导语】） |
| `--no-log` | 跳过日志 |

成功后**告知用户去后台确认并手动点「发布」**（个人订阅号无群发权限，`48001` 属正常）。

## 二、前置条件（缺一不可）

- `python3 tools/preflight.py <稿件>` **退出码 0**（脚本已内置，手工跑只为单独确认）
- `$WX_ENV_FILE` 指定的文件里有 `WX_APPID` / `WX_APPSECRET`｜**绝不写进技能文件、绝不回显**（默认路径见脚本顶部）
- 出口 IP 在微信后台白名单里（IP 会轮换，一次多留几个）

| 项 | 值 |
|---|---|
| 封面尺寸 | 900×383 |
| 视觉主线 | 冷灰科技蓝 **#3D5A80** |
| 封面字体 | 由 `tools/wx_publish.py` 顶部 `FONT_BOLD` 指定（macOS 默认 STHeiti） |

**可配置路径**（用环境变量覆盖，不用改代码；默认值只是作者本机约定）

| 环境变量 | 作用 | 默认 |
|---|---|---|
| `MD2WX` | markdown → 微信 HTML 的渲染脚本 | 见 `tools/wx_publish.py` 顶部 |
| `WXPYTHON` | 渲染器用的 python | 当前解释器 |
| `WX_ENV_FILE` | 存放 `WX_APPID` / `WX_APPSECRET` 的文件 | 见 `tools/wx_publish.py` 顶部 |
| `PUBLISH_LOG_DIR` | 发布日志目录 | 见 `tools/wx_publish.py` 顶部 |

> 渲染器是**外部依赖**，本技能不附带、不重建、不另存副本。
> 没有渲染器时，纯文本流程（写作 → 排版 → 自检）不受影响。

## 三、错误码速查

| 码 | 含义 | 解决 |
|---|---|---|
| `40164` | IP 不在白名单 | 提取报错里的 IP 去后台加白。**换 secret 无用** |
| `40125` | AppSecret 失效 | 请用户给新值；可能一次给多个候选，逐个回测 |
| `40001` | token 过期 | 重取（7200 秒有效） |
| `44003` | empty news data | 检查 payload 是否包了 `articles: [...]` |
| `48001` | 无群发权限 | 推草稿即可，**别再试第二次** |

⚠️ **`draft/add` 成功时不返回 `errcode`**，直接返回 `{"media_id": ..., "item": [...]}`。
判断成功要用 `'media_id' in resp`，写成 `errcode == 0` 会把成功误报成失败。

## 四、手工兜底（仅当脚本报错要排查时）

```bash
# 1 渲染（$WXPYTHON / $MD2WX 见上表）
"$WXPYTHON" "$MD2WX" "outputs/xx.md" "outputs/xx.html"
# 2 取 token（不要回显）
set -a; . "$WX_ENV_FILE"; set +a
curl -s --max-time 15 "https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=$WX_APPID&secret=$WX_APPSECRET"
# 3 上传素材（正文图 type=image，封面 type=thumb，两者不同）
curl -s -X POST "https://api.weixin.qq.com/cgi-bin/material/add_material?access_token=${TOKEN}&type=image" -F media="@path.png"
# 4 推草稿
curl -s -X POST -H "Content-Type: application/json" --data-binary @payload.json \
  "https://api.weixin.qq.com/cgi-bin/draft/add?access_token=${TOKEN}"
```

**必须用 curl**，不要用 python urllib/requests 直连微信 API（本机系统 Python 的 SSL 链连 `api.weixin.qq.com` 必挂）。

## 五、改排版 = 只改样式不改字（硬规矩）

任何"重新排版"都要做字符级核验：md 剥标记后与 HTML 去标签后的纯文本比对，**中文字符、字母数字、emoji 三段序列必须完全一致**（脚本 ④ 已内置）。

三个已知**假阳性**，按此处理：

1. HTML 侧**先把 `<br>` 还原成换行再剥标签**，否则连续两行会被并成一个 token
2. md 侧**先剥掉 YAML frontmatter**——渲染器自带 `strip_frontmatter`，核验不剥会凭空多出 `title:` 那行
3. **加图后**要同时剥 md 侧 `![...](...)` 与 HTML 侧 `<img>`

## 六、推送完成后（必做）

1. **每日日志**：`$PUBLISH_LOG_DIR/YYYY-MM-DD.md`（脚本 ⑨ 自动写）
2. **工作区记忆**：出现新情况（IP 拦截、secret 变化）→ 更新你的记忆文件
3. **联动**：账号数据更新 → 同步 `account-status.md`；发完一篇 → `module-log.md` 追加一行（脚本不代劳，写作环节已登记）

## 七、防坑清单（都是踩过的）

- **`find` 扫大目录会被超时杀掉**（exit 137）导致"找不到文件"的误判 → 用 `ls` 直接看
- **`/tmp` 会被系统清理** → 封面等产物落到 `outputs/`（脚本已这么做）
- token / 封面上传 / 草稿推送**三步独立**，不要 `&&` 串联
- 渲染器 **禁止重建、禁止另存到 outputs/**——它是外部依赖，不随本仓库分发
- 封面装饰元素（如右侧竖条）与标题**留安全距离**，否则会压到字上
