---
name: reference-add
description: 在 cook 工作区引入外部参考：网络搜索资料、用 ref add 把 URL 入库为 reference 节点（扁平存放），补要点与检索关键词并挂接 tag。当用户说"搜个资料""找个参考""引入外部内容""把这个链接存下来"时使用。
---

# reference-add — 外部参考入库

目标：外部内容以 reference 节点形式进入 `docs/reference/`（扁平化，无子目录），并能在日后被 `match` 命中。

## 步骤

1. **自检环境**（首次执行命令前）：`.venv/Scripts/python index.py ...`。

2. **搜索**：用 agent 的网络搜索工具找候选资料；优先官方文档、一手来源；把候选 URL 各自讲什么列给用户，多候选时让用户挑。

3. **入库**：
   ```bash
   .venv/Scripts/python index.py ref add <id> --url "https://..." --tags <tag1>,<tag2>
   ```
   - 脚本自动抓取网页标题/描述填入模板；抓取失败自动降级（`--no-fetch` 可显式跳过），此时必须 `--title` 传标题；
   - id 用小写字母/数字/连字符、见名知意（如 `nanite-paper`）；
   - 目标 tag 不存在时先 `node add tag <id>` 创建；
   - **自动同步**：挂接的每个 tag 会自动把 `URL|标题` 写进其网页资源索引（links）**并同步正文网页资源表**，日后 match 能靠资源标题命中；删除该 reference 时索引条目自动清理。

4. **补内容**（编辑 docs/reference/<id>.md）：
   - `## 要点`：3-5 条核心结论/适用场景，**用你自己的话总结，不是原文粘贴**；
   - frontmatter：`keywords` 补充检索词（含中英文说法）、`desc` 一句话（必填，check 检测空 desc）、`refs` 指向相关节点（如所属 project）；
   - 完成标准：`## 来源` 与 `## 要点` 齐全、无模板占位、必须已挂接 tag（否则 check 报「reference 未挂接任何 tag」）、check 对本节点无 WARN。

5. **自检与回报**：`check` 通过后回报——引入了什么、来自哪（source URL）、挂了哪些 tag、要点是什么。

## 多条资料

- 一条外部来源一个 reference 节点，同一来源的多个要点合并写在一个节点内；
- 多个来源讲同一主题：各建节点，挂同一 tag，可在要点里互相对照；`refs` 互链到相关节点。

## 禁止

- 原文整段粘贴当要点（要总结）；
- 建子目录归类（reference 一律扁平）；
- 引用时不给出处。
