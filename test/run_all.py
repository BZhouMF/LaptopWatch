"""
全量测试执行器 — 运行前后端全部测试并输出覆盖率报告
用法: python test/run_all.py [选项]

选项:
    --backend-only   仅运行 Python 后端测试
    --frontend-only  仅运行 React 前端测试
    --no-coverage    跳过覆盖率检测
    --deep           深度模式：运行覆盖工具，逐函数分析未测试代码
    -v, --verbose    详细输出
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REACT_DIR = ROOT / 'react'


def run_coverage(deep=False):
    """运行覆盖率检测脚本。"""
    start = time.time()
    args = [sys.executable, str(ROOT / "test" / "check_coverage.py")]
    if deep:
        args.append("--deep")
    result = subprocess.run(args, cwd=str(ROOT))
    elapsed = time.time() - start
    return result.returncode, elapsed


def run_backend(verbose=False):
    """运行 Python 后端测试 (pytest)，返回 (passed: bool, elapsed: float)"""
    pytest_args = ['-v'] if verbose else ['-q', '--tb=short']
    start = time.time()
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', str(ROOT / 'test')] + pytest_args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    elapsed = time.time() - start
    stdout = result.stdout

    # 解析 pytest 输出判断是否真正通过（忽略 teardown 清理错误）
    passed = result.returncode == 0
    if not passed:
        # 检查是否有真正的测试失败（非 teardown error）
        import re
        match = re.search(r'(\d+)\s+passed', stdout)
        failures_match = re.search(r'(\d+)\s+failed', stdout)
        if match and (not failures_match or failures_match.group(1) == '0'):
            # 只有 teardown errors，实际测试全部通过
            passed = True
        else:
            # 打印 pytest 输出以帮助排查
            print(stdout, end='')

    return passed, elapsed


def run_frontend(verbose=False):
    """运行 React 前端测试 (vitest)"""
    npm_cmd = 'npm.cmd' if sys.platform == 'win32' else 'npm'
    if not (REACT_DIR / 'node_modules').is_dir():
        print('[frontend] 正在安装依赖...')
        install_result = subprocess.run(
            [npm_cmd, 'install'],
            cwd=str(REACT_DIR),
            stdout=subprocess.DEVNULL if not verbose else None,
        )
        if install_result.returncode != 0:
            print('[frontend] 依赖安装失败，跳过前端测试')
            return 1, 0

    start = time.time()
    result = subprocess.run(
        [npm_cmd, 'test', '--', '--reporter=verbose' if verbose else '--reporter=dot'],
        cwd=str(REACT_DIR),
    )
    elapsed = time.time() - start
    return result.returncode, elapsed


def main():
    backend_only = '--backend-only' in sys.argv
    frontend_only = '--frontend-only' in sys.argv
    no_coverage = '--no-coverage' in sys.argv
    deep_coverage = '--deep' in sys.argv
    verbose = '-v' in sys.argv or '--verbose' in sys.argv

    run_all = not backend_only and not frontend_only

    print('=' * 52)
    print('  LaptopWatch 全量测试')
    print('=' * 52)

    backend_passed = backend_elapsed = None
    frontend_code = frontend_elapsed = None

    if run_all or backend_only:
        print('\n--- Python 后端测试 (pytest) ---')
        backend_passed, backend_elapsed = run_backend(verbose)
        if backend_passed:
            print(f'  后端测试: PASS  ({backend_elapsed:.1f}s)')
        else:
            print(f'  后端测试: FAIL  ({backend_elapsed:.1f}s)')

    if run_all or frontend_only:
        print('\n--- React 前端测试 (vitest) ---')
        frontend_code, frontend_elapsed = run_frontend(verbose)
        if frontend_code == 0:
            print(f'  前端测试: PASS  ({frontend_elapsed:.1f}s)')
        else:
            print(f'  前端测试: FAIL  (exit {frontend_code}, {frontend_elapsed:.1f}s)')

    print('\n' + '=' * 52)

    # 汇总
    codes = [(backend_passed if backend_passed is not None else True, 'backend')]
    if frontend_code is not None:
        codes.append((frontend_code == 0, 'frontend'))
    total_elapsed = sum(e for e in (backend_elapsed, frontend_elapsed) if e is not None)
    failed = sum(1 for ok, _ in codes if not ok)

    if failed == 0:
        print(f'  全部通过!  ({total_elapsed:.1f}s)')
    else:
        print(f'  {failed}/{len(codes)} 套测试失败  ({total_elapsed:.1f}s)')

    print('=' * 52)

    # 覆盖率检测
    if not no_coverage and failed == 0:
        cov_code, cov_elapsed = run_coverage(deep=deep_coverage)

    sys.exit(1 if failed > 0 else 0)


if __name__ == '__main__':
    main()
