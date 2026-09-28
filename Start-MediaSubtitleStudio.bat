@echo off
rem ============================================================
rem  Media Subtitle Studio 便携包 - 启动
rem  自动：切到本目录 -> 用便携包自带的 .venv 启动程序。
rem  未配置过时提示先跑 Setup.bat（不强制，程序自身也能跑）。
rem ============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Media Subtitle Studio

set "LAUNCHER=%~dp0.venv\Scripts\pythonw.exe"
set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [!] 还没有安装运行环境。请先双击 Setup.bat 完成首次配置。
    pause
    exit /b 1
)

rem 配置存在但不完整时给一句提醒（不阻塞启动）
"%PYTHON%" setup_portable.py --check >nul 2>&1
if errorlevel 1 (
    echo [!] 提示：配置不完整（缺依赖 / 权重 / API Key 之一），部分功能不可用。
    echo     可运行 Setup.bat 补齐；现在仍按原样启动。
    timeout /t 4 >nul
)

rem ---- 启动：pythonw 无黑窗；带参数时转发（如拖入媒体文件）----
if exist "%LAUNCHER%" (
    start "" "%LAUNCHER%" "%~dp0media_subtitle_studio.py" %*
) else (
    start "" "%PYTHON%" "%~dp0media_subtitle_studio.py" %*
)
endlocal
