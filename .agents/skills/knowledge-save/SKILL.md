---
name: knowledge-save
description: 把信息存入 cook 工作区知识库（docs/ 下 4 类知识节点：tag/project/spec/reference）的完整流程：查重、选类别、建节点、写正文与 keywords、挂关系、健康检查。当用户说"记住这个""存到知识库""记录这条""把这个约定固化下来"时使用。
---

# knowledge-save — 知识入库

目标：新信息以正确的类别、最小的重复进入知识库，并且**以后能被 match 命中**。

## 步骤

1. **自检环境**（首次执行命令前）：同 context-build（`.venv/Scripts/python index.py ...`）。

2. **查重**：`.venv/Scripts/python index.py match "<核心说法>"` + `node list`。
   - 已有合适节点 → **更新而不是新建**：`node set` 改元数据；正文直接编辑文件，改完必须 `rebuild`；
   - 没有才新建。同一概念全局只建一个节点。

3. **选类别**：

   | 信息形态 | 类别 | 命令 |
   | ---- | ---- | ---- |
   | 跨项目主题/领域概念 | `tag` | `node add tag <id>` |
   | 一个项目或方向的上下文 | `project` | `node add project <id>` |
   | 规范/约定/术语定义 | `spec` | 转 spec-manage（`spec add`） |
   | 外部参考、网页、摘录 | `reference` | 转 reference-add（`ref add`） |
   | 教程文档 | `tutorials/` | `tut add <id> --tags … --project …`（不参与 docs 索引，元数据由 check 校验） |

   不确定时问用户一句，别猜。

4. **建节点**：
   ```bash
   .venv/Scripts/python index.py node add tag <id> --title "中文名" --desc "一句话"
   ```
   id 用小写字母/数字/连字符、见名知意；脚本建完即自动 rebuild。

5. **填内容**（编辑刚生成的文件；**必做步骤，不是可选**）：
   - frontmatter：`title`、`desc`（一句话）、`keywords`（**重要术语必须进来，中英文都放**）；
   - 正文：用真实内容**替换全部模板占位**（如「（这个标签覆盖什么主题、不覆盖什么。）」「| <id> | （说明；…） |」），补写 `## 范围` 与 `## 术语表`；
   - tag/project 的 `## 网页资源` 表必须与 frontmatter `links` 一致：**有 links 必须填表，无 links 则删表或注明去向**；
   - **完成标准：文件中不存在任何模板占位文本**（`check` 会以 WARN 检测残留）；
   - 手改正文后必须 `rebuild`（正文编辑会使 INDEX.json 的 hash 失效）。

6. **挂关系**（语义分工见 AGENTS.md §3）：
   ```bash
   .venv/Scripts/python index.py node set <kind>:<id> --add-tag <tag> --add-ref <kind>:<id> --add-keyword "术语"
   ```
   - 「属于某主题」→ `--add-tag`；「明确引用某节点」→ `--add-ref`（会校验目标存在）；
   - 有值得长期收藏的外部链接 → `--add-link "URL|标题"`（进 tag/project 的网页资源索引，资源标题可被 match 命中）；
   - 目标 tag 不存在时先 `node add tag` 创建。

7. **自检与回报**：`check` 无 ERROR 且**自己范围内无 WARN**（重点核对：占位残留、缺少章节、desc/link 标题、links 与网页资源表同步——处置见 AGENTS.md §10）后回报——建了/改了哪个节点、keywords 进了哪些词、挂了什么关系。结构性变更后建议 git commit（不确定时先问用户）。

## 禁止

- 不查重就建新节点（同概念重复节点是关系网的毒药）；
- 元数据写进正文而不进 frontmatter；
- keywords 留空（match 命中不了等于白存）；
- **交付含模板占位符的节点**——占位符即半成品，`check` 会 WARN；
- **在要求「填充节点正文」的同时禁止「手动 rebuild」**——正文编辑必然使 hash 失效，这是死锁。子代理/受限任务要么同时获得两项授权，要么改用 `node set --desc` 暂存描述、正文留给完整流程。
