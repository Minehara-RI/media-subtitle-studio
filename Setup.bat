@echo off
rem ============================================================
rem  Media Subtitle Studio 便携包 - 首次配置（Setup）
rem  双击运行：自动建虚拟环境、装依赖、复制/下载 Whisper 权重、
rem  配置 API Key（有本机既有配置时自动复制，无需手输）、AI 自检。
rem ============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Media Subtitle Studio - Setup

echo.
echo ==== Media Subtitle Studio 便携包配置 ====
echo.

rem ---- 0. 找 Python（优先 py 启动器，其次 python）----
set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python -c "import sys" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [✗] 没有找到 Python。请先安装 Python 3.10+（勾选 Add to PATH）后重试。
    echo     下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [·] 使用解释器：%PY%

rem ---- 1. 跑配置脚本（缺什么补什么；已配置过的项目自动跳过）----
%PY% setup_portable.py %*
set "RC=%ERRORLEVEL%"
if "%RC%"=="" set "RC=1"

if "%RC%"=="0" (
    echo.
    echo [✓] 配置完成！以后双击 Start-MediaSubtitleStudio.bat 即可使用。
) else if "%RC%"=="2" (
    echo.
    echo [!] 配置基本完成，但还有未就绪项（见上方黄色提示）。修正后重跑本脚本即可。
) else (
    echo.
    echo [✗] 配置失败（退出码 %RC%）。按上方提示处理后重试。
)
echo.
pause
endlocal & exit /b %RC%
