---
name: context-build
description: 在 cook 工作区动态构建对话上下文：用 match 把用户的话在索引层匹配到知识节点（tag/project/spec/reference），用 rels 顺关系边扩展，只读取命中内容。当用户说"先看下知识库""查一下相关的记忆/节点""新任务开始""这个主题有哪些笔记""找不到之前聊过的 X"或会话首次涉及工作区知识时使用。
---

# context-build — 构建对话上下文

目标：用最少的读取拿到最准的上下文。**检索在脚本层完成，禁止通读 docs/。**

## 步骤

1. **自检环境**（首次执行命令前）：`.venv/` 存在且依赖已装？否则先执行
   `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt`
   （命令统一用 `.venv/Scripts/python index.py ...`）。

2. **匹配**：`.venv/Scripts/python index.py match "<用户的话/任务描述>"`
   - 结果为空时：换 1-2 组同义词再试（如「卡顿」→「性能」「帧率」；中文不行试英文）；
   - 仍为空 → `node list` 确认库里有什么 → 工作区确实没有该主题的节点时如实告知，并建议建新节点（转 knowledge-save）；
   - 若命中结果与 `node list` 明显不符，或有人手改过文件：先 `check`，报「INDEX.json 过期」就 `rebuild` 后重检。

3. **读命中内容**：只读「建议先读」的前 2-3 个节点：
   `.venv/Scripts/python index.py node show <节点>`
   需要程序化解析时给 match 加 `--json`（取 `hits[].node` 与 `read_first`）；`node show <节点> --json` 同样可结构化解析 meta+body。

4. **顺关系扩展**（按需）：`.venv/Scripts/python index.py rels <节点>`
   - 出边 refs：它挂的 tag、引用的 spec/reference——**命中 spec 即提示用户「本次工作需遵守 SPEC-XXX」**；
   - 入边 backrefs：谁指向它——用它找「同一主题下还有哪些节点」（含挂靠该 tag 的教程/项目）；
   - 网页资源：tag/project 维护的外部链接索引，rels 会直接列出；match 命中依据里出现「资源」即来自这里。

5. **教程补查**（按需）：教程（tutorials/）不参与 docs 索引，match 看不到。主题相关时用 `.venv/Scripts/python index.py tut list` 查有无挂对应 tag 的教程，有则在简报中作为延伸阅读推荐给用户。

6. **复述共识**：向用户简报——命中的节点、关键约定/结论、与当前任务的关系。一次会话通常 1 次 match + 1-3 次 node show 即可，不要反复全量检索。

## 回报格式（给用户）

> 在知识库命中 N 个节点：`<节点>`（<标题>，命中依据…）。
> 已读：<列出>。关键结论：<1-3 条>。
> 相关：`<backrefs/refs 里的重要节点>`。

## 禁止

- 只读/受限模式（测试、评审）下 `check` 报「INDEX.json 过期」时**不要 rebuild**，如实上报；正常会话中才执行 rebuild 后重检。

- 通读 docs/ 或反复跑 match 碰运气（超过 2 次换词就停，问用户）；
- 命中 spec 却不提示遵守；
- 检索不到就断言「不存在」而不先 `node list`。
