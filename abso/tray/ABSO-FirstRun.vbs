' ABSO-FirstRun.vbs - opens the computa first-time setup window with no
' console flash. Launched by the installer's finish page or manually.
Option Explicit
Dim shell, scriptDir
Set shell = CreateObject("WScript.Shell")
scriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & scriptDir & "ABSO-FirstRun.ps1""", 0, False
