-- Finca Gallinal v8.2 · Supabase Storage para snapshots climáticos
-- Ejecutar en Supabase → SQL Editor.

-- 1) Crear bucket privado para snapshots climáticos
insert into storage.buckets (id, name, public)
values ('climate-snapshots', 'climate-snapshots', false)
on conflict (id) do nothing;

-- 2) Permitir lectura del bucket con clave anon/authenticated
drop policy if exists "climate_snapshots_read" on storage.objects;
create policy "climate_snapshots_read"
on storage.objects
for select
to anon, authenticated
using (bucket_id = 'climate-snapshots');

-- 3) Permitir subida de snapshots
drop policy if exists "climate_snapshots_insert" on storage.objects;
create policy "climate_snapshots_insert"
on storage.objects
for insert
to anon, authenticated
with check (bucket_id = 'climate-snapshots');

-- 4) Permitir sobrescribir/actualizar snapshots
drop policy if exists "climate_snapshots_update" on storage.objects;
create policy "climate_snapshots_update"
on storage.objects
for update
to anon, authenticated
using (bucket_id = 'climate-snapshots')
with check (bucket_id = 'climate-snapshots');

-- 5) Opcional: permitir borrar snapshots desde la app si se añade esa función en el futuro
drop policy if exists "climate_snapshots_delete" on storage.objects;
create policy "climate_snapshots_delete"
on storage.objects
for delete
to anon, authenticated
using (bucket_id = 'climate-snapshots');
