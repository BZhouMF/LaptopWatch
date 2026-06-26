"""LaptopWatch 启动器 — 静默运行同目录下的 start_gui.bat"""
import subprocess
import os
import sys

# --onefile 模式下 sys.executable 指向磁盘上的 EXE 位置（非临时解压目录）
exe_dir = os.path.dirname(sys.executable)
batch_file = os.path.join(exe_dir, 'start_gui.bat')

if os.path.exists(batch_file):
    subprocess.run(
        ['cmd', '/c', batch_file],
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
