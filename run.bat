@echo off
cd /d "%~dp0"
cls
echo.
echo  ==============================================
echo    Hands ^& Head by Fao Labs  -  v2.0
echo  ==============================================
echo.
if not "%GEMINI_API_KEY%"=="" echo  [OK] GEMINI_API_KEY configurada
if "%GEMINI_API_KEY%"=="" echo  [AVISO] GEMINI_API_KEY nao definida - gere sites via Gemini
if not "%GITHUB_TOKEN%"=="" echo  [OK] GITHUB_TOKEN configurado
if "%GITHUB_TOKEN%"=="" echo  [AVISO] GITHUB_TOKEN nao definido - deploy GitHub desativado
echo.
echo  Iniciando servidor...
echo.
echo  UI:   http://localhost:3001
echo  API:  http://localhost:3001/api
echo  Chat: Ollama (qwen3:4b)
echo.
timeout /t 2 /nobreak >nul
start http://localhost:3001
C:\Users\cmvgg\AppData\Local\Programs\Python\Python311\python.exe server.py 3001
pause
