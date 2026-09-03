# Security

## Reporting something

Open a [private security advisory](https://github.com/bilalgurkansanli/BioVision/security/advisories/new)
rather than a public issue. If that is not available to you, open an issue saying
only that you have found something and how to reach you — no details in the
public thread.

There is no bounty and no SLA. This is one person's portfolio project. What there
is, is an answer.

## What this system holds, and for how long

Worth knowing before you look for something:

* **Uploaded photographs are not stored as uploaded.** Faces are blurred and EXIF
  is stripped during ingest; only the redacted derivative is written, and the
  original never reaches disk.
* **Anonymous analyses are not stored at all.** Nobody could retrieve or delete
  them, so keeping the image would be collecting data with no owner and no
  purpose.
* **Stored derivatives are deleted after 7 days** (`BIOVISION_RETENTION_DAYS`).
* **Row-level security is enforced in Postgres, not in the application.** A user
  reads their own rows because the database says so. `tests/integration/test_rls_live.py`
  asserts it against a real Supabase project rather than a mock, because an RLS
  policy that is only tested against a mock is a policy nobody has tested.
* **The `service_role` key bypasses RLS** and exists only on the server. CI fails
  the build if it, the JWT secret, or an Anthropic key appears in the built
  frontend bundle — see `.github/workflows/frontend.yml`.

## Things that are deliberate, so you need not report them

* **The VLM budget is a hard ceiling, and exhausting it returns 503.** That is the
  designed behaviour, not a denial of service: the alternative is an unbounded
  bill.
* **Anonymous callers can run the specialist but never the paid VLM.** This is
  what makes a public demo link safe to publish.
* **Rate limiting is in-process and per-worker.** With more than one worker the
  effective limit is the configured one times the worker count. This is stated in
  `config.py` and bounded by `BIOVISION_UVICORN_WORKERS`; it is a known limit of
  running without shared state, not an oversight.
* **A multi-photograph claim counts as one request against the quota**, not one
  per photograph. Cost is bounded by the six-photograph cap instead.

## If you are forking this

The repository has never contained a live credential — every commit in its
history has been scanned, and `.env` files have been gitignored since the first
commit. But `backend/.env.example` lists every secret the system reads, and the
deployment guide assumes you will generate your own. **Do not reuse any value you
find in a screenshot, a transcript, or a demo.**

Rotate anything that has ever been shown to anyone. A Supabase `service_role` key
bypasses row-level security completely; a JWT secret lets anyone mint a token for
any user.
