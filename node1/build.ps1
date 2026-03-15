$ErrorActionPreference = 'Stop'

$ProfileName = 'node-1-office'
$Root = $PSScriptRoot

python -m pip install pystray pillow psutil pyinstaller

pyinstaller `
 --noconsole `
 --onefile `
 --clean `
 --name $ProfileName `
 --distpath (Join-Path $Root 'dist') `
 --workpath (Join-Path $Root 'build-work') `
 --specpath (Join-Path $Root 'build-spec') `
 --icon (Join-Path $Root 'resources\OpenClaw.jfif') `
 (Join-Path $Root 'openclaw_node_tray_app.py') `
 --hidden-import pystray `
 --hidden-import PIL `
 --hidden-import psutil

if ($LASTEXITCODE -ne 0) {
 throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

New-Item -ItemType Directory -Force -Path `
 (Join-Path $Root 'dist\resources'), `
 (Join-Path $Root 'dist\generated') | Out-Null

Copy-Item (Join-Path $Root 'resources\*') (Join-Path $Root 'dist\resources') -Recurse -Force
Copy-Item (Join-Path $Root "$ProfileName.profile.json") (Join-Path $Root "dist\$ProfileName.profile.json") -Force

Write-Host "Built bundle at: $(Resolve-Path (Join-Path $Root 'dist'))"
