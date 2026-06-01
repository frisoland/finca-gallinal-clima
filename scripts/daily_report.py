#!/usr/bin/env python3
"""
Informe diario automático de Finca Gallinal → Telegram.

Este script se ejecuta sin interfaz (headless). Reutiliza la lógica de `app.py`:
  · Inyecta un stub de Streamlit para poder importar app.py sin renderizar UI.
  · El propio arranque de app.py autocarga los datos desde Supabase
    (histórico, actuaciones, trampas/biofix de carpocapsa) y la previsión Sencrop.
  · Construye el informe con build_daily_report_text() y lo envía con
    telegram_send_message().

Variables de entorno necesarias (GitHub Secrets):
  SUPABASE_URL, SUPABASE_KEY          → para autocargar datos
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID → para enviar el informe
  SENCROP_APP_ID, SENCROP_APP_SECRET   → (opcional) previsión meteo
  (o SENCROP_TOKEN)
"""
import os
import sys
import types

import pandas as pd

# Forzar UTF-8 en la salida (la consola de Windows usa cp1252 por defecto)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# La raíz del repo (donde está app.py) es el directorio padre de scripts/
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ── Forzar modo headless ANTES de importar app ────────────────────────────────
os.environ["FINCA_GALLINAL_HEADLESS"] = "1"


# ══════════════════════════════════════════════════════════════════════════════
# Stub de Streamlit: permite importar app.py fuera de `streamlit run`.
# Todas las llamadas a st.* son no-ops salvo session_state y secrets.
# ══════════════════════════════════════════════════════════════════════════════
class _El:
    """Elemento stub: soporta context manager, llamada y acceso a atributos."""
    def __enter__(self):       return self
    def __exit__(self, *a):    return False
    def __call__(self, *a, **k): return self
    def __getattr__(self, n):  return self
    def __iter__(self):        return iter([])


class _SessionState(dict):
    def __getattr__(self, n):
        try:
            return self[n]
        except KeyError:
            raise AttributeError(n)
    def __setattr__(self, n, v):
        self[n] = v
    def __delattr__(self, n):
        try:
            del self[n]
        except KeyError:
            raise AttributeError(n)


class _Secrets:
    """Lee los secrets desde las variables de entorno."""
    def __init__(self, d):
        self._d = dict(d)
    def get(self, k, default=None):
        return self._d.get(k, default)
    def __getitem__(self, k):
        return self._d[k]
    def __contains__(self, k):
        return k in self._d


class _StreamlitStub(types.ModuleType):
    def __init__(self, name):
        super().__init__(name)
        self.session_state = _SessionState()
        self.secrets = _Secrets(os.environ)

    def set_page_config(self, *a, **k):
        return None

    def cache_data(self, *a, **k):
        # Soporta @st.cache_data y @st.cache_data(ttl=...)
        if a and callable(a[0]) and not k:
            return a[0]
        def deco(fn):
            return fn
        return deco

    cache_resource = cache_data

    def columns(self, spec, *a, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [_El() for _ in range(n)]

    def tabs(self, labels, *a, **k):
        try:
            return [_El() for _ in labels]
        except TypeError:
            return [_El()]

    def __getattr__(self, name):
        # Cualquier otra llamada st.* → no-op que devuelve un elemento stub
        def _noop(*a, **k):
            return _El()
        return _noop


def _install_streamlit_stub():
    st_stub = _StreamlitStub("streamlit")

    comp_pkg = types.ModuleType("streamlit.components")
    comp_v1  = types.ModuleType("streamlit.components.v1")
    comp_v1.html = lambda *a, **k: None
    comp_v1.declare_component = lambda *a, **k: (lambda *a, **k: None)
    comp_pkg.v1 = comp_v1
    st_stub.components = comp_pkg

    sys.modules["streamlit"] = st_stub
    sys.modules["streamlit.components"] = comp_pkg
    sys.modules["streamlit.components.v1"] = comp_v1
    return st_stub


def main():
    _install_streamlit_stub()

    # Importar app.py: al hacerlo, su bloque de arranque autocarga los datos
    # desde Supabase (si SUPABASE_URL / SUPABASE_KEY están en el entorno).
    try:
        import app
    except Exception as exc:
        print(f"ERROR importando app.py: {exc}", file=sys.stderr)
        raise

    # ── DIAGNÓSTICO ───────────────────────────────────────────────────────────
    print("=" * 60)
    print("DIAGNÓSTICO DE ENTORNO")
    def _mask(v):
        if not v:
            return "(vacío)"
        return f"{v[:6]}…{v[-4:]} (len={len(v)})"
    print(f"  SUPABASE_URL       presente: {_mask(os.environ.get('SUPABASE_URL',''))}")
    print(f"  SUPABASE_KEY       presente: {_mask(os.environ.get('SUPABASE_KEY',''))}")
    print(f"  TELEGRAM_BOT_TOKEN presente: {_mask(os.environ.get('TELEGRAM_BOT_TOKEN',''))}")
    print(f"  TELEGRAM_CHAT_ID   presente: {_mask(os.environ.get('TELEGRAM_CHAT_ID',''))}")
    try:
        print(f"  supabase_is_configured() = {app.supabase_is_configured()}")
        _u, _k = app.get_supabase_credentials()
        print(f"  URL normalizada: {_u}")
    except Exception as _e:
        print(f"  ERROR comprobando config Supabase: {_e}")

    # Llamadas directas a los loaders para ver qué devuelve Supabase
    print("-" * 60)
    print("CARGA DIRECTA DESDE SUPABASE")
    try:
        _h, _hmsg = app.load_climate_snapshot_from_supabase(use_cache=False)
        print(f"  histórico  → {0 if _h is None else len(_h)} filas · msg: {_hmsg}")
    except Exception as _e:
        print(f"  histórico  → EXCEPCIÓN: {_e}")
    try:
        _a, _amsg = app.load_activities_from_supabase()
        print(f"  actuaciones→ {0 if _a is None else len(_a)} filas · msg: {_amsg}")
    except Exception as _e:
        print(f"  actuaciones→ EXCEPCIÓN: {_e}")
    try:
        _t, _b, _d, _cmsg = app.load_carpocapsa_snapshot_from_supabase()
        print(f"  carpocapsa → trampas: {0 if _t is None else len(_t)} · "
              f"biofix: {0 if _b is None else len(_b)} · msg: {_cmsg}")
    except Exception as _e:
        print(f"  carpocapsa → EXCEPCIÓN: {_e}")
    print("=" * 60)

    ss = app.st.session_state

    history    = ss.get("history_df",            pd.DataFrame())
    activities = ss.get("activities_df",         pd.DataFrame())
    traps      = ss.get("carpocapsa_traps_df",   pd.DataFrame())
    biofix     = ss.get("carpocapsa_biofix_df",  pd.DataFrame())
    forecast   = ss.get("forecast_df",           pd.DataFrame())

    # Si el autoload del import no rellenó session_state, cargar aquí directamente
    if (history is None or history.empty):
        _h, _ = app.load_climate_snapshot_from_supabase(use_cache=False)
        if _h is not None and not _h.empty:
            history = _h
    if (activities is None or activities.empty):
        _a, _ = app.load_activities_from_supabase()
        if _a is not None and not _a.empty:
            activities = _a
    if (traps is None or traps.empty) or (biofix is None or biofix.empty):
        _t, _b, _d, _ = app.load_carpocapsa_snapshot_from_supabase()
        if _t is not None and not _t.empty:
            traps = _t
        if _b is not None and not _b.empty:
            biofix = _b
            ss["carpocapsa_biofix_df"] = _b

    print(f"Datos finales → histórico: {len(history)} filas · "
          f"actuaciones: {len(activities)} · trampas: {len(traps)} · "
          f"biofix: {len(biofix)} · previsión: {len(forecast)}")

    # ── DIAGNÓSTICO de cálculo (sin try/except, para ver excepciones reales) ────
    print("-" * 60)
    print("CÁLCULO DE VENTANAS / DECISIONES")
    import traceback as _tb
    try:
        _cw = app.carpocapsa_build_multi_windows(
            traps, history, activities_df=activities,
            campaign_year=pd.Timestamp.now().year,
        )
        print(f"  carpocapsa_build_multi_windows → {len(_cw)} ventanas")
        if not _cw.empty:
            print("  Estados:", _cw['Estado'].value_counts().to_dict())
    except Exception:
        print("  EXCEPCIÓN en carpocapsa_build_multi_windows:")
        _tb.print_exc()
    try:
        _rk = app.build_risk_timeline(history, forecast, days_back=60)
        _dc = app.daily_treatment_decision(history, activities, _rk, persistence_days=16)
        print(f"  daily_treatment_decision → {len(_dc)} filas")
        if not _dc.empty and "_priority" in _dc.columns:
            print("  Prioridades:", _dc['_priority'].value_counts().to_dict())
    except Exception:
        print("  EXCEPCIÓN en daily_treatment_decision:")
        _tb.print_exc()
    print("=" * 60)

    # Construir el informe (mismo texto que el botón manual de la app)
    texto = app.build_daily_report_text(
        history, traps, activities,
        forecast_df=forecast,
        persistence_days=16,
    )

    print("─" * 60)
    print(texto)
    print("─" * 60)

    # Enviar a Telegram
    if not app.telegram_is_configured():
        print("AVISO: Telegram no configurado (faltan TELEGRAM_BOT_TOKEN / "
              "TELEGRAM_CHAT_ID). No se envía.", file=sys.stderr)
        return 1

    ok, detalle = app.telegram_send_message(texto)
    if ok:
        print(f"✅ Informe enviado: {detalle}")
        return 0
    print(f"❌ Error al enviar: {detalle}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
