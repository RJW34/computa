@echo off
set PATH=C:\Program Files\nodejs;%PATH%
cd /d "%~dp0"
rmdir /s /q node_modules 2>nul
"C:\Program Files\nodejs\npm.cmd" install
