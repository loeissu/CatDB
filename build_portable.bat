@echo off
chcp 65001 >nul
echo ========================================
echo    豆包喵喵 便携版打包工具 (带图标)
echo ========================================
echo.

REM 检查 Python 是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 未检测到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

echo [1/4] 检查并安装 PyInstaller...
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    pip install pyinstaller
)

echo [2/4] 安装项目依赖...
pip install -r requirements.txt

echo [3/4] 开始打包 (包含图标)...
echo.

REM 使用 PyInstaller 打包
REM --onefile: 打包成单个 exe
REM --console: 保留控制台以显示 IP 地址和提醒
REM 旧的手写 pyinstaller 参数缺少 --add-data www，打出的 EXE 会缺手机页面，已废弃

REM 统一使用 CI 同一份 CatDB.spec（含 www/ 资源、webview/zeroconf hiddenimports）
pyinstaller CatDB.spec --noconfirm

echo.
echo [4/4] 打包完成！
echo.
echo ========================================
echo 📦 便携版位置: dist\CatDB.exe
echo ========================================
echo.
echo 💡 使用方法：
echo    直接双击运行即可。
echo.
pause
