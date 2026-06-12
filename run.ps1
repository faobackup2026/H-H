$host.UI.RawUI.WindowTitle = "Hands & Head by Fao Labs"
Set-Location $PSScriptRoot
Clear-Host
Write-Host @"

 ==============================================
   Hands & Head by Fao Labs  -  v2.0
 ==============================================

"@
if ($env:GEMINI_API_KEY) { Write-Host " [OK] GEMINI_API_KEY configurada" -ForegroundColor Green }
else { Write-Host " [AVISO] GEMINI_API_KEY nao definida" -ForegroundColor Yellow }
if ($env:GITHUB_TOKEN) { Write-Host " [OK] GITHUB_TOKEN configurado`n" -ForegroundColor Green }
else { Write-Host " [AVISO] GITHUB_TOKEN nao definido`n" -ForegroundColor Yellow }
Write-Host " Iniciando servidor..."
Write-Host " UI:   http://localhost:3001"
Write-Host " API:  http://localhost:3001/api"
Write-Host " Chat: Ollama (qwen3:4b)"
Write-Host ""
Start-Sleep 1
Start-Process "http://localhost:3001"
python server.py 3001
