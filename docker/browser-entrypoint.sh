#!/bin/sh
# Virtual screen + window manager + VNC (localhost only) + noVNC web view on :6080, then the given command.
set -e
rm -f /tmp/.X99-lock
Xvfb :99 -screen 0 1440x900x24 -nolisten tcp &
sleep 1
fluxbox >/dev/null 2>&1 &

if [ -z "$VNC_PASSWORD" ]; then
  echo "VNC_PASSWORD is empty: refusing to start the live view without a password" >&2
  exit 1
fi
x11vnc -storepasswd "$VNC_PASSWORD" /tmp/vncpass >/dev/null
# -localhost: VNC itself is reachable only inside the container; noVNC (websockify) is the only way in.
x11vnc -display :99 -forever -shared -rfbauth /tmp/vncpass -rfbport 5900 -localhost -quiet &
websockify --web /usr/share/novnc 6080 localhost:5900 >/dev/null 2>&1 &

# Chrome leaves a lock if the container was killed; it would refuse to start with this profile.
rm -f /profile/SingletonLock /profile/SingletonCookie /profile/SingletonSocket

exec "$@"
