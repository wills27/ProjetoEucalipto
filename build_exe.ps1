$ErrorActionPreference = "Stop"

python -m PyInstaller --clean CellposeLineofCode.spec

Write-Host ""
Write-Host "Build concluido em: dist\CellposeLineofCode\CellposeLineofCode.exe"
Write-Host "Os projetos do usuario ficam fora do executavel, por padrao em Documents\CellposeProjects."
