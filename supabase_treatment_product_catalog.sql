create table if not exists public.treatment_product_catalog (
  product text primary key,
  alias text,
  materias_activas text,
  frac text,
  familia text,
  eficacia_moteado double precision,
  eficacia_monilia double precision,
  eficacia_oidio double precision,
  comentario text,
  activo boolean default true,
  updated_at timestamp without time zone default now()
);

alter table public.treatment_product_catalog enable row level security;

drop policy if exists "treatment_product_catalog_select_all" on public.treatment_product_catalog;
drop policy if exists "treatment_product_catalog_insert_all" on public.treatment_product_catalog;
drop policy if exists "treatment_product_catalog_update_all" on public.treatment_product_catalog;
drop policy if exists "treatment_product_catalog_delete_all" on public.treatment_product_catalog;

create policy "treatment_product_catalog_select_all"
on public.treatment_product_catalog
for select
to anon, authenticated
using (true);

create policy "treatment_product_catalog_insert_all"
on public.treatment_product_catalog
for insert
to anon, authenticated
with check (true);

create policy "treatment_product_catalog_update_all"
on public.treatment_product_catalog
for update
to anon, authenticated
using (true)
with check (true);

create policy "treatment_product_catalog_delete_all"
on public.treatment_product_catalog
for delete
to anon, authenticated
using (true);
