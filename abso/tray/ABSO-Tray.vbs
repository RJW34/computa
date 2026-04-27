' ABSO-Tray.vbs - Hidden launcher for A.B.S.O. tray application
' Starts PowerShell completely hidden (no console window flash)

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

If UCase(objShell.ExpandEnvironmentStrings("%COMPUTERNAME%")) = "MIRAIDON" Then
    If objShell.ExpandEnvironmentStrings("%ABSO_ALLOW_BACKGROUND_TRAY%") <> "1" Then
        WScript.Quit 0
    End If
End If

' Get script directory
strScriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
strPS1Path = objFSO.BuildPath(strScriptDir, "ABSO-Tray.ps1")

' Launch PowerShell hidden
objShell.Run "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & strPS1Path & """", 0, False

Set objShell = Nothing
Set objFSO = Nothing
