@echo off
"%SystemRoot%\System32\chcp.com" 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo [Info] Starting generator...
echo [Info] 입력한 생성 경로가 최종 폴더로 사용됩니다.

set "PYTHON_LAUNCHER="
where python >nul 2>nul
if not errorlevel 1 set "PYTHON_LAUNCHER=python"
if defined PYTHON_LAUNCHER goto run_launcher

where py >nul 2>nul
if not errorlevel 1 set "PYTHON_LAUNCHER=py -3"
if defined PYTHON_LAUNCHER goto run_launcher

echo.
echo [Error] Python launcher not found. Check:
echo   python --version
echo   py -3 --version
echo   pip install anthropic
echo.
pause
exit /b 9009

:run_launcher
echo [Info] Using launcher: %PYTHON_LAUNCHER%
call %PYTHON_LAUNCHER% "%~dp0ai_project_scaffold_generator.py"
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="0" goto success

echo.
echo [Error] Failed. Check:
echo   python --version
echo   py -3 --version
echo   pip install anthropic
echo.
pause
exit /b %EXIT_CODE%

:success
echo.
pause
exit /b 0
