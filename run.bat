@echo off
cd /d "%~dp0"
echo Hands ^& Head by Fao Labs
echo ========================
echo.
echo Verificando GEMINI_API_KEY...
if "%GEMINI_API_KEY%"=="" (
    echo AVISO: GEMINI_API_KEY nao definida!
    echo Configure: set GEMINI_API_KEY=sua-chave-aqui
    echo.
    pause
    exit /b
)
echo KEY ok
echo.
echo Iniciando servidor...
echo.
echo API:  http://localhost:3001/api
echo UI:   http://localhost:3001
echo.
start http://localhost:3001
C:\Users\cmvgg\AppData\Local\Programs\Python\Python311\python.exe server.py 3001
pause
