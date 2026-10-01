---
name: ai-wechat-publish
description: "把公众号稿件渲染并推送到微信公众号草稿箱。当用户说'发布草稿箱''推送到草稿箱''发布''渲染'时使用。不用于写稿、排版内容层（走 ai-article-formatter）。"
---

# 微信草稿箱发布链路（V7.0）

## 一、一键发布（主路径）

```bash
python3 tools/wx_publish.py formatted/xx-排版稿.md --form 资讯 --tag 深度解读
```

常用参数：

| 参数 | 用途 |
|---|---|
| `--form 实测/教程/资讯/批判` | **必填**。发布总闸第 5 步要求的形态标注 |
| `--dry-run` | 跑 preflight + 发布总闸 + 本地渲染，不联网、不推送 |
| `--replace <media_id>` | 确认是同一篇旧稿时重推，避免留下重复草稿 |
| `--tag 深度解读` | 封面左上角标签（与 `--form` 不同） |
| `--account-status <path>` | 覆盖账号状态块路径 |
| `--perf-log <path>` | 覆盖发布流水账路径 |
| `--no-log` | 跳过每日日志（`perf-log.md` 仍会自动追加） |

脚本顺序：
```
preflight → publish_gate（账号健康度四查 + 形态配比）
→ 渲染 → 封面 → 字符级核验
→ 取 token → 草稿箱体检（draft/batchget）
→ 上传封面 + 配图 → draft/add → 回查 → 日志 / perf-log
```

## 二、发布总闸（推送前必过，缺一不推）

1. `tools/preflight.py` 退出码 0，粘贴原始输出
2. 四条低创作度自检都能答出“这篇凭什么不属于这一类”
3. 草稿箱体检：`draft/batchget` 查同主题并存与外来稿
4. 账号健康度四查无 🔴
5. 形态标注：本篇是**实测 / 教程 / 资讯 / 批判**哪一型，并对照最近 6–8 篇配比

`tools/publish_gate.py` 会自动检查第 4、5 步，并对草稿箱同标题稿做拦截：

```bash
python3 tools/publish_gate.py formatted/xx.md --form 资讯
```

### 账号健康度四查

| # | 查什么 | 看哪里 | 判据 |
|---|---|---|---|
| ① | 账号检测 | 后台“账号检测”页 | 第 5 项“符合内容推荐条件”是否异常 |
| ② | 产出结构 | `account-status.md` + `perf-log.md` | 本流程加工稿 vs 直发稿；直发占比越高风险越大 |
| ③ | 断更时长 | 最近成稿日期 / `perf-log.md` | 恢复期距今 > 2 天 = 🔴 |
| ④ | 形态配比 | `perf-log.md` 最近 6–8 篇 | 实测 / 教程应占多数；连续 3 篇资讯 / 批判 = 🔴 |

## 三、草稿箱体检（推送前必做）

脚本会：

1. 调 `draft/batchget` 列出最近草稿
2. 拦截**同标题**草稿；确认是旧稿时用 `--replace <media_id>` 先推后删
3. 打印所有草稿的标题与 media_id，交付时明确：

> **本次只发 `<标题>`（media_id=...）；草稿箱其他条目只做辨认，不要顺手发布。**

⚠️ 草稿箱是公用出口。同一个账号可能并存“加工发法”和“直发发法”的稿子；直发稿也计入账号画像。

## 四、前置条件

- `python3 tools/preflight.py <稿件>` 退出码 0
- `python3 tools/publish_gate.py <稿件> --form <形态>` 退出码 0
- `$WX_ENV_FILE` 里有 `WX_APPID` / `WX_APPSECRET`；**绝不写进技能文件、绝不回显**
- 出口 IP 在微信后台白名单里（IP 会轮换，一次多留几个）
- `tail.md`（或 `WX_TAIL` 指向的文件）已配置固定话题标签
- 排版稿 YAML frontmatter 里有 `form:` 与 `tags:`，且 `form` 与命令 `--form` 一致

| 项 | 值 |
|---|---|
| 封面尺寸 | 900×383 |
| 视觉主线 | 由 md2wx 主题决定；不在此技能写死 |
| 封面字体 | 由 `tools/wx_publish.py` 顶部 `FONT_BOLD` 指定 |
| 文章形态 | `--form` 必填，四选一 |

## 五、发布后必做

1. `perf-log.md` 自动追加一行：日期 / 形态 / 标题 / media_id / 回填状态
2. 24–48h 后回填阅读、涨粉、搜索来源占比
3. 有账号数据更新，同步 `account-status.md`
4. 发完一篇，在 `module-log.md` 追加小标题与切入角度

## 六、错误码速查

| 码 | 含义 | 解决 |
|---|---|---|
| `40164` | IP 不在白名单 | 提取报错里的 IP 去后台加白，换 secret 无用 |
| `40125` | AppSecret 失效 | 请用户给新值，逐个回测 |
| `40001` | token 过期 | 重取（7200 秒有效） |
| `44003` | empty news data | 检查 payload 是否包了 `articles: [...]` |
| `48001` | 无群发权限 | 推草稿即可，别再试第二次 |

⚠️ **`draft/add` 成功时不返回 `errcode`**，直接返回 `{"media_id": ..., "item": [...]}`。
判断成功要用 `'media_id' in resp`。

## 七、防坑清单

- token / 封面上传 / 草稿推送三步独立，不要 `&&` 串联
- 必须用 curl；不要用 Python urllib / requests 直连微信 API
- 多张正文图逐张上传，失败时能定位到具体文件
- 本地路径残留必须为 0；CDN 图数必须等于配图数
- 草稿推送成功后回查标题、图数和本地残留
- 改排版 = 只改样式不改字；字符级核验不通过不推
- 字符核验会额外渲染一份 `--no-tail` HTML 再比对；外置尾部由正式渲染单独注入
- 不要把 `## 排版交接单` 留在排版稿里，否则会干扰渲染与核验
