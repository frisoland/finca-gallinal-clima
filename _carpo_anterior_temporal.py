"""TEMPORAL (15/09/2026): versión ANTERIOR de 4 funciones de Carpocapsa, solo para comprobar
en el servidor (?medir=4) que la versión rápida da lo mismo. BORRAR al retirar el cronómetro."""


def carpocapsa_treatments_from_activities(activities_df, campaign_year, history=None, rain_days_limit=3):
    """
    Extrae tratamientos de carpocapsa desde el histórico de actuaciones/Agroptima.
    - Clasifica cada producto individualmente (carpocapsa / fungicida / abono)
    - Excluye fungicidas puros y abonos
    - Una actuación con mezcla (Bactur + fungicida) se incluye etiquetando cada componente
    - Usa Campo base del Excel de capturas para el cruce, no Campo/Zona
    rain_days_limit: días post-tratamiento para acumular lluvia (periodo crítico larva)
    """
    if activities_df is None or activities_df.empty:
        return pd.DataFrame()

    df = normalize_activities_df(activities_df).copy()
    df = df.drop(columns=[c for c in ["_clave_fallback", "_clave_importacion"] if c in df.columns], errors="ignore")
    df["Fecha_dt"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df.dropna(subset=["Fecha_dt"]).copy()
    df = df[df["Fecha_dt"].dt.year == int(campaign_year)].copy()

    if df.empty:
        return pd.DataFrame()

    # Filtrar: solo actuaciones que contengan al menos un producto de carpocapsa
    productos_col = "Productos" if "Productos" in df.columns else "Producto"
    search_text = (
        df[productos_col].fillna("").astype(str) + " " +
        df.get("Trabajo", pd.Series("", index=df.index)).fillna("").astype(str) + " " +
        df.get("Comentarios", pd.Series("", index=df.index)).fillna("").astype(str)
    )
    # Una actuacion entra si contiene alguna keyword de carpocapsa
    mask = search_text.apply(lambda x: text_contains_any_keyword(x, CARPOCAPSA_TREATMENT_KEYWORDS))
    df = df[mask].copy()

    if df.empty:
        return pd.DataFrame()

    hist = history.copy() if history is not None and not history.empty else pd.DataFrame()
    if not hist.empty and "fecha_hora" in hist.columns:
        hist["fecha_hora"] = pd.to_datetime(hist["fecha_hora"], errors="coerce")
        hist = hist.dropna(subset=["fecha_hora"]).copy()
        hist["fecha_dia"] = hist["fecha_hora"].dt.date
        last_climate_date = hist["fecha_hora"].max().date()
    else:
        last_climate_date = None

    import datetime as _dt
    rows = []
    for _, r in df.iterrows():
        treatment_date = r["Fecha_dt"].date()
        rain_since = np.nan
        days_since = np.nan
        if last_climate_date:
            days_since = max((last_climate_date - treatment_date).days, 0)
            if "lluvia_mm" in hist.columns:
                rain_end_date = min(
                    treatment_date + _dt.timedelta(days=rain_days_limit),
                    last_climate_date
                )
                rain_mask = (hist["fecha_dia"] >= treatment_date) & (hist["fecha_dia"] <= rain_end_date)
                rain_since = pd.to_numeric(hist.loc[rain_mask, "lluvia_mm"], errors="coerce").fillna(0).sum()

        producto_raw = str(r.get(productos_col, "") or "")

        # Clasificar cada producto de la mezcla
        productos_lista = [p.strip() for p in producto_raw.replace(";", ",").split(",") if p.strip()]
        tipos_detectados = [classify_product(p) for p in productos_lista]
        productos_carpocapsa = [p for p, t in zip(productos_lista, tipos_detectados) if t == "carpocapsa"]
        productos_fungicida  = [p for p, t in zip(productos_lista, tipos_detectados) if t == "fungicida"]
        productos_abono      = [p for p, t in zip(productos_lista, tipos_detectados) if t == "abono"]

        tipo_label = "Carpocapsa"
        if productos_fungicida:
            tipo_label += " + Fungicida"
        if productos_abono:
            tipo_label += " + Abono"

        campos_val = str(r.get("Campos reconocidos", "") or r.get("Campos", "") or "")

        rows.append({
            "Fecha":                    treatment_date,
            "Campaña":                  int(campaign_year),
            "Tipo tratamiento":         tipo_label,
            "Producto carpocapsa":      ", ".join(productos_carpocapsa) if productos_carpocapsa else producto_raw,
            "Fungicidas en mezcla":     ", ".join(productos_fungicida),
            "Abonos en mezcla":         ", ".join(productos_abono),
            "Campos":                   campos_val,
            "Superficie tratada ha":    r.get("Superficie tratada ha", np.nan),
            "Cantidad":                 r.get("Cantidad", np.nan),
            "Unidad cantidad":          r.get("Unidad cantidad", ""),
            "Dosis":                    r.get("Dosis", np.nan),
            "Unidad dosis":             r.get("Unidad dosis", ""),
            "Días desde tratamiento":   days_since,
            f"Lluvia {rain_days_limit}d post-tratamiento mm": round(float(rain_since), 2) if pd.notna(rain_since) else np.nan,
            "Comentarios":              r.get("Comentarios", ""),
            "ID Agroptima":             r.get("ID Agroptima", ""),
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("Fecha", ascending=False).reset_index(drop=True)
    return out


def carpocapsa_build_multi_windows(traps_df, history, base_temp=10.0, upper_temp=31.1,
                                    capture_threshold=3, dd_active_start=80, dd_active_end=130,
                                    activities_df=None, campaign_year=None, cierre_aviso_dias=3):
    """
    Modelo de ventanas múltiples por campo (simple).
    Cada lectura con capturas >= capture_threshold abre una ventana de DD propia.

    Estados:
    - ⏳ En espera:        DD acumulados < dd_active_start (ventana aún no activa)
    - 🔴 Activa — tratar:  dd_active_start <= DD <= dd_active_end y SIN tratamiento dentro
    - ✅ Tratado — cerrada: hay un tratamiento (Agroptima) cuyo DD acumulado desde el
                            trigger cae dentro de [dd_active_start, dd_active_end] → cubierta
    - 🔒 Cerrada por DD:   DD > dd_active_end y sin tratamiento dentro (ventana pasada)

    Un mismo tratamiento puede cerrar varias ventanas (todas las que estén activas en
    esa fecha). Sin lógica de reentrada ni de 2º pase.
    """
    if traps_df is None or traps_df.empty:
        return pd.DataFrame()
    
    daily_dd = carpocapsa_daily_degree_days(history, base_temp=base_temp, upper_temp=upper_temp, method="horario")
    if daily_dd.empty:
        return pd.DataFrame()

    traps = carpocapsa_prepare_traps_df(traps_df).copy()
    if traps.empty:
        return pd.DataFrame()

    # Filtrar por campaña si se especifica
    if campaign_year and "Campaña" in traps.columns:
        traps = traps[pd.to_numeric(traps["Campaña"], errors="coerce") == int(campaign_year)]

    traps["Fecha"] = pd.to_datetime(traps["Fecha"], errors="coerce")
    traps["_capturas"] = pd.to_numeric(traps["Capturas machos"], errors="coerce").fillna(0)
    traps = traps.dropna(subset=["Fecha", "Campo/Zona"])

    # Preparar tratamientos si existen
    treatments = pd.DataFrame()
    if activities_df is not None and not activities_df.empty:
        act = activities_df.copy()
        act["fecha_dt"] = pd.to_datetime(act.get("fecha", act.get("Fecha", pd.Series())), errors="coerce")
        # Filtrar solo tratamientos fitosanitarios de carpocapsa
        if "trabajo" in act.columns:
            act = act[act["trabajo"].astype(str).str.contains("fitosanitario|carpocapsa|cydia", case=False, na=False)]
        treatments = act

    rows = []
    today = pd.Timestamp.today().normalize()

    # ── Modelo simple de cierre de ventana ────────────────────────────────────
    # Una ventana se abre con una lectura ≥ umbral de capturas. Está "activa" entre
    # dd_active_start y dd_active_end (los selectores DD inicio / DD fin). Si en
    # Agroptima hay un tratamiento cuyo DD acumulado (desde el trigger de la lectura)
    # cae DENTRO de ese rango [dd_active_start, dd_active_end] → el Bactur llegó al
    # árbol durante la ventana → se da por cubierta y se CIERRA. Un mismo tratamiento
    # puede cerrar varias ventanas (todas las activas en esa fecha). Sin reentrada
    # ni 2º pase: si quieres más margen, ajusta DD inicio/fin en los selectores.

    # Normalizar fechas del calendario DD una sola vez (eficiencia)
    _fechas_dd_norm = pd.to_datetime(daily_dd["Fecha"]).dt.normalize()
    if _fechas_dd_norm.dt.tz is not None:
        _fechas_dd_norm = _fechas_dd_norm.dt.tz_localize(None)

    # ── Helpers de matching (definidos UNA vez, fuera del loop) ───────────────
    def _campo_match_carpo(campos_str, target):
        campos_list = [c.strip().lower() for c in str(campos_str).split(",")]
        target_low  = target.strip().lower()
        if target_low in campos_list:
            return True

        def _substr_whole(needle, haystack):
            """Subcadena completa: el siguiente carácter no puede ser alnum ni guión."""
            idx = haystack.find(needle)
            if idx == -1:
                return False
            end = idx + len(needle)
            if end >= len(haystack):
                return True
            return not (haystack[end].isalnum() or haystack[end] == "-")

        return any(
            _substr_whole(target_low, c) or _substr_whole(c, target_low)
            for c in campos_list if len(c) >= 3
        )

    # Determinar columnas de producto/trabajo/comentarios de treatments una sola vez
    if not treatments.empty:
        _prod_col   = "Productos" if "Productos" in treatments.columns else "Producto"
        _trab_col   = "Trabajo" if "Trabajo" in treatments.columns else (
                      "trabajo" if "trabajo" in treatments.columns else None)
        _comt_col   = "Comentarios" if "Comentarios" in treatments.columns else None
        _campos_col = next((c for c in ["Campos reconocidos", "Campos", "campo", "campos_reconocidos"]
                            if c in treatments.columns), None)
    else:
        _prod_col = _trab_col = _comt_col = _campos_col = None

    def _has_carpocapsa(row):
        texto = str(row.get(_prod_col, "") or "")
        if _trab_col:
            texto += " " + str(row.get(_trab_col, "") or "")
        if _comt_col:
            texto += " " + str(row.get(_comt_col, "") or "")
        return text_contains_any_keyword(texto, CARPOCAPSA_TREATMENT_KEYWORDS)

    for zona in traps["Campo/Zona"].unique():
        zona_str   = str(zona).strip()
        zona_traps = traps[traps["Campo/Zona"].astype(str).str.strip() == zona_str].sort_values("Fecha")

        # Lecturas que superan el umbral, ordenadas de MÁS ANTIGUA a MÁS NUEVA
        # (imprescindible para que la lógica de consumo funcione bien)
        trigger_reads = zona_traps[zona_traps["_capturas"] >= capture_threshold].sort_values("Fecha")

        # Pre-filtrar tratamientos de carpocapsa para esta zona
        campo_treats_carp = pd.DataFrame()
        if not treatments.empty and _campos_col:
            campo_base = zona_str.split(" - ")[0].strip() if " - " in zona_str else zona_str
            _campo_all = treatments[
                treatments[_campos_col].apply(lambda x: _campo_match_carpo(x, campo_base))
            ]
            if not _campo_all.empty:
                campo_treats_carp = (
                    _campo_all[_campo_all.apply(_has_carpocapsa, axis=1)]
                    .sort_values("fecha_dt")
                    .copy()
                )

        for _, trow in trigger_reads.iterrows():
            trigger_date = trow["Fecha"]
            capturas     = int(trow["_capturas"])

            # ── DD acumulados desde el trigger hasta hoy ──────────────────────
            trigger_norm = pd.Timestamp(trigger_date).normalize()
            if trigger_norm.tzinfo is not None:
                trigger_norm = trigger_norm.tz_localize(None)
            dd_future  = daily_dd[_fechas_dd_norm >= trigger_norm]
            dd_current = float(dd_future["DD día"].sum()) if not dd_future.empty else 0.0

            date_ini, _ = carpocapsa_estimated_date_for_dd(daily_dd, trigger_date, dd_active_start)
            date_end, _ = carpocapsa_estimated_date_for_dd(daily_dd, trigger_date, dd_active_end)

            # ── ¿Hay un tratamiento DENTRO del rango activo de ESTA ventana? ──
            # Si el Bactur llegó al árbol con DD acumulados (desde el trigger) entre
            # dd_active_start y dd_active_end, la ventana queda cubierta → cerrada.
            trat_fecha    = ""
            trat_dd       = ""
            trat_producto = ""
            if not campo_treats_carp.empty:
                post = campo_treats_carp[
                    campo_treats_carp["fecha_dt"] >= trigger_date
                ].sort_values("fecha_dt")
                for _, t_row in post.iterrows():
                    t_norm = pd.Timestamp(t_row["fecha_dt"]).normalize()
                    if t_norm.tzinfo is not None:
                        t_norm = t_norm.tz_localize(None)
                    dd_at = round(float(
                        daily_dd[(_fechas_dd_norm >= trigger_norm)
                                 & (_fechas_dd_norm <= t_norm)]["DD día"].sum()
                    ), 1)
                    if dd_active_start <= dd_at <= dd_active_end:
                        trat_fecha    = t_row["fecha_dt"].strftime("%d/%m/%Y")
                        trat_dd       = dd_at
                        trat_producto = str(t_row.get(_prod_col, t_row.get("producto", ""))).strip()
                        break   # el primer tratamiento dentro de la ventana la cierra

            # ── Estado (tratamiento manda; si no, según DD) ───────────────────
            dias_cierre = None
            if trat_fecha:
                estado = "✅ Tratado — cerrada"
                estado_orden = 3
                info_extra = f"Tratado {trat_fecha} ({trat_dd:g} DD)"
            elif dd_current < dd_active_start:
                estado = "⏳ En espera"
                estado_orden = 1
                if pd.notna(date_ini):
                    _dias = max(0, (date_ini.date() - today.date()).days)
                    info_extra = f"{_dias}d hasta ventana"
                else:
                    info_extra = "—"
            elif dd_current <= dd_active_end:
                estado_orden = 0
                # Días que faltan para que la ventana se pase de DD fin (cierre)
                dias_cierre = None
                if pd.notna(date_end):
                    dias_cierre = max(0, (date_end.date() - today.date()).days)
                if dias_cierre is not None and dias_cierre <= cierre_aviso_dias:
                    # PELIGRO: a punto de pasarse sin tratar (rojo)
                    estado = f"🔴 Activa — cierra en {dias_cierre}d"
                    info_extra = f"⚠️ ÚLTIMA OPORTUNIDAD · cierra en {dias_cierre}d sin tratar"
                else:
                    # Precaución: ventana abierta con margen (naranja)
                    estado = "🟠 Activa — tratar"
                    info_extra = ("⚠️ Tratar"
                                  + (f" · cierra en {dias_cierre}d" if dias_cierre is not None else ""))
            else:
                estado = "🔒 Cerrada por DD"
                estado_orden = 2
                info_extra = "Ventana pasada sin tratar"
                dias_cierre = None

            dd_display = int(round(dd_current))

            rows.append({
                "Campo/Zona":                    zona_str,
                "Fecha lectura":                 trigger_date.strftime("%d/%m/%Y"),
                "Capturas":                      capturas,
                "DD actual":                     dd_display,
                f"Fecha estimada {dd_active_start} DD": date_ini.strftime("%d/%m/%Y") if pd.notna(date_ini) else "—",
                f"Fecha estimada {dd_active_end} DD":   date_end.strftime("%d/%m/%Y") if pd.notna(date_end) else "—",
                "Estado":                        estado,
                "Info":                          info_extra,
                "_orden":                        estado_orden,
                "_reentry_wait":                 0,
                "_dias_cierre":                  dias_cierre if dias_cierre is not None else "",
                "Tratamiento fecha":             trat_fecha,
                "DD al tratar":                  trat_dd,
                "Producto":                      trat_producto,
            })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values(["_orden", "Campo/Zona", "Fecha lectura"]).drop(columns=["_orden"])
    return df


def carpocapsa_dd_at_treatment(traps_df, treatments_df, biofix_df, daily_dd, campaign_year,
                               threshold=5, min_days_gap=5,
                               biofix_threshold=CARPOCAPSA_BIOFIX_THRESHOLD):
    """Para cada campo, busca cada lectura con capturas >= threshold,
    el siguiente tratamiento de carpocapsa posterior para ese mismo campo y los DD
    acumulados entre la fecha de captura y la fecha de tratamiento.
    Lógica: captura >= umbral → siguiente trat. de ese campo (al menos min_days_gap días después)
            → DD acumulados → dejar de contar.
    min_days_gap: días mínimos entre la lectura y el tratamiento. Tratamientos dentro de esa
    ventana se consideran pre-planificados (parte del ciclo rutinario) y se saltan."""

    if traps_df is None or traps_df.empty:
        return pd.DataFrame()

    # ── Preparar capturas ──────────────────────────────────────────────────────
    t = traps_df.copy()
    t["Fecha_dt"] = pd.to_datetime(t["Fecha"], errors="coerce")

    cap_col = None
    for c in ["Capturas machos", "Capturas/trampa/día", "Capturas"]:
        if c in t.columns:
            cap_col = c
            break
    if cap_col is None:
        return pd.DataFrame()

    t["_capturas"] = pd.to_numeric(t[cap_col], errors="coerce")

    if "Campaña" in t.columns:
        t = t[pd.to_numeric(t["Campaña"], errors="coerce") == int(campaign_year)]

    t = t.dropna(subset=["Fecha_dt", "_capturas", "Campo/Zona"])

    if t.empty:
        return pd.DataFrame()

    # Biofix por campo según LITERATURA (helper común): primera captura sostenida
    # ≥ umbral, calculado de las lecturas reales (ver _carpocapsa_sustained_biofix).

    # ── DD acumulados entre dos fechas (inicio inclusive, fin inclusive) ───────
    def dd_entre_fechas(start_date, end_date):
        if daily_dd is None or daily_dd.empty or pd.isna(start_date) or pd.isna(end_date):
            return np.nan
        fechas = pd.to_datetime(daily_dd["Fecha"])
        mask = (fechas >= pd.Timestamp(start_date)) & (fechas <= pd.Timestamp(end_date))
        sub = daily_dd[mask]
        if sub.empty:
            return np.nan
        return round(float(pd.to_numeric(sub["DD día"], errors="coerce").fillna(0).sum()), 1)

    # ── Fase fenológica de la carpocapsa según DD desde biofix (literatura) ─────
    # Base 10 °C / techo 31,1 °C (= 50/88 °F, modelo estándar Cydia pomonella).
    # Referencias: Riedl/Croft/Howitt 1976; UC IPM; WSU.
    def _carpo_stage(dd):
        # Fases alineadas con CARPOCAPSA_GEN_DD (única fuente de verdad; ver el comentario
        # de esa constante para la conversión desde UC IPM en base 50 °F).
        # CORREGIDO 2026-08-14: antes 580–750 se llamaba "Eclosión 2ª gen" y >750 "Tras pico
        # 2ª gen". Está desplazado una fase: 580 es la EMERGENCIA DE ADULTOS de la 2ª y 750
        # el INICIO de su eclosión. Consecuencia del error: un campo a 900-1200 DD leía
        # "tras pico, ya pasó" cuando estaba en PLENA eclosión de 2ª gen sobre fruta a punto
        # de cosecha — la fase que más daño hace.
        # Los umbrales salen de carpocapsa_fase(), que es la FUENTE ÚNICA: antes
        # esta función tenía su propia tabla y no coincidía ni con las bandas de la
        # gráfica ni con carpocapsa_status_from_dd. El ⭐ marca la ventana óptima
        # (primeras entradas en fruto) y el ✅ que hay eclosión activa, en cualquier
        # generación — antes el ✅ solo cubría 20 DD en la 1ª y 480 en la 2ª.
        return carpocapsa_fase(dd)["nombre"]

    # ── Preparar tratamientos de carpocapsa ───────────────────────────────────
    treat = pd.DataFrame()
    if treatments_df is not None and not treatments_df.empty:
        treat = treatments_df.copy()
        treat["Fecha_dt"] = pd.to_datetime(treat["Fecha"], errors="coerce")
        treat = treat.dropna(subset=["Fecha_dt"])

    # ── Calcular fila por lectura >= umbral ───────────────────────────────────
    rows = []
    for campo in sorted(t["Campo/Zona"].unique()):
        campo_str = str(campo).strip()
        # Campo base para cruzar con Agroptima (antes del guion: "GY - Gallinal" → "GY")
        campo_base = campo_str.split(" - ")[0].strip() if " - " in campo_str else campo_str
        campo_traps = t[t["Campo/Zona"] == campo].sort_values("Fecha_dt")

        high = campo_traps[campo_traps["_capturas"] >= threshold].copy()
        if high.empty:
            continue

        # Biofix del campo (literatura): primera captura SOSTENIDA. Único por campo:
        # NO cambia entre filas. Usa el umbral BIOLÓGICO, no el de tratamiento —
        # si no, subir el umbral por coste retrasaría el arranque de los DD.
        bf_date, bf_sustained = _carpocapsa_sustained_biofix(campo_traps, biofix_threshold)
        if bf_date is None:
            bf_date = high.iloc[0]["Fecha_dt"].date()
            bf_sustained = False

        # Tratamientos de carpocapsa solo para este campo (sin fallback a otros campos)
        campo_treats = pd.DataFrame()
        if not treat.empty and "Campos" in treat.columns:
            campo_treats = treat[
                treat["Campos"].fillna("").str.contains(campo_base, case=False, na=False)
            ].sort_values("Fecha_dt").reset_index(drop=True)
        # Si no hay columna Campos o no hubo match, campo_treats queda vacío → "Sin tratamiento"

        for _, high_row in high.iterrows():
            high_date  = high_row["Fecha_dt"].date()
            high_capts = int(high_row["_capturas"])

            next_treatment_date    = None
            next_treatment_product = "Sin tratamiento registrado"
            dd_lectura_a_trat      = np.nan
            dd_biofix_a_trat       = np.nan
            dias_hasta_trat        = "—"

            if not campo_treats.empty:
                # Primer tratamiento carpocapsa al menos min_days_gap días después de la lectura
                # (tratamientos dentro de ese gap se consideran pre-planificados, no respuesta a la captura)
                import datetime as _dt
                min_date = high_date + _dt.timedelta(days=min_days_gap)
                posterior = campo_treats[campo_treats["Fecha_dt"].dt.date >= min_date]
                if not posterior.empty:
                    t_row = posterior.iloc[0]
                    next_treatment_date = t_row["Fecha_dt"].date()
                    next_treatment_product = ""
                    for pc in ["Producto carpocapsa", "Productos", "Producto"]:
                        val = str(t_row.get(pc, "") or "").strip()
                        if val and val.lower() not in ("nan", "none", ""):
                            next_treatment_product = val
                            break
                    if not next_treatment_product:
                        next_treatment_product = "Tratamiento carpocapsa"
                    dias_hasta_trat   = (next_treatment_date - high_date).days
                    dd_lectura_a_trat = dd_entre_fechas(high_date, next_treatment_date)
                    dd_biofix_a_trat  = dd_entre_fechas(bf_date, next_treatment_date)

            rows.append({
                "Campo/Zona":                     campo_str,
                "Campaña":                        int(campaign_year),
                f"Lectura ≥{threshold} capturas": high_date,
                "Capturas":                       high_capts,
                "Biofix":                         bf_date.strftime("%d/%m/%Y") + ("" if bf_sustained else " (no sost.)"),
                "Fecha tratamiento":              next_treatment_date if next_treatment_date else "—",
                "Días hasta trat.":               dias_hasta_trat,
                "DD lectura→trat. (tu método)":   dd_lectura_a_trat,
                "DD biofix→trat. (literatura)":   dd_biofix_a_trat,
                "Fase en el tratamiento (literatura)": _carpo_stage(dd_biofix_a_trat),
                "Producto":                       next_treatment_product,
            })

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out = out.sort_values(["Campo/Zona", f"Lectura ≥{threshold} capturas"]).reset_index(drop=True)
    return out


def carpocapsa_treatment_timing_by_field(traps_df, treatments_df, daily_dd, campaign_year,
                                         threshold=5, ideal_lo=120.0, ideal_hi=140.0, active_hi=360.0,
                                         biofix_threshold=CARPOCAPSA_BIOFIX_THRESHOLD):
    """Resumen por campo de la PUNTERÍA de TODOS los tratamientos de carpocapsa.
    Es CONSCIENTE DE GENERACIONES: detecta el biofix de cada generación del campo
    (1ª, 2ª…) y mide cada tratamiento contra el biofix de SU generación. Clasifica:
    Pronto (<ideal_lo) · ✅ Ideal (ideal_lo–ideal_hi) · Eclosión activa
    (ideal_hi–active_hi, aún eficaz) · Tarde (>active_hi: esa generación ya pasó).
    Devuelve un df con columnas de display + columnas numéricas «_…» para totales."""
    empty = pd.DataFrame()
    if traps_df is None or traps_df.empty or treatments_df is None or treatments_df.empty:
        return empty
    t = traps_df.copy()
    t["Fecha_dt"] = pd.to_datetime(t["Fecha"], errors="coerce")
    cap_col = next((c for c in ["Capturas machos", "Capturas/trampa/día", "Capturas"] if c in t.columns), None)
    if cap_col is None:
        return empty
    t["_capturas"] = pd.to_numeric(t[cap_col], errors="coerce")
    if "Campaña" in t.columns:
        t = t[pd.to_numeric(t["Campaña"], errors="coerce") == int(campaign_year)]
    t = t.dropna(subset=["Fecha_dt", "_capturas", "Campo/Zona"])
    if t.empty:
        return empty

    def dd_between(a, b):
        if daily_dd is None or daily_dd.empty or pd.isna(a) or pd.isna(b):
            return np.nan
        f = pd.to_datetime(daily_dd["Fecha"])
        s = daily_dd[(f >= pd.Timestamp(a)) & (f <= pd.Timestamp(b))]
        return round(float(pd.to_numeric(s["DD día"], errors="coerce").fillna(0).sum()), 1) if not s.empty else np.nan

    tr = treatments_df.copy()
    tr["Fecha_dt"] = pd.to_datetime(tr["Fecha"], errors="coerce")
    tr = tr.dropna(subset=["Fecha_dt"])
    tr = tr[tr["Fecha_dt"].dt.year == int(campaign_year)]
    if tr.empty or "Campos" not in tr.columns:
        return empty

    rows = []
    for campo in sorted(t["Campo/Zona"].astype(str).unique()):
        ct = t[t["Campo/Zona"].astype(str) == campo]
        bios = carpocapsa_generation_biofixes(ct, threshold, daily_dd,
                                              biofix_threshold=biofix_threshold)
        if not bios:
            continue
        campo_base = campo.split(" - ")[0].strip() if " - " in campo else campo
        ctr = tr[tr["Campos"].fillna("").str.contains(campo_base, case=False, na=False)]
        dates = sorted(set(ctr["Fecha_dt"].dt.date.tolist()))
        if not dates:
            continue
        npr = nid = nac = nta = 0
        for d in dates:
            gbf = None
            for b in bios:                 # biofix de la generación a la que pertenece
                if b <= d:
                    gbf = b
            if gbf is None:
                npr += 1                    # tratamiento anterior al 1er biofix → pre-vuelo
                continue
            dd = dd_between(gbf, d)
            if dd is None or (isinstance(dd, float) and np.isnan(dd)):
                continue
            if dd < ideal_lo:
                npr += 1
            elif dd <= ideal_hi:
                nid += 1
            elif dd <= active_hi:
                nac += 1
            else:
                nta += 1
        ntot = npr + nid + nac + nta
        if ntot == 0:
            continue
        nefi = nid + nac
        rows.append({
            "Campo/Zona": campo,
            "Gen.": len(bios),
            "Tratam.": ntot,
            "% eficaz (120–360)": f"{nefi}/{ntot} ({round(nefi / ntot * 100)}%)",
            "Pronto (<120)": npr,
            "✅ Ideal (120–140)": nid,
            "Activa (140–360)": nac,
            "Tarde (>360)": nta,
            "_efi": nefi, "_n": ntot, "_pr": npr, "_id": nid, "_ac": nac, "_ta": nta,
        })
    if not rows:
        return empty
    return pd.DataFrame(rows).sort_values("Campo/Zona").reset_index(drop=True)
