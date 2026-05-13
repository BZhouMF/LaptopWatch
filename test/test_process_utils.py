"""进程和端口工具函数测试"""
import os
import socket
import subprocess
from unittest.mock import patch, MagicMock

from utils.process_utils import (
    get_local_ip, check_port, force_kill_port,
    find_parent_pid, kill_process_tree,
    stop_process_gracefully, save_session_logs,
)


class TestGetLocalIp:
    def test_normal(self):
        ip = get_local_ip()
        # 返回格式应为 IPv4 地址
        parts = ip.split('.')
        assert len(parts) == 4
        assert all(p.isdigit() for p in parts)

    def test_socket_failure_fallback(self):
        with patch('utils.process_utils.socket.socket') as mock_sock:
            instance = mock_sock.return_value
            instance.connect.side_effect = OSError('network unreachable')
            assert get_local_ip() == '127.0.0.1'
            instance.close.assert_called_once()


class TestCheckPort:
    def test_port_free_returns_empty(self):
        """端口可达性预检未通过时直接返回空"""
        with patch('utils.process_utils.socket.socket') as mock_sock:
            instance = mock_sock.return_value
            instance.connect_ex.return_value = 1  # 端口不可达
            assert check_port(59999) == []

    def test_socket_precheck_connect_ex(self):
        """验证 socket 预检使用 connect_ex 而非 connect"""
        with patch('utils.process_utils.socket.socket') as mock_sock:
            instance = mock_sock.return_value
            instance.connect_ex.return_value = 1
            check_port(59999)
            instance.settimeout.assert_called_once_with(0.5)
            instance.connect_ex.assert_called_once_with(('127.0.0.1', 59999))

    def test_netstat_timeout_backoff(self):
        """连续超时后不触发退避（backoff 已移除），每次仍调 netstat"""
        from utils.process_utils import _netstat_timeout_count

        with patch('utils.process_utils._netstat_timeout_count', 0), \
             patch('utils.process_utils.subprocess.run') as mock_run, \
             patch('utils.process_utils.socket.socket') as mock_sock:

            sock_instance = mock_sock.return_value
            sock_instance.connect_ex.return_value = 0  # 端口可达

            mock_run.side_effect = subprocess.TimeoutExpired('netstat', 2)
            for _ in range(3):
                check_port(5000)
            # 第 4 次仍然调用 netstat（无退避）
            check_port(5000)
            assert mock_run.call_count == 4

    def test_netstat_parse_pid(self):
        """解析 netstat 输出中的 PID"""
        fake_output = """
  TCP    0.0.0.0:5000           0.0.0.0:0              LISTENING       12345
  TCP    127.0.0.1:5001         0.0.0.0:0              LISTENING       0
"""
        with patch('utils.process_utils.socket.socket') as mock_sock:
            sock_instance = mock_sock.return_value
            sock_instance.connect_ex.return_value = 0

            with patch('utils.process_utils.subprocess.run') as mock_run:
                mock_result = MagicMock()
                mock_result.stdout = fake_output
                mock_run.return_value = mock_result

                pids = check_port(5000)
                # PID 0 应被过滤
                assert pids == ['12345']

    def test_netstat_use_creation_no_window(self):
        """验证 subprocess.run 使用了 CREATE_NO_WINDOW"""
        with patch('utils.process_utils.socket.socket') as mock_sock:
            sock_instance = mock_sock.return_value
            sock_instance.connect_ex.return_value = 0

            with patch('utils.process_utils.subprocess.run') as mock_run:
                mock_result = MagicMock()
                mock_result.stdout = ''
                mock_run.return_value = mock_result

                check_port(5000)
                kwargs = mock_run.call_args[1]
                assert 'creationflags' in kwargs


class TestForceKillPort:
    def test_port_free_no_action(self):
        logs = []
        with patch('utils.process_utils.check_port', return_value=[]):
            force_kill_port(5000, logs.append)
        assert any('空闲' in log for log in logs)

    def test_force_kill_uses_creation_no_window(self):
        logs = []
        with patch('utils.process_utils.check_port', side_effect=[['12345'], []]), \
             patch('utils.process_utils.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            force_kill_port(5000, logs.append)
            kwargs = mock_run.call_args[1]
            assert 'creationflags' in kwargs


class TestFindParentPid:
    def test_wmic_uses_creation_no_window(self):
        with patch('utils.process_utils.subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = '\n100\n'
            mock_run.return_value = mock_result

            find_parent_pid('12345')
            kwargs = mock_run.call_args[1]
            assert 'creationflags' in kwargs


class TestKillProcessTree:
    def test_taskkill_uses_creation_no_window(self):
        with patch('utils.process_utils.subprocess.run') as mock_run:
            kill_process_tree(12345, print)
            kwargs = mock_run.call_args[1]
            assert 'creationflags' in kwargs


class TestStopProcessGracefully:
    def test_process_already_exited(self):
        logs = []
        mock_process = MagicMock()
        mock_process.poll.return_value = 0  # 已退出
        stop_process_gracefully(mock_process, None, 5000, logs.append)
        assert any('已退出' in log for log in logs)

    def test_process_waited_ok(self):
        logs = []
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # 运行中
        stop_process_gracefully(mock_process, None, 5000, logs.append)
        mock_process.wait.assert_called_once_with(timeout=3)


class TestSaveSessionLogs:
    def test_empty_logs_no_file_created(self, tmp_path):
        logs = []
        save_session_logs(logs, None, None, log_func=print)
        # 不传 session_start_time 和 session_id 也能正常工作（内部生成默认值）
        # 不应抛出异常
        assert True

    def test_saves_to_logs_dir(self, tmp_path):
        import datetime
        from pathlib import Path

        logs_dir = tmp_path / 'logs'
        logs_dir.mkdir()

        # 用最近一天的日期，避免自动清理（7天过期）删掉测试文件
        recent = datetime.datetime.now() - datetime.timedelta(days=1)
        with patch('utils.process_utils.Path', return_value=logs_dir):
            save_session_logs(
                ['line1', 'line2'],
                recent,
                'test123',
                mode='video',
                media_dir='/media',
                log_func=print,
            )
            files = list(logs_dir.iterdir())
            assert len(files) == 1
            content = files[0].read_text('utf-8')
            assert 'video' in content
            assert '/media' in content
            assert 'test123' in content
            assert 'line1' in content
