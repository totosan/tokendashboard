#!/usr/bin/env bash
# Idempotent installer for the bounded Bitget recorder on a Raspberry Pi (issue #26).
# Run by the user on the Pi from a checkout: sudo bash research/recorder/install_pi.sh
# No secrets are used or stored; no network listeners are opened (outbound public HTTPS only).
set -euo pipefail

SVC_USER="bitget-recorder"
APP_DIR="/opt/bitget-recorder"
LEGACY_DIR="/var/lib/bitget-recorder"
# Data lives on the external SSD; override with DATA_DIR=... sudo -E bash install_pi.sh
DATA_DIR="${DATA_DIR:-/mnt/external/bitget-recorder}"
SMOKE_DIR="/var/lib/bitget-recorder-smoke"
UNIT_DIR="/etc/systemd/system"
SMOKE_TIMEOUT_SECONDS=60

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${here}/../.." && pwd)"

log() { printf '[install_pi] %s\n' "$*"; }
die() { printf '[install_pi] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "run as root: sudo bash $0"
[[ -f "${repo_root}/research/recorder/recorder.py" ]] || die "not inside a tokendashboard checkout"
command -v python3 >/dev/null || die "python3 missing (sudo apt install python3 python3-venv)"
command -v systemctl >/dev/null || die "systemd required"
python3 -c 'import venv, ensurepip' 2>/dev/null || die "python3-venv missing (sudo apt install python3-venv)"

mount_root="$(dirname "${DATA_DIR}")"
if [[ "${DATA_DIR}" == /mnt/* ]]; then
  mountpoint -q "${mount_root}" || die "${mount_root} is not a mounted drive (refusing to fill the SD card)"
fi

if ! id -u "${SVC_USER}" >/dev/null 2>&1; then
  log "creating system user ${SVC_USER}"
  useradd --system --home-dir "${DATA_DIR}" --no-create-home --shell /usr/sbin/nologin "${SVC_USER}"
fi

install -d -o "${SVC_USER}" -g "${SVC_USER}" -m 0750 "${DATA_DIR}"
if [[ "${DATA_DIR}" != "${LEGACY_DIR}" && -d "${LEGACY_DIR}" && -n "$(ls -A "${LEGACY_DIR}" 2>/dev/null)" ]]; then
  log "migrating existing data ${LEGACY_DIR} -> ${DATA_DIR}"
  systemctl stop bitget-recorder.timer bitget-recorder.service 2>/dev/null || true
  cp -a "${LEGACY_DIR}/." "${DATA_DIR}/"
  chown -R "${SVC_USER}:${SVC_USER}" "${DATA_DIR}"
  diff -rq "${LEGACY_DIR}" "${DATA_DIR}" >/dev/null || die "copy verification failed; legacy data left in place"
  mv "${LEGACY_DIR}" "${LEGACY_DIR}.migrated"
  log "legacy copy kept at ${LEGACY_DIR}.migrated; delete it once verified"
fi
install -d -o root -g root -m 0755 "${APP_DIR}" "${APP_DIR}/app" "${APP_DIR}/app/research"

log "syncing code into ${APP_DIR}/app (root-owned, read-only for the service)"
rm -rf "${APP_DIR}/app/research/recorder"
cp -r "${repo_root}/research/recorder" "${APP_DIR}/app/research/recorder"
cp "${repo_root}/research/trade_pagination.py" "${APP_DIR}/app/research/trade_pagination.py"
find "${APP_DIR}/app" -name '__pycache__' -prune -exec rm -rf {} +
chown -R root:root "${APP_DIR}/app"

if [[ ! -x "${APP_DIR}/venv/bin/python" ]]; then
  log "creating venv"
  python3 -m venv "${APP_DIR}/venv"
fi
req="${repo_root}/research/recorder/requirements.txt"
if [[ -f "${req}" ]]; then
  log "installing dependencies from requirements.txt"
  "${APP_DIR}/venv/bin/python" -m pip install --quiet -r "${req}"
else
  log "no third-party dependencies required (standard library only)"
fi

log "installing systemd units"
sed "s#@DATA_DIR@#${DATA_DIR}#g" "${here}/systemd/bitget-recorder.service" > "${UNIT_DIR}/bitget-recorder.service"
chmod 0644 "${UNIT_DIR}/bitget-recorder.service"
install -m 0644 "${here}/systemd/bitget-recorder.timer" "${UNIT_DIR}/bitget-recorder.timer"
systemctl daemon-reload

log "bounded smoke test (max ${SMOKE_TIMEOUT_SECONDS}s, 1 cycle, scratch dir ${SMOKE_DIR})"
rm -rf "${SMOKE_DIR}"
install -d -o "${SVC_USER}" -g "${SVC_USER}" -m 0750 "${SMOKE_DIR}"
smoke_status=0
(
  cd "${APP_DIR}/app"
  PYTHONDONTWRITEBYTECODE=1 timeout --signal=TERM --kill-after=5s "${SMOKE_TIMEOUT_SECONDS}" \
    runuser -u "${SVC_USER}" -- "${APP_DIR}/venv/bin/python" -m research.recorder.recorder \
    --output-dir "${SMOKE_DIR}" --symbols BTCUSDT --max-cycles 1 --duration-seconds 30 \
    --retries 1 >/dev/null
) || smoke_status=$?
if [[ "${smoke_status}" -ne 0 && "${smoke_status}" -ne 2 ]]; then
  rm -rf "${SMOKE_DIR}"
  die "smoke test failed (exit ${smoke_status}); check network/clock. Timer NOT enabled."
fi
(cd "${APP_DIR}/app" && "${APP_DIR}/venv/bin/python" -m research.recorder.integrity_report \
  "${SMOKE_DIR}" --min-coverage-pct 0 >/dev/null) || {
  rm -rf "${SMOKE_DIR}"
  die "smoke data failed integrity check. Timer NOT enabled."
}
rm -rf "${SMOKE_DIR}"
log "smoke test passed"

systemctl enable --now bitget-recorder.timer

cat <<MSG

Installed. Verify with:
  systemctl list-timers bitget-recorder.timer; journalctl -u bitget-recorder -n 30 --no-pager
  timedatectl show -p NTPSynchronized --value        # expect: yes
  cd ${APP_DIR}/app && ${APP_DIR}/venv/bin/python -m research.recorder.integrity_report ${DATA_DIR}
Stop/uninstall: sudo systemctl disable --now bitget-recorder.timer
MSG
