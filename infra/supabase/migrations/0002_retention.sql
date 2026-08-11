-- Retention: analyses and their stored images are deleted after 7 days.
--
-- A retention claim without a scheduled job behind it is marketing. This is the
-- job, and it runs in the database rather than the API so it keeps running when
-- the API is down, redeployed, or scaled to zero.

-- ===========================================================================
--  Deletion
-- ===========================================================================

create or replace function public.delete_expired_analyses(p_retention_days integer)
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
          select storage_path
          from public.analyses
          where storage_path is not null
            and created_at < now() - make_interval(days => p_retention_days)
      );

    delete from public.analyses
    where created_at < now() - make_interval(days => p_retention_days);

    get diagnostics deleted_count = row_count;
    return deleted_count;
end;
$$;

comment on function public.delete_expired_analyses is
    'Deletes analyses past the retention window and their stored images.';

-- ===========================================================================
--  Schedule
-- ===========================================================================
--
-- Requires pg_cron (Database -> Extensions in the Supabase dashboard).
-- Daily at 03:15 UTC -- off the hour so it does not contend with everything
-- else scheduled on the hour.

create extension if not exists pg_cron;

select cron.unschedule('biovision-retention')
where exists (select 1 from cron.job where jobname = 'biovision-retention');

select cron.schedule(
    'biovision-retention',
    '15 3 * * *',
    $$ select public.delete_expired_analyses(7); $$
);

-- ===========================================================================
--  Verification
-- ===========================================================================
--
-- The retention claim is only as good as the evidence that the job ran. After
-- deploying, confirm:
--
--   select * from cron.job where jobname = 'biovision-retention';
--   select * from cron.job_run_details
--    where jobid = (select jobid from cron.job where jobname = 'biovision-retention')
--    order by start_time desc limit 10;
--
-- Nothing older than the window should remain:
--
--   select count(*) from public.analyses
--    where created_at < now() - interval '7 days';   -- must be 0
