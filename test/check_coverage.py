"""
测试覆盖率检测脚本
扫描项目源文件与测试文件，报告每个模块是否有对应测试，计算覆盖率。

用法:
    python test/check_coverage.py          # 标准模式，输出报告
    python test/check_coverage.py --json   # JSON 格式输出（供程序调用）
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---- 后端源文件 ----
BACKEND_SOURCE_DIRS = {
    "blueprints": ROOT / "blueprints",
    "utils": ROOT / "utils",
}
BACKEND_ROOT_MODULES = [
    "app.py",
    "config.py",
    "qid.py",
    "routes_config.py",
]
BACKEND_TEST_DIR = ROOT / "test"

# ---- 前端源文件 ----
FRONTEND_SRC_DIR = ROOT / "react" / "src"
FRONTEND_TEST_DIR = ROOT / "react" / "src" / "test"

# 不需要测试覆盖的文件（入口 / 类型声明 / 测试工具）
FRONTEND_SKIP = {
    "main.tsx",
    "vite-env.d.ts",
}

# 测试辅助文件（不视作测试用例）
BACKEND_TEST_SKIP = {
    "__init__.py",
    "conftest.py",
    "run_all.py",
    "check_coverage.py",
}
FRONTEND_TEST_SKIP = {
    "setup.ts",
}


def _resolve_test_name(source_stem):
    """将源文件名映射为测试文件名。

    后端: db_utils.py  →  test_db_utils.py
    前端: client.ts    →  client.test.ts
    """
    return f"test_{source_stem}"


def scan_backend():
    """扫描后端源文件与测试文件，返回 (uncovered, covered, test_count, source_count)。"""
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
            # test_db_utils.py → db_utils  (去掉 test_ 前缀)
            stem = test_file.stem
            if stem.startswith("test_"):
                key = stem[len("test_"):]
                test_files[key] = test_file.name

    uncovered = []
    covered = []

    for dir_label, source_path in source_files:
        source_stem = source_path.stem
        expected_test_key = source_stem

        # Exact match first, then fuzzy: test file key contains source stem
        if expected_test_key in test_files:
            covered.append({
                "dir": dir_label,
                "source": source_path.name,
                "test": test_files[expected_test_key],
            })
        elif any(source_stem in test_key or test_key in source_stem
                 for test_key in test_files):
            matched_key = next(
                tk for tk in test_files
                if source_stem in tk or tk in source_stem
            )
            covered.append({
                "dir": dir_label,
                "source": source_path.name,
                "test": test_files[matched_key],
            })
        else:
            uncovered.append({
                "dir": dir_label,
                "source": source_path.name,
            })

    return uncovered, covered, len(test_files), len(source_files)


def scan_frontend():
    """扫描前端源文件与测试文件，返回 (uncovered, covered, test_count, source_count)。"""
    if not FRONTEND_SRC_DIR.is_dir():
        return [], [], 0, 0

    # 收集测试文件
    test_files = {}
    if FRONTEND_TEST_DIR.is_dir():
        for test_file in sorted(FRONTEND_TEST_DIR.glob("*.test.*")):
            if test_file.name in FRONTEND_TEST_SKIP:
                continue
            # client.test.ts → client  (去掉 .test.ts/.test.tsx)
            stem = test_file.stem  # client.test
            if stem.endswith(".test"):
                key = stem[:-len(".test")]
                test_files[key] = test_file.name

    # 收集源文件（排除 test 目录、测试辅助文件、跳过的文件）
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

        rel = source_file.relative_to(FRONTEND_SRC_DIR)
        source_files.append(source_file)

    uncovered = []
    covered = []

    for source_path in source_files:
        source_stem = source_path.stem
        # 子目录下的文件用叶子名匹配（如 components/browse/SelectionBar → SelectionBar）
        leaf_stem = source_stem

        if leaf_stem in test_files:
            covered.append({
                "dir": str(source_path.parent.relative_to(FRONTEND_SRC_DIR)),
                "source": source_path.name,
                "test": test_files[leaf_stem],
            })
        else:
            uncovered.append({
                "dir": str(source_path.parent.relative_to(FRONTEND_SRC_DIR)),
                "source": source_path.name,
            })

    return uncovered, covered, len(test_files), len(source_files)


def print_report(backend_uncovered, backend_covered, backend_tests, backend_sources,
                 frontend_uncovered, frontend_covered, frontend_tests, frontend_sources):
    """打印人类可读的覆盖率报告。"""
    total_covered = len(backend_covered) + len(frontend_covered)
    total_sources = backend_sources + frontend_sources
    total_tests = backend_tests + frontend_tests

    print("=" * 56)
    print("  测试覆盖率报告")
    print("=" * 56)

    # 汇总
    pct = (total_covered / total_sources * 100) if total_sources else 0
    print(f"\n  总源文件: {total_sources}   已覆盖: {total_covered}   测试文件: {total_tests}   覆盖率: {pct:.1f}%")

    # 后端
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

    # 前端
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


def print_json(backend_uncovered, backend_covered, backend_tests, backend_sources,
               frontend_uncovered, frontend_covered, frontend_tests, frontend_sources):
    """JSON 格式输出。"""
    import json
    result = {
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
            "percentage": round(
                ((len(backend_covered) + len(frontend_covered)) / (backend_sources + frontend_sources) * 100), 1
            ) if (backend_sources + frontend_sources) else 0,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    use_json = "--json" in sys.argv

    backend_uncovered, backend_covered, backend_tests, backend_sources = scan_backend()
    frontend_uncovered, frontend_covered, frontend_tests, frontend_sources = scan_frontend()

    if use_json:
        print_json(backend_uncovered, backend_covered, backend_tests, backend_sources,
                   frontend_uncovered, frontend_covered, frontend_tests, frontend_sources)
    else:
        print_report(backend_uncovered, backend_covered, backend_tests, backend_sources,
                     frontend_uncovered, frontend_covered, frontend_tests, frontend_sources)

    # 返回非零退出码表示有未覆盖模块（方便 CI 使用）
    total_uncovered = len(backend_uncovered) + len(frontend_uncovered)
    if total_uncovered > 0:
        sys.exit(0)  # 仅报告，不阻塞


if __name__ == "__main__":
    main()
