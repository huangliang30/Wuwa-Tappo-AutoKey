@echo off
chcp 65001 >nul
title Wuwa Tappo 自动按键 - 打包 EXE
cd /d "%~dp0"

echo ============================================
echo   Wuwa Tappo 自动按键 - 打包为单文件 EXE
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.11 或更高版本。
    pause
    exit /b 1
)

echo [1/3] 正在安装依赖...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)

echo [2/3] 正在打包（约 1~3 分钟）...
python -m PyInstaller --noconfirm --onefile --windowed ^
    --name "WuwaTappo自动按键" ^
    --collect-submodules PySide6 ^
    main.py
if errorlevel 1 (
    echo [错误] 打包失败。常见原因：
    echo   1. 杀毒软件拦截 —— 请添加本目录到白名单后重试；
    echo   2. 磁盘空间不足 —— PyInstaller 需要 2GB 以上临时空间；
    echo   3. 路径含特殊字符 —— 可将项目复制到纯英文路径重试。
    pause
    exit /b 1
)

echo [3/3] 打包完成！
echo.
echo   输出文件：%~dp0dist\WuwaTappo自动按键.exe
echo.
echo   提示：单文件 EXE 首次启动需解压，等待 2~5 秒属正常现象。
echo         如被杀毒软件误报，请添加信任或改用 --onedir 模式打包。
echo.
pause
