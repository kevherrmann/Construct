# ──────────────────────────────────────────────────────────────────────────
#  CONSTRUCT installieren — Windows
#
#  Rechtsklick auf diese Datei -> "Mit PowerShell ausführen",
#  oder im Terminal:            powershell -ExecutionPolicy Bypass -File install.ps1
#
#  Zwei Wege, beide gültig:
#    1) Repository schon geklont: aus dem Ordner heraus starten
#    2) Nur dieses Skript:        es klont selbst
#
#  Ohne Administratorrechte. Alles landet im Benutzerprofil.
# ──────────────────────────────────────────────────────────────────────────
$ErrorActionPreference = 'Stop'

$RepoSsh   = 'git@github.com:kevherrmann/Construct.git'
$RepoHttps = 'https://github.com/kevherrmann/Construct.git'
$Default   = Join-Path $env:USERPROFILE 'construct'

function Info($m){ Write-Host "» $m" -ForegroundColor Cyan }
function Ok($m)  { Write-Host "  $m" -ForegroundColor Green }
function Warn($m){ Write-Host "  $m" -ForegroundColor Yellow }
function Fail($m){ Write-Host "!! $m" -ForegroundColor Red }

Write-Host @'
 ┌──────────────────────────────────────────────┐
 │   CONSTRUCT  —  Installation (Windows)       │
 └──────────────────────────────────────────────┘
'@

# ---- 1) Python ----
# Mindestens 3.10: app.py nutzt Typannotationen mit "X | Y", die davor nicht
# existieren. Ohne Pruefung scheitert erst der Start, mit einem SyntaxError,
# der wie ein kaputter Download aussieht.
Info 'Python prüfen'
$py = $null
foreach ($cand in @(@('py','-3'), @('python'))) {
  $exe = $cand[0]
  if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
  $args = @($cand[1..($cand.Length-1)]) + @('-c','import sys;raise SystemExit(0 if sys.version_info[:2]>=(3,10) else 1)')
  & $exe @args 2>$null
  if ($LASTEXITCODE -eq 0) { $py = $cand; break }
}
if (-not $py) {
  Fail 'Kein Python 3.10 oder neuer gefunden.'
  Warn 'Installieren:  winget install Python.Python.3.12'
  Warn 'Oder von python.org — dabei "Add Python to PATH" ankreuzen.'
  Read-Host 'Enter zum Beenden'; exit 1
}
$pyExe = $py[0]; $pyArgs = @($py[1..($py.Length-1)])
Ok ((& $pyExe @pyArgs '--version') 2>&1)

# ---- 2) Quellcode ----
$dir = $null
if ((Test-Path 'app.py') -and (Test-Path 'start.bat')) {
  $dir = (Get-Location).Path
  Info "Projekt gefunden: $dir"
  if ((Test-Path '.git') -and (Get-Command git -ErrorAction SilentlyContinue)) {
    git pull --ff-only 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Ok 'auf aktuellen Stand gebracht' }
    else { Warn '(nicht aktualisiert — lokale Änderungen oder kein Zugriff)' }
  }
} else {
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail 'git wird gebraucht, um CONSTRUCT zu holen.'
    Warn 'Installieren:  winget install Git.Git'
    Read-Host 'Enter zum Beenden'; exit 1
  }
  $answer = Read-Host "Wohin installieren? [$Default]"
  $dir = if ([string]::IsNullOrWhiteSpace($answer)) { $Default } else { $answer }
  if (Test-Path (Join-Path $dir '.git')) {
    Info 'Vorhandene Installation aktualisieren'
    git -C $dir pull --ff-only | Out-Null
  } else {
    Info "CONSTRUCT holen nach $dir"
    # SSH zuerst: das Repository ist privat, und wer Zugriff hat, hat meist
    # einen Schluessel. HTTPS als Rueckfall fragt nach Zugangsdaten.
    git clone $RepoSsh $dir 2>$null
    if ($LASTEXITCODE -ne 0) { git clone $RepoHttps $dir }
    if ($LASTEXITCODE -ne 0) {
      Fail 'Klonen fehlgeschlagen.'
      Warn 'Das Repository ist privat — du brauchst Zugriff darauf.'
      Read-Host 'Enter zum Beenden'; exit 1
    }
  }
}
Set-Location $dir

# ---- 3) Umgebung bauen ----
Info 'Python-Umgebung und Abhängigkeiten'
$ver  = (& $pyExe @pyArgs '-c' 'import sys;v=sys.version_info;print(str(v[0])+"."+str(v[1]))').Trim()
$venv = ".venv-Windows-$env:PROCESSOR_ARCHITECTURE-py$ver"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
  & $pyExe @pyArgs -m venv $venv
  if ($LASTEXITCODE -ne 0) { Fail 'venv liess sich nicht anlegen.'; Read-Host 'Enter'; exit 1 }
}
$vpy = Join-Path $dir "$venv\Scripts\python.exe"
& $vpy -m pip install -q --upgrade pip
& $vpy -m pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail 'Installation der Abhängigkeiten fehlgeschlagen.'; Read-Host 'Enter'; exit 1 }
# Fenster-Modus ist Kuer: schlaegt das fehl, laeuft CONSTRUCT im Browser.
& $vpy -m pip install -q -r requirements-desktop.txt 2>$null
if ($LASTEXITCODE -ne 0) { Warn '(pywebview nicht installierbar — es öffnet sich dann der Browser)' }
Ok 'fertig'

# ---- 4) Verknuepfungen ----
Info 'Verknüpfungen anlegen'
$target = Join-Path $dir 'start.bat'
$icon   = Join-Path $dir 'static\icon-256.png'
$shell  = New-Object -ComObject WScript.Shell
foreach ($place in @(
    [pscustomobject]@{ Path = [Environment]::GetFolderPath('Desktop'); Name = 'Desktop' },
    [pscustomobject]@{ Path = (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'); Name = 'Startmenü' })) {
  try {
    $lnk = $shell.CreateShortcut((Join-Path $place.Path 'CONSTRUCT.lnk'))
    $lnk.TargetPath       = $target
    $lnk.WorkingDirectory = $dir
    $lnk.Description      = 'CONSTRUCT — Oberfläche für Claude Code'
    # .lnk kann kein PNG als Symbol; ohne .ico bleibt das Standardsymbol.
    if (Test-Path ($icon -replace '\.png$','.ico')) { $lnk.IconLocation = ($icon -replace '\.png$','.ico') }
    $lnk.Save()
    Ok "$($place.Name)-Verknüpfung angelegt"
  } catch { Warn "$($place.Name)-Verknüpfung übersprungen" }
}

Write-Host ''
Write-Host "✓ CONSTRUCT ist installiert in $dir" -ForegroundColor Green
Write-Host @"

  Starten:      Doppelklick auf CONSTRUCT (Desktop oder Startmenü)
                oder start.bat im Ordner
  Nur Server:   start.bat --web      -> http://127.0.0.1:8765

  Danach in der Oberfläche unter (Zahnrad) Einstellungen:
    - Kacheln aussuchen, Farbwelt und Hintergrund wählen
    - unter "Modelle & Anbieter" festlegen, womit du redest

  Ohne weitere Einrichtung kann CONSTRUCT noch nichts — es braucht
  entweder Claude Code (Anthropic-Konto, voller Zugriff) oder den
  API-Schlüssel eines Chat-Anbieters. Beides steht dort erklärt.

  Unter Windows meldet man sich bei Claude Code EINMAL im Terminal an:
  'claude' eingeben und dem Login folgen. Der Login-Knopf in der
  Oberfläche braucht ein Pseudo-Terminal, das es hier nicht gibt.
"@
Read-Host 'Enter zum Schliessen'
