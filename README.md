# cook — AI 知识节点工作区

一个让你和 AI agent 交流时**准确取回上下文**的工作区。你只说意图，agent 执行命令。

## 它解决什么问题

AI 会话最贵的两件事：**上下文不准**（agent 不知道之前聊过什么、约定过什么）和 **token 浪费**（agent 为了找答案通读整个库）。

cook 的做法：

- `docs/` 下只有 4 类**知识节点**（tag / project / spec / reference），每个文件既描述自己讲什么，也描述自己和其它节点的关系；
- 每个目录有一个 `INDEX.json`（派生索引），agent 的 `match` 命令拿你的话在**索引层**匹配，只返回排序命中——不用通读全库；
- `rels` 命令一跳查清节点关系，顺着关系边就能找到相关内容；
- tag/project 节点自带**网页资源索引**（`links`），外部链接一条命令挂进节点，资源标题也能被检索；
- `tutorials/` 的每篇教程带元数据（所属 tag/project/spec），`check` 保证指向真实节点。

## 4 类知识节点

| 类别 | 是什么 | 例子 |
| ---- | ---- | ---- |
| `tag` | 跨项目主题标签（含术语表） | 渲染、性能优化 |
| `project` | 一个项目/方向的上下文 | cpp-game-dev |
| `spec` | 规范（包裹术语），编号 SPEC-XXX | 文档命名规范 |
| `reference` | 外部引入的参考/额外内容（扁平存放） | 某篇论文、某个官方文档的要点 |

两类关系：`tags` =「我属于哪些主题」（挂靠）；`refs` =「我明确引用谁」（指向，任意节点）。反向引用由脚本自动算好（backrefs），`rels` 一跳可查。

## 节点生命周期

```text
检索：match "你的问题" ──► 命中节点 ──► node show 读内容 ──► rels 顺关系扩展
入库：查重（match / node list）──► node add / spec add / ref add ──► 补正文与 keywords
      ──► node set 挂 tags/refs ──► check 自检 ──► git commit
维护：check 报过期/错误 ──► rebuild [--fix] ──► 复检
```

## 怎么用（对话示例）

| 你说 | agent 做 |
| ---- | ---- |
| 「先看下知识库里有没有渲染相关的」 | `match "渲染"` → 读命中节点 → 复述给你 |
| 「记住：我们项目用 UE5，目标是 60fps」 | 查重 → 建节点/更新节点 → 挂关系 → `check` |
| 「定个规范：文档命名用日期前缀」 | `spec add` → 写正文与术语 → 挂接 |
| 「搜下 Nanite 的官方资料存起来」 | 网络搜索 → `ref add --url` 入库 → 挂 tag |
| 「这个方向怎么定？帮我拍板」 | `context-align`：基于库内证据逐轮提问对齐，结论沉淀回知识库 |
| 「SPEC-002 讲什么的」 | `node show spec:SPEC-002` |
| 「渲染和哪些节点有关系」 | `rels tag:rendering` |

## 常用命令（一般由 agent 执行）

```bash
.venv/Scripts/python index.py match "你的问题"             # 检索（--json 供程序解析）
.venv/Scripts/python index.py rels tag:rendering          # 查关系
.venv/Scripts/python index.py node list                   # 列节点
.venv/Scripts/python index.py node show tag:rendering     # 读节点
.venv/Scripts/python index.py tut list                    # 列教程及其 tag/project/spec 元数据
.venv/Scripts/python index.py check                       # 健康检查
.venv/Scripts/python index.py rebuild                     # 重建索引（手动改文件后必须）
```

完整契约见 [AGENTS.md](AGENTS.md)（AI 进入本工作区必读）。

## FAQ

- **「AGENTS 里说的 INDEX.json 在哪？」** 共 4 个，分别在 `docs/tag/`、`docs/project/`、`docs/spec/`、`docs/reference/` 目录内部（不在工作区根目录）；由 `rebuild` 自动生成，手改无效。
- **「明明记过，怎么检索不到？」** 大概率是关键词没进 frontmatter `keywords`。让 agent 执行 `node set <节点> --add-keyword "你的说法"` 即可。
- **「我手动改/删了文件」** 之后必须 `rebuild`，否则索引过期（`check` 会提示）。
- **「能建子目录分类吗？」** 不能。4 类目录内部一律扁平，靠 `tags`/`refs` 表达结构——这正是关系网络优于目录树的地方。
- **「外部资料存在哪？」** 一律 `docs/reference/`，一条来源一个节点；agent 会先总结要点再入库。
- **「教程存在哪？」** 工作区根下的 `tutorials/`（不参与 docs 索引；但每篇必须带 frontmatter 元数据——所属 tag/project/spec，`check` 会校验指向；知识点本身仍在 docs/ 节点里）。

## 环境准备（一次性）

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python index.py init
```
