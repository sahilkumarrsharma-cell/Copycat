create table if not exists public.handwriting_sessions (
    id text primary key check (id ~ '^[a-f0-9]{32}$'),
    found jsonb not null,
    missing jsonb not null,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null
);

alter table public.handwriting_sessions enable row level security;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('copycat-glyphs', 'copycat-glyphs', false, 10485760, array['image/png'])
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;
