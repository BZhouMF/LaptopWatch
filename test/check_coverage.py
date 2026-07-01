"""
测试覆盖率检测脚本
用法:
    python test/check_coverage.py              # 标准模式：文件级覆盖报告
    python test/check_coverage.py --deep       # 深度模式：运行覆盖工具，逐函数分析
    python test/check_coverage.py --json       # JSON 格式输出

深度模式依赖:
    后端: pip install coverage (coverage.py)
    前端: Vitest 内置，已安装 @vitest/coverage-v8
"""
import sys
import json
import os
import re
import ast
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REACT_DIR = ROOT / "react"

# ---- 文件级检测（默认模式） ----
BACKEND_SOURCE_DIRS = {
    "blueprints": ROOT / "blueprints",
    "utils": ROOT / "utils",
}
BACKEND_ROOT_MODULES = ["app.py", "config.py", "qid.py", "routes_config.py"]
BACKEND_TEST_DIR = ROOT / "test"
FRONTEND_SRC_DIR = ROOT / "react" / "src"
FRONTEND_TEST_DIR = ROOT / "react" / "src" / "test"

FRONTEND_SKIP = {"main.tsx", "vite-env.d.ts"}
BACKEND_TEST_SKIP = {"__init__.py", "conftest.py", "run_all.py", "check_coverage.py"}
FRONTEND_TEST_SKIP = {"setup.ts"}


def _resolve_test_name(source_stem):
    return f"test_{source_stem}"


# ─── 文件级检测 ───────────────────────────────────────────

def scan_backend():
    source_files = []
    for dir_label, dir_path in BACKEND_SOURCE_DIRS.items():
        if dir_path.is_dir():
            for py_file in sorted(dir_path.glob("*.py")):
                if py_file.name == "__init__.py":
                    continue
                source_files.append((dir_label, py_file))
    for name in BACKEND_ROOT_MODULES:
        py_file = ROOT / name
        if py_file.is_file():
            source_files.append(("root", py_file))

    test_files = {}
    if BACKEND_TEST_DIR.is_dir():
        for test_file in sorted(BACKEND_TEST_DIR.glob("test_*.py")):
            if test_file.name in BACKEND_TEST_SKIP:
                continue
            stem = test_file.stem
            if stem.startswith("test_"):
                key = stem[len("test_"):]
                test_files[key] = test_file.name

    uncovered, covered = [], []
    for dir_label, source_path in source_files:
        expected_key = source_path.stem
        if expected_key in test_files:
            covered.append({"dir": dir_label, "source": source_path.name,
                            "test": test_files[expected_key]})
        elif any(expected_key in tk or tk in expected_key for tk in test_files):
            matched = next(tk for tk in test_files
                           if expected_key in tk or tk in expected_key)
            covered.append({"dir": dir_label, "source": source_path.name,
                            "test": test_files[matched]})
        else:
            uncovered.append({"dir": dir_label, "source": source_path.name})
    return uncovered, covered, len(test_files), len(source_files)


def scan_frontend():
    if not FRONTEND_SRC_DIR.is_dir():
        return [], [], 0, 0

    test_files = {}
    if FRONTEND_TEST_DIR.is_dir():
        for test_file in sorted(FRONTEND_TEST_DIR.glob("*.test.*")):
            if test_file.name in FRONTEND_TEST_SKIP:
                continue
            stem_parts = test_file.name.split(".test.")
            if len(stem_parts) == 2:
                test_files[stem_parts[0]] = test_file.name

    source_files = []
    for source_file in sorted(FRONTEND_SRC_DIR.rglob("*")):
        if source_file.is_dir():
            continue
        if source_file.suffix not in (".ts", ".tsx"):
            continue
        if source_file.name in FRONTEND_SKIP:
            continue
        if "test" in source_file.parts:
            continue
        source_files.append(source_file)

    uncovered, covered = [], []
    for source_path in source_files:
        leaf_stem = source_path.stem
        if leaf_stem in test_files:
            covered.append({"dir": str(source_path.parent.relative_to(FRONTEND_SRC_DIR)),
                            "source": source_path.name, "test": test_files[leaf_stem]})
        else:
            uncovered.append({"dir": str(source_path.parent.relative_to(FRONTEND_SRC_DIR)),
                              "source": source_path.name})
    return uncovered, covered, len(test_files), len(source_files)


# ─── 深度覆盖率检测 ──────────────────────────────────────

def _parse_python_functions(filepath):
    """用 AST 解析 Python 源文件，返回 {函数名: (start_line, end_line)}"""
    funcs = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                if isinstance(node, ast.FunctionDef):
                    # For class methods, prepend class name
                    for parent in ast.iter_child_nodes(tree):
                        if isinstance(parent, ast.ClassDef):
                            for child in ast.walk(parent):
                                if child is node:
                                    name = f"{parent.name}.{node.name}"
                                    break
                funcs[name] = (node.lineno, node.end_lineno or node.lineno)
    except SyntaxError:
        pass
    return funcs


def _parse_typescript_functions(filepath):
    """解析 TS/TSX 文件，识别函数/组件声明，返回 {函数名: start_line}"""
    funcs = {}
    patterns = [
        # export default function Foo()
        (r'export\s+default\s+function\s+(\w+)', 'function'),
        # function Foo()
        (r'^\s*(?:export\s+)?function\s+(\w+)', 'function'),
        # const Foo = () => { or const Foo = function()
        (r'(?:export\s+)?const\s+(\w+)\s*[:=]\s*(?:\([^)]*\)|[^=])\s*=>', 'arrow'),
        # const Foo: React.FC = ...
        (r'(?:export\s+)?const\s+(\w+)\s*:\s*React\.FC', 'component'),
        # class Foo extends
        (r'(?:export\s+)?class\s+(\w+)\s+extends', 'class'),
        # default export brace
        (r'export\s+default\s+function\s+(\w+)', 'default_export'),
    ]
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            for pattern, _kind in patterns:
                match = re.match(pattern, stripped)
                if match:
                    name = match.group(1)
                    if name not in funcs:
                        funcs[name] = idx
                    break
    except Exception:
        pass
    return funcs


def run_backend_coverage():
    """运行 coverage.py，返回 {文件路径: {percent, missing_lines, functions}}"""
    print("[后端] 运行 coverage.py ...", flush=True)

    # Use venv Python if available (where coverage is installed)
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    python_exe = str(venv_python) if venv_python.exists() else sys.executable

    # Run tests with coverage
    data_file = str(ROOT / ".coverage_deep")
    result = subprocess.run(
        [python_exe, "-m", "coverage", "run",
         f"--data-file={data_file}",
         "--source=blueprints,utils",
         "--omit=*/test*",
         "-m", "pytest", str(ROOT / "test"), "-q", "--tb=short",
         "--ignore=test/test_douyin_live.py"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    # Check that tests actually passed, ignoring teardown errors
    if " passed" not in result.stdout and result.returncode != 0:
        print(f"  [WARN] coverage run failed: {result.stderr[-200:]}")

    # Generate JSON report
    json_file = str(ROOT / "coverage_py.json")
    subprocess.run(
        [python_exe, "-m", "coverage", "json",
         f"--data-file={data_file}",
         "-o", json_file, "-q"],
        cwd=str(ROOT),
        capture_output=True,
    )

    if not os.path.exists(json_file):
        print("  [WARN] coverage JSON not generated")
        return {}

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Filter to project files only (skip __init__.py, test files, .venv)
    result_map = {}
    for filepath, info in data.get("files", {}).items():
        if "__init__.py" in filepath or "test" in filepath.lower():
            continue
        if ".venv" in filepath or "site-packages" in filepath:
            continue

        missing_lines = info.get("missing_lines", [])
        pct = info["summary"]["percent_covered"]
        abs_path = filepath if os.path.isabs(filepath) else str(ROOT / filepath)

        # Find which functions contain uncovered lines
        funcs = _parse_python_functions(abs_path) if missing_lines else {}

        # Map uncovered lines to functions
        uncovered_funcs = {}
        for func_name, (func_start, func_end) in sorted(funcs.items()):
            lines_in_func = [l for l in missing_lines if func_start <= l <= func_end]
            if lines_in_func:
                uncovered_funcs[func_name] = lines_in_func

        result_map[filepath] = {
            "percent": pct,
            "missing_lines": missing_lines,
            "uncovered_functions": uncovered_funcs,
        }

    # Cleanup
    for f in [json_file, data_file]:
        try:
            os.remove(f)
        except OSError:
            pass

    return result_map


def run_frontend_coverage():
    """运行 vitest --coverage，返回 {文件路径: {percent, missing_lines, functions}}"""
    print("[前端] 运行 vitest --coverage ...", flush=True)
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"

    result = subprocess.run(
        [npm_cmd, "test", "--", "--coverage", "--reporter=dot"],
        cwd=str(REACT_DIR),
        capture_output=True,
        text=True,
        timeout=180,
    )

    # Parse the text output for per-file coverage
    coverage_data = {}
    # The terminal output format:
    #  FileName.tsx    |  85.00 |   70.00 |   90.00 |   85.00 | 12-15,30
    in_coverage_table = False
    for line in result.stdout.split('\n'):
        line = line.strip()
        if not line:
            continue
        # Detect table header
        if '|' in line and ('File' in line or '---' in line):
            in_coverage_table = True
            continue
        if in_coverage_table and '|' in line:
            parts = line.split('|')
            if len(parts) >= 5:
                file_cell = parts[0].strip()
                # Get the line coverage % and uncovered lines
                try:
                    stmt_pct = parts[1].strip()  # Statements %
                    line_pct = parts[4].strip()  # Lines %
                    uncovered_lines_str = parts[5].strip() if len(parts) > 5 else ""
                except (IndexError, ValueError):
                    continue

                if not file_cell or file_cell.startswith('---'):
                    continue

                # Skip directory-level aggregate entries (no file extension)
                if '.' not in file_cell.rsplit('/', 1)[-1]:
                    continue

                # The file name is the last component
                filename = file_cell.rsplit('/', 1)[-1] if '/' in file_cell else file_cell

                try:
                    line_pct_val = float(line_pct)
                except ValueError:
                    continue

                # Parse uncovered line ranges like "44-640" or "18-19,66-67"
                missing_lines = []
                if uncovered_lines_str and uncovered_lines_str != "100":
                    for part in uncovered_lines_str.split(','):
                        part = part.strip()
                        if '-' in part:
                            try:
                                a, b = part.split('-')
                                missing_lines.extend(range(int(a), int(b) + 1))
                            except ValueError:
                                pass
                        else:
                            try:
                                missing_lines.append(int(part))
                            except ValueError:
                                pass

                # Find the source file
                rel_path = None
                for walk_root, _dirs, files in os.walk(str(FRONTEND_SRC_DIR)):
                    if filename in files and "test" not in walk_root:
                        rel_path = str(Path(walk_root) / filename)
                        break

                if rel_path is None:
                    rel_path = file_cell

                # Map uncovered lines to functions
                funcs = _parse_typescript_functions(rel_path) if missing_lines else {}
                uncovered_funcs = {}
                func_items = sorted(funcs.items(), key=lambda x: x[1])
                for idx, (func_name, func_line) in enumerate(func_items):
                    next_line = func_items[idx + 1][1] if idx + 1 < len(func_items) else 999999
                    lines_in_func = [l for l in missing_lines if func_line <= l < next_line]
                    if lines_in_func:
                        uncovered_funcs[func_name] = lines_in_func

                coverage_data[rel_path] = {
                    "percent": line_pct_val,
                    "missing_lines": missing_lines,
                    "uncovered_functions": uncovered_funcs,
                }

    return coverage_data


# ─── 输出 ──────────────────────────────────────────────────

def print_file_level(backend_uncovered, backend_covered, backend_tests, backend_sources,
                     frontend_uncovered, frontend_covered, frontend_tests, frontend_sources):
    total_covered = len(backend_covered) + len(frontend_covered)
    total_sources = backend_sources + frontend_sources
    total_tests = backend_tests + frontend_tests

    print("=" * 56)
    print("  测试覆盖率报告（文件级）")
    print("=" * 56)

    pct = (total_covered / total_sources * 100) if total_sources else 0
    print(f"\n  总源文件: {total_sources}   已覆盖: {total_covered}   测试文件: {total_tests}   覆盖率: {pct:.1f}%")

    print(f"\n  ── 后端 ──")
    backend_pct = (len(backend_covered) / backend_sources * 100) if backend_sources else 0
    print(f"  源文件: {backend_sources}   已覆盖: {len(backend_covered)}   覆盖率: {backend_pct:.1f}%")
    if backend_covered:
        print("  已覆盖:")
        for item in backend_covered:
            print(f"    [OK] [{item['dir']}] {item['source']}  <-  {item['test']}")
    if backend_uncovered:
        print("  未覆盖:")
        for item in backend_uncovered:
            print(f"    [--] [{item['dir']}] {item['source']}")

    print(f"\n  ── 前端 ──")
    frontend_pct = (len(frontend_covered) / frontend_sources * 100) if frontend_sources else 0
    print(f"  源文件: {frontend_sources}   已覆盖: {len(frontend_covered)}   覆盖率: {frontend_pct:.1f}%")
    if frontend_covered:
        print("  已覆盖:")
        for item in frontend_covered:
            print(f"    [OK] [{item['dir']}] {item['source']}  <-  {item['test']}")
    if frontend_uncovered:
        print("  未覆盖:")
        for item in frontend_uncovered:
            print(f"    [--] [{item['dir']}] {item['source']}")

    print("\n" + "=" * 56)


def print_deep_level(backend_cov, frontend_cov):
    """打印深度覆盖率报告（函数级）"""
    print("=" * 56)
    print("  深度覆盖率报告（函数级）")
    print("=" * 56)

    # ── 后端 ──
    print(f"\n  ── 后端 (coverage.py) ──")
    backend_total_lines = 0
    backend_covered_lines = 0
    files_with_gaps = []

    for filepath, info in sorted(backend_cov.items()):
        pct = info["percent"]
        missing = info["missing_lines"]
        total = len(missing) + (0 if pct == 100 else 0)
        # Approximate: use pct to derive total
        if pct < 100:
            filename = filepath.replace("\\", "/").split("/")[-1]
            uncovered = info["uncovered_functions"]
            print(f"\n  [PY] {filename}  ({pct:.1f}%)")
            if uncovered:
                for fn_name, lines in uncovered.items():
                    range_str = f"第{lines[0]}-{lines[-1]}行" if len(lines) > 1 else f"第{lines[0]}行"
                    print(f"    [XX] {fn_name}()  ->  {range_str}")
            else:
                # Lines uncovered but couldn't map to function
                if missing:
                    sample = missing[:5]
                    print(f"    [XX] 未覆盖行: {sample}{'...' if len(missing) > 5 else ''}")
        else:
            filename = filepath.replace("\\", "/").split("/")[-1]
            print(f"  [PY] {filename}  (100%)")

    # ── 前端 ──
    print(f"\n  ── 前端 (Vitest coverage) ──")

    for filepath, info in sorted(frontend_cov.items()):
        pct = info["percent"]
        filename = filepath.replace("\\", "/").split("/")[-1]

        if pct < 100:
            uncovered = info["uncovered_functions"]
            print(f"\n  [TS] {filename}  ({pct:.1f}%)")
            if uncovered:
                for fn_name, lines in uncovered.items():
                    range_str = f"第{lines[0]}-{lines[-1]}行" if len(lines) > 1 else f"第{lines[0]}行"
                    print(f"    [XX] {fn_name}()  ->  {range_str}")
            else:
                missing = info["missing_lines"]
                if missing:
                    # Group consecutive lines into ranges
                    ranges = []
                    start = missing[0]
                    end = missing[0]
                    for l in missing[1:]:
                        if l == end + 1:
                            end = l
                        else:
                            ranges.append((start, end))
                            start = end = l
                    ranges.append((start, end))
                    for s, e in ranges:
                        label = f"第{s}行" if s == e else f"第{s}-{e}行"
                        print(f"    [XX] (未识别函数) -> {label}")
        else:
            print(f"  [TS] {filename}  (100%)")

    print("\n" + "=" * 56)


def print_json_output(backend_uncovered, backend_covered, backend_tests, backend_sources,
                      frontend_uncovered, frontend_covered, frontend_tests, frontend_sources,
                      backend_cov, frontend_cov):
    result = {
        "file_level": {
            "backend": {
                "sources": backend_sources,
                "tests": backend_tests,
                "covered": len(backend_covered),
                "uncovered": len(backend_uncovered),
                "percentage": round((len(backend_covered) / backend_sources * 100), 1) if backend_sources else 0,
                "uncovered_files": [{"dir": item["dir"], "source": item["source"]} for item in backend_uncovered],
            },
            "frontend": {
                "sources": frontend_sources,
                "tests": frontend_tests,
                "covered": len(frontend_covered),
                "uncovered": len(frontend_uncovered),
                "percentage": round((len(frontend_covered) / frontend_sources * 100), 1) if frontend_sources else 0,
                "uncovered_files": [{"dir": item["dir"], "source": item["source"]} for item in frontend_uncovered],
            },
            "total": {
                "sources": backend_sources + frontend_sources,
                "tests": backend_tests + frontend_tests,
                "covered": len(backend_covered) + len(frontend_covered),
                "uncovered": len(backend_uncovered) + len(frontend_uncovered),
            },
        },
    }
    if backend_cov or frontend_cov:
        result["deep"] = {
            "backend": {fp: {"percent": d["percent"],
                             "uncovered_functions": d["uncovered_functions"]}
                        for fp, d in backend_cov.items()},
            "frontend": {fp: {"percent": d["percent"],
                              "uncovered_functions": d["uncovered_functions"]}
                         for fp, d in frontend_cov.items()},
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ─── Main ───────────────────────────────────────────────────

def main():
    use_json = "--json" in sys.argv
    deep_mode = "--deep" in sys.argv

    # File-level scan (fast, always run)
    backend_uncovered, backend_covered, backend_tests, backend_sources = scan_backend()
    frontend_uncovered, frontend_covered, frontend_tests, frontend_sources = scan_frontend()

    backend_cov = {}
    frontend_cov = {}

    if deep_mode:
        backend_cov = run_backend_coverage()
        frontend_cov = run_frontend_coverage()
        print_deep_level(backend_cov, frontend_cov)
    elif use_json:
        print_json_output(backend_uncovered, backend_covered, backend_tests, backend_sources,
                          frontend_uncovered, frontend_covered, frontend_tests, frontend_sources,
                          backend_cov, frontend_cov)
    else:
        print_file_level(backend_uncovered, backend_covered, backend_tests, backend_sources,
                         frontend_uncovered, frontend_covered, frontend_tests, frontend_sources)


if __name__ == "__main__":
    main()
