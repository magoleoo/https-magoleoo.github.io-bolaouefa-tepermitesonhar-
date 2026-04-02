-- Supabase shadow schema for Bolão UEFA
-- Objetivo: operar em paralelo ao sistema atual, sem substituir o fluxo oficial.

create table if not exists public.bolao_seasons (
  season_id text primary key,
  season_label text not null,
  is_active boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.bolao_participants (
  participant_id text primary key,
  participant_name text not null unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.bolao_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  participant_id text not null unique references public.bolao_participants(participant_id) on delete restrict,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.bolao_matches (
  season_id text not null references public.bolao_seasons(season_id) on delete cascade,
  match_key text not null,
  phase_key text not null,
  round_label text,
  leg text,
  matchday_label text,
  kickoff_utc timestamptz,
  home_team_name text not null,
  away_team_name text not null,
  score_home_90 integer,
  score_away_90 integer,
  qualified_team_name text,
  status_short text,
  status_long text,
  source text not null default 'shadow-sync',
  updated_at timestamptz not null default now(),
  primary key (season_id, match_key)
);

create table if not exists public.bolao_ranking_snapshot (
  season_id text not null references public.bolao_seasons(season_id) on delete cascade,
  participant_id text not null references public.bolao_participants(participant_id) on delete cascade,
  position integer not null,
  total_points numeric(10,2) not null default 0,
  first_phase_points numeric(10,2) not null default 0,
  playoff_points numeric(10,2) not null default 0,
  round_of_16_points numeric(10,2) not null default 0,
  quarter_points numeric(10,2) not null default 0,
  semi_points numeric(10,2) not null default 0,
  final_points numeric(10,2) not null default 0,
  superclassic_points numeric(10,2) not null default 0,
  hope_solo_hits integer not null default 0,
  favorite_team text,
  scorer_pick text,
  assist_pick text,
  delta_vs_ranking_sheet numeric(10,2) not null default 0,
  source text not null default 'shadow-sync',
  captured_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (season_id, participant_id)
);

create table if not exists public.bolao_predictions (
  season_id text not null references public.bolao_seasons(season_id) on delete cascade,
  participant_id text not null references public.bolao_participants(participant_id) on delete cascade,
  match_key text not null,
  pick_home integer,
  pick_away integer,
  predicted_qualified_team text,
  source text not null default 'site',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (season_id, participant_id, match_key)
);

create table if not exists public.bolao_sync_runs (
  run_id text primary key,
  season_id text not null,
  source text not null,
  status text not null,
  message text,
  participants_upserted integer not null default 0,
  ranking_upserted integer not null default 0,
  matches_upserted integer not null default 0,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

create or replace function public.bolao_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_bolao_seasons_updated_at on public.bolao_seasons;
create trigger trg_bolao_seasons_updated_at
before update on public.bolao_seasons
for each row execute function public.bolao_touch_updated_at();

drop trigger if exists trg_bolao_participants_updated_at on public.bolao_participants;
create trigger trg_bolao_participants_updated_at
before update on public.bolao_participants
for each row execute function public.bolao_touch_updated_at();

drop trigger if exists trg_bolao_profiles_updated_at on public.bolao_profiles;
create trigger trg_bolao_profiles_updated_at
before update on public.bolao_profiles
for each row execute function public.bolao_touch_updated_at();

drop trigger if exists trg_bolao_matches_updated_at on public.bolao_matches;
create trigger trg_bolao_matches_updated_at
before update on public.bolao_matches
for each row execute function public.bolao_touch_updated_at();

drop trigger if exists trg_bolao_ranking_snapshot_updated_at on public.bolao_ranking_snapshot;
create trigger trg_bolao_ranking_snapshot_updated_at
before update on public.bolao_ranking_snapshot
for each row execute function public.bolao_touch_updated_at();

drop trigger if exists trg_bolao_predictions_updated_at on public.bolao_predictions;
create trigger trg_bolao_predictions_updated_at
before update on public.bolao_predictions
for each row execute function public.bolao_touch_updated_at();

alter table public.bolao_profiles enable row level security;
alter table public.bolao_predictions enable row level security;

drop policy if exists profiles_select_own on public.bolao_profiles;
create policy profiles_select_own
on public.bolao_profiles
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists profiles_insert_own on public.bolao_profiles;
create policy profiles_insert_own
on public.bolao_profiles
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists profiles_update_own on public.bolao_profiles;
create policy profiles_update_own
on public.bolao_profiles
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists predictions_read_all_authenticated on public.bolao_predictions;
create policy predictions_read_all_authenticated
on public.bolao_predictions
for select
to authenticated
using (true);

drop policy if exists predictions_insert_own on public.bolao_predictions;
create policy predictions_insert_own
on public.bolao_predictions
for insert
to authenticated
with check (
  exists (
    select 1
    from public.bolao_profiles p
    where p.user_id = auth.uid()
      and p.participant_id = bolao_predictions.participant_id
  )
);

drop policy if exists predictions_update_own on public.bolao_predictions;
create policy predictions_update_own
on public.bolao_predictions
for update
to authenticated
using (
  exists (
    select 1
    from public.bolao_profiles p
    where p.user_id = auth.uid()
      and p.participant_id = bolao_predictions.participant_id
  )
)
with check (
  exists (
    select 1
    from public.bolao_profiles p
    where p.user_id = auth.uid()
      and p.participant_id = bolao_predictions.participant_id
  )
);

drop policy if exists predictions_delete_own on public.bolao_predictions;
create policy predictions_delete_own
on public.bolao_predictions
for delete
to authenticated
using (
  exists (
    select 1
    from public.bolao_profiles p
    where p.user_id = auth.uid()
      and p.participant_id = bolao_predictions.participant_id
  )
);

grant select on public.bolao_seasons to anon, authenticated;
grant select on public.bolao_participants to anon, authenticated;
grant select on public.bolao_matches to anon, authenticated;
grant select on public.bolao_ranking_snapshot to anon, authenticated;

grant select, insert, update on public.bolao_profiles to authenticated;
grant select, insert, update, delete on public.bolao_predictions to authenticated;
