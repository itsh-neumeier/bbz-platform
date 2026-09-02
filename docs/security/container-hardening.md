# Container hardening

Roadmap **E23-08**, MASTER_PROMPT §22, `.ai/SECURITY.md`.

## Non-root — enforced

Every self-built image must run as a non-root user. `server/Dockerfile` is the
only one today: multi-stage, `USER bbz` (uid `10001`) in the runtime stage.

Two CI gates (`security.yml`, job `non-root images`):

1. **`tools/security/check_dockerfiles.py`** — static: for every `**/Dockerfile`,
   the effective final `USER` (last `USER` in the last stage) must exist and not
   be `root` / `0`. A multi-stage file that sets `USER` only in a builder stage
   fails — the runtime stage inherits root.
2. **build + `docker inspect`** — the api image is built and its `Config.User`
   checked for the real answer.

`tests/test_dockerfiles_nonroot.py` covers the checker.

## Runtime lock-down — compose

`docker-compose.yml` (dev) and `deploy/node/docker-compose.yml` (prod node) set,
on the `api` (and the future `web`):

| directive | effect |
|---|---|
| `read_only: true` | root filesystem is immutable — the app only writes to stdout |
| `tmpfs: ["/tmp"]` | the one writable path, in memory, wiped on restart |
| `cap_drop: ["ALL"]` | no Linux capabilities (the app binds 8000 as non-root, needs none) |
| `security_opt: ["no-new-privileges:true"]` | no setuid escalation |

Verified: the api starts, runs the cluster singletons, and serves under all four.
Alembic migrations run as a separate one-shot (`docker compose run api alembic …`)
and are unaffected.

## Still to come (blocked)

| image | status |
|---|---|
| `bbz-web` | Epic 07 (blocked). The prod `web` service already carries the hardening directives; they apply the moment the image exists. It must ship non-root and serve static files only. |
| `cucm-cti-gateway`, worker | Epic 12 (blocked). Same checklist: non-root `USER`, `read_only` + `tmpfs`, `cap_drop: ALL`, `no-new-privileges`. The `check_dockerfiles.py` gate covers them automatically once their Dockerfiles land. |

## Not here

Foreign images (`postgres`, `etcd`, `caddy`, `grafana`, `prometheus`,
`otel-collector`) — configured, not rebuilt. Their upstreams handle the user;
`cap_drop` / `read_only` for them is a per-image exercise deferred to the
production hardening pass in Epic 24.
