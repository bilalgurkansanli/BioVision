-- Corrections: what the person looking at the photograph says the model got wrong.
--
-- `docs/OPEN_QUESTIONS.md` has said the same thing since the first evaluation set
-- was built: what this project lacks is not code but **photographs from a real
-- intake**. README 7.1 says `phone_screen` scores 100% from one source in one
-- photographic style; 7.7 says the whole published evaluation was measured on
-- close-ups because VehiDE is close-ups, so it cannot see the failure that
-- matters most; 7.7 again says the part-based comparison cannot be settled
-- because nobody has whole-vehicle photographs with damage annotations.
--
-- Every one of those is the same missing thing, and the product has been
-- throwing away the only source of it: the user is looking at the photograph and
-- at the findings, and knows which ones are wrong.
--
-- ===========================================================================
--  Three decisions, because each is a place this could go wrong quietly
-- ===========================================================================
--
-- 1. A CORRECTION IS A NEW RECORD, NOT AN EDIT.
--
--    `analyses` has no UPDATE policy on purpose -- it is a record of what a model
--    said at a point in time, and editing it would make the history meaningless.
--    That reasoning does not weaken because the edit would be a user's. So a
--    correction sits beside the analysis and the analysis stays exactly as the
--    model produced it. Both are readable, and which is which is never in doubt.
--
-- 2. IT NEVER FEEDS A MODEL BY ITSELF.
--
--    Nothing here retrains anything. These rows are an evaluation set being
--    assembled by hand, and the moment they close a loop automatically the
--    system starts learning from whatever a user was willing to click. Every
--    number this project publishes was measured against data somebody looked at.
--
-- 3. KEEPING THE PHOTOGRAPH IS A SEPARATE, EXPLICIT ANSWER.
--
--    A correction without its image is nearly worthless -- it says a `dent` at
--    these coordinates was wrong, about pixels that no longer exist. But the
--    retention claim in the README is 7 days, and quietly extending it because
--    somebody reported a bad box would turn a correction into a consent form
--    nobody read. So `retain_image` is its own boolean, defaulting to false, and
--    the retention job honours it. A user who withdraws by deleting the analysis
--    takes the correction with it, by cascade.

create table if not exists public.corrections (
    id              uuid primary key,
    analysis_id     uuid not null references public.analyses (id) on delete cascade,
    user_id         uuid not null references auth.users (id) on delete cascade,
    created_at      timestamptz not null default now(),

    -- What is wrong. A closed vocabulary rather than free text: an open field
    -- produces a thousand phrasings of four things, and none of them counts.
    kind            text not null check (kind in (
                        'wrong_finding',    -- this finding is not there
                        'missed_damage',    -- there is damage nothing reported
                        'wrong_type',       -- right place, wrong class
                        'wrong_severity',   -- right damage, wrong band
                        'nothing_wrong'     -- the car is undamaged
                    )),

    -- Which finding, by its index in the stored `findings` array. Null for
    -- `missed_damage` and `nothing_wrong`, which are about the list as a whole.
    finding_index   integer check (finding_index is null or finding_index >= 0),

    -- What it should have said, where the user can say. A DamageType for
    -- `missed_damage` and `wrong_type`; validated in the API against the enum,
    -- not here, so the vocabulary has one home.
    expected_type   text,

    note            text check (note is null or char_length(note) <= 1000),

    -- Explicit consent to keep the photograph past the retention window so the
    -- correction remains attached to something. See decision 3 above.
    retain_image    boolean not null default false,

    -- A correction about a specific finding has to name one, and a correction
    -- about the list as a whole must not: `finding_index = 0` on a
    -- `missed_damage` row would read as "finding 0 is missing", which is not a
    -- sentence anybody meant.
    constraint finding_kinds_name_a_finding check (
        (kind in ('wrong_finding', 'wrong_type', 'wrong_severity')
            and finding_index is not null)
        or (kind in ('missed_damage', 'nothing_wrong') and finding_index is null)
    ),

    -- One correction per user per finding per kind. Clicking twice is a
    -- double-click, not two disagreements.
    constraint one_correction_per_finding
        unique (analysis_id, user_id, kind, finding_index)
);

comment on table public.corrections is
    'What a user says the model got wrong. Never edits the analysis; never retrains anything.';
comment on column public.corrections.retain_image is
    'Explicit consent to keep the photograph past the retention window.';

create index if not exists corrections_analysis_idx
    on public.corrections (analysis_id);

-- The retention job asks "is this analysis donated?" for every expiring row.
create index if not exists corrections_retained_idx
    on public.corrections (analysis_id) where retain_image;

-- ===========================================================================
--  Row-level security
-- ===========================================================================

alter table public.corrections enable row level security;

-- No UPDATE, for the same reason `analyses` has none: a correction is also a
-- record of what somebody said at a point in time. Changing your mind is a
-- delete and a new row.
grant select, insert, delete on public.corrections to authenticated;

drop policy if exists corrections_select_own on public.corrections;
create policy corrections_select_own on public.corrections
    for select using (auth.uid() = user_id);

-- The `exists` clause is what stops a user filing corrections against an
-- analysis that is not theirs. RLS on `analyses` already hides those rows, so
-- the subquery finds nothing and the insert is refused.
drop policy if exists corrections_insert_own on public.corrections;
create policy corrections_insert_own on public.corrections
    for insert with check (
        auth.uid() = user_id
        and exists (
            select 1 from public.analyses a
            where a.id = analysis_id and a.user_id = auth.uid()
        )
    );

drop policy if exists corrections_delete_own on public.corrections;
create policy corrections_delete_own on public.corrections
    for delete using (auth.uid() = user_id);

-- ===========================================================================
--  Retention, revised
-- ===========================================================================
--
-- A donated photograph is kept longer, not forever. `p_donated_retention_days`
-- is a stated second window rather than an absence of one: "we keep it while it
-- is useful" is not a policy anybody can check, and the whole point of the
-- separate boolean is that the user was told what they were agreeing to.
--
-- Deleting the analysis cascades to the correction, so withdrawing consent is
-- the deletion path that already exists and is already documented.

-- Separate and immutable-ish so both the object delete and the row delete ask
-- the same question. Two hand-written `exists` clauses is how one of them would
-- eventually gain a condition the other lacked, and storage would drift from
-- the rows it belongs to.
create or replace function public.is_donated(p_analysis_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1 from public.corrections c
        where c.analysis_id = p_analysis_id and c.retain_image
    );
$$;

create or replace function public.delete_expired_analyses(
    p_retention_days integer,
    p_donated_retention_days integer default 365
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    deleted_count integer;
begin
    -- Storage objects first. If this transaction fails after removing them the
    -- rows survive and the next run retries; the reverse order would orphan
    -- objects that nothing references and nothing would ever clean up.
    delete from storage.objects
    where bucket_id = 'biovision-images'
      and name in (
          select a.storage_path
          from public.analyses a
          where a.storage_path is not null
            and a.created_at < now() - make_interval(
                days => case when public.is_donated(a.id)
                             then p_donated_retention_days
                             else p_retention_days end
            )
      );

    delete from public.analyses a
    where a.created_at < now() - make_interval(
        days => case when public.is_donated(a.id)
                     then p_donated_retention_days
                     else p_retention_days end
    );

    get diagnostics deleted_count = row_count;
    return deleted_count;
end;
$$;

comment on function public.delete_expired_analyses is
    'Deletes analyses past their retention window. Donated ones get the longer window.';

-- The schedule names both windows explicitly rather than relying on the default,
-- so the policy is readable from the job.
select cron.unschedule('biovision-retention')
where exists (select 1 from cron.job where jobname = 'biovision-retention');

select cron.schedule(
    'biovision-retention',
    '15 3 * * *',
    $$ select public.delete_expired_analyses(7, 365); $$
);

-- ===========================================================================
--  Verification
-- ===========================================================================
--
-- Nothing undonated older than the short window should remain:
--
--   select count(*) from public.analyses a
--    where a.created_at < now() - interval '7 days'
--      and not public.is_donated(a.id);        -- must be 0
--
-- What has been collected, which is the point of the table:
--
--   select kind, count(*) from public.corrections group by kind order by 2 desc;
