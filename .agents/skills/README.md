# 公众号内容技能套件（V7.0 体系）

**八个技能**覆盖 选题 → 写作 → 标题 → 排版 → 发布 → 复盘。放在仓库内 `.agents/skills/`，
**提交 git 后谁 clone 谁就有同一套行为**。

> 唯一宪法见根目录 `SOUL.md`；恢复期节奏见 `恢复期作战表.md`；
> 完整介绍见根目录 `README.md`；工具参数见 `docs/工具手册.md`。

## 目录

```
.agents/skills/
├── ai-content-ops/       **总纲与统一入口**：路由 + 跨阶段红线 + 发布总闸入口
├── ai-topic-scout/       选题（三层扫描 + 低创作度四道排除 + 建议形态 + 搜索词）
├── ai-article-writer/    写作（素材状态 + 六模块 + 落地段 + 形态标注 + preflight）
├── ai-title-optimizer/   标题（关键词前置 + 8 候选双维打分）
├── ai-article-formatter/ **排版**（移动端可读性 + 小标题/加粗/配图节奏）
├── writing-voice/        **文风**（从真实语料提取风格卡；正文自称统一为“我”）
├── ai-data-analyst/      数据复盘（账号健康度四查 + 指标 + 归因 + perf-log 回填）
└── _shared/
    └── account-status.template.md   账号状态块模板（含账号健康度字段）
```

## 配套文件

| 文件 | 作用 |
|---|---|
| `SOUL.md` | **唯一宪法**：身份、红线、平台原文、账号健康度、搜索优先 |
| `恢复期作战表.md` | 四条战线、周节奏、好转信号、红线速查 |
| `docs/低创作度判例库.md` | 通用风险模式与修复动作 |
| `tools/topic_scan.py` | 选题扫描：抓源 → 聚类 → 搜索验证 → 归档 |
| `tools/draft_kit.py` | 写稿提速：`brief` / `check` / `handoff` |
| `tools/preflight.py` | 稿件机械自检：禁用词 / 结构 / 合规 / 排版 / 形态 / 口头禅 |
| `tools/publish_gate.py` | **发布总闸**：账号健康度四查 + 形态配比 + 断更检查 |
| `tools/wx_publish.py` | 渲染 → 草稿箱体检 → 推草稿箱 → 回查 → 写日志 / perf-log |
| `account-status.md` | 账号状态与账号检测快照，**已 gitignore** |
| `perf-log.md` | 发布流水账与 24–48h 回填，**已 gitignore** |
| `tail.md` | 外置文末尾部与话题标签，**已 gitignore** |

## V7.0 的四个硬约束

1. **低创作度四条优先排除**：同质化 / 抄袭搬运 / 低信息量 / 低价值 AIGC
2. **每个选题必须回答“这件事改变了什么旧规则？”**——答不出来就是纯资讯
3. **无素材不写实测**：默认分析型，禁止亲历式描述；文末声明「本文未做实测」
4. **发布总闸缺一不推**：preflight 退出码 0 + 四条自检 + 草稿箱体检 + 账号健康度四查 + 形态标注

## 正文形态

每篇必须在排版交接单标为 **实测 / 教程 / 资讯 / 批判** 四选一。
“能拿走”型（实测 / 教程）应占多数；连续 3 篇资讯 / 批判 = 🔴。

## 用法

```
今天有什么选题       → ai-topic-scout      → tools/topic_scan.py
选题3 / 写这篇       → ai-article-writer   → tools/draft_kit.py brief
起标题               → ai-title-optimizer
排版 / 准备发布      → ai-article-formatter → tools/make_figs.py
发布草稿箱           → ai-wechat-publish   → preflight + publish_gate + tools/wx_publish.py
太AI化 / 不像我写的   → writing-voice
分析这周数据         → ai-data-analyst      → account-status + perf-log
```

## 两条维护约定

1. **规则只改 `SOUL.md` 一处**；技能只改执行步骤，不重复抄红线
2. 平台规则更新时标注日期；账号数据只放本机 gitignore 文件
