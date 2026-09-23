# 内容技能套件（V6 体系）

**八个技能**覆盖 选题 → 写作 → 标题 → 排版 → 发布 → 复盘。放在仓库内 `.agents/skills/`，
**提交 git 后谁 clone 谁就有同一套行为**，改动随代码走评审。

> 完整介绍见根目录 `README.md`；技能细节见 `docs/技能手册.md`；工具参数见 `docs/工具手册.md`。

## 目录

```
.agents/skills/
├── ai-content-ops/       **总纲与统一入口**：认意图 → 路由子技能 + 跨阶段红线 + 文件地图
├── ai-topic-scout/       选题（三层扫描 + 低创作度四道排除 + 选题卡 + 优先级表）
├── ai-article-writer/    写作（素材状态判断 + 六模块结构 + preflight）
├── ai-title-optimizer/   标题（关键词前置 + 8 候选双维打分）
├── ai-article-formatter/ **排版**（移动端可读性 + 小标题/加粗/配图节奏 + 编辑器清单）
├── writing-voice/        **文风**（从用户真实语料提取风格卡；写作前必读）
├── ai-data-analyst/      数据复盘（涨粉率 + 搜一搜占比 + 基线自校准）
└── _shared/
    └── account-status.template.md   账号状态块模板
```

## 配套文件（都在仓库里）

| 文件 | 作用 |
|---|---|
| `tools/topic_scan.py` | **选题扫描一键跑**：抓源 → 自动聚类 → 搜索验证 → 归档 |
| `tools/draft_kit.py` | **写稿提速**：`brief` 情报包 / `check` 完稿体检 / `handoff` 交接单骨架 |
| `tools/make_figs.py` | **配图模板**：信息 / 对照 / 清单 / 条目 / 柱状 五类版式 |
| `tools/wx_publish.py` | **一键发布**：渲染 → 封面 → 上传素材 → 推草稿箱 → 回查 → 写日志 |
| `tools/preflight.py` | **发布前自检脚本**（**27 项**，含风格卡校验）。只读、离线、确定性，退出码 0 = 可发布 |
| `tools/search_demand.py` | **搜索需求验证**：调 Bing/Google/百度 公开建议接口，给选题的"搜索价值"打分并产出可用长尾词 |
| `tools/voice_check.py` | **文风体检 / AI 味检测**：建基线（从你的语料）或体检某篇稿，逐项对照 |
| `tools/backup.sh` | **一键备份**：提交改动 → 推送到所有远程 |
| `account-status.md` | 账号状态块，含收入数据，**已 gitignore，不要提交** |
| `module-log.md` | 小标题写法与切入顺序记录，用于**同质化去重** |
| `topic-scans/` | 每次扫描存档（含覆盖度与失败源） |
| `sources/` | 一手源存档（官方公告 PDF、官方原文要点） |

## V6 体系的四个硬约束

1. **低创作度四条是最高优先级**：同质化 / 抄袭搬运 / 低信息量 / 低价值 AIGC，命中任一即排除
2. **每个选题必须回答"这件事改变了什么旧规则？"**——答不出来就是纯资讯
3. **无素材不写实测**：默认分析型，禁止亲历式描述；有素材才升级为实测型
4. **交付前跑脚本，贴原始输出**——不用自己打的勾代替

## 六模块 = 功能固定、表达不固定

核心判断开篇 / 事件背景（≤20%）/ 分层拆解 / 行业对照 / 深层变化 / 结论。
**功能点必须全覆盖，但小标题措辞与切入顺序每篇必须不同**——篇篇同构会触发同质化判定。

## 用法

```
今天有什么选题       → ai-topic-scout      → tools/topic_scan.py
选题3 / 写这篇       → ai-article-writer   → tools/draft_kit.py brief
起标题               → ai-title-optimizer
排版 / 准备发布      → ai-article-formatter → tools/make_figs.py
发布草稿箱           → ai-wechat-publish   → tools/wx_publish.py
太AI化 / 不像我写的   → writing-voice
分析这周数据         → ai-data-analyst
```

## 两条维护约定

1. **引用的平台规则都标注日期**，各人拿到的规则版本才一致
2. 改动走 git 提交；`account-status.md` 是本机私有状态，不进仓库

## 修改技能时注意

`.agents/` 在 Codex 工作区里是**只读保护区**——改这里的文件需要用户批准一次写入权限。
