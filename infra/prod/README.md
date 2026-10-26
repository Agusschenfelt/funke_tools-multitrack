# Production deploy (shared VPS)

Runbook for running the multitrack tool on a VPS that already hosts other production containers.
Rule one: **never touch client containers, networks or volumes.** The only change to existing
infrastructure is one new Caddy site block plus a Caddy reload (and connecting Caddy to one network).

Every step is marked `READ-ONLY` (inspects only) or `CHANGES` (modifies the VPS). Run the
`CHANGES` steps only after the exact list has been approved.

## What gets deployed

| Piece | Where | Notes |
| --- | --- | --- |
| `mt-web` (Next standalone) | container `multitrack-web`, port 3000 | joins the Caddy network only |
| `mt-api` (FastAPI) | container `multitrack-api`, port 8000 | internal + Caddy network |
| `worker-cpu`, `redis`, `postgres` | project `multitrack` | internal network only, no published ports |
| `multitrack.slice` | systemd | caps the whole stack: 2 CPU cores, 5 GiB RAM, no swap, low CPU/IO weight |

Per-container limits: worker 2 CPUs / 3.5 GiB (no swap; measured peak 2.9 GiB for a 4-minute song),
api 256 MiB, postgres 256 MiB, redis 128 MiB (`maxmemory 96mb`, `noeviction`), web 192 MiB. All have
`cpu_shares: 256` (default is 1024), so client containers win under contention.

Networks: `multitrack_internal` (`internal: true`, no outbound route) holds redis, postgres, api and
worker. The worker also joins `multitrack_egress` so it can download model weights on the first job.
`mt-web` and `mt-api` additionally join the existing Caddy network (`CADDY_NETWORK`). They are named
`mt-*` so their DNS aliases cannot collide with an `api` or `web` service of another stack on that network.

## Host and URL model

Two DNS names may not be available yet, so there are two supported shapes. Pick one before building the
web image, because `NEXT_PUBLIC_API_URL` is baked into the browser bundle at build time.

- **Single host (default):** `https://tool.example.com` serves the web app and `https://tool.example.com/api`
  serves the API (Caddy strips `/api`). Build with `NEXT_PUBLIC_API_URL=https://tool.example.com/api`.
  Same origin, so CORS is not exercised; `CORS_ORIGINS` is still set.
- **Separate API host:** `tool.example.com` and `api.example.com`. Build with
  `NEXT_PUBLIC_API_URL=https://api.example.com` and `CORS_ORIGINS=https://tool.example.com`.
  The alternative Caddy block is at the bottom of `Caddyfile.snippet`.

TLS: Caddy issues certificates automatically, but only if the DNS A record of the name(s) already points
to the VPS. Create the record first. Without a DNS name, test through an SSH tunnel to the container
instead (no public exposure); HTTPS on a bare IP is not available.

## Prerequisites

- Approval of the exact change list below.
- A DNS name pointing at the VPS (or the SSH tunnel fallback).
- Docker Compose v2 on the VPS (Docker 29.x already installed).

## 1. Discovery (all READ-ONLY)

```sh
docker info | grep -i "cgroup"                       # READ-ONLY: need "Cgroup Driver: systemd", "Cgroup Version: 2"
docker ps --format '{{.Names}}\t{{.Ports}}' | head -50   # READ-ONLY: see what binds 80/443 and which names exist
docker inspect core-caddy-1 --format '{{json .Mounts}}'  # READ-ONLY: where the Caddyfile / config dir live
docker inspect core-caddy-1 --format '{{json .NetworkSettings.Networks}}'  # READ-ONLY: Caddy network name(s)
docker inspect core-caddy-1 --format '{{json .Config.Cmd}} {{json .Config.Labels}}'  # READ-ONLY: how it loads config
docker exec core-caddy-1 caddy version                 # READ-ONLY
docker exec core-caddy-1 sh -c 'ls -la /etc/caddy; head -40 /etc/caddy/Caddyfile'  # READ-ONLY: confirm Caddyfile format and `import` globs
free -h; df -h /var/lib/docker /opt; nproc            # READ-ONLY
getent hosts tool.example.com                          # READ-ONLY: DNS points at the VPS?
```

Record: the Caddy network name (goes into `CADDY_NETWORK`), the host path of the Caddyfile (or of an
imported sites directory), and whether Caddy uses the Caddyfile (not the JSON API or labels). If Caddy is
driven by something other than a Caddyfile, stop and adapt the snippet before continuing.

If `docker info` does not say `Cgroup Driver: systemd`, `cgroup_parent: multitrack.slice` will fail to start
containers. Fallbacks, in order of preference: (1) do not change the Docker daemon (it would restart client
containers); instead remove `cgroup_parent` lines and rely on the per-container limits, which already sum to
about 4.6 GiB and 3.75 CPUs at the very worst; (2) with a maintenance window agreed with the owner, set
`"exec-opts": ["native.cgroupdriver=systemd"]` in `/etc/docker/daemon.json` (restarts Docker). Do not do (2)
without explicit approval.

## 2. Files created on the VPS

Only these (all new, none overwrite anything):

| Path | Purpose |
| --- | --- |
| `/opt/multitrack/src/` | checkout of this repo (build context) |
| `/opt/multitrack/env.prod` | production env, mode 600, secrets generated on the server |
| `/etc/systemd/system/multitrack.slice` | resource cap |
| `<caddy sites dir or Caddyfile>` | one appended/imported site block (path from discovery) |
| Docker: images `multitrack-{web,api,worker-cpu}:prod`, networks `multitrack_internal`, `multitrack_egress`, volumes `multitrack_{storage,model_cache,postgres_data}`, 5 containers | the stack |

## 3. Deploy (in order)

```sh
# CHANGES: create the directory and fetch the code (git clone, or rsync from the dev machine)
sudo install -d -m 755 /opt/multitrack
git clone <repo-url> /opt/multitrack/src && cd /opt/multitrack/src && git checkout <release-ref>

# CHANGES: install the resource cap
sudo cp infra/prod/multitrack.slice /etc/systemd/system/multitrack.slice
sudo systemctl daemon-reload && sudo systemctl start multitrack.slice
systemctl show multitrack.slice -p CPUQuotaPerSecUSec -p MemoryMax -p MemorySwapMax   # READ-ONLY: verify

# CHANGES: env file with fresh secrets (edit hosts and CADDY_NETWORK afterwards)
sudo install -m 600 /dev/null /opt/multitrack/env.prod
cp infra/prod/env.prod.example /opt/multitrack/env.prod   # keep mode 600
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 24)/;
        s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=$(openssl rand -hex 24)/;
        s/^SIGNING_SECRET=.*/SIGNING_SECRET=$(openssl rand -hex 32)/" /opt/multitrack/env.prod
$EDITOR /opt/multitrack/env.prod   # set CADDY_NETWORK, NEXT_PUBLIC_API_URL, CORS_ORIGINS, PUBLIC_ORIGIN

# READ-ONLY: validate (the Caddy network must already exist, it does)
docker compose -f infra/prod/docker-compose.prod.yml --env-file /opt/multitrack/env.prod config --quiet

# CHANGES: build and start. The build competes with clients for CPU: run it off-peak, with low priority.
sudo systemd-run --slice=multitrack.slice --scope --uid=$(id -u) nice -n 19 \
  docker compose -f infra/prod/docker-compose.prod.yml --env-file /opt/multitrack/env.prod build
# (Docker builds run in the daemon's cgroup, so the slice does not cap them; nice only affects the client.
#  Alternative with no VPS build load: build on the dev machine with --platform linux/amd64 and
#  `docker save ... | ssh vps docker load`. That needs separate approval for the file transfer.)
docker compose -f infra/prod/docker-compose.prod.yml --env-file /opt/multitrack/env.prod up -d   # CHANGES

docker compose -f infra/prod/docker-compose.prod.yml --env-file /opt/multitrack/env.prod ps    # READ-ONLY: all healthy
docker stats --no-stream $(docker ps --filter label=com.docker.compose.project=multitrack -q)   # READ-ONLY
```

The API runs `alembic upgrade head` on start. The first analysis or separation downloads model weights into
the `model_cache` volume (slow once, needs the egress network).

## 4. Caddy route (the only change to existing infrastructure)

```sh
# CHANGES: let Caddy reach the two multitrack containers (adds a network to Caddy; nothing is removed)
docker network connect <CADDY_NETWORK> core-caddy-1   # skip if Caddy is already on that network (it is, if you used its network)

# CHANGES: append the block from infra/prod/Caddyfile.snippet (host replaced) to the Caddyfile path found in discovery.
# Back it up first:
cp <caddyfile> <caddyfile>.bak-multitrack                       # CHANGES (new backup file)

# READ-ONLY: validate before applying
docker exec core-caddy-1 caddy validate --config /etc/caddy/Caddyfile

# CHANGES: graceful reload (no dropped connections for other sites)
docker exec core-caddy-1 caddy reload --config /etc/caddy/Caddyfile
```

Use `reload`, never `restart`. If `validate` fails, restore the backup and do not reload.

## 5. Smoke test

From the dev machine (needs the repo and `uv`):

```sh
uv run python scripts/e2e_smoke.py --api https://tool.example.com/api    # single-host shape
```

Then open `https://tool.example.com`, upload a short song, and watch `docker stats`. Check that client
containers are unaffected (`docker stats --no-stream`, Uptime Kuma). Songs and files disappear after 24 h.

## Rollback

Nothing else on the VPS depends on these steps, so rollback only removes what was added:

```sh
# 1. Remove the Caddy route, then reload (restore the backup or delete the block)
cp <caddyfile>.bak-multitrack <caddyfile>
docker exec core-caddy-1 caddy validate --config /etc/caddy/Caddyfile && \
docker exec core-caddy-1 caddy reload --config /etc/caddy/Caddyfile

# 2. Stop and remove the stack (add -v only to also delete songs, models and the database)
docker compose -f /opt/multitrack/src/infra/prod/docker-compose.prod.yml --env-file /opt/multitrack/env.prod down

# 3. Disconnect Caddy from the network only if this deploy added it
docker network disconnect <CADDY_NETWORK> core-caddy-1

# 4. Remove the cap and files
sudo systemctl stop multitrack.slice && sudo rm /etc/systemd/system/multitrack.slice && sudo systemctl daemon-reload
sudo rm -rf /opt/multitrack
docker image rm multitrack-web:prod multitrack-api:prod multitrack-worker-cpu:prod
```

Only ever use `docker compose ... down` for this project; never `docker system prune`, `docker network prune`
or `docker volume prune` on this host, which could remove client resources.

## Operations

- Update: `git pull`, rebuild, `up -d` (drain the queue first if a change touches the job serializer).
- Drop outbound access after models are cached: remove `egress` from `worker-cpu.networks`, `up -d`.
- Logs: `docker compose ... logs -f --tail 100 worker-cpu`. Log files are capped at 3 x 10 MB per container.
- Manual orphan sweep: `docker compose ... run --rm worker-cpu python -m worker_cpu.cleanup`.
