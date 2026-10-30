Option Explicit

Dim shell
Dim fso
Dim workspace
Dim scriptPath
Dim command
Dim exitCode

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

workspace = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = workspace
scriptPath = workspace & "\scripts\app-start.ps1"

If Not fso.FileExists(scriptPath) Then
    MsgBox _
        "Could not find:" & vbCrLf & scriptPath, _
        vbCritical, _
        "News Intelligence Platform"
    WScript.Quit 2
End If

command = _
    "powershell.exe -NoLogo -NoProfile " & _
    "-ExecutionPolicy Bypass " & _
    "-WindowStyle Hidden " & _
    "-File """ & scriptPath & """"

' 0 = hidden window
' True = wait until PowerShell finishes
exitCode = shell.Run(command, 0, True)

If exitCode <> 0 Then
    MsgBox _
        "News Intelligence could not be started." & vbCrLf & vbCrLf & _
        "Check the logs in:" & vbCrLf & _
        workspace & "\.run\logs", _
        vbCritical, _
        "News Intelligence Platform"
End If

WScript.Quit exitCode
