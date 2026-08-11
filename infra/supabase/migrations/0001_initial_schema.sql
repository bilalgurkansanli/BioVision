-- BioVision -- initial schema
--
-- Two tables and a storage bucket. Authorisation is enforced by row-level
-- security in Postgres, not by WHERE clauses in the API: a WHERE clause is
-- something a future refactor can drop, whereas an RLS policy denies the read
-- outright. The API could have a bug and still not leak another user's rows.

-- ===========================================================================
--  analyses -- one row per completed /v1/analyze
-- ===========================================================================

create table if not exists public.analyses (
    id                  uuid primary key,
    user_id             uuid not null references auth.users (id) on delete cascade,
    created_at          timestamptz not null default now(),

    -- Routing
    domain              text not null,
    domain_confidence   double precision not null
                        check (domain_confidence >= 0 and domain_confidence <= 1),
    domain_confidence_calibrated boolean not null default false,

    -- Result. `specialist_model IS NULL` is the honest-answer case and is
    -- expected to be the majority of rows, so the constraint below enforces the
    -- same invariant the response schema does.
    specialist_model    text,
    calibrated          boolean not null default false,
    findings            jsonb not null default '[]'::jsonb,
    vlm_description     text,
    warning             text,

    -- Integrity. GPS is a boolean: whether a photo carried location data is what
    -- matters for triage, and storing coordinates would be a liability with no
    -- analytical payoff.
    phash               text not null,
    exif_datetime       timestamptz,
    exif_gps_present    boolean not null default false,
    device              text,
    duplicate_of        uuid references public.analyses (id) on delete set null,

    -- Privacy. NULL detector means that class was not redacted.
    faces_blurred       integer not null default 0 check (faces_blurred >= 0),
    plates_blurred      integer not null default 0 check (plates_blurred >= 0),
    face_detector       text,
    plate_detector      text,

    -- The stored derivative: redacted, EXIF-free, <= 1280px. The original upload
    -- is never persisted anywhere.
    storage_path        text,

    timing_ms           jsonb not null default '{}'::jsonb,

    -- The honesty contract, enforced in the database as well as the schema.
    -- Findings without a specialist behind them cannot be written at all.
    constraint findings_require_a_specialist
        check (specialist_model is not null or findings = '[]'::jsonb),
    constraint calibrated_requires_a_specialist
        check (specialist_model is not null or calibrated = false),
    constraint description_excludes_a_specialist
        check (specialist_model is null or vlm_description is null)
);

comment on table public.analyses is
    'One row per completed analysis. Deleted after the retention window.';
comment on constraint findings_require_a_specialist on public.analyses is
    'The core invariant: no model produced them, so a non-empty list would be a lie.';

create index if not exists analyses_user_created_idx
    on public.analyses (user_id, created_at desc);

-- Duplicate detection scans by hash within one user's own rows.
create index if not exists analyses_user_phash_idx
    on public.analyses (user_id, phash);

-- The retention job deletes by age across all users; without this it seq-scans.
create index if not exists analyses_created_idx
    on public.analyses (created_at);

-- ===========================================================================
--  vlm_spend -- the shared monthly budget counter
-- ===========================================================================
--
-- Phase 6 keeps this in process memory, which forces the ceiling to be divided
-- between workers. A shared row removes that: workers charge the same counter,
-- so the limit holds however traffic is distributed and a busy worker can use
-- an idle one's share.

create table if not exists public.vlm_spend (
    month           text primary key,           -- 'YYYY-MM'
    spent_usd       numeric(10, 6) not null default 0 check (spent_usd >= 0),
    calls           integer not null default 0 check (calls >= 0),
    updated_at      timestamptz not null default now()
);

comment on table public.vlm_spend is
    'Global monthly VLM spend. Not user-scoped: it is an operational limit, not user data.';

-- Atomic charge. Doing this in the API would be read-modify-write across
-- workers, which is exactly how a spend ceiling gets exceeded.
create or replace function public.charge_vlm_spend(
    p_month text,
    p_cost_usd numeric,
    p_limit_usd numeric
)
returns table (spent_usd numeric, calls integer, exhausted boolean)
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.vlm_spend as s (month, spent_usd, calls)
    values (p_month, p_cost_usd, 1)
    on conflict (month) do update
        set spent_usd = s.spent_usd + p_cost_usd,
            calls = s.calls + 1,
            updated_at = now()
    returning s.spent_usd, s.calls into spent_usd, calls;

    exhausted := spent_usd >= p_limit_usd;
    return next;
end;
$$;

-- ===========================================================================
--  Row-level security
-- ===========================================================================

alter table public.analyses enable row level security;
alter table public.vlm_spend enable row level security;

-- A user sees, and can delete, only their own analyses. There is no UPDATE
-- policy: an analysis is a record of what a model said at a point in time, and
-- editing it would make the history meaningless.
drop policy if exists analyses_select_own on public.analyses;
create policy analyses_select_own on public.analyses
    for select using (auth.uid() = user_id);

drop policy if exists analyses_insert_own on public.analyses;
create policy analyses_insert_own on public.analyses
    for insert with check (auth.uid() = user_id);

drop policy if exists analyses_delete_own on public.analyses;
create policy analyses_delete_own on public.analyses
    for delete using (auth.uid() = user_id);

-- vlm_spend gets no policy at all. RLS is enabled and nothing is permitted, so
-- every ordinary client -- anon and authenticated alike -- is denied. Only the
-- service role, which bypasses RLS, can touch it. An operational counter is not
-- user data and no user has any business reading it.

-- ===========================================================================
--  Storage
-- ===========================================================================
--
-- Objects are keyed `<user_id>/<analysis_id>.jpg`, so the first path segment is
-- the owner and the policies below compare it against auth.uid().

insert into storage.buckets (id, name, public)
values ('biovision-images', 'biovision-images', false)
on conflict (id) do nothing;

drop policy if exists images_select_own on storage.objects;
create policy images_select_own on storage.objects
    for select using (
        bucket_id = 'biovision-images'
        and (storage.foldername(name))[1] = auth.uid()::text
    );

drop policy if exists images_insert_own on storage.objects;
create policy images_insert_own on storage.objects
    for insert with check (
        bucket_id = 'biovision-images'
        and (storage.foldername(name))[1] = auth.uid()::text
    );

drop policy if exists images_delete_own on storage.objects;
create policy images_delete_own on storage.objects
    for delete using (
        bucket_id = 'biovision-images'
        and (storage.foldername(name))[1] = auth.uid()::text
    );
