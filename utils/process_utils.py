"""
进程和端口工具函数
gui.py 与 qid.py 共享，避免重复代码
"""
import os
import time
import socket
import subprocess
import signal
import datetime
from pathlib import Path
from typing import List, Optional, Callable


# ==================== 网络工具 ====================

def get_local_ip() -> str:
    """获取本机局域网 IP"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()


# ==================== 端口工具 ====================

_netstat_timeout_count = 0


def check_port(port: int = 5000) -> List[str]:
    """检查端口是否被占用，返回占用进程的 PID 列表"""
    global _netstat_timeout_count

    # socket 快速预检：端口不可达则直接返回空，避免调用 netstat
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        if sock.connect_ex(('127.0.0.1', port)) != 0:
            return []
    except Exception:
        pass
    finally:
        sock.close()

    try:
        result = subprocess.run(
            ['netstat', '-ano'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=2,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        _netstat_timeout_count = 0
        pids = []
        for line in result.stdout.split('\n'):
            if f':{port}' in line and 'LISTENING' in line:
                parts = line.strip().split()
                pid = parts[-1]
                if pid.isdigit() and int(pid) != 0:
                    pids.append(pid)
        return pids
    except subprocess.TimeoutExpired:
        _netstat_timeout_count += 1
        return []
    except Exception:
        return []


def _is_stale_pid_error(err_msg: str) -> bool:
    """判断 taskkill 错误是否为"进程不存在"（stale PID / TIME_WAIT）"""
    return '没有找到' in err_msg or 'not found' in err_msg.lower() or '不存在' in err_msg


def filter_alive_pids(pids) -> list:
    """过滤出实际存活的 PID（排除 TIME_WAIT 等 stale 条目）"""
    alive = []
    for pid in pids:
        try:
            result = subprocess.run(
                ['tasklist', '/FI', f'PID eq {pid}', '/NH'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=3, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            # tasklist 输出格式: "python.exe 13096 Console ..."，
            # PID 是第 2 个字段。不存在时输出语言无关的描述文本。
            parts = result.stdout.strip().split()
            if len(parts) >= 2 and parts[1] == pid:
                alive.append(pid)
        except Exception:
            alive.append(pid)  # 保守：出错时当作存活
    return alive


def force_kill_port(port: int = 5000, log_func: Callable = print):
    """强制释放端口，最多等待约 5 秒"""
    log_func(f' 开始检查端口{port}占用情况...')

    pids = check_port(port)
    if not pids:
        log_func(f' 端口{port}当前空闲，无需释放')
        return

    log_func(f' 端口{port}被占用，PID: {",".join(pids)}')

    # 第一轮 taskkill：对每个 PID 执行，区分正常运行和被 skip 的 stale PID
    killed_any = False
    all_stale = True
    for pid in pids:
        try:
            result = subprocess.run(
                ['taskkill', '/F', '/PID', pid],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=3,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                killed_any = True
                all_stale = False
            else:
                err_msg = result.stderr.strip() or result.stdout.strip() or ''
                if _is_stale_pid_error(err_msg):
                    log_func(f' PID {pid} 已不存在（TCP TIME_WAIT），跳过')
                else:
                    log_func(f' taskkill /F /PID {pid} 返回失败: {err_msg[:120]}')
                    all_stale = False
        except Exception as e:
            log_func(f' taskkill /F /PID {pid} 异常: {e}')
            all_stale = False

    # 全是 stale PID（TCP TIME_WAIT）→ 无法强制释放，短等后返回
    if all_stale:
        log_func(f' 端口{port}处于 TIME_WAIT 状态（PID 已不存在），不影响重启')
        return

    # 成功杀掉了存活 PID → 轮询确认释放（最多 3 秒）
    if killed_any:
        for _ in range(10):
            if not check_port(port):
                log_func(f' 端口{port}已成功释放')
                return
            if not filter_alive_pids(check_port(port)):
                log_func(f' 端口{port}进程已终止（TIME_WAIT 中），不影响重启')
                return
            # 端口仍被占用 → 可能 reloader 重启了新进程，直接杀父进程 + 当前 PID
            alive_pids = filter_alive_pids(check_port(port))
            for new_pid in alive_pids:
                root_pid = find_parent_pid(new_pid)
                if root_pid:
                    log_func(f' 检测到 reloader（父进程 {root_pid}），树杀...')
                    subprocess.run(
                        ['taskkill', '/F', '/T', '/PID', str(root_pid)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        timeout=3, creationflags=subprocess.CREATE_NO_WINDOW
                    )
                subprocess.run(
                    ['taskkill', '/F', '/PID', str(new_pid)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=3, creationflags=subprocess.CREATE_NO_WINDOW
                )
            time.sleep(0.3)

def find_parent_pid(child_pid: str) -> Optional[str]:
    """获取父进程PID，仅上一级（使用 PowerShell，兼容 Windows 11）"""
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             f'Get-CimInstance Win32_Process -Filter "ProcessId={child_pid}" | Select-Object -ExpandProperty ParentProcessId'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=5, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        pid_str = result.stdout.strip()
        if pid_str.isdigit() and pid_str != '0':
            return pid_str
    except Exception:
        pass
    return None


def kill_process_tree(pid: int, log_func: Callable = print):
    """强制终止进程树（Windows）"""
    try:
        subprocess.run(
            ['taskkill', '/F', '/T', '/PID', str(pid)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    except Exception as e:
        if '找不到进程' not in str(e) and 'No such process' not in str(e):
            log_func(f' taskkill树终止失败: {e}')


def stop_process_gracefully(process, process_pid: Optional[int],
                            port: int = 5000, log_func: Callable = print):
    """
    尝试优雅停止进程，逐步升级到强制终止，最后兜底释放端口。
    兼容 Flask reloader 子进程场景。
    """
    if process is None:
        return
    if process.poll() is not None:
        log_func(' 服务进程已退出')
        return

    if os.name == 'nt':
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
        except Exception as e:
            log_func(f' 发送中断信号失败: {e}')
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except Exception as e:
            log_func(f' 终止进程组失败: {e}')

    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        log_func(' 进程未正常退出，强制终止中...')
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()

    if os.name == 'nt' and process_pid:
        kill_process_tree(process_pid, log_func)

    force_kill_port(port, log_func)


# ==================== 会话日志工具 ====================

def save_session_logs(session_logs, session_start_time, session_id,
                      mode='normal', media_dir='', log_func: Callable = print):
    """保存当前会话日志到文件"""
    if not session_logs:
        return
    if not session_start_time:
        session_start_time = datetime.datetime.now()
    if not session_id:
        import uuid
        session_id = str(uuid.uuid4())[:8]

    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True, parents=True)

    timestamp = session_start_time.strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{session_id}.txt"
    filepath = logs_dir / filename

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("=== LaptopWatch 会话日志 ===\n")
            f.write(f"会话ID: {session_id}\n")
            f.write(f"启动时间: {session_start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"结束时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"运行模式: {mode}\n")
            if media_dir:
                f.write(f"媒体目录: {media_dir}\n")
            f.write(f"会话时长: {datetime.datetime.now() - session_start_time}\n")
            f.write("=" * 40 + "\n\n")

            for log_entry in session_logs:
                f.write(f"{log_entry}\n")

            f.write(f"\n" + "=" * 40 + "\n")
            f.write(f"会话结束 - 共 {len(session_logs)} 条日志\n")

        log_func(f' 日志已保存到: {filepath}')

        # 自动清理 7 天前的旧日志
        stale_threshold = datetime.datetime.now() - datetime.timedelta(days=7)
        for old_f in list(logs_dir.iterdir()):
            try:
                date_str = old_f.stem.split('_')[0]
                file_date = datetime.datetime.strptime(date_str, '%Y%m%d')
                if file_date < stale_threshold:
                    old_f.unlink()
            except (ValueError, IndexError):
                continue
    except Exception as e:
        log_func(f'[ERROR] 日志保存失败: {e}')
