---
name: spec-manage
description: 在 cook 工作区创建、修订编号规范（docs/spec/ 下 SPEC-XXX 节点）并挂接到 tag/project 索引。当用户说"定个规范""新建一个 SPEC""修订规范""把这条约定固化"时使用。
---

# spec-manage — 规范管理

spec 是一种**规范节点**，包裹术语：正文是约定本身，术语进 frontmatter `keywords`。命中 spec 的会话必须提示遵守。

## 新建

1. **自检环境**（首次执行命令前）：`.venv/Scripts/python index.py ...`。
2. **查重**：`match "<规范主题>"` + `node list --kind spec`，避免对同一件事重复立规。
3. **建**：`.venv/Scripts/python index.py spec add "<规范标题>"`（编号 SPEC-XXX 自动分配，不得手改文件名）。
4. **写正文**（编辑 docs/spec/SPEC-XXX.md）：

   ```markdown
   ## 规范

   - 规则条目（可执行、可判断违反）
   - 适用范围与例外
   - 违反后果/如何纠正（可选）

   ## 术语

   | 术语 | 定义 |
   | ---- | ---- |
   ```

   frontmatter：`keywords` 放术语（中英文），`desc` 一句话概括，`tags` 挂主题（用 `node set --add-tag`）。
   完成标准：`## 规范` 与 `## 术语` 齐全、无模板占位、有网页资源表且与 links 一致、check 对本节点无 WARN。
5. **挂接**（必做，否则 check 报「spec 未被任何节点挂接」）：
   ```bash
   .venv/Scripts/python index.py node set spec:SPEC-XXX --add-tag <tag> --add-ref <kind>:<id>
   ```
   相关的 project/tag 节点也可反向 `--add-ref spec:SPEC-XXX` 挂过来（双向都有边，rels 任一端可查）；
   tutorials/ 下的教程若演示/遵守本规范，用 `tut set <id> --add-spec SPEC-XXX` 挂接（check 校验）。
6. **自检与回报**：`check` 通过后回报编号、标题、挂接关系、适用范围。

## 修订

- 直接编辑 docs/spec/SPEC-XXX.md 正文（改完 `rebuild`）；
- 规则变化大时在正文顶部加「更新记录：YYYY-MM-DD 变更点」；
- 术语增删记得同步 `keywords`（`node set --add-keyword/--rm-keyword`）。

## 废弃

- 规范只废弃不删除：正文顶部标注「已废弃，原因与替代方案」，编号永久保留。

## 禁止

- 手改 SPEC 文件名/编号；
- 一个规范塞多件事（大规范拆多条 SPEC 并互挂 refs）；
- 规则写成口号（不可执行、不可判断违反的不要进 spec）。
