# UB Server

The server stack has four roles:

- `bot`: aiogram polling bot that opens the Mini App.
- `web`: HTTPS-facing Mini App API and Telethon login flow.
- `orchestrator`: private worker launcher. It is the only service with Docker socket access.
- tenant workers: one isolated `ub-worker` container per Telegram user.

This is the third repository (`server`). Clone `skeleton` and `modules` inside this repository directory. Those nested clones are ignored by the server Git repo and referenced by Compose through `SKELETON_DIR` and `MODULES_DIR`.

The server repo consumes the sibling `modules` repo as its versioned catalog and the sibling `skeleton` repo as the worker runtime. Only server-allowlisted modules are shown. Python source is installed into each tenant's module directory; runtime config, state, databases, and bot tokens are created separately per tenant.

## Configure

The local `.env` is ignored by this repository. It already contains the temporary bot token supplied for this setup. Do not publish it; rotate it with BotFather before exposing the service to real users.

Fill these values in `.env`:

- `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`: server-side Telegram application credentials from `my.telegram.org`.
- `TELEGRAM_DEVICE_PROFILE`: metadata sent by the registration client. Defaults to `iphone_14_pro_max`; use `telethon_default` to compare with Telethon's default device metadata. Profiles live in `app/device_profiles.py`. This does not change the worker or control code delivery.
- `WEBAPP_URL`: public HTTPS URL serving this Mini App. Telegram Web Apps do not work from a plain HTTP or localhost URL.
- `WEBAPP_DOMAIN`: DNS name for the optional Caddy TLS profile; set it to the same host as `WEBAPP_URL`.
- `HOST_USERS_DIR`: absolute path to `server/users` as seen by the Docker daemon. On a Linux host, for example, `/opt/ub/server/users`.
- `ORCHESTRATOR_TOKEN`: replace the development value with a long random secret.

By default the Compose stack binds the web/API to `127.0.0.1:8080`. Put a TLS reverse proxy in front of that address and set `WEBAPP_URL` to the public HTTPS URL. Alternatively, point `WEBAPP_DOMAIN` DNS to this server, set both URL variables, and start the included Caddy service with `docker compose --profile https up -d --build`. For local development, a temporary HTTPS tunnel can forward to port 8080; set its URL in `.env` and restart the bot service.

## Run

From this directory, after cloning the two sibling repositories into `server/skeleton` and `server/modules`:

```sh
docker compose up --build
```

Compose builds `ub-worker:local` through a one-shot image-build service, then starts the orchestrator and control plane. Send `/start` to the configured bot and open the Mini App. `base` is always enabled and `spaceTW` is selected by default. The Telegram account logged into the Mini App must match the account authorized by phone/code. After authorization, the server creates that user's data/module directories and starts their worker.

`spaceTW` creates its notification bot through BotFather on the user's account during the first worker start. That token and its state/database are written only under that user's module directory.

## Interactive Telegram login test

From the `server` directory with `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` set in `.env`:

```sh
docker compose --profile check-code run --rm --no-deps check-code
```

This runs `check_code/cc.py` in the foreground using the existing worker image (`WORKER_IMAGE`, default `ub-worker:local`). If the image is missing, run `docker compose build worker-image` first. `run` starts only the diagnostic container and attaches the terminal so you can enter the phone number, login code, and 2FA password if prompted. Do not use `-d` or `-T` for this test.

The script is mounted read-only; script changes do not require an image rebuild. Telethon uses an in-memory session and does not write a session file. A successful login may still appear in Telegram's active sessions; revoke the test login there if no longer needed. The test neither launches userbot modules nor uses existing users' sessions. It prints the Telethon version in the worker image, which may differ from the `web` image.

## Storage and module catalog

```text
server/users/<telegram_id>/
  data/                 # Telethon session, server API credentials, selection
  modules/<module_id>/  # per-user module source and persistent module files
```

The worker receives only that user's two directories. Worker filesystems are read-only outside those mounts and `/tmp`; workers have memory, CPU, and PID limits. The control service does not receive Docker socket access.

The `modules` repo is bind-mounted read-only into web and orchestrator containers. Module source is not baked into those images, so catalog changes do not require a server-image rebuild. Releases are immutable version directories, for example `modules/spaceTW/1.0.0/`; the backend lists the highest semantic version allowed by `SERVER_MODULE_ALLOWLIST`. Add new source directly to the modules repo under a new version with a manifest. The worker image only needs rebuilding when the skeleton runtime or its Python dependencies change. Each tenant records its installed module versions in `data/installed-modules.json`.

When a module is selected, the orchestrator copies only `.py` files from its selected catalog release into that tenant's existing module folder, preserving config, state, and databases. That per-user folder is then bind-mounted into the worker. Initial registration installs the latest catalog version and records it; existing tenants remain pinned to their copied version. The user-facing update action is not implemented in this first server slice. Before adding it, define backup/migration behavior for module databases.

## Important limitations

- Pending login clients are held in control-process memory and expire after ten minutes. If the control service restarts during authorization, the user starts registration again.
- The test bot token has been placed in the ignored local `.env`; do not commit it. Rotate it before public deployment.
- `spaceTW` automation depends on the user's account being able to create a bot through BotFather. Worker startup logs are available with `docker compose logs -f` and `docker logs ub-user-<telegram_id>`.
- `HOST_USERS_DIR` must identify the same host directory mounted as `server/users`; otherwise the Docker daemon cannot bind the tenant folders into workers.
- This repository intentionally ignores the nested `skeleton/` and `modules/` clones. Keep each repository's Git history separate.
