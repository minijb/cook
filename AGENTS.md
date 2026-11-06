# AGENTS.md — cook 工作区契约

> 任何 AI session 进入本工作区，**必须先读本文件**。它与 `index.py`、`.agents/skills/` 共同构成本工作区的操作系统。
> 面向人类用户的说明在 `README.md`；本文件是 Agent 的行为契约。

## 0. Session 快速开始（Agent 每次进入）

1. **读本文件**（就是现在）；
2. **环境自检**：`.venv/Scripts/python index.py check`——通过即就绪；报缺依赖先执行 §11 环境准备；ERROR 先自愈（§10）；
3. **拿到任务先检索**：`match "<任务描述>"`，只读命中内容，再动手。**禁止通读 docs/**。

## 1. 这是什么

cook 是一个 **AI 知识节点工作区**：`docs/` 下的每个文件都是一个知识节点，描述自身内容与节点间关系。工作区唯一目的——**用户与 AI agent 交流时，准确、低成本地取回对应上下文**。

交互模型：**用户只说意图，Agent 执行命令**。所有检索先走 `match` / `rels`，命中后再读内容。

**反模式（禁止）**：通读 docs/ 找答案；手改 `INDEX.json`；不查重就新建节点；把元数据写在正文里而不是 frontmatter。

## 2. 目录结构

```text
cook/
├── AGENTS.md / README.md      ← 契约（本文件）/ 面向用户的使用指南
├── index.py                   ← 唯一脚本入口（节点增删改查 + 检索 + 索引维护）
├── requirements.txt           ← 依赖（typer、rich）
├── .venv/                     ← Python 环境（已 gitignore）
├── .pi/                       ← pi 项目配置（运行时文件 .pi/tasks/ 已 gitignore）
├── .agents/skills/            ← 工作区技能（见 §8）
├── tutorials/                 ← 教程输出区（每篇带元数据 tags/project/specs，见 §4.1；不参与 docs 索引）
└── docs/                      ← 知识库（只有以下 4 个目录，全部扁平存放）
    ├── tag/                   ← 标签节点：<id>.md + INDEX.json
    ├── project/               ← 项目节点：<id>.md + INDEX.json
    ├── spec/                  ← 规范节点：SPEC-XXX.md + INDEX.json
    └── reference/             ← 参考节点：<id>.md + INDEX.json

每个目录内形如（以 tag 为例，INDEX.json 不在根目录）：

```text
docs/tag/
├── INDEX.json        ← 派生索引（rebuild 生成，禁止手改）
├── rendering.md
├── cpp.md
└── …
```
```

**docs/ 下只有上述 4 个目录**；工作区根下另有 `tutorials/`（教程输出区，不参与索引）。外部参考一律作为 reference 节点进 `docs/reference/`。

## 3. 知识节点模型

4 类节点（kind）与编址方式 `kind:id`：

| kind | 目录 | 文件名 | 是什么 |
| ---- | ---- | ---- | ---- |
| `tag` | docs/tag/ | `<id>.md` | 跨项目主题标签，含术语表；id 小写字母/数字/连字符 |
| `project` | docs/project/ | `<id>.md` | 一个项目/方向的上下文与范围 |
| `spec` | docs/spec/ | `SPEC-XXX.md` | 一种规范，**包裹术语**；编号由 `spec add` 自动分配 |
| `reference` | docs/reference/ | `<id>.md` | 外部引入的参考或额外内容（网页、文章、摘录），**扁平化**，不建子目录 |

**所有节点的共性**（frontmatter 承载）：

1. **描述自己与其它节点的关系**（如果有的话）；
2. **描述自身的内容与范围**：`title` + `desc`（一句话）+ `keywords`（检索术语）+ 正文 `## 范围` 等；
3. **网页资源索引**（tag/project 维护）：`links`（`URL|标题` 条目）+ 正文 `## 网页资源` 表，外部链接直接挂在节点上，资源标题参与 match 检索。

**两类关系边的语义分工**：

| 字段 | 语义 | 方向 | 适用 |
| ---- | ---- | ---- | ---- |
| `tags` | 「我属于这些主题」——挂靠，弱关系 | 节点 → tag | 仅非 tag 节点（tag 自身恒为空） |
| `refs` | 「我明确引用/关联它」——指向，强关系 | 节点 → 任意节点 | 所有节点，编址 `kind:id` |

反向查询不用写：`rebuild` 会为每个节点自动算出入边 `backrefs`，`rels` 一跳可查。

## 4. frontmatter 契约（元数据唯一来源）

```yaml
---
title: 渲染
kind: tag                       # 必须与所在目录一致
tags: []                        # 非 tag 节点：所属 tag 的 id 列表（tag 自身恒为空）
refs: [project:cpp-game-dev]    # 指向其它节点，kind:id 编址
keywords: [渲染, render, 管线]   # 检索术语表（match 的主要命中依据，中英文都放）
links: []                        # 网页资源索引，条目格式 "URL|标题"（tag/project 维护）
desc: 渲染主题：管线、性能与调试  # 一句话描述（参与 match 打分）
source: ""                      # 仅 reference：外部 URL 或出处
created: 2026-11-05
updated: 2026-11-05             # 由脚本在 node set 时自动刷新
---
```

正文约定：tag/project 写 `## 范围` + `## 术语表` + `## 网页资源`（标题/URL 表，与 links 对应）；spec 写 `## 规范` + `## 术语`（spec 包裹术语）；reference 写 `## 来源` + `## 要点`。

### 4.1 教程元数据（tutorials/）

tutorials/ 每篇教程必须带 frontmatter（不参与 docs 索引，但 `check` 校验指向真实节点）：

```yaml
---
title: UE5 性能剖析与帧预算
kind: tutorial
tags: [performance, ue5]     # 指向真实 tag
project: cpp-game-dev        # 可选，指向真实 project
specs: [SPEC-001]            # 可选，本教程遵守/演示的规范
created: 2026-11-04
updated: 2026-11-04
---
```

管理命令：`tut add` / `tut list` / `tut set`。

## 5. INDEX.json（派生数据）

每个目录下有一个 `INDEX.json`（即 `docs/tag/INDEX.json` 等 4 个），描述该目录全部节点的内容指纹与关系边：

```json
{
  "kind": "tag",
  "generated_at": "2026-11-05 14:00:00",
  "count": 1,
  "nodes": {
    "rendering": {
      "title": "渲染", "desc": "…", "file": "rendering.md",
      "keywords": ["渲染", "render"],
      "links": [{"url": "https://…", "title": "UE5 官方文档"}],
      "tags": [],
      "refs": ["project:cpp-game-dev"],
      "backrefs": ["spec:SPEC-001"],
      "body_head": "…",
      "hash": "a1b2c3d4e5f6"
    }
  }
}
```

- `backrefs`：谁指向它——含两类入边：`refs` 引用 + `tags` 挂靠（挂到本 tag 的节点）；`body_head`：正文前 600 字（match 用，免读文件）；`hash`：文件指纹（check 检测过期）。
- `match` / `rels` / `node list` 只读 INDEX.json，不读节点文件——这是省 token 的关键。

## 6. 硬性契约（AI 与用户都必须遵守）

1. **4 个 `INDEX.json` 只能由 `index.py` 产生和修改**，禁止手改。
2. **节点元数据只写在 frontmatter**；INDEX.json 是派生数据。
3. **绕过 index.py 直接动文件（新建/移动/删除/改 frontmatter）后，必须 `rebuild`**（`--fix` 可顺带修复 kind 错标与无效 refs）；日常操作用 `node add` / `node rm` / `node set` 即时同步。
4. **重要术语必须写进 frontmatter `keywords`**，否则 `match` 命中不了。
5. **`refs` 编址 `kind:id`，必须指向真实存在的节点**（`check` 校验）。
6. **挂主题用 `tags`**；tag 节点自身恒为空，它表达与其它节点的关系一律走 `refs`。
7. **同一概念全局只建一个节点**：id 全局唯一，新建前先 `match` / `node list` 查重；确实需要细分再拆节点并互挂 `refs`。
8. **reference 一律扁平**放 `docs/reference/`，不建子目录；一条外部来源一个节点。
9. **节点命名**：tag/project/reference id 用小写字母/数字/连字符；spec 用 `SPEC-XXX`（三位数字，自动分配，不得手改文件名）。
10. **检索一律先 `match` / `rels`**，脚本层过滤后再读命中内容。
11. **网页资源索引**：外部链接挂在 tag/project 的 `links`（`URL|标题`）与正文 `## 网页资源` 表；`ref add --tags` 自动同步进所挂 tag；`node rm` reference 时自动清理。
12. **tutorials/ 教程必须带 §4.1 元数据**，tags/project/specs 必须指向真实节点（`check` 校验）。
13. **节点正文不得保留模板占位文本**（如「（这个标签覆盖什么主题…）」「（说明；重要术语…）」「（网页资源索引：…）」）：`check` 会以 WARN 提示；手改正文后必须 `rebuild`。

## 7. 命令速查

```bash
# 环境准备（一次性；Agent 首次执行命令前自检 .venv 与依赖）
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt

# 检索与关系（Agent 最常用）
.venv/Scripts/python index.py match "UE5 渲染管线卡顿"        # 对话式检索（--json 结构化）
.venv/Scripts/python index.py match "..." --kind tag,spec     # 限定类别 --limit N 控制条数
.venv/Scripts/python index.py rels tag:rendering              # 一跳关系：refs 出边 + backrefs 入边 + tags

# 节点增删改查
.venv/Scripts/python index.py node add tag rendering --title "渲染" --desc "…"
.venv/Scripts/python index.py node list [--kind spec] [--json]
.venv/Scripts/python index.py node show tag:rendering         # 读节点全文（检索命中后才读）
.venv/Scripts/python index.py node set project:cpp --add-tag cpp \
  --add-ref spec:SPEC-001 --add-keyword "虚幻引擎"             # 改元数据/挂关系/补术语
.venv/Scripts/python index.py node set tag:cpp --rm-ref spec:SPEC-001 --rm-keyword "旧词"
.venv/Scripts/python index.py node rm tag:rendering --yes     # 删除并清理反向引用

# 规范 / 参考
.venv/Scripts/python index.py spec add 文档命名规范            # 自动编号 SPEC-XXX + 模板
.venv/Scripts/python index.py ref add nanite-paper --url "https://..." \
  --tags rendering                                             # 自动抓标题/描述；并同步进所挂 tag 的网页资源索引

# 教程（tutorials/，不参与 docs 索引）
.venv/Scripts/python index.py node set tag:rendering --add-link "https://dev.epicgames.com/...|UE5 官方文档"
.venv/Scripts/python index.py tut add ue5-gamemode-tutorial --title "…" --tags ue5 --project cpp-game-dev
.venv/Scripts/python index.py tut list
.venv/Scripts/python index.py tut set ue5-gamemode-tutorial --add-spec SPEC-001

# 维护
.venv/Scripts/python index.py init                            # 初始化骨架
.venv/Scripts/python index.py check                           # 健康检查（ERROR 需处理，见 §10）
.venv/Scripts/python index.py rebuild [--fix]                 # 重建 INDEX.json；--fix 顺带修文件元数据
```

## 8. 工作区技能（.agents/skills/）

| skill | 触发场景 |
| ---- | ---- |
| `context-build` | 对话中构建上下文：先查知识库 / 找相关节点 / 新任务开始 / "之前聊过的 X 在哪" |
| `context-align` | "对齐一下""讨论下方向""帮我确认关键决策""别猜，问我"——基于知识库证据逐轮提问，对齐方向与关键决策，结论沉淀回库 |
| `knowledge-save` | "记住这个""存到知识库""记录这条"——新建/更新任意类别节点 |
| `spec-manage` | "定个规范""新建 SPEC""修订规范" |
| `reference-add` | "搜个资料""找个参考""引入外部内容"——网络搜索后入库为 reference 节点 |

## 9. 典型工作流

- **对话检索 / 冷启动**（context-build）：`match "任务描述"` → 只读"建议先读"的节点（`node show`）→ 需要时 `rels` 顺关系边扩展 → 向用户复述共识。
- **存知识**（knowledge-save）：查重 → `node add` / `spec add` / `ref add` → **补正文（清除全部模板占位，links 与网页资源表一致）**与 `keywords` → `node set` 挂 `refs`/`tags` → `check`。
- **定规范**（spec-manage）：`spec add <标题>` → 补规范正文与术语 → `node set --add-tag/--add-ref` 挂接。
- **引参考**（reference-add）：网络搜索（agent 工具）→ `ref add <id> --url`（脚本自动抓标题/描述，并同步进所挂 tag 的网页资源索引）→ 补要点与 keywords。
- **写教程**：确定主题（挂哪个 tag/project/spec）→ `tut add <id> --tags … --project …` 生成骨架 → 撰写正文 → `check` 校验元数据指向。
- **方向对齐**（context-align）：先消解话术歧义（多解歧义→选项题 / 欠指定→补充题 / 指代不明→消解题）→ `match` 装载上下文并盘库缺口（空白/断裂/规范缺口/冲突）→ 每问先过**实质闸门**（答案不改变行动则降级为假设台账）+ 选项必须判别（殊途同归不问）→ 结论沉淀（关键决策用 MADR-lite 决策记录，含被否选项）→ `check`。
- **健康自愈**：`check` → 按下表处理 → 复检 → 汇报。**Agent 在每次结构性变更后应主动自检并回报证据**（路径、check 结果、git diff 摘要）；变更落定后建议 git commit（不确定时先问用户）。

## 10. check 结果解读与处置

| 输出 | 级别 | 处置 |
| ---- | ---- | ---- |
| `INDEX.json 过期` | WARN | `rebuild` 同步 |
| `keywords 为空` | WARN | `node set --add-keyword` 补术语 |
| `reference 缺少 source` | WARN | `node set --source <URL>` |
| `tag 节点自身不应有 tags` | WARN | `rebuild --fix` 自动清空 |
| `refs/tags 指向不存在的节点` | ERROR | 补建目标节点，或 `node set --rm-ref/--rm-tag`，然后 `rebuild` |
| `kind 与目录不一致` / `缺少 frontmatter` / 文件名不合规 | ERROR | 手工修复文件后 `rebuild --fix` |
| `INDEX.json 缺失` / 目录缺失 | ERROR | `init` + `rebuild` |
| 教程 `tags/project/specs 指向不存在的节点` | ERROR | `tut set` 修正指向 |
| 正文仍是模板占位（未完成） | WARN | 补写范围/术语/要点/网页资源表，完成后 `rebuild` |
| `缺少章节`（节点必需章节或教程核心章节） | WARN | 按模板补齐章节后 `rebuild` |
| `desc 为空` | WARN | `node set --desc` 补一句话 |
| `link 缺标题` / `links 未同步到正文网页资源表` / 表含未登记 URL | WARN | `node set --rm-link` 后带标题重挂，或补/改正文表行后 `rebuild` |
| `reference/spec 未被挂接` | WARN | 挂 tag（`--add-tag`）或由相关节点 `--add-ref` |
| 教程 `缺少 frontmatter` / kind 不对 | ERROR | 按 §4.1 格式补元数据 |
| `教程未挂任何 tag` | WARN | `tut set --add-tag` |
| `教程延伸阅读未包含任何 URL` | WARN | 在延伸阅读补真实来源 URL |

## 11. Python 环境

- Python 3.8+，依赖仅 `typer` 与 `rich`（见 requirements.txt）；
- 推荐使用 `.venv/`（已 gitignore）；所有文件一律 UTF-8；
- Agent 执行命令统一用 `.venv/Scripts/python index.py ...`。
