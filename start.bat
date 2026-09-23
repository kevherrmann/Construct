@echo off
setlocal enabledelayedexpansion
rem ============================================================
rem   CONSTRUCT starten - Windows
rem
rem     start.bat            eigenes Fenster
rem     start.bat --web      nur Server auf http://127.0.0.1:8765
rem     start.bat --update   Abhaengigkeiten neu installieren
rem
rem   Gegenstueck zu start.sh. Legt beim ersten Start eine eigene
rem   Python-Umgebung an, benannt nach Plattform und Python-Version -
rem   derselbe Ordner laesst sich damit auch von Linux/Mac aus starten
rem   (USB-Stick), ohne dass sich die Pakete in die Quere kommen.
rem ============================================================
cd /d "%~dp0"

rem ---- Python finden. Der py-Launcher kommt mit dem offiziellen
rem      Installer und trifft die Version zuverlaessiger als "python",
rem      das unter Windows haeufig auf den Store-Platzhalter zeigt.
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo !! Python wurde nicht gefunden.
  echo    Von python.org installieren und dabei "Add Python to PATH" ankreuzen.
  pause
  exit /b 1
)

rem  Ohne Prozentzeichen im Python: in Batch-Dateien ist %% die Escape-Sequenz
rem  fuer ein einzelnes %, und diese Regel mit einer Format-Zeichenkette zu
rem  kreuzen ist eine Fehlerquelle ohne jeden Gegenwert.
for /f "usebackq delims=" %%v in (`%PY% -c "import sys;v=sys.version_info;print(str(v[0])+'.'+str(v[1]))"`) do set "PYVER=%%v"
set "VENV=.venv-Windows-%PROCESSOR_ARCHITECTURE%-py%PYVER%"

set "UPDATE=0"
set "ARGS="
for %%a in (%*) do (
  if /i "%%a"=="--update" (set "UPDATE=1") else (set "ARGS=!ARGS! %%a")
)

rem ---- CONSTRUCT selbst aktualisieren (git, nur Fast-Forward) ----
rem  Exit 10 = aktualisiert -> neu starten. Das MUSS in einem Klammerblock
rem  stehen: cmd liest .bat-Dateien zeilenweise per Byte-Position nach, und
rem  nach dem Update ist diese Datei womoeglich eine andere. Ein Block wird
rem  vorab komplett eingelesen, der Neustart kommt also sicher an.
if not defined CONSTRUCT_UPDATED (
  %PY% selfupdate.py
  if errorlevel 10 (
    set "CONSTRUCT_UPDATED=1"
    "%~f0" %*
    exit /b
  )
)

rem ---- Umgebung anlegen ----
if not exist "%VENV%\Scripts\python.exe" (
  echo ^> lege Python-Umgebung an ^(%VENV%^) ...
  %PY% -m venv "%VENV%" || (echo !! venv liess sich nicht anlegen. & pause & exit /b 1)
  set "UPDATE=1"
)
set "VPY=%VENV%\Scripts\python.exe"

rem ---- Abhaengigkeiten nur bei Aenderung ----
rem  Die Pruefsumme der requirements-Dateien als Stempel: sonst laeuft bei
rem  jedem Start ein pip-Durchlauf, und der kostet auf Windows spuerbar.
set "STAMP=%VENV%\deps-stamp"
for /f "usebackq delims=" %%h in (`%VPY% -c "import zlib,pathlib;d=b''.join(pathlib.Path(f).read_bytes() for f in ('requirements.txt','requirements-desktop.txt') if pathlib.Path(f).exists());print(zlib.crc32(d))"`) do set "NOW=%%h"
set "OLD="
if exist "%STAMP%" set /p OLD=<"%STAMP%"
if "%UPDATE%"=="1" goto install
if not "%OLD%"=="%NOW%" goto install
goto run

:install
echo ^> installiere Abhaengigkeiten ... ^(dauert beim ersten Mal ein, zwei Minuten^)
"%VPY%" -m pip install -q --upgrade pip
"%VPY%" -m pip install -q -r requirements.txt || (echo !! Installation fehlgeschlagen. & pause & exit /b 1)
rem  Fenster-Modus ist Kuer: schlaegt das fehl, laeuft CONSTRUCT im Browser.
"%VPY%" -m pip install -q -r requirements-desktop.txt || echo    ^(pywebview liess sich nicht installieren - es oeffnet sich stattdessen der Browser.^)
> "%STAMP%" echo %NOW%

:run
rem  Kein Hinweis auf ein fehlendes claude-CLI: unter Windows meldet die
rem  Oberflaeche das selbst (der Schluessel-Chip oben rechts), und ohne
rem  Claude Code laeuft der Chat ueber den Anbieter aus dem Modell-Menue.
"%VPY%" desktop.py%ARGS%
if errorlevel 1 pause
endlocal
