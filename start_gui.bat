@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "VENV_ACTIVATE=%SCRIPT_DIR%.venv\Scripts\activate.bat"
set "TARGET_PY=%SCRIPT_DIR%gui.py"

:: 检查文件是否存在
if not exist "%VENV_ACTIVATE%" (
    exit /b 1
)
if not exist "%TARGET_PY%" (
    exit /b 1
)

:: 激活虚拟环境并阻塞运行python（改用python而非pythonw，或监控pythonw进程）
call "%VENV_ACTIVATE%"
:: 方案1：改用python（有控制台，关闭控制台时进程会终止）
:: python "%TARGET_PY%"

:: 方案2：继续用pythonw，但监控进程（推荐）
start /wait pythonw "%TARGET_PY%"

:: 捕获退出码
set "EXIT_CODE=%errorlevel%"

:: 停用虚拟环境
deactivate

:: 额外保险：强制终止残留的 gui.py 进程（通过命令行精确匹配，不误伤其他 pythonw）
powershell -NoProfile "Get-CimInstance Win32_Process -Filter 'Name=\"pythonw.exe\"' | Where-Object { $_.CommandLine -match 'gui.py' } | Stop-Process -Force" >nul 2>&1

exit /b %EXIT_CODE%
endlocal