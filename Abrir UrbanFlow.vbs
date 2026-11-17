' Abre UrbanFlow sin ventana de consola. Doble clic en este archivo.
Option Explicit

Dim fso, shell, folder, python
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)

Function FindExecutable(fileName)
  Dim pathVar, parts, item, candidate
  FindExecutable = ""
  pathVar = shell.Environment("PROCESS")("PATH")
  parts = Split(pathVar, ";")
  For Each item In parts
    If Len(item) > 0 Then
      candidate = fso.BuildPath(item, fileName)
      If fso.FileExists(candidate) Then
        If fso.GetFile(candidate).Size > 0 Then
          FindExecutable = candidate
          Exit Function
        End If
      End If
    End If
  Next
End Function

python = FindExecutable("pythonw.exe")
If python = "" Then python = FindExecutable("python.exe")
If python = "" Then
  MsgBox "No se encontró Python." & vbCrLf & vbCrLf & "Instalá Python 3 para Windows, con la opción de agregarlo al PATH, y volvé a abrir UrbanFlow.", vbCritical, "UrbanFlow"
  WScript.Quit 1
End If

If Not fso.FileExists(fso.BuildPath(folder, "abrir_urbanflow.py")) Then
  MsgBox "Falta abrir_urbanflow.py junto a este acceso." & vbCrLf & vbCrLf & "No se puede iniciar UrbanFlow.", vbCritical, "UrbanFlow"
  WScript.Quit 1
End If

shell.CurrentDirectory = folder
shell.Run """" & python & """ -B """ & fso.BuildPath(folder, "abrir_urbanflow.py") & """", 0, False
