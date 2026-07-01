"""
全量测试执行器 — 运行前后端全部测试并输出覆盖率报告
用法: python test/run_all.py [选项]

选项:
    --backend-only   仅运行 Python 后端测试
    --frontend-only  仅运行 React 前端测试
    --no-coverage    跳过覆盖率检测
    -v, --verbose    详细输出
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REACT_DIR = ROOT / 'react'


def run_coverage():
    """运行覆盖率检测脚本。"""
    start = time.time()
    result = subprocess.run(
        [sys.executable, str(ROOT / "test" / "check_coverage.py")],
        cwd=str(ROOT),
    )
    elapsed = time.time() - start
    return result.returncode, elapsed


def run_backend(verbose=False):
    """运行 Python 后端测试 (pytest)"""
    pytest_args = ['-v'] if verbose else ['-q', '--tb=short']
    start = time.time()
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', str(ROOT / 'test')] + pytest_args,
        cwd=str(ROOT),
    )
    elapsed = time.time() - start
    return result.returncode, elapsed


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
    verbose = '-v' in sys.argv or '--verbose' in sys.argv

    run_all = not backend_only and not frontend_only

    print('=' * 52)
    print('  LaptopWatch 全量测试')
    print('=' * 52)

    backend_code = backend_elapsed = None
    frontend_code = frontend_elapsed = None

    if run_all or backend_only:
        print('\n--- Python 后端测试 (pytest) ---')
        backend_code, backend_elapsed = run_backend(verbose)
        if backend_code == 0:
            print(f'  后端测试: PASS  ({backend_elapsed:.1f}s)')
        else:
            print(f'  后端测试: FAIL  (exit {backend_code}, {backend_elapsed:.1f}s)')

    if run_all or frontend_only:
        print('\n--- React 前端测试 (vitest) ---')
        frontend_code, frontend_elapsed = run_frontend(verbose)
        if frontend_code == 0:
            print(f'  前端测试: PASS  ({frontend_elapsed:.1f}s)')
        else:
            print(f'  前端测试: FAIL  (exit {frontend_code}, {frontend_elapsed:.1f}s)')

    print('\n' + '=' * 52)

    # 汇总
    codes = [c for c in (backend_code, frontend_code) if c is not None]
    total_elapsed = sum(e for e in (backend_elapsed, frontend_elapsed) if e is not None)
    failed = sum(1 for c in codes if c != 0)

    if failed == 0:
        print(f'  全部通过!  ({total_elapsed:.1f}s)')
    else:
        print(f'  {failed}/{len(codes)} 套测试失败  ({total_elapsed:.1f}s)')

    print('=' * 52)

    # 覆盖率检测
    if not no_coverage and failed == 0:
        cov_code, cov_elapsed = run_coverage()

    sys.exit(1 if failed > 0 else 0)


if __name__ == '__main__':
    main()
