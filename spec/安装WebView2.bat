@echo off
chcp 65001 >nul
echo ============================================
echo   一键安装 WebView2 Runtime（国企大表哥 必需）
echo ============================================
echo.
echo 该脚本会下载 Microsoft 官方离线安装器（约 80MB），
echo 用 /silent 静默模式安装，绕开 Edge 状态检测。
echo 如果已安装则会显示"已是最新版本"。
echo.

set "URL=https://go.microsoft.com/fwlink/?linkid=2124701"
set "DEST=%temp%\WebView2RuntimeInstallerX64.exe"

echo [1/3] 下载 WebView2 Standalone 安装包（约 80MB）...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri '%URL%' -OutFile '%DEST%' -UseBasicParsing -ErrorAction Stop; 'Downloaded' } catch { Write-Host ('ERROR: ' + $_.Exception.Message); exit 1 }"
if not exist "%DEST%" (
    echo.
    echo [失败] 下载未完成，请检查网络后重试。
    echo        如公司网络限制，可手动从此地址下载：
    echo        https://developer.microsoft.com/zh-cn/microsoft-edge/webview2/
    echo.
    pause
    exit /b 1
)

echo [2/3] 静默安装 WebView2 Runtime...
"%DEST%" /silent /install
set "RC=%ERRORLEVEL%"
echo        返回码: %RC% （0=成功 / 4=已是最新 / 其他=失败）

echo [3/3] 清理临时文件...
del /f /q "%DEST%" >nul 2>&1

echo.
if "%RC%"=="0" (
    echo [成功] WebView2 已安装！现在可以双击运行 国企大表哥.exe。
) else if "%RC%"=="4" (
    echo [成功] WebView2 已是最新版本！可以直接运行 国企大表哥.exe。
) else (
    echo [失败] 安装未完成（返回码 %RC%）。请尝试：
    echo        1. 关闭所有 Microsoft Edge 窗口
    echo        2. 任务管理器结束所有 msedge.exe 进程
    echo        3. 重新运行本脚本
)
echo.
pause
