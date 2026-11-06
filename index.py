#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cook — AI 知识节点工作区管理器
================================

工作区模型：docs/ 下只有 4 类「AI 知识节点」，全部扁平存放：

  docs/tag/<id>.md           标签节点：跨项目主题，含术语表
  docs/project/<id>.md       项目节点：一个项目/方向的上下文
  docs/spec/SPEC-XXX.md      规范节点：规范正文，包裹术语
  docs/reference/<id>.md     参考节点：外部引入的参考/额外内容

所有节点的共性（frontmatter 承载）：
  1. 与其它节点的关系（tags / refs，编址 kind:id）；
  2. 自身内容描述（title / desc / keywords）；
  3. 网页资源索引（links，条目 "URL|标题"；tag/project 维护，资源标题参与 match 检索）。

tutorials/ 为教程输出区（不参与 docs 索引）：每篇带 frontmatter 元数据
（kind: tutorial + tags/project/specs，须指向真实节点，check 校验），
用 tut add / tut list / tut set 管理。

每个目录有一个 INDEX.json（派生数据，只能由本脚本生成），描述该目录
所有节点的内容指纹与关系边（refs 出边 + backrefs 入边），供 match/rels
快速检索，避免 Agent 通读全库。

契约（详见 AGENTS.md）：
  1. 各目录 INDEX.json 只能由本脚本产生和修改；
  2. 节点元数据（title/kind/tags/refs/keywords/desc/source/created/updated）
     唯一来源是文件 frontmatter；
  3. 绕过本脚本直接动文件（新建/移动/删除/改 frontmatter）后必须 rebuild；
  4. 重要术语必须写进 frontmatter keywords，否则 match 命中不了；
  5. reference 一律扁平放在 docs/reference/ 下，不建子目录。

用法示例：
  python index.py init
  python index.py match "UE5 渲染管线卡顿"
  python index.py rels tag:rendering
  python index.py node add tag rendering --title "渲染" --desc "渲染相关主题"
  python index.py spec add 文档命名规范
  python index.py ref add nanite-paper --url https://... --tags rendering
  python index.py check / rebuild [--fix]
"""

from __future__ import annotations

import hashlib
import html as html_mod
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import typer
    from rich.console import Console
    from rich.table import Table
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "[缺少依赖] 本脚本需要 typer 与 rich：\n"
        "    pip install -r requirements.txt\n"
        "（或在 .venv 中安装：.venv\\Scripts\\pip install -r requirements.txt）\n"
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# 常量与路径
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
KINDS = ["tag", "project", "spec", "reference"]
KIND_DIRS = {k: DOCS / k for k in KINDS}
KIND_INDEX = {k: KIND_DIRS[k] / "INDEX.json" for k in KINDS}
DIR_TUT = ROOT / "tutorials"

DIR_PI = ROOT / ".pi"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")       # tag/project/reference id
SPEC_ID_RE = re.compile(r"^SPEC-\d{3}$")                  # spec id
REF_RE = re.compile(r"^(tag|project|spec|reference):(\S+)$")  # kind:id 编址

# 模板占位标记：节点正文残留这些文本 = 未完成（check 会 WARN）
TEMPLATE_MARKERS = (
    "（这个标签覆盖什么主题",
    "（这个项目/方向包含什么",
    "（说明；重要术语必须同时写入",
    "（外部内容的摘要与适用场景",
    "（规范正文；spec 是一种规范",
    "（网页资源索引：frontmatter links 写",
    "（教程正文）",
)

# 各类节点正文必需章节（check 完备性检查）
REQUIRED_SECTIONS = {
    "tag": ("## 范围", "## 术语表"),
    "project": ("## 范围", "## 术语表"),
    "spec": ("## 规范", "## 术语"),
    "reference": ("## 来源", "## 要点"),
}
TUT_REQUIRED_SECTIONS = ("## 核心概念", "## 实操步骤", "## 常见坑", "## 延伸阅读")


def extract_webres_section(body: str) -> Optional[str]:
    """取正文 ## 网页资源 小节文本（到下一个 ## 或文末）；无该节返回 None。"""
    m = re.search(r"^## 网页资源\s*$", body, re.M)
    if not m:
        return None
    rest = body[m.end():]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def append_webres_row(body: str, url: str, title: str) -> str:
    """向正文 ## 网页资源 表追加一行；无该节则补建完整小节。"""
    row = f"| {title} | {url} |"
    m = re.search(r"^## 网页资源\s*$", body, re.M)
    if not m:
        return body.rstrip() + "\n\n## 网页资源\n\n| 标题 | URL |\n| ---- | ---- |\n" + row + "\n"
    rest = body[m.end():]
    sep = re.search(r"^\|(?:\s*-+\s*\|)+\s*$", rest, re.M)
    if not sep:
        return body
    at = m.end() + sep.end()
    return body[:at] + "\n" + row + body[at:]

FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
LIST_KEYS = {"tags", "refs", "keywords", "links", "specs"}
SCALAR_KEYS = ["title", "kind", "desc", "source", "created", "updated"]

app = typer.Typer(
    help="cook 工作区管理器：知识节点（tag/project/spec/reference）的增删改查与检索。",
    no_args_is_help=True,
)
console = Console()

# Windows 控制台默认 GBK，统一切到 UTF-8，避免中文/符号写入失败
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 节点编址与路径
# ---------------------------------------------------------------------------

def parse_node_ref(arg: str) -> Tuple[str, str]:
    """'tag:rendering' -> ('tag','rendering')；kind 必须显式给出。"""
    m = REF_RE.match(arg.strip())
    if not m:
        console.print(
            f"[red]错误[/red]：节点编址应为 [bold]kind:id[/bold]（kind ∈ {', '.join(KINDS)}），收到：{arg}"
        )
        raise typer.Exit(1)
    kind, nid = m.group(1), m.group(2)
    if kind != "spec" and not NAME_RE.match(nid):
        console.print(f"[red]错误[/red]：id '{nid}' 不合规（小写字母/数字/连字符）。")
        raise typer.Exit(1)
    if kind == "spec" and not SPEC_ID_RE.match(nid):
        console.print(f"[red]错误[/red]：spec id 应为 SPEC-XXX（三位数字），收到：{nid}")
        raise typer.Exit(1)
    return kind, nid


def node_path(kind: str, nid: str) -> Path:
    return KIND_DIRS[kind] / f"{nid}.md"


def node_exists(kind: str, nid: str) -> bool:
    return node_path(kind, nid).exists()


def ensure_dirs() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    DIR_TUT.mkdir(parents=True, exist_ok=True)
    DIR_PI.mkdir(parents=True, exist_ok=True)
    for k in KINDS:
        KIND_DIRS[k].mkdir(parents=True, exist_ok=True)


def empty_index(kind: str) -> dict:
    return {"kind": kind, "generated_at": now_ts(), "count": 0, "nodes": {}}


# ---------------------------------------------------------------------------
# frontmatter 解析与渲染
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> Optional[dict]:
    m = FM_RE.match(text)
    if not m:
        return None
    meta: dict = {}
    last_key: Optional[str] = None
    for line in m.group(1).splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if re.match(r"^\s+-\s+", line) and last_key in LIST_KEYS:
            val = line.strip()[1:].strip()
            if val:
                meta[last_key].append(val.strip("'\""))
            continue
        mm = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if not mm:
            continue
        key, val = mm.group(1), mm.group(2).strip()
        last_key = key
        if key in LIST_KEYS:
            if val.startswith("[") and val.endswith("]"):
                val = val[1:-1]
            meta[key] = [t.strip().strip("'\"") for t in val.split(",") if t.strip()]
        else:
            meta[key] = val.strip().strip("'\"")
    for k in LIST_KEYS:
        meta.setdefault(k, [])
    for k in SCALAR_KEYS:
        meta.setdefault(k, "")
    return meta


def render_frontmatter(meta: dict) -> str:
    """按规范字段序渲染 frontmatter（未设字段输出空值，保持结构稳定）。"""
    lines = ["---"]
    lines.append(f"title: {meta.get('title', '')}")
    lines.append(f"kind: {meta.get('kind', '')}")
    for key in ("tags", "refs", "keywords", "links"):
        lines.append(f"{key}: [" + ", ".join(meta.get(key, [])) + "]")
    lines.append(f"desc: {meta.get('desc', '')}")
    if meta.get("source"):
        lines.append(f"source: {meta.get('source')}")
    lines.append(f"created: {meta.get('created', '')}")
    lines.append(f"updated: {meta.get('updated', '')}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def split_file(path: Path) -> Tuple[Optional[dict], str]:
    """返回 (frontmatter 或 None, 正文)。"""
    text = path.read_text(encoding="utf-8")
    meta = parse_frontmatter(text)
    if meta is None:
        return None, text
    body = text[FM_RE.match(text).end():]  # type: ignore[union-attr]
    return meta, body


def file_hash(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:12]


def parse_link(entry: str) -> dict:
    """'URL|标题' -> {'url':…, 'title':…}；无标题时 title 为空串。"""
    url, _, title = entry.partition("|")
    return {"url": url.strip(), "title": title.strip()}


# ---------------------------------------------------------------------------
# 节点模板
# ---------------------------------------------------------------------------

def node_template(kind: str, nid: str, title: str, desc: str, source: str = "") -> str:
    d = today()
    meta = {
        "title": title or nid,
        "kind": kind,
        "tags": [],
        "refs": [],
        "keywords": [nid] if kind != "spec" else [nid, title],
        "desc": desc,
        "source": source,
        "created": d,
        "updated": d,
    }
    heads = {
        "tag": f"# {title or nid}（tag）\n\n## 范围\n\n（这个标签覆盖什么主题、不覆盖什么。）\n\n## 术语表\n\n| 术语 | 含义 |\n| ---- | ---- |\n| {nid} | （说明；重要术语必须同时写入 frontmatter keywords，否则 match 命中不了） |\n\n## 网页资源\n\n（网页资源索引：frontmatter links 写 \"URL|标题\" 条目供 match 命中；下表给人看。）\n\n| 标题 | URL |\n| ---- | ---- |\n",
        "project": f"# {title or nid}（project）\n\n## 范围\n\n（这个项目/方向包含什么、目标是什么、不包含什么。）\n\n## 术语表\n\n| 术语 | 含义 |\n| ---- | ---- |\n| {nid} | （说明；重要术语必须同时写入 frontmatter keywords） |\n\n## 网页资源\n\n（网页资源索引：frontmatter links 写 \"URL|标题\" 条目供 match 命中；下表给人看。）\n\n| 标题 | URL |\n| ---- | ---- |\n",
        "spec": f"# {nid}：{title or nid}\n\n## 规范\n\n（规范正文；spec 是一种规范，包裹术语。涉及的重要术语写入 frontmatter keywords。）\n\n## 术语\n\n| 术语 | 定义 |\n| ---- | ---- |\n",
        "reference": f"# {title or nid}（reference）\n\n## 来源\n\n- URL: {source or '（外部 URL 或出处说明）'}\n- 引入时间: {d}\n\n## 要点\n\n（外部内容的摘要与适用场景；补充检索关键词写入 frontmatter keywords。）\n",
    }
    return render_frontmatter(meta) + "\n" + heads[kind]


def read_node(kind: str, nid: str) -> Tuple[dict, str, Path]:
    p = node_path(kind, nid)
    if not p.exists():
        console.print(f"[red]错误[/red]：节点 {kind}:{nid} 不存在（{p.relative_to(ROOT).as_posix()}）。")
        raise typer.Exit(1)
    meta, body = split_file(p)
    if meta is None:
        console.print(f"[red]错误[/red]：{p.relative_to(ROOT).as_posix()} 缺少 frontmatter。先修复再操作。")
        raise typer.Exit(1)
    return meta, body, p


def write_node_meta(path: Path, meta: dict, body: str) -> None:
    meta["updated"] = today()
    path.write_text(render_frontmatter(meta) + "\n" + body.lstrip("\n"), encoding="utf-8")


# ---------------------------------------------------------------------------
# 全库扫描与 INDEX.json
# ---------------------------------------------------------------------------

def scan_kind(kind: str) -> Dict[str, dict]:
    """扫描 docs/<kind>/ 下全部 .md，返回 id -> {meta, body, path, hash}。"""
    out: Dict[str, dict] = {}
    d = KIND_DIRS[kind]
    if not d.exists():
        return out
    for p in sorted(d.glob("*.md")):
        meta, body = split_file(p)
        if meta is None:
            meta, body = {}, p.read_text(encoding="utf-8")
        out[p.stem] = {"meta": meta, "body": body, "path": p, "hash": file_hash(p)}
    return out


def scan_all() -> Dict[str, Dict[str, dict]]:
    return {k: scan_kind(k) for k in KINDS}


def body_head(body: str, n: int = 600) -> str:
    t = re.sub(r"\s+", " ", body).strip()
    return t[:n]


def rebuild_all() -> None:
    """重建全部 4 个 INDEX.json（派生数据唯一入口）。"""
    ensure_dirs()
    all_nodes = scan_all()
    backrefs: Dict[str, List[str]] = {}

    def key(kind: str, nid: str) -> str:
        return f"{kind}:{nid}"

    for kind, nodes in all_nodes.items():
        for nid, item in nodes.items():
            for r in item["meta"].get("refs", []):
                backrefs.setdefault(r, [])
                if key(kind, nid) not in backrefs[r]:
                    backrefs[r].append(key(kind, nid))
            # tags 挂靠也是一条入边：project 挂 tag:x，则 tag:x 有一条来自 project 的入边
            if kind != "tag":
                for t in item["meta"].get("tags", []):
                    tk = f"tag:{t}"
                    backrefs.setdefault(tk, [])
                    if key(kind, nid) not in backrefs[tk]:
                        backrefs[tk].append(key(kind, nid))

    for kind in KINDS:
        entries: Dict[str, dict] = {}
        for nid, item in all_nodes[kind].items():
            meta = item["meta"]
            entries[nid] = {
                "title": meta.get("title", ""),
                "desc": meta.get("desc", ""),
                "file": item["path"].name,
                "keywords": meta.get("keywords", []),
                "tags": meta.get("tags", []),
                "refs": meta.get("refs", []),
                "links": [parse_link(l) for l in meta.get("links", [])],
                "backrefs": sorted(backrefs.get(key(kind, nid), [])),
                "body_head": body_head(item["body"]),
                "hash": item["hash"],
            }
        data = {
            "kind": kind,
            "generated_at": now_ts(),
            "count": len(entries),
            "nodes": entries,
        }
        KIND_INDEX[kind].write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def load_index(kind: str) -> dict:
    f = KIND_INDEX[kind]
    if not f.exists():
        return empty_index(kind)
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        console.print(f"[red]错误[/red]：{f.relative_to(ROOT).as_posix()} 解析失败：{e}。执行 rebuild 修复。")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# 检索打分（中文友好：全等 > 包含 > 公共子串）
# ---------------------------------------------------------------------------

def _query_tokens(q: str) -> List[str]:
    parts = re.split(r"[\s,，。、；;:：!?！？()（）\[\]【】\"'`|]+", q)
    toks = [p for p in parts if p]
    full = q.strip()
    if full and full not in toks:
        toks.append(full)
    return toks


def _has_cjk(s: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", s))


def _lcs_len(a: str, b: str) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def _score_field(tok: str, field: str, weight: float) -> float:
    if not field:
        return 0.0
    tl, fl = tok.lower(), field.lower()
    if not tl:
        return 0.0
    if tl == fl:
        return weight * 1.5
    if tl in fl:
        ratio = len(tl) / max(1, len(fl))
        base = 0.4 + ratio
        if ratio < 0.5:
            base *= 0.6  # 泛词弱包含降权：区分「碰巧出现」与「实质命中」
        return weight * min(1.0, base)
    min_l = 2 if (_has_cjk(tl) or _has_cjk(fl)) else 3
    l = _lcs_len(tl, fl)
    if l >= min_l:
        return weight * 0.8 * min(1.0, 0.3 + l / max(len(tl), len(fl)))
    return 0.0


FIELD_W = {"id": 1.2, "title": 2.5, "desc": 2.0, "keyword": 3.0, "body": 1.0}
SCORE_THRESHOLD = 0.8


def match_nodes(query: str, kinds: List[str], limit: int) -> List[dict]:
    toks = _query_tokens(query)
    results: List[dict] = []

    for kind in kinds:
        idx = load_index(kind)
        for nid, e in idx.get("nodes", {}).items():
            fields: List[Tuple[str, str, float]] = [("id", nid, FIELD_W["id"])]
            if e.get("title"):
                fields.append(("标题", e["title"], FIELD_W["title"]))
            if e.get("desc"):
                fields.append(("描述", e["desc"], FIELD_W["desc"]))
            for kw in e.get("keywords", []):
                fields.append(("术语", kw, FIELD_W["keyword"]))
            for lk in e.get("links", []):
                if lk.get("title"):
                    fields.append(("资源", lk["title"], 2.2))
                if lk.get("url"):
                    fields.append(("URL", lk["url"], 0.9))
            if e.get("body_head"):
                fields.append(("正文", e["body_head"], FIELD_W["body"]))
            score, evid = 0.0, []
            for label, field, w in fields:
                best = 0.0
                for tok in toks:
                    s = _score_field(tok, field, w)
                    if s > best:
                        best = s
                if best > 0:
                    score += best
                    shown = field if len(field) <= 20 else field[:20] + "…"
                    evid.append((best, f"{label}「{shown}」"))
            if score >= SCORE_THRESHOLD:
                evid.sort(key=lambda x: -x[0])  # 强依据优先展示，避免关键术语被截断
                why = [e[1] for e in evid]
                results.append(
                    {
                        "node": f"{kind}:{nid}",
                        "kind": kind,
                        "id": nid,
                        "title": e.get("title", ""),
                        "desc": e.get("desc", ""),
                        "score": round(score, 1),
                        "why": why,
                    }
                )
    results.sort(key=lambda x: -x["score"])
    return results[:limit]


# ---------------------------------------------------------------------------
# URL 抓取（reference 入库辅助）
# ---------------------------------------------------------------------------

def fetch_url_meta(url: str) -> Tuple[Optional[str], Optional[str]]:
    """抓取网页 <title> 与 meta description，失败返回 (None, None)。"""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (cook-workspace; reference-index)"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read(131072)
        text = raw.decode("utf-8", errors="replace")
        title = desc = None
        m = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
        if m:
            title = html_mod.unescape(re.sub(r"\s+", " ", m.group(1)).strip()) or None
        m = re.search(
            r"<meta[^>]+name=[\"']description[\"'][^>]*content=[\"'](.*?)[\"']",
            text, re.S | re.I,
        )
        if not m:
            m = re.search(
                r"<meta[^>]+content=[\"'](.*?)[\"'][^>]*name=[\"']description[\"']",
                text, re.S | re.I,
            )
        if m:
            desc = html_mod.unescape(re.sub(r"\s+", " ", m.group(1)).strip()) or None
        return title, desc
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# 命令：init
# ---------------------------------------------------------------------------

@app.command()
def init() -> None:
    """初始化工作区骨架（docs/4 目录 + 各 INDEX.json + .pi/）。"""
    ensure_dirs()
    for k in KINDS:
        if not KIND_INDEX[k].exists():
            KIND_INDEX[k].write_text(
                json.dumps(empty_index(k), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    (DIR_PI / ".gitkeep").touch(exist_ok=True)
    for k in KINDS:
        console.print(f"  [green]✓[/green] docs/{k}/（INDEX.json）")
    console.print("[green]完成[/green]：工作区骨架就绪。")


# ---------------------------------------------------------------------------
# 命令：match
# ---------------------------------------------------------------------------

@app.command()
def match(
    query: str = typer.Argument(..., help="用户的话 / 任务描述 / 关键词"),
    limit: int = typer.Option(8, "--limit", "-n", help="最多返回条数"),
    kinds: str = typer.Option("", "--kind", "-k", help="限定类别，逗号分隔（tag,project,spec,reference）"),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON（供 agent 解析）"),
) -> None:
    """对话式检索：拿用户的话匹配知识节点，返回排序命中（Agent 只读命中内容，省 token）。"""
    kind_list = [k.strip() for k in kinds.split(",") if k.strip()] if kinds else KINDS
    bad = [k for k in kind_list if k not in KINDS]
    if bad:
        console.print(f"[red]错误[/red]：未知类别 {bad}（可选：{', '.join(KINDS)}）")
        raise typer.Exit(1)
    hits = match_nodes(query, kind_list, limit)
    read_first = [h["node"] for h in hits[:3]]

    if json_out:
        print(json.dumps(
            {"query": query, "count": len(hits), "read_first": read_first, "hits": hits},
            ensure_ascii=False, indent=2,
        ))
        return

    if not hits:
        console.print(f"[yellow]无命中[/yellow]：\"{query}\"。可尝试换词，或为新主题建节点（node add）。")
        return
    console.print(f"[bold]命中 {len(hits)} 个节点[/bold]（按相关度排序）：\n")
    t = Table(show_header=True, header_style="bold")
    t.add_column("#", justify="right", width=3)
    t.add_column("节点", style="cyan", no_wrap=True)
    t.add_column("标题", max_width=24)
    t.add_column("分", justify="right")
    t.add_column("命中依据", max_width=56)
    for i, h in enumerate(hits, 1):
        t.add_row(str(i), h["node"], h["title"] or "-", str(h["score"]), " / ".join(h["why"][:4]))
    console.print(t)
    console.print(f"\n[bold]建议先读[/bold]：{', '.join(read_first)}")
    console.print(f"读内容：[cyan]python index.py node show <节点>[/cyan]；查关系：[cyan]python index.py rels <节点>[/cyan]")


# ---------------------------------------------------------------------------
# 命令：rels
# ---------------------------------------------------------------------------

@app.command()
def rels(node: str = typer.Argument(..., help="节点编址 kind:id，如 tag:rendering")) -> None:
    """一跳查清某节点的关系边：refs 出边、backrefs 入边、所属 tags。"""
    kind, nid = parse_node_ref(node)
    if not node_exists(kind, nid):
        console.print(f"[red]错误[/red]：节点 {kind}:{nid} 不存在。")
        raise typer.Exit(1)
    idx = load_index(kind).get("nodes", {}).get(nid, {})
    meta, _, _ = read_node(kind, nid)

    console.print(f"[bold]{kind}:{nid}[/bold]  {meta.get('title', '')}")
    if meta.get("desc"):
        console.print(f"  {meta['desc']}")

    tags = meta.get("tags", [])
    if kind != "tag":
        console.print(f"\n[bold]所属 tags[/bold]：{', '.join(tags) if tags else '（无）'}")

    refs = meta.get("refs", [])
    console.print(f"\n[bold]出边 refs[/bold]（{len(refs)}）：")
    if refs:
        for r in refs:
            rk, rid = parse_node_ref(r)
            exists = "[green]✓[/green]" if node_exists(rk, rid) else "[red]✗ 不存在[/red]"
            title = load_index(rk).get("nodes", {}).get(rid, {}).get("title", "")
            console.print(f"  → {r}  {exists}  {title}")
    else:
        console.print("  （无）")

    back = idx.get("backrefs", [])
    console.print(f"\n[bold]入边 backrefs[/bold]（{len(back)}，谁指向它）：")
    if back:
        for b in back:
            console.print(f"  ← {b}")
    else:
        console.print("  （无）")

    links = meta.get("links", [])
    if links:
        console.print(f"\n[bold]网页资源[/bold]（{len(links)}）：")
        for l in links:
            url, _, ltitle = l.partition("|")
            console.print(f"  → {ltitle or url}  [dim]{url}[/dim]")


# ---------------------------------------------------------------------------
# 子命令：node（增删改查）
# ---------------------------------------------------------------------------

node_app = typer.Typer(help="知识节点增删改查（tag / project / spec / reference）。", no_args_is_help=True)
app.add_typer(node_app, name="node")


@node_app.command("add")
def node_add(
    kind: str = typer.Argument(..., help="类别：tag | project | spec | reference"),
    nid: str = typer.Argument(..., help="节点 id；spec 为 SPEC-XXX（用 spec add 自动编号）"),
    title: str = typer.Option("", "--title", "-t", help="标题"),
    desc: str = typer.Option("", "--desc", "-d", help="一句话描述"),
) -> None:
    """新建知识节点（生成模板文件，元数据写 frontmatter）。"""
    if kind not in KINDS:
        console.print(f"[red]错误[/red]：未知类别 '{kind}'（可选：{', '.join(KINDS)}）")
        raise typer.Exit(1)
    if kind == "spec":
        console.print("[red]错误[/red]：spec 编号自动分配，请使用 [bold]python index.py spec add <标题>[/bold]")
        raise typer.Exit(1)
    if not NAME_RE.match(nid):
        console.print(f"[red]错误[/red]：id '{nid}' 不合规（小写字母/数字/连字符，如 cpp-rendering）。")
        raise typer.Exit(1)
    if node_exists(kind, nid):
        console.print(f"[red]错误[/red]：{kind}:{nid} 已存在。")
        raise typer.Exit(1)
    ensure_dirs()
    p = node_path(kind, nid)
    p.write_text(node_template(kind, nid, title, desc), encoding="utf-8")
    rebuild_all()
    console.print(f"[green]✓[/green] 已创建 {kind}:{nid} → {p.relative_to(ROOT).as_posix()}")
    console.print("下一步：编辑正文与 keywords，再用 node set 挂关系（refs/tags）。")


@node_app.command("rm")
def node_rm(
    node: str = typer.Argument(..., help="节点编址 kind:id"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """删除节点文件，并清理其它节点指向它的 refs/tags。"""
    kind, nid = parse_node_ref(node)
    if not node_exists(kind, nid):
        console.print(f"[red]错误[/red]：节点 {kind}:{nid} 不存在。")
        raise typer.Exit(1)
    if not yes:
        confirm = typer.confirm(f"确认删除 {kind}:{nid}？其它节点指向它的引用会被清理")
        if not confirm:
            console.print("已取消。")
            raise typer.Exit(0)
    src_meta, _, _ = read_node(kind, nid)
    src_url = src_meta.get("source", "") if kind == "reference" else ""
    node_path(kind, nid).unlink()
    target = f"{kind}:{nid}"
    cleaned = 0
    for k in KINDS:
        for other_id, item in scan_kind(k).items():
            meta, body = item["meta"], item["body"]
            changed = False
            if target in meta.get("refs", []):
                meta["refs"] = [r for r in meta["refs"] if r != target]
                changed = True
            if kind == "tag" and nid in meta.get("tags", []):
                meta["tags"] = [t for t in meta["tags"] if t != nid]
                changed = True
            if src_url and any(l.split("|", 1)[0].strip() == src_url for l in meta.get("links", [])):
                meta["links"] = [l for l in meta["links"] if l.split("|", 1)[0].strip() != src_url]
                changed = True
            if changed:
                write_node_meta(item["path"], meta, body)
                cleaned += 1
    rebuild_all()
    console.print(f"[green]✓[/green] 已删除 {target}，清理 {cleaned} 个节点的引用。")


@node_app.command("list")
def node_list(
    kind: str = typer.Option("", "--kind", "-k", help="只列某类别（tag/project/spec/reference）"),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """列出知识节点（读 INDEX.json，不读正文，省 token）。"""
    kind_list = [kind] if kind else KINDS
    if kind and kind not in KINDS:
        console.print(f"[red]错误[/red]：未知类别 '{kind}'")
        raise typer.Exit(1)
    if json_out:
        out = {}
        for k in kind_list:
            out[k] = load_index(k).get("nodes", {})
        console.print_json(json.dumps(out, ensure_ascii=False))
        return
    total = 0
    for k in kind_list:
        nodes = load_index(k).get("nodes", {})
        total += len(nodes)
        console.print(f"\n[bold]docs/{k}/[/bold]（{len(nodes)}）")
        if not nodes:
            console.print("  （空）")
            continue
        t = Table(show_header=True, header_style="bold")
        t.add_column("节点", style="cyan", no_wrap=True)
        t.add_column("标题", max_width=26)
        t.add_column("描述", max_width=36)
        t.add_column("refs", justify="right")
        t.add_column("backrefs", justify="right")
        for nid, e in nodes.items():
            t.add_row(
                nid, e.get("title", "") or "-", (e.get("desc", "") or "-")[:36],
                str(len(e.get("refs", []))), str(len(e.get("backrefs", []))),
            )
        console.print(t)
    console.print(f"\n共 {total} 个节点。")


@node_app.command("show")
def node_show(
    node: str = typer.Argument(..., help="节点编址 kind:id"),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON（meta+body，供程序解析）"),
) -> None:
    """输出节点文件全文（Agent 据此获取该节点上下文）。"""
    kind, nid = parse_node_ref(node)
    meta, body, _ = read_node(kind, nid)
    if json_out:
        print(json.dumps({"node": f"{kind}:{nid}", "meta": meta, "body": body}, ensure_ascii=False, indent=2))
        return
    text = render_frontmatter(meta) + "\n" + body.rstrip() + "\n"
    # 原样输出：不经 rich 折行/裁剪，保留文件原始行宽，也不解析 [..] markup
    print(text)


@node_app.command("set")
def node_set(
    node: str = typer.Argument(..., help="节点编址 kind:id"),
    title: str = typer.Option("", "--title", "-t", help="设置标题"),
    desc: str = typer.Option("", "--desc", "-d", help="设置一句话描述"),
    source: str = typer.Option("", "--source", "-s", help="设置来源 URL（reference）"),
    add_kw: List[str] = typer.Option(None, "--add-keyword", help="追加检索术语（可多次）"),
    rm_kw: List[str] = typer.Option(None, "--rm-keyword", help="移除检索术语（可多次）"),
    add_ref: List[str] = typer.Option(None, "--add-ref", help="追加关系节点 kind:id（校验存在）"),
    rm_ref: List[str] = typer.Option(None, "--rm-ref", help="移除关系节点"),
    add_tag: List[str] = typer.Option(None, "--add-tag", help="挂接到 tag（仅非 tag 节点）"),
    rm_tag: List[str] = typer.Option(None, "--rm-tag", help="取消挂接 tag"),
    add_link: List[str] = typer.Option(None, "--add-link", help='追加网页资源索引，格式 "URL|标题"（可多次）'),
    rm_link: List[str] = typer.Option(None, "--rm-link", help="按 URL 移除网页资源索引（可多次）"),
) -> None:
    """修改节点元数据（frontmatter；正文请直接编辑文件）。"""
    kind, nid = parse_node_ref(node)
    meta, body, path = read_node(kind, nid)

    if title:
        meta["title"] = title
    if desc:
        meta["desc"] = desc
    if source:
        meta["source"] = source
    for kw in add_kw or []:
        if kw and kw not in meta["keywords"]:
            meta["keywords"].append(kw)
    for kw in rm_kw or []:
        meta["keywords"] = [x for x in meta["keywords"] if x != kw]
    for r in add_ref or []:
        rk, rid = parse_node_ref(r)
        if not node_exists(rk, rid):
            console.print(f"[red]错误[/red]：引用目标 {r} 不存在，先创建它。")
            raise typer.Exit(1)
        if r not in meta["refs"]:
            meta["refs"].append(r)
    for r in rm_ref or []:
        meta["refs"] = [x for x in meta["refs"] if x != r]
    if kind == "tag" and (add_tag or rm_tag):
        console.print("[yellow]提示[/yellow]：tag 节点自身不再挂 tags（关系写 refs）。")
    else:
        for t in add_tag or []:
            if not node_exists("tag", t):
                console.print(f"[red]错误[/red]：tag '{t}' 不存在，先 node add tag {t}。")
                raise typer.Exit(1)
            if t not in meta["tags"]:
                meta["tags"].append(t)
        for t in rm_tag or []:
            meta["tags"] = [x for x in meta["tags"] if x != t]

    for entry in add_link or []:
        if "|" not in entry:
            console.print("[red]错误[/red]：--add-link 格式应为 \"URL|标题\"。")
            raise typer.Exit(1)
        url, ltitle = (s.strip() for s in entry.split("|", 1))
        if not url.startswith("http"):
            console.print(f"[red]错误[/red]：link 应以 http(s) 开头：{url}")
            raise typer.Exit(1)
        if not any(l.split("|", 1)[0].strip() == url for l in meta["links"]):
            meta["links"].append(f"{url}|{ltitle}")
    for url in rm_link or []:
        meta["links"] = [l for l in meta["links"] if l.split("|", 1)[0].strip() != url]

    write_node_meta(path, meta, body)
    rebuild_all()
    console.print(f"[green]✓[/green] 已更新 {kind}:{nid}")


# ---------------------------------------------------------------------------
# 子命令：spec / ref
# ---------------------------------------------------------------------------

spec_app = typer.Typer(help="规范节点（SPEC-XXX）专用。", no_args_is_help=True)
app.add_typer(spec_app, name="spec")


def next_spec_id() -> str:
    existing = [p.stem for p in KIND_DIRS["spec"].glob("SPEC-*.md")]
    nums = [int(m.group(1)) for s in existing if (m := re.match(r"^SPEC-(\d{3})$", s))]
    return f"SPEC-{max(nums) + 1:03d}" if nums else "SPEC-001"


@spec_app.command("add")
def spec_add(
    title: str = typer.Argument(..., help="规范标题"),
    desc: str = typer.Option("", "--desc", "-d", help="一句话描述"),
) -> None:
    """新建规范节点：自动分配 SPEC-XXX 编号并生成模板。"""
    ensure_dirs()
    nid = next_spec_id()
    p = node_path("spec", nid)
    p.write_text(node_template("spec", nid, title, desc), encoding="utf-8")
    rebuild_all()
    console.print(f"[green]✓[/green] 已创建 {nid}：{title} → {p.relative_to(ROOT).as_posix()}")
    console.print("下一步：补写规范正文与术语，再用 node set --add-tag/--add-ref 挂接。")


ref_app = typer.Typer(help="参考节点（外部引入内容）专用。", no_args_is_help=True)
app.add_typer(ref_app, name="ref")


@ref_app.command("add")
def ref_add(
    nid: str = typer.Argument(..., help="参考节点 id（小写字母/数字/连字符）"),
    url: str = typer.Option("", "--url", "-u", help="外部 URL（可选）"),
    title: str = typer.Option("", "--title", "-t", help="标题（缺省时尝试抓取网页标题）"),
    desc: str = typer.Option("", "--desc", "-d", help="一句话描述"),
    tags: str = typer.Option("", "--tags", help="挂接的 tag，逗号分隔"),
    no_fetch: bool = typer.Option(False, "--no-fetch", help="不抓取网页元数据"),
) -> None:
    """新建参考节点；给 --url 时自动抓取网页标题/描述填入模板。"""
    if not NAME_RE.match(nid):
        console.print(f"[red]错误[/red]：id '{nid}' 不合规（小写字母/数字/连字符）。")
        raise typer.Exit(1)
    if node_exists("reference", nid):
        console.print(f"[red]错误[/red]：reference:{nid} 已存在。")
        raise typer.Exit(1)
    real_title, real_desc = title, desc
    if url and not no_fetch:
        ft, fd = fetch_url_meta(url)
        if ft and not real_title:
            real_title = ft
        if fd and not real_desc:
            real_desc = fd[:120]
        if ft:
            console.print(f"[dim]抓取到标题：{ft}[/dim]")
        else:
            console.print("[yellow]提示[/yellow]：网页抓取失败，使用传入/默认标题。")
    ensure_dirs()
    p = node_path("reference", nid)
    p.write_text(node_template("reference", nid, real_title, real_desc, source=url), encoding="utf-8")
    # 挂接 tags（校验存在）
    if tags:
        meta, body, _ = read_node("reference", nid)
        for t in [x.strip() for x in tags.split(",") if x.strip()]:
            if not node_exists("tag", t):
                console.print(f"[yellow]跳过[/yellow]：tag '{t}' 不存在（先创建再手动 node set --add-tag）。")
                continue
            if t not in meta["tags"]:
                meta["tags"].append(t)
        write_node_meta(p, meta, body)
        # 自动同步网页资源索引：把 URL|标题 写进所挂 tag 的 links
        if url and real_title:
            synced = 0
            for t in [x.strip() for x in tags.split(",") if x.strip()]:
                if not node_exists("tag", t):
                    continue
                tmeta, tbody, tpath = read_node("tag", t)
                if not any(l.split("|", 1)[0].strip() == url for l in tmeta["links"]):
                    tmeta["links"].append(f"{url}|{real_title}")
                    tbody = append_webres_row(tbody, url, real_title)
                    write_node_meta(tpath, tmeta, tbody)
                    synced += 1
            if synced:
                console.print(f"[dim]已同步网页资源索引到 {synced} 个 tag[/dim]")
    rebuild_all()
    console.print(f"[green]✓[/green] 已创建 reference:{nid} → {p.relative_to(ROOT).as_posix()}")


# ---------------------------------------------------------------------------
# 子命令：tut（tutorials/ 教程输出区，不参与 docs 索引）
# ---------------------------------------------------------------------------

tut_app = typer.Typer(help="教程文档（tutorials/）：创建与维护元数据（tags/project/specs）。", no_args_is_help=True)
app.add_typer(tut_app, name="tut")


def render_tut_frontmatter(meta: dict) -> str:
    lines = ["---", f"title: {meta.get('title', '')}", "kind: tutorial"]
    lines.append("tags: [" + ", ".join(meta.get("tags", [])) + "]")
    if meta.get("project"):
        lines.append(f"project: {meta.get('project')}")
    lines.append("specs: [" + ", ".join(meta.get("specs", [])) + "]")
    lines.append(f"created: {meta.get('created', '')}")
    lines.append(f"updated: {meta.get('updated', '')}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def read_tut(nid: str) -> Tuple[dict, str, Path]:
    p = tut_path(nid)
    if not p.exists():
        console.print(f"[red]错误[/red]：教程 {p.relative_to(ROOT).as_posix()} 不存在。")
        raise typer.Exit(1)
    meta, body = split_file(p)
    if meta is None:
        console.print(f"[red]错误[/red]：{p.relative_to(ROOT).as_posix()} 缺少 frontmatter。")
        raise typer.Exit(1)
    return meta, body, p


def tut_path(nid: str) -> Path:
    return DIR_TUT / f"{nid}.md"


@tut_app.command("add")
def tut_add(
    nid: str = typer.Argument(..., help="教程 id（文件名，不含 .md）"),
    title: str = typer.Option("", "--title", "-t", help="标题"),
    tags: str = typer.Option("", "--tags", help="所属 tag，逗号分隔（校验存在）"),
    project: str = typer.Option("", "--project", help="所属 project id（校验存在）"),
    specs: str = typer.Option("", "--specs", help="关联 SPEC 编号，逗号分隔（校验存在）"),
) -> None:
    """新建教程骨架：frontmatter 元数据（kind: tutorial + tags/project/specs）。"""
    if not NAME_RE.match(nid):
        console.print(f"[red]错误[/red]：id '{nid}' 不合规（小写字母/数字/连字符）。")
        raise typer.Exit(1)
    p = tut_path(nid)
    if p.exists():
        console.print(f"[red]错误[/red]：教程 {nid} 已存在。")
        raise typer.Exit(1)
    meta: dict = {"title": title or nid, "tags": [], "project": "", "specs": [], "created": today(), "updated": today()}
    for t in [x.strip() for x in tags.split(",") if x.strip()]:
        if not node_exists("tag", t):
            console.print(f"[red]错误[/red]：tag '{t}' 不存在，先创建。")
            raise typer.Exit(1)
        meta["tags"].append(t)
    if project:
        if not node_exists("project", project):
            console.print(f"[red]错误[/red]：project '{project}' 不存在。")
            raise typer.Exit(1)
        meta["project"] = project
    for s in [x.strip().upper() for x in specs.split(",") if x.strip()]:
        if not node_exists("spec", s):
            console.print(f"[red]错误[/red]：spec '{s}' 不存在。")
            raise typer.Exit(1)
        meta["specs"].append(s)
    DIR_TUT.mkdir(parents=True, exist_ok=True)
    p.write_text(render_tut_frontmatter(meta) + f"\n# {meta['title']}\n\n（教程正文）\n", encoding="utf-8")
    console.print(f"[green]✓[/green] 已创建教程 → {p.relative_to(ROOT).as_posix()}")


@tut_app.command("list")
def tut_list() -> None:
    """列出教程及其元数据（tags/project/specs）。"""
    if not DIR_TUT.exists():
        console.print("（tutorials/ 不存在）")
        return
    files = sorted(DIR_TUT.glob("*.md"))
    console.print(f"[bold]tutorials/[/bold]（{len(files)}）")
    t = Table(show_header=True, header_style="bold")
    t.add_column("教程", style="cyan", no_wrap=True)
    t.add_column("标题", max_width=26)
    t.add_column("tags", max_width=22)
    t.add_column("project", max_width=16)
    t.add_column("specs", max_width=14)
    for p in files:
        meta, _ = split_file(p)
        if not meta:
            t.add_row(p.stem, "[red]缺 frontmatter[/red]", "-", "-", "-")
            continue
        t.add_row(
            p.stem, meta.get("title", "") or "-", ",".join(meta.get("tags", [])) or "-",
            meta.get("project", "") or "-", ",".join(meta.get("specs", [])) or "-",
        )
    console.print(t)


@tut_app.command("set")
def tut_set(
    nid: str = typer.Argument(..., help="教程 id"),
    title: str = typer.Option("", "--title", "-t", help="设置标题"),
    add_tag: List[str] = typer.Option(None, "--add-tag", help="追加所属 tag（校验存在）"),
    rm_tag: List[str] = typer.Option(None, "--rm-tag", help="移除所属 tag"),
    project: str = typer.Option("", "--project", help="设置所属 project（校验存在）"),
    add_spec: List[str] = typer.Option(None, "--add-spec", help="追加关联 SPEC（校验存在）"),
    rm_spec: List[str] = typer.Option(None, "--rm-spec", help="移除关联 SPEC"),
) -> None:
    """修改教程元数据（校验指向真实节点）。"""
    meta, body, p = read_tut(nid)
    if title:
        meta["title"] = title
    for t in add_tag or []:
        if not node_exists("tag", t):
            console.print(f"[red]错误[/red]：tag '{t}' 不存在。")
            raise typer.Exit(1)
        if t not in meta["tags"]:
            meta["tags"].append(t)
    for t in rm_tag or []:
        meta["tags"] = [x for x in meta["tags"] if x != t]
    if project:
        if not node_exists("project", project):
            console.print(f"[red]错误[/red]：project '{project}' 不存在。")
            raise typer.Exit(1)
        meta["project"] = project
    for s in add_spec or []:
        s = s.upper()
        if not node_exists("spec", s):
            console.print(f"[red]错误[/red]：spec '{s}' 不存在。")
            raise typer.Exit(1)
        if s not in meta["specs"]:
            meta["specs"].append(s)
    for s in rm_spec or []:
        meta["specs"] = [x for x in meta["specs"] if x != s.upper()]
    meta["updated"] = today()
    p.write_text(render_tut_frontmatter(meta) + "\n" + body.lstrip("\n"), encoding="utf-8")
    console.print(f"[green]✓[/green] 已更新教程 {nid}")


# ---------------------------------------------------------------------------
# 命令：check / rebuild
# ---------------------------------------------------------------------------

def collect_issues() -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warns: List[str] = []
    all_nodes = scan_all()
    node_ids = {k: set(v.keys()) for k, v in all_nodes.items()}
    ref_targets = set()
    for nodes_map in all_nodes.values():
        for item in nodes_map.values():
            ref_targets.update(item["meta"].get("refs", []))

    if not DOCS.exists():
        errors.append("docs/ 不存在（执行 init）")
        return errors, warns
    for k in KINDS:
        if not KIND_DIRS[k].exists():
            errors.append(f"docs/{k}/ 目录缺失（执行 init）")

    for kind, nodes in all_nodes.items():
        for nid, item in nodes.items():
            rel = item["path"].relative_to(ROOT).as_posix()
            meta = item["meta"]
            if not meta:
                errors.append(f"{rel}: 缺少 frontmatter")
                continue
            if meta.get("kind") != kind:
                errors.append(f"{rel}: frontmatter kind='{meta.get('kind')}' 与目录 docs/{kind}/ 不一致")
            if kind == "spec":
                if not SPEC_ID_RE.match(nid):
                    errors.append(f"{rel}: spec 文件名应为 SPEC-XXX")
            elif not NAME_RE.match(nid):
                errors.append(f"{rel}: id '{nid}' 不合规")
            if kind == "reference" and not meta.get("source"):
                warns.append(f"{rel}: reference 缺少 source（外部 URL 或出处）")
            if kind == "tag" and meta.get("tags"):
                warns.append(f"{rel}: tag 节点自身不应有 tags，请用 refs 表达关系")
            for r in meta.get("refs", []):
                if not REF_RE.match(r):
                    errors.append(f"{rel}: refs 编址不合规 '{r}'（应 kind:id）")
                    continue
                rk, rid = r.split(":", 1)
                if rid not in node_ids.get(rk, set()):
                    errors.append(f"{rel}: refs 指向不存在的节点 '{r}'")
            for t in meta.get("tags", []):
                if t not in node_ids.get("tag", set()):
                    errors.append(f"{rel}: tags 指向不存在的 tag '{t}'")
            if not meta.get("keywords"):
                warns.append(f"{rel}: keywords 为空（重要术语写进 keywords 才能被 match 命中）")
            if any(m in item["body"] for m in TEMPLATE_MARKERS):
                warns.append(f"{rel}: 正文仍是模板占位（未完成），补写范围/术语/要点后执行 rebuild")
            missing_secs = [s for s in REQUIRED_SECTIONS.get(kind, ()) if s not in item["body"]]
            if missing_secs:
                warns.append(f"{rel}: 缺少章节 {'、'.join(missing_secs)}（正文未完成）")
            if not meta.get("desc"):
                warns.append(f"{rel}: desc 为空（desc 参与 match 打分）")
            links_parsed = [parse_link(l) for l in meta.get("links", [])]
            for lk in links_parsed:
                if not lk["title"]:
                    warns.append(f"{rel}: link 缺标题 '{lk['url']}'（格式应为 URL|标题）")
            webres = extract_webres_section(item["body"])
            if webres is None:
                if links_parsed:
                    warns.append(f"{rel}: 有 links 但正文缺少 ## 网页资源 章节")
            else:
                table_urls = set(re.findall(r"https?://[^\s|<>）]+", webres))
                for u in sorted({lk["url"] for lk in links_parsed} - table_urls):
                    warns.append(f"{rel}: links 未同步到正文网页资源表：{u}")
                for u in sorted(table_urls - {lk["url"] for lk in links_parsed}):
                    warns.append(f"{rel}: 正文网页资源表含未登记 links 的 URL：{u}")
            if kind == "reference" and not meta.get("tags", []):
                warns.append(f"{rel}: reference 未挂接任何 tag（检索难命中）")
            if kind == "spec" and not meta.get("tags", []) and f"{kind}:{nid}" not in ref_targets:
                warns.append(f"{rel}: spec 未被任何节点挂接（挂 tag 或由他人 --add-ref）")

    # tutorials/ 教程元数据（不参与索引，但须指向真实节点）
    if DIR_TUT.exists():
        for p in sorted(DIR_TUT.glob("*.md")):
            rel = p.relative_to(ROOT).as_posix()
            tmeta, tbody = split_file(p)
            if not tmeta:
                errors.append(f"{rel}: 缺少 frontmatter（kind: tutorial + tags/project/specs）")
                continue
            if "（教程正文）" in tbody:
                warns.append(f"{rel}: 正文仍是模板占位（未完成），补写教程内容")
            if tmeta.get("kind") != "tutorial":
                errors.append(f"{rel}: frontmatter kind 应为 tutorial")
            for t in tmeta.get("tags", []):
                if t not in node_ids.get("tag", set()):
                    errors.append(f"{rel}: tags 指向不存在的 tag '{t}'")
            proj = tmeta.get("project", "")
            if proj and proj not in node_ids.get("project", set()):
                errors.append(f"{rel}: project 指向不存在的节点 '{proj}'")
            for s in tmeta.get("specs", []):
                if s not in node_ids.get("spec", set()):
                    errors.append(f"{rel}: specs 指向不存在的 spec '{s}'")
            if not tmeta.get("tags"):
                warns.append(f"{rel}: 教程未挂任何 tag（不利于检索）")
            missing_tut = [s for s in TUT_REQUIRED_SECTIONS if s not in tbody]
            if missing_tut:
                warns.append(f"{rel}: 缺少章节 {'、'.join(missing_tut)}")
            if "## 延伸阅读" in tbody and not re.search(r"https?://", tbody.split("## 延伸阅读", 1)[1]):
                warns.append(f"{rel}: 延伸阅读未包含任何 URL")

    # INDEX.json 新鲜度
    for k in KINDS:
        if not KIND_INDEX[k].exists():
            errors.append(f"docs/{k}/INDEX.json 缺失（执行 rebuild）")
            continue
        idx = load_index(k).get("nodes", {})
        on_disk = {
            nid: item["hash"] for nid, item in all_nodes[k].items() if item["meta"]
        }
        idx_hashes = {nid: e.get("hash", "") for nid, e in idx.items()}
        if set(idx_hashes) != set(on_disk) or idx_hashes != on_disk:
            warns.append(f"docs/{k}/INDEX.json 过期（文件有变动），执行 rebuild 同步")
    return errors, warns


@app.command()
def check() -> None:
    """健康检查：结构、frontmatter、refs/tags 指向、INDEX.json 新鲜度。"""
    errors, warns = collect_issues()
    if not errors and not warns:
        console.print("[green]✓ 全部通过[/green]：结构与索引一致。")
        return
    for e in errors:
        console.print(f"[red]ERROR[/red] {e}")
    for w in warns:
        console.print(f"[yellow]WARN[/yellow] {w}")
    console.print(f"\n共 {len(errors)} 个错误，{len(warns)} 个警告。")
    if errors:
        console.print("修复建议：改文件后执行 [cyan]python index.py rebuild --fix[/cyan]")
        raise typer.Exit(1)


@app.command()
def rebuild(
    fix: bool = typer.Option(False, "--fix", help="同时修复可自动修复的文件问题（补 kind、清无效 refs/tags）"),
) -> None:
    """重建全部 INDEX.json（绕过脚本动文件后必须执行）。"""
    ensure_dirs()
    if fix:
        fixed = 0
        for kind in KINDS:
            for nid, item in scan_kind(kind).items():
                meta, body = item["meta"], item["body"]
                if not meta:
                    continue
                changed = False
                if meta.get("kind") != kind:
                    meta["kind"] = kind
                    changed = True
                valid_refs = []
                for r in meta.get("refs", []):
                    if REF_RE.match(r):
                        rk, rid = r.split(":", 1)
                        if node_exists(rk, rid):
                            valid_refs.append(r)
                            continue
                    changed = True
                if len(valid_refs) != len(meta.get("refs", [])):
                    meta["refs"] = valid_refs
                if kind == "tag" and meta.get("tags"):
                    meta["tags"] = []
                    changed = True
                if changed:
                    write_node_meta(item["path"], meta, body)
                    fixed += 1
        if fixed:
            console.print(f"[green]fix[/green] 修复了 {fixed} 个文件的 frontmatter。")
    rebuild_all()
    counts = ", ".join(f"{k}={load_index(k).get('count', 0)}" for k in KINDS)
    console.print(f"[green]✓[/green] INDEX.json 已重建（{counts}）。")


if __name__ == "__main__":
    app()
