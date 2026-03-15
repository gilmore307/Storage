$ProfileName = 'node-2-lab'
python -m pip install pystray pillow psutil pyinstaller
pyinstaller --noconsole --onefile --clean --name $ProfileName --distpath dist --workpath build-work --specpath build-spec --icon resources/OpenClaw.jfif openclaw_node_tray_app.py --hidden-import pystray --hidden-import PIL --hidden-import psutil
New-Item -ItemType Directory -Force -Path (Join-Path 'dist' 'resources'), (Join-Path 'dist' 'generated') | Out-Null
Copy-Item resources\* (Join-Path 'dist' 'resources') -Recurse -Force
Copy-Item "$ProfileName.profile.json" (Join-Path 'dist' "$ProfileName.profile.json") -Force
Write-Host "Built bundle at: $(Resolve-Path dist)"
