#!/bin/sh
# NAVI face kiosk: a bare X server on the DisplayPort panel running face.py.
#
# Started as root by navi-face.service (see navi-face.service next to this file):
#
#   face_kiosk.sh          start Xorg :0 on the panel, then run the client below inside it
#   face_kiosk.sh client   (called by xinit once X is up) disable blanking, run face.py
#                          as bracketbot so it shares uv's cache and the /dev/shm/navi bus
#
# Xorg uses /etc/X11/xorg.conf, which pins the output to DFP-0 (the physical
# DisplayPort) with a forced 1024x600 EDID, because the panel behind the
# DP->HDMI adapter never answers EDID/AUX requests on its own.
set -eu

HERE=$(dirname "$(readlink -f "$0")")
UV=/home/bracketbot/.local/bin/uv

if [ "${1:-}" = client ]; then
    xset s off s noblank -dpms || true          # the face must never blank
    # SDL_AUDIODRIVER=dummy: pygame.init() must not open ALSA; the BBOS speaker
    # daemon owns that device.
    exec runuser -u bracketbot -- env DISPLAY="$DISPLAY" HOME=/home/bracketbot \
        SDL_AUDIODRIVER=dummy "$UV" run "$HERE/face.py"
fi

exec xinit "$0" client -- /usr/lib/xorg/Xorg :0 \
    -config /etc/X11/xorg.conf -nolisten tcp -noreset -nocursor \
    -logfile /var/log/Xorg.face.log vt7
