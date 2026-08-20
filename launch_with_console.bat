@echo off
REM ============================================
REM   春雪考研 - 启动脚本 (Windows)
REM   双击即可运行, 错误信息会显示在控制台
REM ============================================

cd /d %~dp0

REM 检查 Python
where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python, 请先安装 Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 第一次运行安装依赖
if not exist .installed (
    echo [首次运行] 正在安装依赖...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败, 请检查网络
        pause
        exit /b 1
    )
    echo. > .installed
    echo [完成] 依赖已安装
)

REM 启动主程序
python spring_snow_pyqt.py
pause
