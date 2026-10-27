#!/usr/bin/env bash
# READ-ONLY. Waits until the RQ queue `cpu` has nothing queued and nothing running, so an update
# does not interrupt a separation (they take ~15 min). Exit 0 = drained, 1 = still busy at timeout,
# 2 = the queue could not be read (worker down, Redis unreachable): do not treat that as drained.
#
#   infra/prod/drain.sh [timeout_seconds]        # default 1800
#
# Env: ENV_FILE (default /opt/multitrack/env.prod), COMPOSE_FILE (default: next to this script),
#      EXEC (command prefix that runs inside the worker; override for tests).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-/opt/multitrack/env.prod}"
COMPOSE_FILE="${COMPOSE_FILE:-$here/docker-compose.prod.yml}"
timeout="${1:-1800}"
EXEC="${EXEC:-docker compose -f $COMPOSE_FILE --env-file $ENV_FILE exec -T worker-cpu}"

probe='import os; from redis import Redis; from rq import Queue; from rq.registry import StartedJobRegistry
q = Queue("cpu", connection=Redis.from_url(os.environ["REDIS_URL"]))
print(len(q), StartedJobRegistry(queue=q).count)'

deadline=$((SECONDS + timeout))
while true; do
  # shellcheck disable=SC2086  # EXEC is a command prefix and must word-split
  if ! out="$($EXEC python -c "$probe")"; then
    echo "cannot read the queue (is worker-cpu running?): not drained" >&2
    exit 2
  fi
  read -r queued running <<<"$out"
  if ! [[ "$queued" =~ ^[0-9]+$ && "$running" =~ ^[0-9]+$ ]]; then
    echo "unexpected queue probe output: '$out'" >&2
    exit 2
  fi
  echo "queued=$queued running=$running"
  if [ "$queued" = 0 ] && [ "$running" = 0 ]; then
    echo "drained: safe to update"
    exit 0
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "still busy after ${timeout}s: do not update yet (or accept that the running job is killed)" >&2
    exit 1
  fi
  sleep 15
done
