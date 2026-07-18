@echo off
set PATH=C:\msys64\mingw64\bin;C:\Program Files\nodejs;%USERPROFILE%\.cargo\bin;%PATH%
cd /d "%~dp0"
"C:\Program Files\nodejs\npm.cmd" run tauri:dev
