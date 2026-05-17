# Finca Gallinal · Plataforma agroclimática v9.0.0

Aplicación web en Streamlit para análisis agroclimático, seguimiento fitosanitario, gestión de riego, fenología y control de carpocapsa en Finca Gallinal.

---

## Historial de versiones

### v9.0.0 — Mayo 2026
**Correcciones de bugs y mejoras funcionales**

#### Bugs corregidos

- **Error de sintaxis (línea 8994):** Indentación rota en la pestaña Carpocapsa que impedía arrancar la app. Introducida por edición incorrecta en v8.9.9.
- **`io.io.BytesIO()` → `io.BytesIO()`:** Error al crear el snapshot Parquet comprimido en la pestaña de Importación (`No se pudo crear el Parquet comprimido: module 'io' has no attribute 'io'`).
- **`NameError` en Carpocapsa:** Faltaban la constante `CARPOCAPSA_TREATMENT_KEYWORDS` y la función auxiliar `text_contains_any_keyword()`, que se llamaban pero nunca se habían definido en el código. Causaba error al cargar actuaciones desde snapshot.
- **Error `TypeError` en pestaña Frío:** `winter_label_from_analysis_year()` petaba con `int(None)` al añadir nuevos CSV climáticos con datos de 2026, porque se generaba el año 2027 como opción sin datos reales. Corregido blindando la función y limitando `available_chill_analysis_years()` a periodos con al menos 24 horas de datos reales.
- **Sanidad no leía tratamientos recientes:** Al analizar "última semana", `end_ts` era la última fecha del CSV climático, que podía ser anterior al día actual. Los tratamientos aplicados ese mismo día quedaban fuera del filtro y la app recomendaba tratar campos ya tratados. Corregido usando `max(end_ts, hoy)` como límite de búsqueda de actuaciones y calculando `days_since_last` siempre desde hoy.

#### Mejoras añadidas

- **Carpocapsa → Histórico multi-año en Supabase:** Nuevo expander "☁️ Guardar / Cargar histórico carpocapsa en Supabase". Permite acumular capturas, biofix y daños de varios años (ej. 2025 + 2026) guardados como Parquet comprimido en Supabase Storage, igual que el snapshot climático. Flujo: importar Excel 2025 → importar Excel 2026 → guardar snapshot → la próxima sesión carga ambos años de golpe.
- **Carpocapsa → Sección 6: DD acumulados en el momento del tratamiento:** Nueva sección que cruza las lecturas de trampa con los tratamientos de Agroptima y calcula los grados-día acumulados **entre la lectura de presión y la fecha de tratamiento**. Permite evaluar si se trató a tiempo o con retraso respecto a la señal de las trampas. Umbral de capturas configurable mediante selector (1, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20). Los campos sin biofix asignado se omiten del análisis.

---

### v8.9.9 — Base de partida
- Integración de tratamientos de carpocapsa desde actuaciones Agroptima.
- Detección automática por palabras clave: Bactur, Bacillus thuringiensis, Bt, Carpocapsa, Cydia, Codling, Granulovirus, CpGV, Madex, Carpovirusina, Delfin, Xentari, Dipel.
- Bloque `5. Tratamientos de carpocapsa desde Agroptima` en pestaña Carpocapsa.
- Información mostrada por tratamiento: fecha, campaña, producto, trabajo, campos, superficie, cantidad, dosis, días desde tratamiento, lluvia acumulada desde tratamiento, comentarios, ID Agroptima.

---

## Estructura de la aplicación

| Pestaña | Función |
|---|---|
| Instrucciones | Guía de uso de la plataforma |
| Dashboard | Resumen general del estado de la finca |
| Importación | Carga y actualización del snapshot climático (CSV → Parquet comprimido en Supabase) |
| Análisis | Análisis climático por periodo: última semana, último mes, año completo o rango personalizado |
| Fenología | Fases fenológicas del cultivo por campaña |
| Frío | Horas frío, unidades Utah y porciones de frío por campaña invernal |
| Comparador | Comparación de campañas climáticas |
| Sanidad | Semáforo fitosanitario (Moteado, Monilia, Oídio) y recomendaciones de tratamiento por campo cruzadas con Agroptima |
| Carpocapsa | Seguimiento de trampas, biofix, grados-día, estado fenológico, tratamientos y análisis DD-tratamiento |
| Riego | Seguimiento y recomendaciones de riego |
| Campos | Gestión de campos y superficies |
| Actuaciones | Importación y gestión del histórico de actuaciones desde Agroptima |
| Informe semanal | Generación de informe PDF semanal |
| Configuración | Parámetros generales de la plataforma |

---

## Tecnologías

- **Streamlit** — interfaz web
- **Pandas / NumPy** — procesamiento de datos climáticos
- **PyArrow / Snappy** — serialización Parquet comprimida
- **ReportLab** — generación de informes PDF
- **Supabase** — base de datos y almacenamiento en la nube (actuaciones + snapshots climáticos + snapshots carpocapsa)
- **OpenPyXL** — lectura de Excel de Agroptima

---

## Uso recomendado

1. Importar CSVs climáticos periódicamente desde la pestaña **Importación** y guardar el snapshot.
2. Exportar actuaciones desde Agroptima e importarlas en la pestaña **Actuaciones** (fungicidas y carpocapsa juntos).
3. Revisar el semáforo en **Sanidad** — la app cruza automáticamente con los tratamientos recientes de Agroptima para no recomendar tratar campos ya tratados.
4. En **Carpocapsa**, importar el Excel de capturas por año, acumular varios años y guardar en Supabase. Usar la sección 6 para analizar el tiempo de respuesta entre señal de trampa y tratamiento.

