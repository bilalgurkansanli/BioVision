# Deployment

> **Not yet executed.** Everything here is written against the configuration in
> `backend/Dockerfile`, `infra/`, and `infra/supabase/migrations/`, but no part of
> it has run: the VPS details are outstanding and Docker was unavailable on the
> development machine, so the image has never been built. Treat this as a runbook
> to follow, not a record of a deployment that happened. The verification section
> at the end is what turns it into the latter.

Two targets. The frontend is static and goes to Vercel; the backend is a
container on your own VPS behind Caddy.

---

## 0. Prerequisites

| Item | Where | Notes |
|---|---|---|
| VPS | 4 vCPU / 8 GB / 100 GB | Docker + compose plugin; ports 80 and 443 free |
| DNS `A` record | `api.biovision.bilalgurkansanli.com` → VPS IP | **Must resolve before Caddy starts** — it obtains a certificate over HTTP-01 and cannot without it |
| DNS record | `biovision.bilalgurkansanli.com` → Vercel | Vercel supplies the target |
| Supabase project | free tier | for auth, rows, and objects |
| Anthropic API key | console | optional; without it descriptions are disabled and the API says so |

---

## 1. Supabase

Apply the migrations in order, from the SQL editor or the CLI:

```bash
supabase db push   # or paste infra/supabase/migrations/*.sql in order
```

`0002_retention.sql` needs **pg_cron** (Database → Extensions). Without it the
schedule silently does not exist and rows accumulate past the retention window —
step 5 checks for exactly that.

Then, in the dashboard:

* **Authentication → Providers → Google** — enable, and add
  `https://biovision.bilalgurkansanli.com` plus the Supabase callback URL to the
  authorised redirect URIs.
* **Settings → API** — copy the project URL, the `anon` key, the `service_role`
  key, and the **JWT secret**.

The `service_role` key goes on the VPS only. It bypasses row-level security, so a
copy of it in the browser would make every policy in the database decorative.

---

## 2. Backend

```bash
git clone https://github.com/<owner>/biovision.git && cd biovision/backend
cp .env.example .env      # fill in; see the table below
```

Values that are not optional:

| Key | Value |
|---|---|
| `BIOVISION_ENV` | `production` |
| `BIOVISION_MODEL_BACKEND` | `real` |
| `BIOVISION_UVICORN_WORKERS` | `2` — **must match the `--workers` the container runs with**, because the VLM budget is divided by it |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` | from step 1 |
| `SUPABASE_SERVICE_ROLE_KEY` | from step 1 |
| `ANTHROPIC_API_KEY` | optional; omit to run without descriptions |
| `BIOVISION_VLM_ENABLED` | `true` only if the key is set |

Fetch the weights onto the host — they are mounted read-only rather than baked
into the image, so a code deploy does not re-ship gigabytes:

```bash
uv run python -m scripts.fetch_weights --with-clip
mkdir -p ../infra/weights && cp -r weights/* ../infra/weights/
```

Then bring it up:

```bash
cd .. && docker compose -f infra/docker-compose.prod.yml up -d --build
```

> **Two workers, not four.** Each loads its own copy of CLIP (~1.1 GB resident,
> measured) and, once Phase 5 lands, YOLO as well. Four exhausts 8 GB and takes
> the machine down. The compose file sets a 6 GB memory limit so a leak gets the
> container OOM-killed and restarted instead of the host.

---

## 3. Frontend

Import the repository in Vercel, then set:

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Framework | Next.js (detected) |
| `NEXT_PUBLIC_API_URL` | `https://api.biovision.bilalgurkansanli.com` |
| `NEXT_PUBLIC_SUPABASE_URL` | from step 1 |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | from step 1 |

Only `NEXT_PUBLIC_*` values, and only these three. Anything else would be inlined
into the JavaScript every visitor downloads; CI fails the build if a server-side
secret name ever appears in the output.

---

## 4. Measure, then publish

The README's latency table is empty until this runs **on the VPS**. A developer
laptop and a 4-vCPU box with no GPU are different machines, and the decision to
stay synchronous rests on the p95 measured where the service actually runs.

```bash
docker compose -f infra/docker-compose.prod.yml exec api \
  python -m scripts.bench_latency --n 50
```

Paste the p50/p95 table into README section 7.4. If end-to-end p95 exceeds
**3000 ms**, that is the documented trigger to reconsider the queue (README
section 9) — the number decides, not a preference.

---

## 5. Verification — the deployment is not done until these pass

Each row corresponds to a claim the README makes. An unchecked row is a claim
that is currently unverified.

| Check | Command | Expected |
|---|---|---|
| API is up | `curl -s https://api.biovision.../health` | `"status":"ok"` |
| Real models loaded | same response | `"model_backend":"real"`, gate and router `ready: true` |
| TLS | `curl -sI https://api.biovision.../health` | HTTP/2 200, valid certificate |
| Gate rejects | upload a selfie | `422 out_of_distribution` |
| Honest fallback | upload a wall crack | `specialist_model: null` + warning |
| Anonymous cannot spend budget | same, signed out | `vlm_description: null` |
| **RLS holds** | `BIOVISION_TEST_SUPABASE=1 … pytest tests/integration/test_rls_live.py` | all pass |
| Retention job scheduled | `select * from cron.job where jobname='biovision-retention'` | one row |
| Retention job ran | `select * from cron.job_run_details … order by start_time desc limit 5` | recent successes |
| Nothing outlives the window | `select count(*) from analyses where created_at < now() - interval '7 days'` | `0` |
| Survives a reboot | `sudo reboot`, wait, re-check `/health` | `ok` |
| No secret in the browser | DevTools → Sources, search `service_role` | no match |

**The RLS row is the important one.** Until `test_rls_live.py` has passed against
the deployed project, the authorisation guarantee in README section 8.1 is a
design, not a demonstration — and the README says so. Running it is what removes
that caveat.

---

## Rollback

```bash
git checkout <previous-tag>
docker compose -f infra/docker-compose.prod.yml up -d --build
```

Weights and the database are outside the image, so a rollback moves code only.
Migrations are additive; none of them drops a column, so an older image runs
against a newer schema.
