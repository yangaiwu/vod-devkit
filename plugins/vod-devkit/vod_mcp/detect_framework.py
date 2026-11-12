"""只读项目识别：语言构成 + 框架/构建工具线索。

对标 huaweicloud-devkit 的 detect-framework*（513 行）：它做的推论比我们多
（框架 → 推荐能力），我们只需要"这是哪个语言/框架的项目"给采集端补上下文，
所以刻意只做**确定性证据**：

- 语言：按扩展名统计文件数（跳过 vendor 目录 / node_modules / .git / 大二进制），
  取前 N 个；不做"猜测比例"。
- 框架/构建：只认标记文件与清单里的显式依赖（package.json 的 dependencies、
  requirements.txt、pyproject.toml、pom.xml、go.mod、Cargo.toml、build.gradle），
  不做字符串模糊匹配——误报比不报更糟（会把运维带偏）。

只读：本模块不写任何文件、不发网络请求。
"""
import json
import os
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", ".venv", "venv",
             "__pycache__", ".mypy_cache", ".pytest_cache", "target", ".idea"}
MAX_FILES = 20000          # 扫描上限：大仓不做全量遍历（41s 索引卡死过 UI）
MAX_DEPTH = 12

LANG_EXT = {
    ".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".jsx": "JavaScript",
    ".java": "Java", ".kt": "Kotlin", ".go": "Go", ".rs": "Rust",
    ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".c": "C", ".cc": "C++",
    ".cpp": "C++", ".h": "C/C++ header", ".swift": "Swift", ".scala": "Scala",
    ".sh": "Shell", ".sql": "SQL", ".vue": "Vue", ".md": "Markdown",
}

# 标记文件 → (种类, 名称)
MARKERS = {
    "package.json": ("node", "npm/node"),
    "pnpm-lock.yaml": ("node", "pnpm"),
    "yarn.lock": ("node", "yarn"),
    "requirements.txt": ("python", "pip"),
    "pyproject.toml": ("python", "pyproject"),
    "setup.py": ("python", "setuptools"),
    "Pipfile": ("python", "pipenv"),
    "pom.xml": ("java", "Maven"),
    "build.gradle": ("java", "Gradle"),
    "build.gradle.kts": ("java", "Gradle"),
    "go.mod": ("go", "Go modules"),
    "Cargo.toml": ("rust", "Cargo"),
    "Gemfile": ("ruby", "Bundler"),
    "composer.json": ("php", "Composer"),
    "Dockerfile": ("infra", "Docker"),
    "docker-compose.yml": ("infra", "Docker Compose"),
    "Makefile": ("infra", "Make"),
}

# 依赖名 → 框架名（只认清单里的显式依赖）
JS_FRAMEWORKS = {
    "react": "React", "vue": "Vue", "next": "Next.js", "nuxt": "Nuxt",
    "express": "Express", "fastify": "Fastify", "koa": "Koa", "@nestjs/core": "NestJS",
    "vite": "Vite", "webpack": "Webpack", "electron": "Electron",
}
PY_FRAMEWORKS = {
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI",
    "torch": "PyTorch", "tensorflow": "TensorFlow", "pytest": "pytest",
    "sqlalchemy": "SQLAlchemy", "pydantic": "Pydantic",
}


def _iter_files(root: Path):
    seen = 0
    root_s = str(root)
    for dirpath, dirnames, filenames in os.walk(root_s):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel = os.path.relpath(dirpath, root_s)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > MAX_DEPTH:
            dirnames[:] = []
            continue
        for name in filenames:
            yield Path(dirpath) / name
            seen += 1
            if seen >= MAX_FILES:
                return


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def _js_frameworks(path: Path) -> list:
    data = _read_json(path)
    names = set()
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        for dep in (data.get(section) or {}):
            if dep in JS_FRAMEWORKS:
                names.add(JS_FRAMEWORKS[dep])
    return sorted(names)


def _py_frameworks(root: Path) -> list:
    names = set()
    req = root / "requirements.txt"
    if req.exists():
        for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
            token = line.strip().split("==")[0].split(">=")[0].split("[")[0].lower()
            if token in PY_FRAMEWORKS:
                names.add(PY_FRAMEWORKS[token])
    pyproj = root / "pyproject.toml"
    if pyproj.exists():
        text = pyproj.read_text(encoding="utf-8", errors="replace").lower()
        for dep, label in PY_FRAMEWORKS.items():
            if f'"{dep}"' in text or f"'{dep}'" in text:
                names.add(label)
    return sorted(names)


def detect(path=".") -> dict:
    """返回 {root, languages[{name,files,share}], markers, frameworks, truncated}。"""
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"{root} 不是目录")
    counts = {}
    truncated = False
    scanned = 0
    for f in _iter_files(root):
        scanned += 1
        ext = f.suffix.lower()
        lang = LANG_EXT.get(ext)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
        if scanned >= MAX_FILES:
            truncated = True
            break
    total = sum(counts.values()) or 1
    languages = [{"name": n, "files": c, "share": round(c / total, 3)}
                 for n, c in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:8]]
    markers = []
    for name, (kind, label) in MARKERS.items():
        if (root / name).exists():
            markers.append({"file": name, "kind": kind, "label": label})
    frameworks = []
    pkg = root / "package.json"
    if pkg.exists():
        frameworks += _js_frameworks(pkg)
    frameworks += _py_frameworks(root)
    return {"root": str(root), "scanned": scanned, "truncated": truncated,
            "languages": languages,
            "markers": sorted(markers, key=lambda m: m["file"]),
            "frameworks": sorted(set(frameworks))}


def summary_line(info: dict) -> str:
    top = "、".join(f"{l['name']} {int(l['share'] * 100)}%" for l in info["languages"][:3])
    parts = [f"主语言 {top}"] if top else ["未识别到源码文件"]
    if info["frameworks"]:
        parts.append("框架 " + "、".join(info["frameworks"][:4]))
    if info["markers"]:
        parts.append("构建 " + "、".join(m["label"] for m in info["markers"][:3]))
    return "；".join(parts)