' Starts Speedy Scandocs with no console window.
' The first time, it installs the Python libraries the app needs.

Option Explicit
Dim shell, fso, here, extra, check, answer
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = here

extra = ""
If WScript.Arguments.Count > 0 Then extra = " " & WScript.Arguments(0)

If shell.Run("cmd /c where pythonw", 0, True) <> 0 Then
    MsgBox "Python isn't installed." & vbCrLf & vbCrLf & _
           "Install Python 3.11 or newer from python.org, and tick ""Add to PATH""." & vbCrLf & _
           "Then open Speedy Scandocs again.", vbExclamation, "Speedy Scandocs"
    WScript.Quit 1
End If

check = "python """ & here & "\check_setup.py"""

If shell.Run("cmd /c """ & check & """", 0, True) <> 0 Then
    answer = MsgBox("Speedy Scandocs needs to install a few things the first time." & vbCrLf & _
                    "This takes a minute or two. Continue?", vbOKCancel + vbInformation, "Speedy Scandocs")
    If answer <> vbOK Then WScript.Quit 0
    shell.Run "cmd /c python -m pip install -r requirements.txt", 1, True
    If shell.Run("cmd /c """ & check & """", 0, True) <> 0 Then
        MsgBox "The install didn't finish. Check the internet connection and try again.", _
               vbExclamation, "Speedy Scandocs"
        WScript.Quit 1
    End If
End If

shell.Run "pythonw """ & here & "\app.py""" & extra, 1, False
