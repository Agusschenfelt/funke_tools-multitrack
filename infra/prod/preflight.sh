#!/usr/bin/env bash
# READ-ONLY pre-flight for the production deploy: checks the permissions and prerequisites that
# otherwise fail halfway through the runbook. Run it as the deploy user (NOT with sudo), from any
# directory, before `docker compose ... up`. Exit 0 = ready, 1 = at least one FAIL.
#
#   infra/prod/preflight.sh
#
# Env: ENV_FILE (default /opt/multitrack/env.prod), BASE_DIR (default /opt/multitrack).
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-/opt/multitrack/env.prod}"
BASE_DIR="${BASE_DIR:-/opt/multitrack}"
COMPOSE_FILE="$here/docker-compose.prod.yml"
fails=0
errf="$(mktemp)"; trap 'rm -f "$errf"' EXIT
ok() { printf '  ok    %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

echo "user: $(id -un) (uid $(id -u))"
[ "$(id -u)" -ne 0 ] && ok "not running as root" || bad "running as root: run as the deploy user so files are not root-only"

echo "docker"
if docker info >/dev/null 2>&1; then ok "docker daemon reachable by this user"; else bad "cannot talk to docker (add the user to the docker group, then log in again)"; fi
docker compose version >/dev/null 2>&1 && ok "docker compose v2" || bad "docker compose v2 missing"
info="$(docker info 2>/dev/null || true)"
printf '%s' "$info" | grep -qi 'Cgroup Driver: systemd' && ok "cgroup driver systemd" || bad "cgroup driver is not systemd (cgroup_parent will fail; see README, discovery)"
printf '%s' "$info" | grep -qi 'Cgroup Version: 2' && ok "cgroup v2" || bad "cgroup v2 not reported"

echo "slice"
if systemctl is-active --quiet multitrack.slice 2>/dev/null; then ok "multitrack.slice active"; else bad "multitrack.slice not active (README step: install the resource cap)"; fi

echo "files"
if [ -w "$BASE_DIR" ] || [ -w "$(dirname "$BASE_DIR")" -a ! -e "$BASE_DIR" ]; then ok "$BASE_DIR writable by this user"; else bad "$BASE_DIR is not writable (sudo install -d -o $(id -un) -g $(id -gn) -m 755 $BASE_DIR)"; fi
if [ ! -e "$ENV_FILE" ]; then
  bad "$ENV_FILE does not exist"
else
  [ -r "$ENV_FILE" ] && ok "env file readable by this user (compose reads it as you, not as the daemon)" || bad "env file not readable by $(id -un) (chown it to this user)"
  mode="$(stat -c %a "$ENV_FILE" 2>/dev/null || stat -f %Lp "$ENV_FILE")"
  owner="$(stat -c %u "$ENV_FILE" 2>/dev/null || stat -f %u "$ENV_FILE")"
  [ "$mode" = 600 ] && ok "env file mode 600" || bad "env file mode is $mode (chmod 600)"
  [ "$owner" = "$(id -u)" ] && ok "env file owned by this user" || bad "env file owned by uid $owner (sudo chown $(id -un) $ENV_FILE)"
  if grep -Eq '^(POSTGRES_PASSWORD|REDIS_PASSWORD|SIGNING_SECRET)=(generate-with|$)' "$ENV_FILE"; then bad "a secret still has its placeholder value"; else ok "secrets filled in"; fi
  if grep -Eq '^(NEXT_PUBLIC_API_URL|CORS_ORIGINS)=.*example\.com' "$ENV_FILE"; then bad "NEXT_PUBLIC_API_URL / CORS_ORIGINS still point at example.com"; else ok "public URLs customised"; fi
  if docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" config --quiet 2>"$errf"; then ok "compose config valid"; else bad "compose config invalid: $(head -1 "$errf")"; fi
  net="$(grep -E '^CADDY_NETWORK=' "$ENV_FILE" | cut -d= -f2-)"
  if [ -n "$net" ] && docker network inspect "$net" >/dev/null 2>&1; then ok "caddy network $net exists"; else bad "CADDY_NETWORK '$net' not found (docker network ls)"; fi
fi

echo
if [ "$fails" -eq 0 ]; then echo "preflight passed"; else echo "preflight: $fails check(s) failed"; fi
[ "$fails" -eq 0 ]
