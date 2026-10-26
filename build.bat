@echo off
chcp 65001 >nul
title Wuwa Tappo 自动按键 - 启动
cd /d "%~dp0"

echo ============================================
echo   Wuwa Tappo 自动按键 - 安装依赖并启动
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.11 或更高版本：
    echo        https://www.python.org/downloads/
    echo        安装时勾选 "Add python.exe to PATH"。
    pause
    exit /b 1
)

echo [1/2] 正在安装依赖（PySide6）...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)

echo [2/2] 启动程序...
python main.py
if errorlevel 1 pause
