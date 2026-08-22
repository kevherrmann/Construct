#!/usr/bin/env bash
# Sagt, warum der Fenster-Modus nicht geht (Linux). Nichts wird verändert.
#   ./check-desktop.sh
cd "$(dirname "$0")"

PYVER=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "?")
VENV=".venv-$(uname -s)-$(uname -m)-py$PYVER"
VPY="$VENV/bin/python"
[ -x "$VPY" ] || VPY=$(command -v python3)

echo "=== System ==="
echo "OS:            $(uname -srm)"
. /etc/os-release 2>/dev/null && echo "Distro:        ${PRETTY_NAME:-?}"
echo "Session:       ${XDG_SESSION_TYPE:-?}  (WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-–}, DISPLAY=${DISPLAY:-–})"
echo "venv-Python:   $("$VPY" -V 2>&1)  [$VPY]"

echo
echo "=== WebKit-Typelibs auf dem System ==="
found=0
for d in /usr/lib64/girepository-1.0 /usr/lib/girepository-1.0 \
         /usr/lib/x86_64-linux-gnu/girepository-1.0 /usr/lib/aarch64-linux-gnu/girepository-1.0; do
  [ -d "$d" ] || continue
  hits=$(ls "$d" 2>/dev/null | grep -iE 'webkit|^Gtk-' || true)
  if [ -n "$hits" ]; then found=1; echo "$d:"; echo "$hits" | sed 's/^/  /'; fi
done
[ "$found" = "1" ] || echo "  ⚠  KEINE gefunden — python3-gobject / WebKitGTK sind nicht installiert."

echo
echo "=== Was Python davon sieht ==="
"$VPY" - <<'PY'
try:
    import gi
    print(f"  gi:          da ({gi.__file__})")
except Exception as e:
    print(f"  gi:          FEHLT ({e})")
    raise SystemExit

for mod, ver in (("WebKit2", "4.1"), ("WebKit2", "4.0"), ("WebKit", "6.0")):
    try:
        gi.require_version(mod, ver)
        __import__(f"gi.repository.{mod}")
        print(f"  {mod}-{ver}:  da")
    except Exception as e:
        print(f"  {mod}-{ver}:  fehlt ({type(e).__name__})")
PY

echo
echo "=== pywebview ==="
"$VPY" - <<'PY'
try:
    import webview
    print(f"  Version:     {getattr(webview, '__version__', '?')}")
except Exception as e:
    print(f"  pywebview:   FEHLT ({e})")
    raise SystemExit
try:
    from webview import guilib
    print(f"  Backend:     {guilib.initialize()}")
except Exception as e:
    print(f"  Backend:     KEINS nutzbar -> {type(e).__name__}: {e}")
PY

echo
echo "=== Fazit ==="
if "$VPY" -c "import gi; gi.require_version('WebKit2','4.1')" 2>/dev/null; then
  echo "  WebKitGTK ist da. Wenn das Fenster trotzdem schwarz bleibt oder"
  echo "  'Protokollfehler' kommt, ist es Wayland — dann probier:"
  echo "      GDK_BACKEND=x11 ./start.sh"
else
  echo "  Es fehlt WebKitGTK bzw. das Python-Binding. Installieren mit:"
  echo "      sudo dnf install python3-gobject webkit2gtk4.1     # Fedora/Nobara"
  echo "      sudo apt install python3-gi gir1.2-webkit2-4.1     # Debian/Ubuntu"
  echo "  Danach reicht ein normales  ./start.sh  — das venv sieht System-Pakete"
  echo "  zur Laufzeit (--system-site-packages), es muss NICHT neu gebaut werden."
fi
