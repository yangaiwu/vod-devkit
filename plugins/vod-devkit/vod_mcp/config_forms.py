"""宿主配置文件的形态分类与受管块扫描（单一实现，零第三方依赖）。

背景：安装器要改两类文本配置——codex 的 `config.toml` 与 dsh 的
`cordis.patch.yml`。历史缺陷全都是"尽力猜"造成的：

- TOML：`args = ["…"]` 行内方括号让正则提前断块 → 旧 env 子表残留；
  更隐蔽的一层是残留的子表 `[mcp_servers.vod-devkit.env]` 在 TOML 语义里
  会**重新创建父表**——于是装出一个没有 command 的假 server，改完配置
  反而更坏。
- YAML：模板里的字面量 `[]` 顶层行 + 追加 `- id:` = 非法 YAML，整个
  profile 启动崩溃；dsh 运行期序列化还会冲掉"打平"的块。

借鉴 huaweicloud-devkit 的纪律（`mcp-config-merge.ts`）：**一个扫描器同时
支撑写入、删除与增量**，非已知形态在改字节**之前**拒绝——宁可装不上，
不可改坏用户文件。本模块只做分类与扫描，不做 IO，也不做"修复"。
"""
import re

# 受管 TOML 表前缀：本插件拥有该表及其全部子表
TOML_MANAGED = "mcp_servers.vod-devkit"

_HEADER = re.compile(r"^\[([^\[\]]+)\]$")
_MAPPING_ROOT = re.compile(r"^[A-Za-z_][\w.\-]*\s*:")
_DSH_ID = "- id: vod-devkit"


class Refused(Exception):
    """文件形态不在已知集合内：调用方必须原样放弃修改（字节不变）。"""


# ---------------- TOML ----------------

def _split_header(line: str):
    """行 → 表名；非表头返回 None。空行/注释返回 ""。"""
    s = line.strip()
    if not s or s.startswith("#"):
        return ""
    # 表头允许行尾注释：`[a.b] # note`（表名里不会出现 #）
    if "#" in s:
        s = s.split("#", 1)[0].strip()
    m = _HEADER.match(s)
    if m:
        return m.group(1).strip()
    if s.startswith("["):
        raise Refused(f"疑似表头但不合法：{line.rstrip()[:60]}")
    return None


def scan_toml_sections(text: str) -> list:
    """按行扫描 TOML 表：返回 [{name, start, end}]（end 为下一个表头行，排他）。"""
    lines = text.splitlines()
    heads = []  # (name, line_no)
    for i, line in enumerate(lines):
        name = _split_header(line)
        if name:
            heads.append((name, i))
    out = []
    for idx, (name, start) in enumerate(heads):
        end = heads[idx + 1][1] if idx + 1 < len(heads) else len(lines)
        out.append({"name": name, "start": start, "end": end})
    return out


def classify_codex_toml(text: str) -> tuple:
    """codex config.toml 形态判定 → (verdict, reason)；verdict ∈ {ok, refuse}。

    拒绝条件（都会让"删我们那一段"变成不安全的操作）：
    - 表头重复定义（TOML 本身非法；删哪一份都是猜）
    - 出现"疑似表头"的畸形行（我们的扫描器与用户的文件理解不一致）
    """
    sections = scan_toml_sections(text)  # 畸形表头在此抛 Refused
    seen = set()
    for sec in sections:
        if sec["name"] in seen:
            return "refuse", f"表头重复定义 [{sec['name']}]（TOML 非法，拒绝猜测）"
        seen.add(sec["name"])
    return "ok", ""


def managed_toml_sections(sections: list) -> list:
    """属于本插件的表（含子表）：name == 前缀 或 name.startswith(前缀 + ".")。"""
    return [s for s in sections
            if s["name"] == TOML_MANAGED or s["name"].startswith(TOML_MANAGED + ".")]


def strip_managed_toml(text: str) -> tuple:
    """删除本插件拥有的全部 TOML 段（含子表）→ (new_text, removed_names)。

    子表必须一起删：留下 `[mcp_servers.vod-devkit.env]` 会在 TOML 语义里
    重建父表，得到一个没有 command 的 vod-devkit server（旧实现的残留 bug）。
    """
    sections = scan_toml_sections(text)
    doomed = managed_toml_sections(sections)
    if not doomed:
        return text.rstrip(), []
    lines = text.splitlines()
    drop = set()
    for sec in doomed:
        drop.update(range(sec["start"], sec["end"]))
    kept = [ln for i, ln in enumerate(lines) if i not in drop]
    return "\n".join(kept).rstrip(), [s["name"] for s in doomed]


# ---------------- YAML（dsh cordis.patch.yml） ----------------

def classify_dsh_patch(lines: list) -> tuple:
    """dsh profile patch 形态判定 → (verdict, reason)。

    这个文件是**顶层数组**（元素形如 `- insert:`）。拒绝条件：
    - 缩进里有 tab（YAML 禁止 tab 缩进，任何解析器行为都不可依赖）
    - 根是映射（追加顶层数组元素会造出非法文档）
    - 根是 flow 集合（`{...}` / `[...]`，同上；字面量 `[]` 占位例外）
    - 本插件的 `- id: vod-devkit` 出现多次（删/替换哪一份都是猜）
    """
    for ln in lines:
        lead = ln[:len(ln) - len(ln.lstrip())]
        if "\t" in lead:
            return "refuse", "缩进含 tab（YAML 禁止 tab 缩进）"
    significant = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    if not significant:
        return "ok", ""
    root = significant[0].strip()
    if root.startswith("{") or (root.startswith("[") and root != "[]"):
        return "refuse", f"根节点是 flow 集合（{root[:20]}），本插件只写块数组"
    if _MAPPING_ROOT.match(root):
        return "refuse", f"根节点是映射（{root[:20]}），不是本插件写的顶层数组"
    if sum(1 for ln in lines if ln.strip().startswith(_DSH_ID)) > 1:
        return "refuse", "出现多个 `- id: vod-devkit` 块（无法判定哪一份是活的）"
    return "ok", ""


def find_dsh_block(lines: list) -> tuple:
    """定位 vod-devkit 块的 (start, end)；不存在返回 (None, None)。

    块边界=下一顶层元素行（`- ` 开头）或 EOF。嵌套铁律（真机实锤）：
    dsh 只认缩进在 `- insert:` 之下的块——命中行带缩进时 start 向上归并到
    该组头，整组替换；历史平铺形态按原语义顶格替换。install 的幂等 upsert
    与 uninstall 的摘除共用本边界语义（单一实现，防两处扫描规则漂移）。
    """
    for i, ln in enumerate(lines):
        if ln.strip().startswith(_DSH_ID):
            start = i
            if ln[:1] == " ":  # 嵌套形态：向上归并组头
                for k in range(i - 1, -1, -1):
                    if lines[k].startswith("- "):
                        start = k
                        break
            end = len(lines)
            for j in range(start + 1, len(lines)):
                if lines[j].startswith("- "):
                    end = j
                    break
            return start, end
    return None, None