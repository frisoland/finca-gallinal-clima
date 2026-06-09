import re

import io
import time
from datetime import timedelta, date

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as _st_components
import requests
import copy
import os

# Modo "headless": cuando la app se importa desde un script externo (p. ej. el
# informe diario automático de GitHub Actions) NO se debe renderizar la interfaz.
# Solo se reutilizan las funciones de cálculo y el autocargado de datos.
_HEADLESS = os.environ.get("FINCA_GALLINAL_HEADLESS") == "1"


st.set_page_config(
    page_title="Finca Gallinal · Plataforma agroclimática",
    page_icon="🌿",
    layout="wide",
)


# ── CSS: colapsar el wrapper del iframe a cero real ──────────────────────────
# _st_components.html(height=0) crea un iframe con height=0, pero el div
# wrapper de Streamlit añade márgen/padding que genera un segundo scrollbar.
# Este st.markdown elimina ese espacio extra visual.
st.markdown(
    """
    <style>
    div[data-testid="stCustomComponentV1"] {
        height: 0px !important;
        min-height: 0px !important;
        max-height: 0px !important;
        overflow: hidden !important;
        margin-top: 0px !important;
        margin-bottom: 0px !important;
        padding-top: 0px !important;
        padding-bottom: 0px !important;
        border: none !important;
        line-height: 0 !important;
    }

    /* ── Ocultar botón "Manage app" / viewer-badge de Streamlit Cloud ──
       Se aplica solo en móvil (<768px). Se prueban todos los selectores
       conocidos: data-testid oficial, clases parciales y el viewer badge. */
    @media (max-width: 767px) {
        [data-testid="stStatusWidget"],
        [data-testid="stAppToolbar"],
        [data-testid="stToolbar"],
        [data-testid="stDeployButton"],
        [data-testid="stDecoration"],
        [class*="viewerBadge"],
        [class*="StatusWidget"],
        [class*="deployButton"],
        [class*="stToolbar"] {
            display: none !important;
        }
    }

    /* ── Sidebar: esquinas derechas redondeadas ── */
    section[data-testid="stSidebar"] {
        border-radius: 0 20px 20px 0 !important;
    }
    section[data-testid="stSidebar"] > div:first-child {
        border-radius: 0 20px 20px 0 !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
    }

        /* ── Widgets: fondo blanco para contrastar con fondo gris ── */
        [data-testid="stDateInput"] > div > div,
        [data-testid="stSelectbox"] > div > div:first-child,
        [data-testid="stTextInput"] > div > div,
        [data-testid="stNumberInput"] > div > div,
        [data-testid="stFileUploader"] > div {
            background-color: #ffffff !important;
            border-radius: 6px !important;
        }
        [data-testid="stRadio"] > div {
            background-color: rgba(255,255,255,0.7) !important;
            border-radius: 8px !important;
            padding: 4px 8px !important;
        }
        /* ── Widgets desactivados: fondo gris + etiqueta atenuada ── */
        [data-testid="stDateInput"]:has([disabled]) > div > div,
        [data-testid="stSelectbox"]:has([disabled]) > div > div:first-child,
        [data-testid="stSelectbox"]:has([aria-disabled="true"]) > div > div:first-child {
            background-color: #dde3e1 !important;
            border-color: #b0bab8 !important;
            color: #888 !important;
        }
        [data-testid="stDateInput"]:has([disabled]) label,
        [data-testid="stSelectbox"]:has([disabled]) label,
        [data-testid="stSelectbox"]:has([aria-disabled="true"]) label {
            color: #999 !important;
            font-style: italic !important;
        }
        /* ── Móvil: dejar que el scroll vertical de la página pase por encima de
           las gráficas en vez de que la gráfica capture el gesto (pan/zoom). En
           ratón no afecta (touch-action solo aplica a entrada táctil). ── */
        [data-testid="stPlotlyChart"],
        [data-testid="stPlotlyChart"] *,
        .stPlotlyChart, .stPlotlyChart *,
        .js-plotly-plot, .js-plotly-plot * {
            touch-action: pan-y !important;
        }
        /* ── Móvil: el glitch del fondo de los encabezados en webkit ocurre con
           position:sticky dentro de un contenedor con scroll táctil. Se ataca por
           CLASE (no por el texto del style inline, que Streamlit reformatea y rompía
           el selector). En móvil:
             • encabezados normales → position:static (celda normal → SIEMPRE pinta
               su fondo, sin bug de sticky).
             • esquina → sticky solo horizontal (left) para acompañar a la 1ª columna.
           La tabla usa además border-collapse:separate, que es la cura documentada
           del bug de repintado de celdas sticky en webkit. En PC (≥768px) los
           encabezados siguen pegados arriba con normalidad. ── */
        @media (max-width: 767px) {
            table.fg-fixedcol thead th.fg-th {
                position: static !important;
            }
            table.fg-fixedcol thead th.fg-th-corner {
                position: sticky !important;
                top: auto !important;
                left: 0 !important;
                z-index: 4 !important;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Fondo gris claro + marca de agua con el logo ────────────────────────────
try:
    import base64 as _b64bg, os as _osbg
    if _osbg.path.exists("finca_gallinal_logo.jpeg"):
        with open("finca_gallinal_logo.jpeg", "rb") as _lf:
            _bg_b64 = _b64bg.b64encode(_lf.read()).decode()
        st.markdown(
            f"""
            <style>
            /* Fondo gris suave en toda la app */
            [data-testid="stAppViewContainer"] {{
                background-color: #f2f4f0 !important;
            }}
            [data-testid="stMain"] {{
                background-color: transparent !important;
            }}
            /* Margen izquierdo SOLO en pantallas anchas (PC): evita que el menú
               lateral se despliegue solo al pasar el ratón cerca del borde y que
               los controles queden pegados al sidebar. En móvil NO se aplica
               (el menú se abre con el botón ☰, no al pasar el dedo), así se
               aprovecha el ancho completo de la pantalla. */
            @media (min-width: 768px) {{
                [data-testid="stMain"] .block-container {{
                    padding-left: 5.5rem !important;
                }}
            }}
            /* Logo difuminado como marca de agua fija */
            [data-testid="stAppViewContainer"]::before {{
                content: "";
                position: fixed;
                top: 50%;
                left: 55%;
                transform: translate(-50%, -50%);
                width: 340px;
                height: 340px;
                background-image: url("data:image/jpeg;base64,{_bg_b64}");
                background-size: contain;
                background-repeat: no-repeat;
                background-position: center;
                opacity: 0.055;
                filter: blur(2px) grayscale(15%);
                pointer-events: none;
                z-index: 0;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )
except Exception:
    pass

# ── Botón flotante "volver arriba" ──────────────────────────────────────────
# Estrategia: el script dentro del iframe inyecta el botón DIRECTAMENTE
# en document.body del padre (window.parent.document.body.appendChild).
# Así position:fixed es relativo al viewport real, no al iframe,
# y el onclick corre en el contexto de la ventana padre.
_st_components.html(
    """
    <script>
    (function () {
      try {
        var win = window.parent;
        var doc = win.document;

        /* ── En móvil, redirigir con ?embed=true para ocultar la barra
           de herramientas de Streamlit Cloud (botón Manage app, Fork, etc.)
           ?embed=true es un parámetro oficial y documentado de Streamlit Cloud.
           Se ejecuta una sola vez: si el parámetro ya está, no redirige. ── */
        if (win.innerWidth < 768) {
          try {
            var _url = new URL(win.location.href);
            if (!_url.searchParams.has('embed')) {
              _url.searchParams.set('embed', 'true');
              win.location.replace(_url.toString());
            }
          } catch(e) {}
        }

        /* Eliminar instancia previa (re-renders de Streamlit) */
        var old = doc.getElementById('fg-scroll-fab');
        if (old) old.remove();

        /* Crear el botón en el DOM padre */
        var fab = doc.createElement('div');
        fab.id = 'fg-scroll-fab';
        fab.textContent = '↑';
        fab.title = 'Volver arriba · ver pestañas';

        var isSmall = win.innerWidth <= 768;
        fab.style.cssText =
          'position:fixed;' +
          'bottom:' + (isSmall ? '72' : '28') + 'px;' +
          'right:18px;' +
          'width:46px;height:46px;border-radius:50%;' +
          'background:#1b6b35;color:#fff;' +
          'font-size:22px;font-weight:bold;' +
          'box-shadow:0 4px 14px rgba(0,0,0,.42);' +
          'border:2px solid rgba(255,255,255,.28);' +
          'cursor:pointer;' +
          'display:flex;align-items:center;justify-content:center;' +
          'z-index:9999;user-select:none;';

        /* Click: scroll al inicio en todos los contenedores posibles */
        fab.addEventListener('click', function () {
          win.scrollTo({ top: 0, behavior: 'smooth' });
          doc.documentElement.scrollTop = 0;
          doc.body.scrollTop = 0;
          ['section.main','[data-testid="stMain"]','.stMain'].forEach(function (s) {
            var el = doc.querySelector(s);
            if (el) el.scrollTo({ top: 0, behavior: 'smooth' });
          });
        });

        /* Reajustar posición al redimensionar */
        win.addEventListener('resize', function () {
          fab.style.bottom = win.innerWidth <= 768 ? '72px' : '28px';
        });

        /* Active feedback */
        fab.addEventListener('mousedown',  function () { fab.style.transform = 'scale(.92)'; });
        fab.addEventListener('touchstart', function () { fab.style.transform = 'scale(.92)'; });
        fab.addEventListener('mouseup',    function () { fab.style.transform = ''; });
        fab.addEventListener('touchend',   function () { fab.style.transform = ''; });

        doc.body.appendChild(fab);

        /* ── Barra de navegación inferior en móvil ── */
        var oldNav = doc.getElementById('fg-mobile-nav');
        if (oldNav) oldNav.remove();
        var oldNavStyle = doc.getElementById('fg-mobile-nav-style');
        if (oldNavStyle) oldNavStyle.remove();

        var mobileNavStyle = doc.createElement('style');
        mobileNavStyle.id = 'fg-mobile-nav-style';
        mobileNavStyle.textContent =
          '@media (min-width:768px){#fg-mobile-nav{display:none!important}}' +
          '@media (max-width:767px){' +
          '  section[data-testid="stMain"]{padding-bottom:68px!important}' +
          '  #fg-scroll-fab{bottom:78px!important}' +
          '}';
        doc.head.appendChild(mobileNavStyle);

        /* ── Ocultar botón "Manage app" de Streamlit Cloud en móvil ──
           Triple estrategia:
           1. CSS injection con selectores conocidos de Streamlit Cloud.
           2. TreeWalker: busca texto "manage" y sube al ancestro fixed.
           3. Posición: cualquier elemento fixed en esquina inferior-derecha. */

        /* Estrategia 1 — CSS (funciona aunque el JS tarde en ejecutarse) */
        var fgHideStyle = doc.getElementById('fg-hide-manage-style');
        if (!fgHideStyle) {
          fgHideStyle = doc.createElement('style');
          fgHideStyle.id = 'fg-hide-manage-style';
          doc.head.appendChild(fgHideStyle);
        }
        fgHideStyle.textContent =
          '@media (max-width:767px){' +
          '[data-testid="stStatusWidget"],' +
          '[data-testid="stAppToolbar"],' +
          '[data-testid="stToolbar"],' +
          '[data-testid="stDeployButton"],' +
          '[class*="StatusWidget"],' +
          '[class*="stToolbar"]' +
          '{display:none!important}' +
          '}';

        /* Estrategias 2 y 3 — loop periódico */
        (function fgHideManageBtn() {
          if (win.innerWidth >= 768) { setTimeout(fgHideManageBtn, 2000); return; }

          /* 2. Buscar texto "manage" en todos los documentos accesibles */
          var docsToSearch = [doc];
          try { if (win.top && win.top.document !== doc) docsToSearch.push(win.top.document); } catch(e){}
          docsToSearch.forEach(function(d) {
            try {
              /* 2a. TreeWalker: texto que contenga "manage" */
              var walker = d.createTreeWalker(d.body, NodeFilter.SHOW_TEXT, null, false);
              var tn;
              while ((tn = walker.nextNode())) {
                if (!tn.nodeValue) continue;
                if (tn.nodeValue.trim().toLowerCase().indexOf('manage') === -1) continue;
                var el = tn.parentElement;
                while (el && el !== d.body) {
                  try {
                    var pos = win.getComputedStyle(el).position;
                    if (pos === 'fixed' || pos === 'sticky') {
                      if (el.id !== 'fg-mobile-nav' && el.id !== 'fg-scroll-fab') {
                        el.style.setProperty('display','none','important');
                      }
                      break;
                    }
                  } catch(e2){}
                  el = el.parentElement;
                }
              }
              /* 2b. Selectores de Streamlit conocidos */
              ['[data-testid="stStatusWidget"]','[data-testid="stAppToolbar"]',
               '[data-testid="stToolbar"]','[data-testid="stDeployButton"]'].forEach(function(sel) {
                try {
                  d.querySelectorAll(sel).forEach(function(el) {
                    el.style.setProperty('display','none','important');
                  });
                } catch(e3){}
              });
            } catch(ex){}
          });

          /* 3. Posición: elemento fixed/sticky en esquina inferior-derecha */
          try {
            var nodes = doc.querySelectorAll('*');
            for (var k = 0; k < nodes.length; k++) {
              var n = nodes[k];
              if (n.id === 'fg-mobile-nav' || n.id === 'fg-scroll-fab' ||
                  n.id === 'fg-mobile-nav-style' || n.id === 'fg-hide-manage-style') continue;
              var pos2 = win.getComputedStyle(n).position;
              if (pos2 !== 'fixed' && pos2 !== 'sticky') continue;
              var nr = n.getBoundingClientRect();
              if (nr.width > 0 && nr.width < 220 && nr.height < 130 &&
                  nr.bottom >= win.innerHeight - 130 &&
                  nr.right  >= win.innerWidth  - 220) {
                n.style.setProperty('display','none','important');
              }
            }
          } catch(ex){}

          setTimeout(fgHideManageBtn, 1500);
        })();

        var mobileNav = doc.createElement('div');
        mobileNav.id = 'fg-mobile-nav';
        /* padding-right deja libre la esquina inferior-derecha donde
           Streamlit Cloud coloca su botón "Manage app" (cross-origin,
           inaccesible desde la app).
           border-radius en esquinas superiores para aspecto redondeado. */
        mobileNav.style.cssText =
          'position:fixed;bottom:0;left:0;right:0;height:60px;' +
          'background:#1a2e1e;' +
          'border-radius:20px 20px 0 0;' +
          'box-shadow:0 -4px 20px rgba(0,0,0,0.45);' +
          'display:flex;align-items:stretch;z-index:2147483646;' +
          'padding-right:90px;';

        var mnItems = [
          {ic:'🔎', lb:'Análisis',  tx:'🔎 Análisis'},
          {ic:'🌤️', lb:'Clima',     tx:'🌦️ Sencrop'},
          {ic:'🧾', lb:'Agroptima', tx:'🧾 Agroptima'},
          {ic:'🍎', lb:'Producción',tx:'🍎 Producción'}
        ];

        var mnItemGroup = ['analisis','clima','agroptima','produccion'];

        var mnBtns = [];
        mnItems.forEach(function(item, idx) {
          var btn = doc.createElement('button');
          btn.style.cssText =
            'flex:1;display:flex;flex-direction:column;align-items:center;' +
            'justify-content:center;gap:2px;border:none;background:transparent;' +
            'cursor:pointer;font-size:0.58rem;color:rgba(255,255,255,0.55);padding:4px 0;' +
            'border-radius:12px;' +
            '-webkit-tap-highlight-color:transparent;transition:all 0.15s;';
          btn.innerHTML =
            '<span style="font-size:1.35rem;line-height:1">' + item.ic + '</span>' +
            '<span>' + item.lb + '</span>';

          btn.addEventListener('click', function() {
            /* Navegar clicando el botón del sidebar (aunque esté oculto) */
            var sb = doc.querySelector('section[data-testid="stSidebar"]');
            if (!sb) return;
            var sbtns = sb.querySelectorAll('button');
            for (var i = 0; i < sbtns.length; i++) {
              if (sbtns[i].textContent.trim() === item.tx) {
                sbtns[i].click(); return;
              }
            }
          });
          mobileNav.appendChild(btn);
          mnBtns.push(btn);
        });

        /* ── Botón ☰ Menú: abre/cierra la barra lateral (controles + navegación)
           de forma fiable con un toque. Sustituye al gesto de swipe, que chocaba
           con el "atrás" de Chrome Android y sacaba al usuario de la app. ── */
        var menuBtn = doc.createElement('button');
        menuBtn.id = 'fg-mobile-menu-btn';
        menuBtn.style.cssText =
          'flex:1;display:flex;flex-direction:column;align-items:center;' +
          'justify-content:center;gap:2px;border:none;background:transparent;' +
          'cursor:pointer;font-size:0.58rem;color:rgba(255,255,255,0.55);padding:4px 0;' +
          'border-radius:12px;' +
          '-webkit-tap-highlight-color:transparent;transition:all 0.15s;';
        menuBtn.innerHTML =
          '<span style="font-size:1.35rem;line-height:1">☰</span>' +
          '<span>Menú</span>';
        menuBtn.addEventListener('click', function () {
          /* Detectar si la barra lateral está abierta y alternar */
          var sb = doc.querySelector('section[data-testid="stSidebar"]');
          var isOpen = false;
          if (sb) {
            var aria = sb.getAttribute('aria-expanded');
            if (aria !== null) { isOpen = (aria === 'true'); }
            else { isOpen = sb.getBoundingClientRect().width > 50; }
          }
          fgToggleSidebar(!isOpen);
        });
        /* Se coloca el botón ☰ a la IZQUIERDA del todo, lejos de la esquina
           inferior-derecha donde Streamlit Cloud pone su insignia (que se
           solapaba con el botón si iba al final). */
        mobileNav.insertBefore(menuBtn, mobileNav.firstChild);

        doc.body.appendChild(mobileNav);

        /* Actualizar estado activo de la barra móvil */
        if (!doc._fgMobileNavTimer) {
          doc._fgMobileNavTimer = setInterval(function() {
            var activeDiv = doc.querySelector('.nav-active-item');
            var activeText = activeDiv ? activeDiv.textContent.trim() : '';
            /* Determinar grupo activo a partir del texto de la página */
            var textToKey = {
              '🔎 Análisis':'analisis',
              '📊 Dashboard':'clima','🌦️ Sencrop':'clima',
              '📈 Comparador':'clima','❄️ Frío':'clima',
              '🧾 Agroptima':'agroptima',
              '🍎 Producción':'produccion',
              '🍏 Análisis Gallinal':'produccion'
            };
            var activeGroup = textToKey[activeText] || '';
            mnBtns.forEach(function(btn, idx) {
              var isActive = mnItemGroup[idx] && mnItemGroup[idx] === activeGroup;
              btn.style.color      = isActive ? '#fff' : 'rgba(255,255,255,0.55)';
              btn.style.fontWeight = isActive ? '700' : '400';
              btn.style.background = isActive ? 'rgba(255,255,255,0.18)' : 'transparent';
            });
          }, 400);
        }

        /* ── Auto-expand/collapse sidebar al acercar/alejar el ratón ── */

        /* Estado persistente en doc (sobrevive a re-renders de Streamlit).
           Los timers se guardan en doc para no perderlos entre renders. */
        if (typeof doc._fgHoverOpened === 'undefined') doc._fgHoverOpened = false;
        if (typeof doc._fgHoverTimer  === 'undefined') doc._fgHoverTimer  = null;
        if (typeof doc._fgCloseTimer  === 'undefined') doc._fgCloseTimer  = null;

        /* Toggle sidebar por posición en pantalla */
        function fgToggleSidebar(open) {
          var halfW = win.innerWidth / 2;
          var semantic = open
            ? ['[data-testid="stSidebarCollapsedControl"] button',
               '[data-testid="collapsedControl"] button',
               'button[aria-label="Open sidebar"]',
               'button[aria-label="Abrir barra lateral"]',
               '[class*="collapsedControl"] button']
            : ['button[aria-label="Close sidebar"]',
               'button[aria-label="Cerrar barra lateral"]',
               '[data-testid="stSidebar"] [data-testid="stBaseButton-header"]',
               '[data-testid="stSidebarCloseButton"] button'];
          for (var si = 0; si < semantic.length; si++) {
            var b = doc.querySelector(semantic[si]);
            if (b) { b.click(); return true; }
          }
          var allBtns = doc.querySelectorAll('button');
          for (var bi = 0; bi < allBtns.length; bi++) {
            var r = allBtns[bi].getBoundingClientRect();
            var match = open
              ? (r.left < 100 && r.top < 120 && r.right < halfW)
              : (r.left >= 50 && r.right < 310 && r.top < 100 && r.right < halfW);
            if (match) { allBtns[bi].click(); return true; }
          }
          return false;
        }

        function fgExpandSidebar()   { if (fgToggleSidebar(true))  doc._fgHoverOpened = true;  }
        doc._fgExpandSidebar = fgExpandSidebar; /* expuesto para la barra móvil */
        function fgCollapseSidebar() { if (fgToggleSidebar(false)) doc._fgHoverOpened = false; }

        /* ── mousemove: abrir al acercarse, cerrar al alejarse ──
           Se reemplaza el handler en cada render para usar siempre el
           código más reciente (evita handlers obsoletos en memoria). */
        if (doc._fgMouseMoveHandler) win.removeEventListener('mousemove', doc._fgMouseMoveHandler);
        doc._fgMouseMoveHandler = function (e) {
          var x = e.clientX;
          if (x < 60) {
            if (doc._fgCloseTimer) { clearTimeout(doc._fgCloseTimer); doc._fgCloseTimer = null; }
            if (!doc._fgHoverTimer) doc._fgHoverTimer = setTimeout(function () {
              fgExpandSidebar(); doc._fgHoverTimer = null;
            }, 250);
          } else {
            if (doc._fgHoverTimer) { clearTimeout(doc._fgHoverTimer); doc._fgHoverTimer = null; }
            if (doc._fgHoverOpened && x > 290) {
              if (!doc._fgCloseTimer) doc._fgCloseTimer = setTimeout(function () {
                fgCollapseSidebar(); doc._fgCloseTimer = null;
              }, 900);
            } else if (x <= 290 && doc._fgCloseTimer) {
              clearTimeout(doc._fgCloseTimer); doc._fgCloseTimer = null;
            }
          }
        };
        win.addEventListener('mousemove', doc._fgMouseMoveHandler);

        /* ── click: cerrar al navegar ── */
        if (doc._fgClickHandler) doc.removeEventListener('click', doc._fgClickHandler);
        doc._fgClickHandler = function (e) {
          var sidebar = doc.querySelector('section[data-testid="stSidebar"]');
          if (!sidebar) return;
          var t = e.target;
          while (t && t !== doc.body) {
            if (t.tagName === 'BUTTON' && sidebar.contains(t)) {
              var rect = t.getBoundingClientRect();
              if (rect.top > 100) setTimeout(function () { fgCollapseSidebar(); }, 700);
              break;
            }
            t = t.parentElement;
          }
        };
        doc.addEventListener('click', doc._fgClickHandler);

        /* ── Móvil: el swipe desde el borde izquierdo se ELIMINA. En Chrome Android
           el deslizar desde el borde es el gesto "atrás" del navegador, que sacaba
           al usuario de la app. La barra lateral se abre/cierra con el botón ☰ de
           la barra inferior. Aquí solo se limpian handlers de renders anteriores. ── */
        if (doc._fgTouchStartHandler) { win.removeEventListener('touchstart', doc._fgTouchStartHandler); doc._fgTouchStartHandler = null; }
        if (doc._fgTouchMoveHandler)  { win.removeEventListener('touchmove',  doc._fgTouchMoveHandler);  doc._fgTouchMoveHandler  = null; }
        if (doc._fgTouchEndHandler)   { win.removeEventListener('touchend',   doc._fgTouchEndHandler);   doc._fgTouchEndHandler   = null; }
        doc._fgTouchX0 = null;

      } catch (e) {
        console.warn('fg-fab error:', e);
      }
    })();
    </script>
    """,
    height=0,
)

COLUMN_MAP = {
    "Irradiancia": "irradiancia",
    "Lluvia": "lluvia_mm",
    "Humedad relativa": "hr_media",
    "Humedad relativa max": "hr_max",
    "Humedad relativa mín": "hr_min",
    "Temperatura": "temp_media",
    "Temperatura max": "temp_max",
    "Temperatura mín": "temp_min",
    "Humedad en hoja": "humectacion_hoja",
    "Humedad en hoja importante": "humectacion_importante",
    "Humedad en hoja moderada": "humectacion_moderada",
    "Dirección del viento": "viento_direccion",
    "Ráfaga de viento": "viento_rafaga",
    "Velocidad del viento": "viento_velocidad",
}

CANONICAL_COLUMNS = [
    "fecha_hora",
    "irradiancia",
    "lluvia_mm",
    "hr_media",
    "hr_max",
    "hr_min",
    "temp_media",
    "temp_max",
    "temp_min",
    "humectacion_hoja",
    "humectacion_importante",
    "humectacion_moderada",
    "viento_direccion",
    "viento_rafaga",
    "viento_velocidad",
]

SENSOR_BLOCKS = {
    "Temperatura / humedad / lluvia": ["temp_media", "temp_max", "temp_min", "hr_media", "lluvia_mm"],
    "Humectación de hoja": ["humectacion_hoja", "humectacion_importante", "humectacion_moderada"],
    "Viento": ["viento_direccion", "viento_rafaga", "viento_velocidad"],
    "Radiación solar": ["irradiancia"],
}

SOIL_PROFILES = {
    "Arenoso": {
        "retencion": "Muy baja",
        "coef_demanda": 1.30,
        "coef_lluvia_efectiva": 0.55,
        "comentario": "Drena rápido y retiene poca agua. Puede necesitar riegos más frecuentes y menos largos.",
    },
    "Franco-arenoso": {
        "retencion": "Baja-media",
        "coef_demanda": 1.15,
        "coef_lluvia_efectiva": 0.65,
        "comentario": "Buen drenaje, pero reserva limitada. Vigilar semanas con viento y radiación alta.",
    },
    "Franco": {
        "retencion": "Media",
        "coef_demanda": 1.00,
        "coef_lluvia_efectiva": 0.75,
        "comentario": "Equilibrio razonable entre drenaje y retención. Usar como referencia base.",
    },
    "Franco-arcilloso": {
        "retencion": "Media-alta",
        "coef_demanda": 0.88,
        "coef_lluvia_efectiva": 0.82,
        "comentario": "Retiene más agua. Conviene evitar excesos y comprobar aireación/encharcamiento.",
    },
    "Arcilloso": {
        "retencion": "Alta",
        "coef_demanda": 0.78,
        "coef_lluvia_efectiva": 0.88,
        "comentario": "Alta retención y drenaje lento. El riesgo principal puede ser exceso de humedad si llueve.",
    },
}



# La estación entrega la radiación solar horaria en MJ/m².
# Conversión: 1 kWh/m² = 3.6 MJ/m².
MJ_TO_KWH = 1 / 3.6

# Umbrales operativos de polinización adaptados a manzano y a datos horarios.
# Se aplican como modelo orientativo; la floración real y la presencia de polinizadores mandan.
POLLINATION = {
    "temp_min_activity": 13.0,
    "temp_opt_low": 16.0,
    "temp_opt_high": 24.0,
    "temp_max_activity": 28.0,
    "wind_good": 15.0,       # km/h aproximados si el sensor está en km/h
    "wind_ok": 25.0,
    "gust_good": 30.0,
    "gust_ok": 40.0,
    "rad_daylight": 0.10,    # MJ/m² por hora, luz mínima
    "rad_good": 0.40,        # MJ/m² por hora, luz útil
    "hr_good_low": 40.0,
    "hr_good_high": 85.0,
    "hr_ok_low": 30.0,
    "hr_ok_high": 95.0,
}


# Módulo de eventos de humectación foliar.
# El sensor mide minutos de hoja mojada por hora.
LEAF_WETNESS = {
    "min_minutes_to_start_event": 1,
    "dry_hours_to_close_event": 6,
}

def parse_datetime_column(df):
    """
    Lectura robusta de fechas.

    Motivo:
    algunos CSV históricos traen dateLocale en formato americano M/D/YYYY,
    aunque visualmente pueda confundirse con D/M/YYYY. Si se fuerza dayfirst=True,
    una fecha como 6/11/2019 puede convertirse en 6 de noviembre en vez de 11 de junio,
    y la app acaba contando solo una parte de las horas.

    Regla:
    1) Si existe dateUTC, se usa como fuente principal porque no es ambiguo.
       Se convierte a hora local Europe/Madrid para que los informes salgan en hora de finca.
    2) Si no existe dateUTC, se intenta fecha_hora.
    3) Si solo existe dateLocale, se prueban dayfirst=False y dayfirst=True y se elige
       la interpretación que conserva más filas y genera una serie temporal más continua.
    """
    if "dateUTC" in df.columns:
        parsed = pd.to_datetime(df["dateUTC"], errors="coerce", utc=True)
        if parsed.notna().sum() > 0:
            try:
                df["fecha_hora"] = parsed.dt.tz_convert("Europe/Madrid").dt.tz_localize(None)
            except Exception:
                df["fecha_hora"] = parsed.dt.tz_convert(None)
        else:
            df["fecha_hora"] = pd.NaT

    elif "fecha_hora" in df.columns:
        df["fecha_hora"] = pd.to_datetime(df["fecha_hora"], errors="coerce")

    elif "dateLocale" in df.columns:
        raw = df["dateLocale"]

        p_month_first = pd.to_datetime(raw, errors="coerce", dayfirst=False)
        p_day_first = pd.to_datetime(raw, errors="coerce", dayfirst=True)

        def score(parsed):
            valid = parsed.dropna()
            if valid.empty:
                return -1
            ordered = valid.sort_values()
            span_hours = max((ordered.max() - ordered.min()).total_seconds() / 3600, 1)
            unique_hours = ordered.dt.floor("h").nunique()
            continuity = unique_hours / span_hours
            return valid.size + continuity

        df["fecha_hora"] = p_month_first if score(p_month_first) >= score(p_day_first) else p_day_first

    else:
        raise ValueError("El archivo no contiene fecha_hora, dateLocale ni dateUTC.")

    df = df.dropna(subset=["fecha_hora"]).copy()
    try:
        df["fecha_hora"] = df["fecha_hora"].dt.tz_localize(None)
    except Exception:
        pass

    return df


def normalize_dataframe(df):
    df = parse_datetime_column(df)
    df = df.rename(columns=COLUMN_MAP)

    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    out = df[CANONICAL_COLUMNS].copy()

    for c in out.columns:
        if c != "fecha_hora":
            out[c] = pd.to_numeric(out[c], errors="coerce")

    return out.sort_values("fecha_hora").drop_duplicates(subset=["fecha_hora"], keep="last")


def read_csv_bytes(file_name, raw):
    df_original = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
    normalized = normalize_dataframe(df_original)
    return normalized


def diagnose_csv_file(file_name, raw):
    """
    Devuelve un diagnóstico de cómo se ha leído cada CSV.
    Sirve para detectar al momento si un archivo histórico se ha interpretado con fechas incorrectas.
    """
    try:
        df_original = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
        normalized = normalize_dataframe(df_original)

        if normalized.empty:
            return {
                "Archivo": file_name,
                "Registros leídos": 0,
                "Desde": "Sin datos",
                "Hasta": "Sin datos",
                "Horas únicas": 0,
                "Temperatura con datos": 0,
                "Lluvia con datos": 0,
                "Hoja con datos": 0,
                "Viento con datos": 0,
                "Radiación con datos": 0,
                "Estado": "Sin datos válidos",
            }

        return {
            "Archivo": file_name,
            "Registros leídos": len(normalized),
            "Desde": normalized["fecha_hora"].min(),
            "Hasta": normalized["fecha_hora"].max(),
            "Horas únicas": normalized["fecha_hora"].dt.floor("h").nunique(),
            "Temperatura con datos": int(normalized["temp_media"].notna().sum()),
            "Lluvia con datos": int(normalized["lluvia_mm"].notna().sum()),
            "Hoja con datos": int(normalized["humectacion_hoja"].notna().sum()),
            "Viento con datos": int(normalized["viento_velocidad"].notna().sum()),
            "Radiación con datos": int(normalized["irradiancia"].notna().sum()),
            "Estado": "Correcto",
        }
    except Exception as e:
        return {
            "Archivo": file_name,
            "Registros leídos": 0,
            "Desde": "Error",
            "Hasta": "Error",
            "Horas únicas": 0,
            "Temperatura con datos": 0,
            "Lluvia con datos": 0,
            "Hoja con datos": 0,
            "Viento con datos": 0,
            "Radiación con datos": 0,
            "Estado": f"Error: {e}",
        }


def merge_new_files(files):
    frames = []
    errors = []

    for f in files:
        try:
            frames.append(read_csv_bytes(f.name, f.getvalue()))
        except Exception as e:
            errors.append(f"{f.name}: {e}")

    if not frames:
        return pd.DataFrame(columns=CANONICAL_COLUMNS), errors

    return pd.concat(frames, ignore_index=True), errors


def compact_history(df):
    if df.empty:
        return df

    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    df = df[CANONICAL_COLUMNS].copy()
    df = df.sort_values("fecha_hora")

    # Combina filas de distintos sensores que comparten la misma hora.
    grouped = df.groupby("fecha_hora", as_index=False).agg(
        {col: "last" for col in CANONICAL_COLUMNS if col != "fecha_hora"}
    )

    return grouped.sort_values("fecha_hora").reset_index(drop=True)


def load_master_history(file):
    if file is None:
        return pd.DataFrame(columns=CANONICAL_COLUMNS), []

    try:
        return read_csv_bytes(file.name, file.getvalue()), []
    except Exception as e:
        return pd.DataFrame(columns=CANONICAL_COLUMNS), [f"{file.name}: {e}"]


def expected_hours(start, end):
    try:
        start_ts = pd.Timestamp(start).tz_localize(None).floor("h")
        end_ts = pd.Timestamp(end).tz_localize(None).floor("h")
        if end_ts < start_ts:
            return 0
        return int(pd.date_range(start_ts, end_ts, freq="h").size)
    except Exception:
        return 0


def availability_table(df, start, end):
    total = expected_hours(start, end)
    rows = []

    for block, cols in SENSOR_BLOCKS.items():
        existing_cols = [c for c in cols if c in df.columns]
        if total == 0:
            rows.append({
                "Sensor": block,
                "Registros con datos": 0,
                "Horas esperadas": 0,
                "Cobertura %": 0,
                "Estado": "Periodo no válido o sin horas esperadas",
                "Mensaje": f"No se puede calcular disponibilidad para {block.lower()} en este periodo.",
            })
            continue

        if not existing_cols:
            rows.append({
                "Sensor": block,
                "Registros con datos": 0,
                "Horas esperadas": total,
                "Cobertura %": 0,
                "Estado": "Sin datos",
                "Mensaje": f"Para este periodo no disponemos de datos de {block.lower()}.",
            })
            continue

        has_data = df[existing_cols].notna().any(axis=1)
        count = int(has_data.sum())
        coverage = round(count / total * 100, 1) if total else 0

        if count == 0:
            state = "Sin datos"
            msg = f"Para este periodo no disponemos de datos de {block.lower()}."
        elif coverage >= 95:
            state = "Correcto"
            msg = f"Disponemos de datos suficientes de {block.lower()} para este periodo."
        else:
            state = "Incompleto"
            msg = f"El sensor de {block.lower()} tiene datos incompletos en este periodo. El análisis se ha calculado con los registros disponibles."

        rows.append({
            "Sensor": block,
            "Registros con datos": count,
            "Horas esperadas": total,
            "Cobertura %": coverage,
            "Estado": state,
            "Mensaje": msg,
        })

    return pd.DataFrame(rows)


def has_sensor(df, block_name):
    cols = SENSOR_BLOCKS[block_name]
    existing = [c for c in cols if c in df.columns]
    return bool(existing) and df[existing].notna().any(axis=1).sum() > 0


def direction_to_sector(degrees):
    if pd.isna(degrees):
        return "Sin dato"
    sectors = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
    idx = int((degrees + 22.5) // 45) % 8
    return sectors[idx]


def circular_mean_degrees(series):
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return np.nan
    radians = np.deg2rad(values)
    sin_mean = np.sin(radians).mean()
    cos_mean = np.cos(radians).mean()
    if sin_mean == 0 and cos_mean == 0:
        return np.nan
    angle = np.rad2deg(np.arctan2(sin_mean, cos_mean))
    return angle % 360


def wet_periods_hours(series, threshold=30):
    wet = series.fillna(0) >= threshold
    periods = []
    active = False
    length = 0

    for _, is_wet in wet.items():
        if is_wet:
            active = True
            length += 1
        else:
            if active:
                periods.append(length)
            active = False
            length = 0

    if active:
        periods.append(length)
    return periods



def scab_mills_threshold_hours(temp_c):
    """Umbral orientativo de horas húmedas equivalentes para moteado tipo Mills/LaPlante."""
    if pd.isna(temp_c):
        return np.nan
    t = float(temp_c)
    if t < 6:
        return 48.0
    if t < 8:
        return 30.0
    if t < 10:
        return 20.0
    if t < 11:
        return 18.0
    if t < 13:
        return 14.0
    if t < 14:
        return 12.0
    if t < 16:
        return 11.0
    if t <= 24:
        return 9.0
    if t <= 26:
        return 12.0
    return 24.0


def monilia_threshold_hours(temp_c):
    """Umbral orientativo de horas húmedas equivalentes para vigilancia de Monilinia."""
    if pd.isna(temp_c):
        return np.nan
    t = float(temp_c)
    if t < 10:
        return 24.0
    if t < 15:
        return 18.0
    if t < 20:
        return 10.0
    if t <= 25:
        return 5.0
    return 10.0


def risk_from_ratio(ratio):
    if pd.isna(ratio):
        return "Sin dato"
    if ratio >= 1.25:
        return "Alto"
    if ratio >= 1.0:
        return "Medio-alto"
    if ratio >= 0.75:
        return "Medio"
    return "Bajo"




def ratio_interpretation_text(ratio):
    """Explica un ratio técnico de infección en lenguaje sencillo."""
    if pd.isna(ratio):
        return "No calculable por falta de temperatura, humectación o umbral."
    ratio = float(ratio)
    pct = ratio * 100
    if ratio < 0.75:
        return f"Alcanzó aprox. el {pct:.0f} % del umbral estimado; no llega al umbral de infección."
    if ratio < 1.0:
        return f"Alcanzó aprox. el {pct:.0f} % del umbral estimado; evento cercano al umbral, conviene vigilar."
    if ratio < 1.25:
        return f"Superó ligeramente el umbral estimado ({pct:.0f} % del umbral); infección compatible si había tejido sensible."
    if ratio < 1.75:
        return f"Superó claramente el umbral estimado ({pct:.0f} % del umbral); riesgo alto si no había cobertura preventiva suficiente."
    return f"Superó ampliamente el umbral estimado ({pct:.0f} % del umbral); riesgo muy alto en fase sensible."


def action_from_event_ratio(ratio, phases=None, rain_mm=0.0):
    """
    Acción orientativa basada en ratio de infección, fase fenológica y lluvia.
    No recomienda productos; solo orienta decisión técnica.
    """
    phases = phases or []
    phase_lower = " ".join(phases).lower()
    sensitive = any(w in phase_lower for w in ["brot", "flor", "cuaj", "fruto", "madur"])

    if pd.isna(ratio):
        return "Datos insuficientes: revisar evento y completar sensores si es posible."

    ratio = float(ratio)

    if ratio < 0.75:
        if rain_mm >= 5:
            return "Observar y vigilar la previsión: aunque no se alcanza el umbral, hubo lluvia."
        return "Observar: no se alcanza el umbral estimado de infección."

    if ratio < 1.0:
        return "Vigilar previsión meteorológica y revisar finca: el evento queda cerca del umbral."

    if ratio < 1.25:
        if sensitive:
            return "Revisar cobertura y valorar intervención técnica en las próximas 24–36 h si no había protección suficiente."
        return "Revisar finca y cobertura; valorar actuación si hay nuevas lluvias o tejido sensible."

    if ratio < 1.75:
        if sensitive:
            return "Riesgo alto: valorar intervención técnica en las próximas 24 h si no había cobertura preventiva suficiente."
        return "Riesgo alto: revisar finca, cobertura y previsión antes de decidir intervención."

    if sensitive:
        return "Riesgo muy alto: priorizar revisión e intervención técnica cuanto antes si no había cobertura previa."
    return "Riesgo muy alto: revisar finca y cobertura; decidir actuación según estado fenológico y previsión."


def explain_sanitary_concepts_box():
    with st.expander("Cómo interpretar eventos, ratio y acciones sugeridas", expanded=False):
        st.markdown(
            """
            **Evento de hoja mojada**  
            Es un periodo continuado en el que la hoja permanece mojada. La app agrupa las horas húmedas seguidas y calcula su duración, temperatura media y lluvia asociada.

            **Ratio de moteado o monilia**  
            No es un porcentaje directo. Es la relación entre las horas húmedas equivalentes del evento y las horas mínimas estimadas para que pueda producirse infección.

            **Cómo leer el ratio**  
            - **0,67**: el evento alcanzó aproximadamente el 67 % del umbral estimado.  
            - **1,00**: el evento alcanzó justo el umbral estimado.  
            - **1,50**: el evento superó el umbral en un 50 %.

            **Acción sugerida**  
            La app usa el ratio, la fase fenológica, lluvia y humectación para orientar la decisión: observar, vigilar previsión, revisar finca o valorar intervención técnica. No recomienda productos concretos.
            """
        )
        st.caption(
            "Base técnica: modelos tipo Mills/Mills-LaPlante para moteado, donde temperatura y duración de hoja mojada determinan el riesgo; "
            "y recomendaciones de manejo integrado que priorizan protección preventiva y revisión post-infección según cobertura, lluvia y fase sensible."
        )


def add_event_interpretation_columns(events_df, phases=None):
    if events_df is None or events_df.empty:
        return events_df

    out = events_df.copy()
    phases = phases or []

    if "Ratio moteado" in out.columns:
        out["Interpretación ratio moteado"] = out["Ratio moteado"].apply(ratio_interpretation_text)
        out["Acción sugerida moteado"] = out.apply(
            lambda r: action_from_event_ratio(
                r.get("Ratio moteado", np.nan),
                phases=phases,
                rain_mm=r.get("Lluvia evento mm", 0.0),
            ),
            axis=1,
        )

    if "Ratio monilia" in out.columns:
        out["Interpretación ratio monilia"] = out["Ratio monilia"].apply(ratio_interpretation_text)
        out["Acción sugerida monilia"] = out.apply(
            lambda r: action_from_event_ratio(
                r.get("Ratio monilia", np.nan),
                phases=phases,
                rain_mm=r.get("Lluvia evento mm", 0.0),
            ),
            axis=1,
        )

    return out


def detect_leaf_wetness_events(df, min_minutes=1, dry_hours_to_close=6):
    """Detecta eventos de hoja mojada acumulando minutos por hora."""
    if df.empty or "humectacion_hoja" not in df.columns:
        return pd.DataFrame()

    data = df.copy().sort_values("fecha_hora")
    data["wet_minutes"] = pd.to_numeric(data["humectacion_hoja"], errors="coerce").fillna(0).clip(lower=0, upper=60)

    events = []
    active_rows = []
    dry_count = 0

    def close_event(rows):
        if not rows:
            return None
        ev = pd.DataFrame(rows)
        wet_ev = ev[pd.to_numeric(ev["wet_minutes"], errors="coerce").fillna(0) >= min_minutes].copy()
        if wet_ev.empty:
            return None

        start = ev["fecha_hora"].min()
        end = ev["fecha_hora"].max()
        wet_minutes_total = float(wet_ev["wet_minutes"].sum())
        wet_hours_eq = wet_minutes_total / 60.0
        clock_hours = int(((end - start).total_seconds() / 3600) + 1) if pd.notna(start) and pd.notna(end) else len(ev)
        temp_mean = pd.to_numeric(wet_ev["temp_media"], errors="coerce").mean()
        hr_mean = pd.to_numeric(wet_ev["hr_media"], errors="coerce").mean()
        rain_total = pd.to_numeric(wet_ev["lluvia_mm"], errors="coerce").fillna(0).sum()
        max_wet_min = pd.to_numeric(wet_ev["wet_minutes"], errors="coerce").max()

        scab_th = scab_mills_threshold_hours(temp_mean)
        scab_ratio = wet_hours_eq / scab_th if scab_th and not pd.isna(scab_th) else np.nan
        monilia_th = monilia_threshold_hours(temp_mean)
        monilia_ratio = wet_hours_eq / monilia_th if monilia_th and not pd.isna(monilia_th) else np.nan

        return {
            "Inicio": start,
            "Fin": end,
            "Duración reloj h": clock_hours,
            "Minutos hoja mojada": round(wet_minutes_total, 0),
            "Horas húmedas equivalentes": round(wet_hours_eq, 2),
            "Temperatura media evento ºC": round(temp_mean, 2) if not pd.isna(temp_mean) else np.nan,
            "HR media evento %": round(hr_mean, 1) if not pd.isna(hr_mean) else np.nan,
            "Lluvia evento mm": round(rain_total, 1),
            "Máx minutos mojados en una hora": round(max_wet_min, 0) if not pd.isna(max_wet_min) else np.nan,
            "Umbral moteado h": round(scab_th, 1) if not pd.isna(scab_th) else np.nan,
            "Ratio moteado": round(scab_ratio, 2) if not pd.isna(scab_ratio) else np.nan,
            "Riesgo moteado evento": risk_from_ratio(scab_ratio),
            "Umbral monilia h": round(monilia_th, 1) if not pd.isna(monilia_th) else np.nan,
            "Ratio monilia": round(monilia_ratio, 2) if not pd.isna(monilia_ratio) else np.nan,
            "Riesgo monilia evento": risk_from_ratio(monilia_ratio),
        }

    for _, row in data.iterrows():
        is_wet = row["wet_minutes"] >= min_minutes
        if is_wet:
            active_rows.append(row.to_dict())
            dry_count = 0
        else:
            if active_rows:
                dry_count += 1
                if dry_count < dry_hours_to_close:
                    active_rows.append(row.to_dict())
                else:
                    event = close_event(active_rows)
                    if event is not None:
                        events.append(event)
                    active_rows = []
                    dry_count = 0

    if active_rows:
        event = close_event(active_rows)
        if event is not None:
            events.append(event)

    return pd.DataFrame(events)


def leaf_event_metrics(df):
    events = detect_leaf_wetness_events(df)
    if events.empty:
        return {
            "Eventos hoja mojada": 0,
            "Horas húmedas equivalentes": 0.0,
            "Máx horas húmedas evento": 0.0,
            "Eventos moteado medio/alto": 0,
            "Eventos moteado alto": 0,
            "Eventos monilia medio/alto": 0,
            "Eventos monilia alto": 0,
            "Evento más crítico moteado": "Sin eventos",
            "Evento más crítico monilia": "Sin eventos",
        }

    moteado_medium = events["Riesgo moteado evento"].isin(["Medio", "Medio-alto", "Alto"])
    moteado_high = events["Riesgo moteado evento"].eq("Alto")
    monilia_medium = events["Riesgo monilia evento"].isin(["Medio", "Medio-alto", "Alto"])
    monilia_high = events["Riesgo monilia evento"].eq("Alto")

    idx_scab = events["Ratio moteado"].fillna(0).idxmax()
    idx_mon = events["Ratio monilia"].fillna(0).idxmax()

    def event_label(row, disease):
        risk_col = "Riesgo moteado evento" if disease == "moteado" else "Riesgo monilia evento"
        ratio_col = "Ratio moteado" if disease == "moteado" else "Ratio monilia"
        return (
            f"{row['Inicio'].strftime('%d/%m/%Y %H:%M')} → {row['Fin'].strftime('%d/%m/%Y %H:%M')} "
            f"({row['Horas húmedas equivalentes']} h eq., Tª {row['Temperatura media evento ºC']} ºC, "
            f"riesgo {row[risk_col]}, ratio {row[ratio_col]})"
        )

    return {
        "Eventos hoja mojada": int(len(events)),
        "Horas húmedas equivalentes": round(float(events["Horas húmedas equivalentes"].sum()), 2),
        "Máx horas húmedas evento": round(float(events["Horas húmedas equivalentes"].max()), 2),
        "Eventos moteado medio/alto": int(moteado_medium.sum()),
        "Eventos moteado alto": int(moteado_high.sum()),
        "Eventos monilia medio/alto": int(monilia_medium.sum()),
        "Eventos monilia alto": int(monilia_high.sum()),
        "Evento más crítico moteado": event_label(events.loc[idx_scab], "moteado"),
        "Evento más crítico monilia": event_label(events.loc[idx_mon], "monilia"),
    }


def utah_weight(temp):
    if pd.isna(temp):
        return 0.0
    if temp <= 1.4:
        return 0.0
    if temp <= 2.4:
        return 0.5
    if temp <= 9.1:
        return 1.0
    if temp <= 12.4:
        return 0.5
    if temp <= 15.9:
        return 0.0
    if temp <= 18.0:
        return -0.5
    return -1.0


def dynamic_chill_portions(hour_temps):
    temps = pd.to_numeric(pd.Series(hour_temps), errors="coerce").interpolate(limit_direction="both")
    temps = temps.bfill().ffill()

    n = len(temps)
    if n == 0:
        return np.array([])

    E0 = 4153.5
    E1 = 12888.8
    A0 = 139500.0
    A1 = 2.567e18
    slope = 1.6
    Tf = 277.0

    TK = temps.to_numpy(dtype=float) + 273.0
    aa = A0 / A1
    ee = E1 - E0
    sr = np.exp(slope * Tf * (TK - Tf) / TK)
    xi = sr / (1 + sr)
    xs = aa * np.exp(ee / TK)
    eak1 = np.exp(-A1 * np.exp(-E1 / TK))

    x = np.zeros(n)
    for l in range(1, n):
        S = x[l - 1]
        if x[l - 1] >= 1:
            S = S * (1 - xi[l - 1])
        x[l] = xs[l - 1] - (xs[l - 1] - S) * eak1[l - 1]

    delta = np.zeros(n)
    idx = np.where(x >= 1)[0]
    for i in idx:
        prev = max(i - 1, 0)
        delta[i] = x[i] * xi[prev]

    return delta


def winter_season_label(ts):
    year = ts.year
    if ts.month >= 11:
        return f"{year}/{year + 1}"
    return f"{year - 1}/{year}"


# ── Periodo de acumulación de frío invernal: CRITERIO ÚNICO de toda la app ────
# Fuente: SERIDA / Delgado, Dapena, Fernández & Luedeling (2021), estudio de la
# sidra del NO de España (comarca de la sidra, variedades locales como 'Regona').
# Calculan el frío (Chill Portions modelo Dynamic, Utah, horas) sobre 1 nov → 31 mar.
# Este mismo periodo se usa en: item Frío, correlación clima-producción y la fase
# de frío del Análisis Gallinal. Modelo de referencia: Dynamic (Chill Portions).
CHILL_PERIOD_START_MD = (11, 1)   # (mes, día) — del año ANTERIOR al de análisis
CHILL_PERIOD_END_MD   = (3, 31)   # (mes, día) — del año de análisis


def winter_period_from_analysis_year(analysis_year):
    """
    El año de análisis es el año en el que termina el invierno.
    Periodo de frío = 1 nov (año-1) → 31 mar (año), criterio único de la app
    (CHILL_PERIOD_START_MD / CHILL_PERIOD_END_MD; fuente SERIDA/Delgado 2021).

    Ejemplos:
    - Año 2020 = 01/11/2019 a 31/03/2020
    - Año 2025 = 01/11/2024 a 31/03/2025
    """
    y = int(analysis_year)
    return (pd.Timestamp(y - 1, CHILL_PERIOD_START_MD[0], CHILL_PERIOD_START_MD[1]),
            pd.Timestamp(y, CHILL_PERIOD_END_MD[0], CHILL_PERIOD_END_MD[1], 23, 0))


def winter_label_from_analysis_year(analysis_year):
    if analysis_year is None:
        return "—"
    try:
        y = int(analysis_year)
    except (TypeError, ValueError):
        return "—"
    return f"{y - 1}/{y}"


def available_chill_analysis_years(df):
    """
    Devuelve años seleccionables para frío invernal.
    El año representa el cierre del periodo frío, no el inicio.
    Con datos 2019-2020, aparecerá 2020 para analizar 2019/2020.
    Solo incluye años con datos reales solapados en el periodo Nov-Mar.
    """
    if df.empty:
        return []

    min_year = int(df["fecha_hora"].dt.year.min())
    max_year = int(df["fecha_hora"].dt.year.max())

    years = []
    # Limitamos a max_year + 1 para no generar años sin datos reales
    for y in range(min_year, max_year + 2):
        start, end = winter_period_from_analysis_year(y)
        # Solo incluir si hay datos reales en ese periodo (no solo solapamiento futuro)
        overlap = df[(df["fecha_hora"] >= start) & (df["fecha_hora"] <= end)]
        if not overlap.empty and len(overlap) >= 24:  # al menos 24 horas de datos
            years.append(y)

    return years



def pollination_score_row(row):
    """
    Modelo de polinización por puntos. Evita que falte radiación o viento y todo salga 0.
    Pondera temperatura, lluvia, viento, radiación y humedad si están disponibles.
    """
    if not row.get("en_ventana_polinizacion", False):
        return 0.0

    score = 0.0
    max_score = 0.0

    t = row.get("temp_media", np.nan)
    max_score += 40
    if pd.notna(t):
        if POLLINATION["temp_opt_low"] <= t <= POLLINATION["temp_opt_high"]:
            score += 40
        elif POLLINATION["temp_min_activity"] <= t <= POLLINATION["temp_max_activity"]:
            score += 25

    max_score += 20
    rain = row.get("lluvia_hora", 0)
    if pd.notna(rain) and rain == 0:
        score += 20

    wind = row.get("viento_velocidad", np.nan)
    gust = row.get("viento_rafaga", np.nan)
    if pd.notna(wind) or pd.notna(gust):
        max_score += 15
        wind_ok = True
        wind_good = True
        if pd.notna(wind):
            wind_good = wind <= POLLINATION["wind_good"]
            wind_ok = wind <= POLLINATION["wind_ok"]
        if pd.notna(gust):
            wind_good = wind_good and gust <= POLLINATION["gust_good"]
            wind_ok = wind_ok and gust <= POLLINATION["gust_ok"]
        if wind_good:
            score += 15
        elif wind_ok:
            score += 8

    rad = row.get("irradiancia", np.nan)
    if pd.notna(rad):
        max_score += 15
        if rad >= POLLINATION["rad_good"]:
            score += 15
        elif rad >= POLLINATION["rad_daylight"]:
            score += 8

    hr = row.get("hr_media", np.nan)
    if pd.notna(hr):
        max_score += 10
        if POLLINATION["hr_good_low"] <= hr <= POLLINATION["hr_good_high"]:
            score += 10
        elif POLLINATION["hr_ok_low"] <= hr <= POLLINATION["hr_ok_high"]:
            score += 5

    if max_score == 0:
        return 0.0
    return round(score / max_score * 100, 1)


def pollination_quality_from_score(mean_score, fav_hours, total_hours):
    if total_hours == 0:
        return "Fuera de ventana"
    if fav_hours == 0 and (pd.isna(mean_score) or mean_score < 35):
        return "Muy limitada"
    if mean_score >= 70:
        return "Buena"
    if mean_score >= 50:
        return "Media"
    return "Limitada"

def add_risk_columns(df, hoja_humeda_threshold=30):
    out = df.copy()

    for col in CANONICAL_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan

    out["frio_menor_7"] = (out["temp_media"] < 7).astype(int)
    out["frio_0_7_2"] = ((out["temp_media"] >= 0) & (out["temp_media"] <= 7.2)).astype(int)
    out["utah_cu_hora"] = out["temp_media"].apply(utah_weight)

    out["hr_90"] = (out["hr_media"] >= 90).astype(int)
    out["lluvia_hora"] = (out["lluvia_mm"].fillna(0) > 0).astype(int)

    out["hoja_humeda"] = (out["humectacion_hoja"].fillna(0) >= hoja_humeda_threshold).astype(int)

    if has_sensor(out, "Humectación de hoja"):
        out["moteado_hora_favorable"] = (
            (out["hoja_humeda"] == 1) &
            (out["temp_media"] >= 6) &
            (out["temp_media"] <= 24)
        ).astype(int)
    else:
        out["moteado_hora_favorable"] = 0

    out["oidio_hora_favorable"] = (
        (out["temp_media"] >= 10) &
        (out["temp_media"] <= 25) &
        (out["hr_media"] >= 70) &
        (out["hoja_humeda"] == 0)
    ).astype(int)

    if has_sensor(out, "Humectación de hoja"):
        out["monilia_hora_favorable"] = (
            ((out["lluvia_hora"] == 1) | (out["hoja_humeda"] == 1) | (out["hr_media"] >= 90)) &
            (out["temp_media"] >= 10) &
            (out["temp_media"] <= 25)
        ).astype(int)
    else:
        out["monilia_hora_favorable"] = (
            ((out["lluvia_hora"] == 1) | (out["hr_media"] >= 90)) &
            (out["temp_media"] >= 10) &
            (out["temp_media"] <= 25)
        ).astype(int)

    out["sector_viento"] = out["viento_direccion"].apply(direction_to_sector)

    temp_component = ((out["temp_media"] - 5) / 25).clip(lower=0, upper=1)
    hr_component = ((100 - out["hr_media"]) / 70).clip(lower=0, upper=1)
    wind_component = (out["viento_velocidad"] / 8).clip(lower=0, upper=1)
    radiation_component = (out["irradiancia"] / 2.16).clip(lower=0, upper=1)

    out["indice_evaporativo_hora"] = (
        0.30 * temp_component.fillna(0) +
        0.25 * hr_component.fillna(0) +
        0.25 * wind_component.fillna(0) +
        0.20 * radiation_component.fillna(0)
    ) * 100

    out["horas_demanda_evaporativa_alta"] = (out["indice_evaporativo_hora"] >= 60).astype(int)
    out["horas_radiacion_alta"] = (out["irradiancia"] >= 2.16).astype(int)
    out["horas_viento_moderado"] = (out["viento_velocidad"] >= 3).astype(int)
    out["horas_rafaga_fuerte"] = (out["viento_rafaga"] >= 8).astype(int)

    out["en_ventana_polinizacion"] = out["fecha_hora"].apply(
        lambda x: (x.month == 4 and x.day >= 15) or x.month == 5 or (x.month == 6 and x.day <= 15)
    )

    out["polinizacion_score"] = out.apply(pollination_score_row, axis=1)
    out["polinizacion_hora_favorable"] = (
        out["en_ventana_polinizacion"] &
        (out["polinizacion_score"] >= 65) &
        (out["lluvia_hora"] == 0) &
        (out["temp_media"] >= POLLINATION["temp_min_activity"]) &
        (out["temp_media"] <= POLLINATION["temp_max_activity"])
    ).astype(int)

    out["polinizacion_limitada_frio"] = (out["en_ventana_polinizacion"] & (out["temp_media"] < POLLINATION["temp_min_activity"])).astype(int)
    out["polinizacion_limitada_calor"] = (out["en_ventana_polinizacion"] & (out["temp_media"] > POLLINATION["temp_max_activity"])).astype(int)
    out["polinizacion_limitada_lluvia"] = (out["en_ventana_polinizacion"] & (out["lluvia_hora"] == 1)).astype(int)
    out["polinizacion_limitada_viento"] = (
        out["en_ventana_polinizacion"] &
        (
            (out["viento_velocidad"].notna() & (out["viento_velocidad"] > POLLINATION["wind_ok"])) |
            (out["viento_rafaga"].notna() & (out["viento_rafaga"] > POLLINATION["gust_ok"]))
        )
    ).astype(int)
    out["polinizacion_limitada_baja_luz"] = (
        out["en_ventana_polinizacion"] &
        out["irradiancia"].notna() &
        (out["irradiancia"] < POLLINATION["rad_daylight"])
    ).astype(int)

    return out


def day_hour_str(ts):
    if pd.isna(ts):
        return "Sin dato"
    dias = {
        0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves",
        4: "viernes", 5: "sábado", 6: "domingo"
    }
    return f"{dias[ts.weekday()]} {ts.strftime('%d/%m/%Y')} a las {ts.strftime('%H:%M')}"


def get_extreme_info(g, value_col, mode="max"):
    if value_col not in g.columns:
        return np.nan, "Sin dato"
    s = pd.to_numeric(g[value_col], errors="coerce").dropna()
    if s.empty:
        return np.nan, "Sin dato"
    idx = s.idxmax() if mode == "max" else s.idxmin()
    return round(float(s.loc[idx]), 2), day_hour_str(idx)


def get_daily_extreme(g, value_col, agg="mean", mode="max"):
    if value_col not in g.columns:
        return np.nan, "Sin dato"
    daily = g[value_col].resample("D").agg(agg).dropna()
    if daily.empty:
        return np.nan, "Sin dato"
    idx = daily.idxmax() if mode == "max" else daily.idxmin()
    return round(float(daily.loc[idx]), 2), idx.strftime("%d/%m/%Y")


def pollination_quality(fav, total):
    if total == 0:
        return "Fuera de ventana"
    pct = fav / total * 100
    if pct >= 55:
        return "Buena"
    if pct >= 30:
        return "Media"
    return "Limitada"


def weekly_summary(df, soil_type):
    if df.empty:
        return pd.DataFrame()

    soil = SOIL_PROFILES[soil_type]
    data = df.copy()
    data["semana_inicio"] = data["fecha_hora"].dt.to_period("W-SUN").apply(lambda p: p.start_time)
    data = data.set_index("fecha_hora")

    has_leaf = has_sensor(df, "Humectación de hoja")
    has_wind = has_sensor(df, "Viento")
    has_rad = has_sensor(df, "Radiación solar")

    rows = []
    for week_start, g in data.groupby("semana_inicio"):
        wet_lengths = wet_periods_hours(g["humectacion_hoja"], threshold=30) if has_leaf else []
        leaf_metrics = leaf_event_metrics(g.reset_index()) if has_leaf else leaf_event_metrics(pd.DataFrame())
        week_end = week_start + timedelta(days=6)

        predominant_degrees = circular_mean_degrees(g["viento_direccion"]) if has_wind else np.nan
        predominant_sector = direction_to_sector(predominant_degrees) if has_wind else "Sin datos"

        sector_txt = ""
        if has_wind:
            sector_counts = g["sector_viento"].value_counts()
            sector_txt = ", ".join(
                [f"{sector}: {int(count)} h" for sector, count in sector_counts.items() if sector != "Sin dato"]
            )

        radiacion_acumulada_mj = g["irradiancia"].fillna(0).sum() if has_rad else np.nan
        radiacion_acumulada_kwh = radiacion_acumulada_mj * MJ_TO_KWH if has_rad else np.nan
        demanda_base = g["indice_evaporativo_hora"].mean()
        demanda_ajustada_suelo = demanda_base * soil["coef_demanda"] if not pd.isna(demanda_base) else np.nan
        lluvia_efectiva = g["lluvia_mm"].fillna(0).sum() * soil["coef_lluvia_efectiva"]

        if pd.isna(demanda_ajustada_suelo):
            orientacion_riego = "No se puede calcular demanda evaporativa por falta de datos suficientes."
        elif demanda_ajustada_suelo >= 55 and lluvia_efectiva < 5:
            orientacion_riego = "Vigilar riego: demanda alta y poca lluvia efectiva."
        elif demanda_ajustada_suelo >= 40 and lluvia_efectiva < 10:
            orientacion_riego = "Atención moderada: revisar humedad del suelo antes de decidir riego."
        elif lluvia_efectiva >= 20:
            orientacion_riego = "Probable menor necesidad de riego por lluvia efectiva relevante."
        else:
            orientacion_riego = "Sin señal clara de estrés hídrico semanal; confirmar con suelo/planta."

        temp_max_val, temp_max_when = get_extreme_info(g, "temp_max", "max")
        temp_min_val, temp_min_when = get_extreme_info(g, "temp_min", "min")
        rad_max_val, rad_max_when = get_extreme_info(g, "irradiancia", "max") if has_rad else (np.nan, "Sin datos")
        rad_daily_max_val, rad_daily_max_day = get_daily_extreme(g, "irradiancia", agg="sum", mode="max") if has_rad else (np.nan, "Sin datos")
        rain_daily_max_val, rain_daily_max_day = get_daily_extreme(g, "lluvia_mm", agg="sum", mode="max")
        wind_gust_val, wind_gust_when = get_extreme_info(g, "viento_rafaga", "max") if has_wind else (np.nan, "Sin datos")

        total_pollination_hours = int(g["en_ventana_polinizacion"].sum())
        fav_pollination_hours = int(g["polinizacion_hora_favorable"].sum())
        mean_pollination_score = round(g.loc[g["en_ventana_polinizacion"], "polinizacion_score"].mean(), 1) if total_pollination_hours else np.nan

        rows.append({
            "Semana": f"{week_start.date()} a {week_end.date()}",
            "Horas con datos": len(g),
            "Temp. media ºC": round(g["temp_media"].mean(), 1),
            "Temp. mín ºC": round(g["temp_min"].min(), 1),
            "Temp. máx ºC": round(g["temp_max"].max(), 1),
            "Momento más cálido": temp_max_when,
            "Valor momento más cálido ºC": temp_max_val,
            "Momento más frío": temp_min_when,
            "Valor momento más frío ºC": temp_min_val,
            "HR media %": round(g["hr_media"].mean(), 1),
            "Horas HR ≥90%": int(g["hr_90"].sum()),
            "Lluvia total mm": round(g["lluvia_mm"].sum(), 1),
            "Día más lluvioso": rain_daily_max_day,
            "Lluvia día más lluvioso mm": rain_daily_max_val,
            "Lluvia efectiva estimada mm": round(lluvia_efectiva, 1),
            "Horas con lluvia": int(g["lluvia_hora"].sum()),
            "Horas hoja húmeda": int(g["hoja_humeda"].sum()) if has_leaf else np.nan,
            "Periodo húmedo máximo h": int(max(wet_lengths) if wet_lengths else 0) if has_leaf else np.nan,
            **leaf_metrics,
            "Horas favorables moteado": int(g["moteado_hora_favorable"].sum()) if has_leaf else np.nan,
            "Horas favorables oídio": int(g["oidio_hora_favorable"].sum()),
            "Horas favorables monilia": int(g["monilia_hora_favorable"].sum()),
            "Viento medio": round(g["viento_velocidad"].mean(), 2) if has_wind else np.nan,
            "Viento máximo medio horario": round(g["viento_velocidad"].max(), 2) if has_wind else np.nan,
            "Ráfaga máxima": round(g["viento_rafaga"].max(), 2) if has_wind else np.nan,
            "Momento ráfaga máxima": wind_gust_when,
            "Horas viento ≥3": int(g["horas_viento_moderado"].sum()) if has_wind else np.nan,
            "Horas ráfaga ≥8": int(g["horas_rafaga_fuerte"].sum()) if has_wind else np.nan,
            "Dirección predominante": predominant_sector,
            "Dirección predominante grados": round(predominant_degrees, 0) if not pd.isna(predominant_degrees) else np.nan,
            "Distribución viento": sector_txt if has_wind else "Sin datos",
            "Radiación media": round(g["irradiancia"].mean(), 2) if has_rad else np.nan,
            "Radiación máxima": round(g["irradiancia"].max(), 2) if has_rad else np.nan,
            "Momento radiación máxima": rad_max_when,
            "Día mayor radiación acumulada": rad_daily_max_day,
            "Radiación acumulada día máximo MJ/m²": round(rad_daily_max_val, 2) if has_rad and not pd.isna(rad_daily_max_val) else np.nan,
            "Radiación acumulada día máximo kWh/m²": round(rad_daily_max_val * MJ_TO_KWH, 2) if has_rad and not pd.isna(rad_daily_max_val) else np.nan,
            "Radiación acumulada MJ/m²": round(radiacion_acumulada_mj, 2) if has_rad else np.nan,
            "Radiación acumulada kWh/m²": round(radiacion_acumulada_kwh, 2) if has_rad else np.nan,
            "Horas radiación alta ≥2,16 MJ/m²": int(g["horas_radiacion_alta"].sum()) if has_rad else np.nan,
            "Horas frío <7 ºC": int(g["frio_menor_7"].sum()),
            "Horas frío 0-7,2 ºC": int(g["frio_0_7_2"].sum()),
            "Utah CU semana": round(g["utah_cu_hora"].sum(), 1),
            "Índice evaporativo medio": round(demanda_base, 1) if not pd.isna(demanda_base) else np.nan,
            "Índice evaporativo ajustado suelo": round(demanda_ajustada_suelo, 1) if not pd.isna(demanda_ajustada_suelo) else np.nan,
            "Horas demanda evaporativa alta": int(g["horas_demanda_evaporativa_alta"].sum()),
            "Orientación riego": orientacion_riego,
            "Horas en ventana polinización": total_pollination_hours,
            "Horas favorables polinización": fav_pollination_hours,
            "% horas favorables polinización": round((fav_pollination_hours / total_pollination_hours * 100), 1) if total_pollination_hours else np.nan,
            "Índice medio polinización": mean_pollination_score,
            "Calidad polinización": pollination_quality_from_score(mean_pollination_score, fav_pollination_hours, total_pollination_hours),
            "Limitación polinización por frío": int(g["polinizacion_limitada_frio"].sum()),
            "Limitación polinización por calor": int(g["polinizacion_limitada_calor"].sum()),
            "Limitación polinización por lluvia": int(g["polinizacion_limitada_lluvia"].sum()),
            "Limitación polinización por viento": int(g["polinizacion_limitada_viento"].sum()) if has_wind else np.nan,
            "Limitación polinización por baja luz": int(g["polinizacion_limitada_baja_luz"].sum()) if has_rad else np.nan,
        })

    return pd.DataFrame(rows)



def period_summary(df, soil_type, start_ts, end_ts):
    """
    Resumen global real del periodo seleccionado.
    No agrupa por semanas. Calcula máximos, mínimos, lluvia, viento,
    radiación, polinización y riesgos usando todas las filas del periodo.
    """
    if df.empty:
        return pd.DataFrame()

    soil = SOIL_PROFILES[soil_type]
    data = df.copy().set_index("fecha_hora").sort_index()

    has_leaf = has_sensor(df, "Humectación de hoja")
    has_wind = has_sensor(df, "Viento")
    has_rad = has_sensor(df, "Radiación solar")

    wet_lengths = wet_periods_hours(data["humectacion_hoja"], threshold=30) if has_leaf else []
    leaf_metrics = leaf_event_metrics(data.reset_index()) if has_leaf else leaf_event_metrics(pd.DataFrame())

    predominant_degrees = circular_mean_degrees(data["viento_direccion"]) if has_wind else np.nan
    predominant_sector = direction_to_sector(predominant_degrees) if has_wind else "Sin datos"

    sector_txt = ""
    if has_wind:
        sector_counts = data["sector_viento"].value_counts()
        sector_txt = ", ".join(
            [f"{sector}: {int(count)} h" for sector, count in sector_counts.items() if sector != "Sin dato"]
        )

    radiacion_acumulada_mj = data["irradiancia"].fillna(0).sum() if has_rad else np.nan
    radiacion_acumulada_kwh = radiacion_acumulada_mj * MJ_TO_KWH if has_rad else np.nan
    demanda_base = data["indice_evaporativo_hora"].mean()
    demanda_ajustada_suelo = demanda_base * soil["coef_demanda"] if not pd.isna(demanda_base) else np.nan
    lluvia_efectiva = data["lluvia_mm"].fillna(0).sum() * soil["coef_lluvia_efectiva"]

    if pd.isna(demanda_ajustada_suelo):
        orientacion_riego = "No se puede calcular demanda evaporativa por falta de datos suficientes."
    elif demanda_ajustada_suelo >= 55 and lluvia_efectiva < 5:
        orientacion_riego = "Vigilar riego: demanda alta y poca lluvia efectiva."
    elif demanda_ajustada_suelo >= 40 and lluvia_efectiva < 10:
        orientacion_riego = "Atención moderada: revisar humedad del suelo antes de decidir riego."
    elif lluvia_efectiva >= 20:
        orientacion_riego = "Probable menor necesidad de riego por lluvia efectiva relevante."
    else:
        orientacion_riego = "Sin señal clara de estrés hídrico semanal; confirmar con suelo/planta."

    temp_max_val, temp_max_when = get_extreme_info(data, "temp_max", "max")
    temp_min_val, temp_min_when = get_extreme_info(data, "temp_min", "min")
    rad_max_val, rad_max_when = get_extreme_info(data, "irradiancia", "max") if has_rad else (np.nan, "Sin datos")
    rad_daily_max_val, rad_daily_max_day = get_daily_extreme(data, "irradiancia", agg="sum", mode="max") if has_rad else (np.nan, "Sin datos")
    rain_daily_max_val, rain_daily_max_day = get_daily_extreme(data, "lluvia_mm", agg="sum", mode="max")
    wind_gust_val, wind_gust_when = get_extreme_info(data, "viento_rafaga", "max") if has_wind else (np.nan, "Sin datos")

    total_pollination_hours = int(data["en_ventana_polinizacion"].sum())
    fav_pollination_hours = int(data["polinizacion_hora_favorable"].sum())
    mean_pollination_score = round(data.loc[data["en_ventana_polinizacion"], "polinizacion_score"].mean(), 1) if total_pollination_hours else np.nan

    row = {
        "Semana": f"{pd.Timestamp(start_ts).date()} a {pd.Timestamp(end_ts).date()}",
        "Horas con datos": len(data),
        "Temp. media ºC": round(data["temp_media"].mean(), 1),
        "Temp. mín ºC": round(data["temp_min"].min(), 1),
        "Temp. máx ºC": round(data["temp_max"].max(), 1),
        "Momento más cálido": temp_max_when,
        "Valor momento más cálido ºC": temp_max_val,
        "Momento más frío": temp_min_when,
        "Valor momento más frío ºC": temp_min_val,
        "HR media %": round(data["hr_media"].mean(), 1),
        "Horas HR ≥90%": int(data["hr_90"].sum()),
        "Lluvia total mm": round(data["lluvia_mm"].sum(), 1),
        "Día más lluvioso": rain_daily_max_day,
        "Lluvia día más lluvioso mm": rain_daily_max_val,
        "Lluvia efectiva estimada mm": round(lluvia_efectiva, 1),
        "Horas con lluvia": int(data["lluvia_hora"].sum()),
        "Horas hoja húmeda": int(data["hoja_humeda"].sum()) if has_leaf else np.nan,
        "Periodo húmedo máximo h": int(max(wet_lengths) if wet_lengths else 0) if has_leaf else np.nan,
        **leaf_metrics,
        "Horas favorables moteado": int(data["moteado_hora_favorable"].sum()) if has_leaf else np.nan,
        "Horas favorables oídio": int(data["oidio_hora_favorable"].sum()),
        "Horas favorables monilia": int(data["monilia_hora_favorable"].sum()),
        "Viento medio": round(data["viento_velocidad"].mean(), 2) if has_wind else np.nan,
        "Viento máximo medio horario": round(data["viento_velocidad"].max(), 2) if has_wind else np.nan,
        "Ráfaga máxima": round(data["viento_rafaga"].max(), 2) if has_wind else np.nan,
        "Momento ráfaga máxima": wind_gust_when,
        "Horas viento ≥3": int(data["horas_viento_moderado"].sum()) if has_wind else np.nan,
        "Horas ráfaga ≥8": int(data["horas_rafaga_fuerte"].sum()) if has_wind else np.nan,
        "Dirección predominante": predominant_sector,
        "Dirección predominante grados": round(predominant_degrees, 0) if not pd.isna(predominant_degrees) else np.nan,
        "Distribución viento": sector_txt if has_wind else "Sin datos",
        "Radiación media": round(data["irradiancia"].mean(), 2) if has_rad else np.nan,
        "Radiación máxima": round(data["irradiancia"].max(), 2) if has_rad else np.nan,
        "Momento radiación máxima": rad_max_when,
        "Día mayor radiación acumulada": rad_daily_max_day,
        "Radiación acumulada día máximo MJ/m²": round(rad_daily_max_val, 2) if has_rad and not pd.isna(rad_daily_max_val) else np.nan,
        "Radiación acumulada día máximo kWh/m²": round(rad_daily_max_val * MJ_TO_KWH, 2) if has_rad and not pd.isna(rad_daily_max_val) else np.nan,
        "Radiación acumulada MJ/m²": round(radiacion_acumulada_mj, 2) if has_rad else np.nan,
        "Radiación acumulada kWh/m²": round(radiacion_acumulada_kwh, 2) if has_rad else np.nan,
        "Horas radiación alta ≥2,16 MJ/m²": int(data["horas_radiacion_alta"].sum()) if has_rad else np.nan,
        "Horas frío <7 ºC": int(data["frio_menor_7"].sum()),
        "Horas frío 0-7,2 ºC": int(data["frio_0_7_2"].sum()),
        "Utah CU semana": round(data["utah_cu_hora"].sum(), 1),
        "Índice evaporativo medio": round(demanda_base, 1) if not pd.isna(demanda_base) else np.nan,
        "Índice evaporativo ajustado suelo": round(demanda_ajustada_suelo, 1) if not pd.isna(demanda_ajustada_suelo) else np.nan,
        "Horas demanda evaporativa alta": int(data["horas_demanda_evaporativa_alta"].sum()),
        "Orientación riego": orientacion_riego,
        "Horas en ventana polinización": total_pollination_hours,
        "Horas favorables polinización": fav_pollination_hours,
        "% horas favorables polinización": round((fav_pollination_hours / total_pollination_hours * 100), 1) if total_pollination_hours else np.nan,
        "Índice medio polinización": mean_pollination_score,
            "Calidad polinización": pollination_quality_from_score(mean_pollination_score, fav_pollination_hours, total_pollination_hours),
        "Limitación polinización por frío": int(data["polinizacion_limitada_frio"].sum()),
        "Limitación polinización por calor": int(data["polinizacion_limitada_calor"].sum()),
        "Limitación polinización por lluvia": int(data["polinizacion_limitada_lluvia"].sum()),
        "Limitación polinización por viento": int(data["polinizacion_limitada_viento"].sum()) if has_wind else np.nan,
        "Limitación polinización por baja luz": int(data["polinizacion_limitada_baja_luz"].sum()) if has_rad else np.nan,
    }

    return pd.DataFrame([row])

def winter_chill_summary(df, analysis_year):
    season = winter_label_from_analysis_year(analysis_year)
    start, end = winter_period_from_analysis_year(analysis_year)
    data = df[(df["fecha_hora"] >= start) & (df["fecha_hora"] <= end)].copy()

    if data.empty:
        return pd.DataFrame(), pd.DataFrame(), start, end

    data = add_risk_columns(data)
    data = data.sort_values("fecha_hora").copy()

    cp = dynamic_chill_portions(data["temp_media"])
    data["chill_portion_hora"] = cp
    data["chill_portion_acumulada"] = np.cumsum(cp)
    data["utah_acumulado"] = data["utah_cu_hora"].cumsum()
    data["horas_menor_7_acum"] = data["frio_menor_7"].cumsum()

    total_expected = expected_hours(start, end)
    coverage = round(len(data.dropna(subset=["temp_media"])) / total_expected * 100, 1) if total_expected else 0

    season_row = pd.DataFrame([{
        "Campaña frío": season,
        "Desde": start,
        "Hasta": end,
        "Horas esperadas": total_expected,
        "Horas con datos temperatura": int(data["temp_media"].notna().sum()),
        "Cobertura temperatura %": coverage,
        "Horas frío <7 ºC": int(data["frio_menor_7"].sum()),
        "Horas frío 0-7,2 ºC": int(data["frio_0_7_2"].sum()),
        "Utah Chill Units": round(data["utah_cu_hora"].sum(), 1),
        "Chill Portions": round(float(np.sum(cp)), 2),
        "Temp media periodo frío ºC": round(data["temp_media"].mean(), 2),
        "Temp mínima periodo frío ºC": round(data["temp_media"].min(), 2),
        "Temp máxima periodo frío ºC": round(data["temp_media"].max(), 2),
        "Aviso": "Campaña incompleta: interpretar con prudencia." if coverage < 95 else "Campaña con cobertura suficiente.",
    }])

    daily = data.set_index("fecha_hora").resample("D").agg({
        "frio_menor_7": "sum",
        "frio_0_7_2": "sum",
        "utah_cu_hora": "sum",
        "chill_portion_hora": "sum",
        "temp_media": "mean"
    }).reset_index()
    daily["chill_portions_acum"] = daily["chill_portion_hora"].cumsum()
    daily["utah_acum"] = daily["utah_cu_hora"].cumsum()
    daily["horas_menor_7_acum"] = daily["frio_menor_7"].cumsum()

    return season_row, daily, start, end



def chill_column_comparison(df, analysis_year):
    """
    Comparativa directa para verificar por qué un Excel puede dar un valor distinto.
    Cuenta horas <7, <=7 y 0-7.2 usando las tres columnas del CSV.
    """
    start, end = winter_period_from_analysis_year(analysis_year)
    data = df[(df["fecha_hora"] >= start) & (df["fecha_hora"] <= end)].copy()

    rows = []
    labels = {
        "temp_media": "Temperatura",
        "temp_min": "Temperatura mín",
        "temp_max": "Temperatura max",
    }

    total_expected = expected_hours(start, end)

    for col, label in labels.items():
        if col not in data.columns:
            continue
        s = pd.to_numeric(data[col], errors="coerce")
        rows.append({
            "Columna usada": label,
            "Horas esperadas campaña": total_expected,
            "Horas con dato": int(s.notna().sum()),
            "Horas <7 ºC": int((s < 7).sum()),
            "Horas <=7 ºC": int((s <= 7).sum()),
            "Horas 0-7,2 ºC": int(((s >= 0) & (s <= 7.2)).sum()),
            "Temp media periodo": round(s.mean(), 2) if s.notna().any() else np.nan,
            "Temp mínima periodo": round(s.min(), 2) if s.notna().any() else np.nan,
            "Temp máxima periodo": round(s.max(), 2) if s.notna().any() else np.nan,
        })

    return pd.DataFrame(rows)


def classify_index(value):
    if pd.isna(value):
        return "sin dato"
    if value >= 60:
        return "alto"
    if value >= 40:
        return "medio"
    return "bajo"


def render_interpreted_report(summary, availability, soil_type):
    """
    Informe interpretado en bloques visuales, no como un único párrafo.
    """
    if summary.empty:
        st.warning("No hay datos suficientes para generar un informe del periodo seleccionado.")
        return

    soil = SOIL_PROFILES[soil_type]
    row = summary.iloc[0]

    missing_msgs = availability[availability["Estado"] == "Sin datos"]["Mensaje"].tolist()
    incomplete_msgs = availability[availability["Estado"] == "Incompleto"]["Mensaje"].tolist()

    st.markdown("### Informe interpretado del periodo")

    # 1. Temperatura
    with st.container(border=True):
        st.markdown("#### 🌡️ Temperatura")
        st.write(
            f"El periodo analizado tuvo una **temperatura media de {row['Temp. media ºC']} ºC**. "
            f"El momento más cálido alcanzó **{row['Valor momento más cálido ºC']} ºC** "
            f"el **{row['Momento más cálido']}**, mientras que el momento más frío fue de "
            f"**{row['Valor momento más frío ºC']} ºC** el **{row['Momento más frío']}**."
        )

        if row["Temp. media ºC"] >= 18:
            st.info("Semana o periodo térmicamente templado-cálido. Puede acelerar desarrollo vegetativo y aumentar demanda hídrica si coincide con radiación y viento.")
        elif row["Temp. media ºC"] <= 8:
            st.info("Periodo frío. Puede contribuir a acumulación de frío si está dentro de la ventana invernal.")
        else:
            st.info("Temperatura media moderada, sin señal térmica extrema en el promedio del periodo.")

    # 2. Humedad
    with st.container(border=True):
        st.markdown("#### 💧 Humedad ambiental y hoja")
        st.write(
            f"La humedad relativa media fue de **{row['HR media %']} %**, con "
            f"**{row['Horas HR ≥90%']} horas** por encima o igual al 90 %."
        )

        if not pd.isna(row.get("Horas hoja húmeda", np.nan)):
            st.write(
                f"En humedad foliar, se registraron **{row['Horas hoja húmeda']} horas de hoja húmeda** "
                f"y un periodo continuo máximo de **{row['Periodo húmedo máximo h']} horas** según el indicador simple."
            )

            if "Eventos hoja mojada" in row.index:
                st.write(
                    f"Con el nuevo análisis por eventos, se detectaron **{row['Eventos hoja mojada']} eventos de hoja mojada**, "
                    f"con **{row['Horas húmedas equivalentes']} horas húmedas equivalentes** acumuladas. "
                    f"El evento más largo acumuló **{row['Máx horas húmedas evento']} horas equivalentes**."
                )
            if row["Horas hoja húmeda"] >= 40:
                st.warning("La acumulación de hoja húmeda es relevante. Si coincide con brotación, floración, cuajado o presencia de inóculo, aumenta la vigilancia sanitaria.")
            elif row["Horas hoja húmeda"] >= 15:
                st.info("Hay presencia moderada de hoja húmeda. Conviene interpretarla junto con temperatura y fase fenológica.")
            else:
                st.success("La humectación foliar no destaca como especialmente elevada en este periodo.")
        else:
            st.warning("Para este periodo no disponemos de datos de humectación de hoja, por lo que el análisis de hoja mojada y parte del riesgo de moteado debe interpretarse con prudencia.")

    # 3. Lluvia
    with st.container(border=True):
        st.markdown("#### 🌧️ Lluvia")
        st.write(
            f"La precipitación acumulada fue de **{row['Lluvia total mm']} mm**. "
            f"El día más lluvioso fue **{row['Día más lluvioso']}**, con "
            f"**{row['Lluvia día más lluvioso mm']} mm**."
        )

        st.write(
            f"Para un suelo **{soil_type.lower()}**, la lluvia efectiva estimada es de "
            f"**{row['Lluvia efectiva estimada mm']} mm**."
        )

        if row["Lluvia total mm"] >= 30:
            st.info("Periodo húmedo por lluvia acumulada. Puede reducir necesidad de riego, pero aumentar presión de enfermedades si coincide con hoja húmeda y temperaturas favorables.")
        elif row["Lluvia total mm"] >= 10:
            st.info("Lluvia moderada. Conviene valorar reparto de la lluvia y capacidad de retención del suelo.")
        else:
            st.warning("Lluvia escasa. Si coincide con radiación/viento altos o suelo ligero, conviene revisar humedad del suelo.")

    # 4. Viento
    with st.container(border=True):
        st.markdown("#### 🌬️ Viento")
        if not pd.isna(row.get("Viento medio", np.nan)):
            st.write(
                f"El viento medio fue de **{row['Viento medio']}**, con una ráfaga máxima de "
                f"**{row['Ráfaga máxima']}** registrada el **{row['Momento ráfaga máxima']}**."
            )
            st.write(
                f"La dirección predominante fue **{row['Dirección predominante']}** "
                f"({row['Dirección predominante grados']}º)."
            )

            if row["Horas ráfaga ≥8"] >= 10:
                st.warning("Hubo varias horas con ráfagas relevantes. Esto puede aumentar evaporación, secado de suelo, estrés en floración y riesgo de deriva en tratamientos.")
            elif row["Horas viento ≥3"] >= 24:
                st.info("El viento tuvo presencia moderada durante el periodo y puede contribuir al secado de hoja y suelo.")
            else:
                st.success("El viento no destaca como factor limitante principal en este periodo.")
        else:
            st.warning("Para este periodo no disponemos de datos de viento.")

    # 5. Radiación solar y riego
    with st.container(border=True):
        st.markdown("#### ☀️ Radiación solar, evaporación y orientación de riego")
        if not pd.isna(row.get("Radiación media", np.nan)):
            st.write(
                f"La radiación media horaria fue de **{row['Radiación media']} MJ/m²**, con máximo horario de "
                f"**{row['Radiación máxima']} MJ/m²** el **{row['Momento radiación máxima']}**."
            )
            st.write(
                f"El día con mayor radiación acumulada fue **{row['Día mayor radiación acumulada']}**, "
                f"con **{row['Radiación acumulada día máximo MJ/m²']} MJ/m²** "
                f"(**{row['Radiación acumulada día máximo kWh/m²']} kWh/m²**). "
                f"La radiación acumulada del periodo fue de **{row['Radiación acumulada MJ/m²']} MJ/m²** "
                f"(**{row['Radiación acumulada kWh/m²']} kWh/m²**)."
            )
        else:
            st.warning("Para este periodo no disponemos de datos de radiación solar.")

        st.write(
            f"El índice evaporativo ajustado al tipo de suelo fue **{row['Índice evaporativo ajustado suelo']}/100**. "
            f"**Orientación:** {row['Orientación riego']}"
        )

        st.write(
            f"El suelo seleccionado es **{soil_type}**, con retención **{soil['retencion'].lower()}**. "
            f"{soil['comentario']}"
        )

        if pd.isna(row.get("Radiación media", np.nan)) or pd.isna(row.get("Viento medio", np.nan)):
            st.info("El índice evaporativo puede estar calculado de forma parcial si faltan datos de viento o radiación.")

    # 6. Polinización
    with st.container(border=True):
        st.markdown("#### 🐝 Polinización")
        if row["Horas en ventana polinización"] > 0:
            st.write(
                f"El periodo cae dentro de la ventana orientativa de polinización. "
                f"Se registraron **{row['Horas favorables polinización']} horas favorables** de "
                f"**{row['Horas en ventana polinización']} horas posibles**, equivalente al "
                f"**{row['% horas favorables polinización']} %**. "
                f"El índice medio de polinización fue **{row['Índice medio polinización']}/100**."
            )
            st.write(f"Calidad estimada de polinización: **{row['Calidad polinización']}**.")

            st.write(
                f"Limitaciones detectadas: frío **{row['Limitación polinización por frío']} h**, "
                f"calor **{row['Limitación polinización por calor']} h**, "
                f"lluvia **{row['Limitación polinización por lluvia']} h**, "
                f"viento **{row['Limitación polinización por viento']} h** y "
                f"baja luz **{row['Limitación polinización por baja luz']} h**."
            )

            if row["Calidad polinización"] == "Buena":
                st.success("Las condiciones meteorológicas fueron globalmente favorables para la actividad de polinizadores.")
            elif row["Calidad polinización"] == "Media":
                st.info("Las condiciones fueron parcialmente favorables. Conviene revisar si coincidieron con plena floración.")
            else:
                st.warning("Las condiciones fueron limitantes para la polinización. Revisar coincidencia con floración real y presencia de polinizadores.")
        else:
            st.info("El periodo seleccionado queda fuera de la ventana orientativa de polinización definida en la app.")

    # 7. Riesgo de hongos
    with st.container(border=True):
        st.markdown("#### 🍄 Riesgo potencial de infección por hongos")

        if "Eventos hoja mojada" in row.index and not pd.isna(row.get("Eventos hoja mojada", np.nan)):
            st.write(
                f"Análisis por eventos de humectación: **{row['Eventos hoja mojada']} eventos** detectados, "
                f"con **{row['Horas húmedas equivalentes']} h equivalentes** de hoja mojada."
            )
            st.write(
                f"Eventos con riesgo medio/alto para moteado: **{row['Eventos moteado medio/alto']}** "
                f"(**{row['Eventos moteado alto']}** altos). "
                f"Evento más crítico: {row['Evento más crítico moteado']}."
            )
            st.write(
                f"Eventos con riesgo medio/alto para monilia: **{row['Eventos monilia medio/alto']}** "
                f"(**{row['Eventos monilia alto']}** altos). "
                f"Evento más crítico: {row['Evento más crítico monilia']}."
            )

        if pd.isna(row.get("Horas favorables moteado", np.nan)):
            st.warning("No se puede valorar correctamente el moteado ligado a hoja húmeda porque no hay datos de humectación de hoja.")
        else:
            st.write(f"**Moteado:** {row['Horas favorables moteado']} horas favorables.")
            if row["Horas favorables moteado"] >= 40:
                st.warning("Riesgo potencial de moteado alto por acumulación relevante de hoja húmeda con temperatura favorable.")
            elif row["Horas favorables moteado"] >= 15:
                st.info("Riesgo potencial de moteado medio. Conviene revisar protección, fenología y antecedentes de inóculo.")
            else:
                st.success("Riesgo potencial de moteado bajo según los umbrales simplificados.")

        st.write(f"**Oídio:** {row['Horas favorables oídio']} horas favorables.")
        if row["Horas favorables oídio"] >= 100:
            st.warning("Ventana favorable para oídio elevada por muchas horas con temperatura templada y humedad alta.")
        elif row["Horas favorables oídio"] >= 40:
            st.info("Ventana favorable para oídio moderada.")
        else:
            st.success("Ventana favorable para oídio reducida.")

        st.write(f"**Monilia:** {row['Horas favorables monilia']} horas favorables.")
        if row["Horas favorables monilia"] >= 80:
            st.warning("Condiciones húmedas compatibles con vigilancia de monilia si coincide con floración, heridas o fruto sensible.")
        elif row["Horas favorables monilia"] >= 30:
            st.info("Condiciones moderadas para vigilancia de monilia.")
        else:
            st.success("Condiciones de monilia poco destacables en el periodo.")

    # 8. Calidad de datos
    if missing_msgs or incomplete_msgs:
        with st.container(border=True):
            st.markdown("#### ⚠️ Calidad y disponibilidad de datos")
            for msg in missing_msgs + incomplete_msgs:
                st.write(f"- {msg}")




def iso_week_period(year, week):
    start = pd.Timestamp.fromisocalendar(int(year), int(week), 1)
    end = pd.Timestamp.fromisocalendar(int(year), int(week), 7) + pd.Timedelta(hours=23)
    return start, end


def add_numeric_deviation_table(df, base_label_col="Comparación", base_row_index=0):
    if df.empty or len(df) < 2:
        return pd.DataFrame()

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        return pd.DataFrame()

    base = df.iloc[base_row_index][numeric_cols]
    base_name = df.iloc[base_row_index].get(base_label_col, "Base")
    rows = []

    for i, row in df.iterrows():
        if i == base_row_index:
            continue
        label = row.get(base_label_col, f"Fila {i}")
        for col in numeric_cols:
            base_val = base[col]
            val = row[col]
            if pd.isna(base_val) or pd.isna(val):
                continue
            rows.append({
                "Comparado": label,
                "Base": base_name,
                "Variable": col,
                "Valor comparado": round(float(val), 3),
                "Valor base": round(float(base_val), 3),
                "Diferencia": round(float(val - base_val), 3),
                "Diferencia %": round(float((val - base_val) / base_val * 100), 2) if base_val != 0 else np.nan,
            })

    return pd.DataFrame(rows)


def compare_chill_campaigns(history, years):
    rows = []
    for y in years:
        chill_summary, _, start, end = winter_chill_summary(history, int(y))
        if chill_summary.empty:
            rows.append({
                "Comparación": f"Frío {int(y)-1}/{int(y)}",
                "Año análisis": int(y),
                "Desde": start,
                "Hasta": end,
                "Aviso": "Sin datos",
            })
        else:
            row = chill_summary.iloc[0].to_dict()
            row["Comparación"] = f"Frío {int(y)-1}/{int(y)}"
            row["Año análisis"] = int(y)
            rows.append(row)
    return pd.DataFrame(rows)



def monthly_chill_breakdown(history, years):
    """
    Desglose mensual de campañas de frío para el comparador.

    El año de análisis representa el cierre de la campaña:
    2024 = 01/11/2023 a 31/03/2024.
    """
    rows = []
    if history is None or history.empty:
        return pd.DataFrame()

    hist = history.copy()
    hist["fecha_hora"] = pd.to_datetime(hist["fecha_hora"], errors="coerce")
    hist = hist.dropna(subset=["fecha_hora"]).sort_values("fecha_hora")

    month_order = {
        11: 1,
        12: 2,
        1: 3,
        2: 4,
        3: 5,
    }

    for y in years:
        y = int(y)
        start, end = winter_period_from_analysis_year(y)
        data = hist[(hist["fecha_hora"] >= start) & (hist["fecha_hora"] <= end)].copy()
        if data.empty:
            continue

        data = add_risk_columns(data)
        cp = dynamic_chill_portions(data["temp_media"])
        data["chill_portion_hora"] = cp
        data["Mes número"] = data["fecha_hora"].dt.month
        data["Mes"] = data["Mes número"].map({
            11: "Noviembre",
            12: "Diciembre",
            1: "Enero",
            2: "Febrero",
            3: "Marzo",
        })
        data["Orden mes campaña"] = data["Mes número"].map(month_order)

        grouped = data.groupby(["Mes número", "Mes", "Orden mes campaña"], as_index=False).agg(
            **{
                "Horas frío <7 ºC": ("frio_menor_7", "sum"),
                "Horas frío 0-7,2 ºC": ("frio_0_7_2", "sum"),
                "Utah Chill Units": ("utah_cu_hora", "sum"),
                "Chill Portions": ("chill_portion_hora", "sum"),
                "Temp media ºC": ("temp_media", "mean"),
                "Horas con datos": ("temp_media", lambda s: int(pd.to_numeric(s, errors="coerce").notna().sum())),
            }
        )

        for _, row in grouped.sort_values("Orden mes campaña").iterrows():
            rows.append({
                "Campaña frío": f"{y-1}/{y}",
                "Campaña": f"Frío {y-1}/{y}",
                "Año análisis": y,
                "Mes": row["Mes"],
                "Mes número": int(row["Mes número"]),
                "Orden mes campaña": int(row["Orden mes campaña"]),
                "Mes orden": int(row["Orden mes campaña"]),
                "Horas frío <7 ºC": int(row["Horas frío <7 ºC"]),
                "Horas frío 0-7,2 ºC": int(row["Horas frío 0-7,2 ºC"]),
                "Utah Chill Units": round(float(row["Utah Chill Units"]), 1),
                "Chill Portions": round(float(row["Chill Portions"]), 2),
                "Temp media ºC": round(float(row["Temp media ºC"]), 2) if pd.notna(row["Temp media ºC"]) else np.nan,
                "Horas con datos": int(row["Horas con datos"]),
            })

    return pd.DataFrame(rows)


def compare_iso_weeks(history, years, week, soil_type, hoja_threshold):
    rows = []
    for y in years:
        start, end = iso_week_period(int(y), int(week))
        period = history[(history["fecha_hora"] >= start) & (history["fecha_hora"] <= end)].copy()
        if period.empty:
            rows.append({
                "Comparación": f"{int(y)} · semana {int(week)}",
                "Año": int(y),
                "Semana ISO": int(week),
                "Desde": start,
                "Hasta": end,
                "Aviso": "Sin datos",
            })
            continue

        period = add_risk_columns(period, hoja_humeda_threshold=hoja_threshold)
        row_df = period_summary(period, soil_type, start, end)
        row = row_df.iloc[0].to_dict() if not row_df.empty else {}
        row["Comparación"] = f"{int(y)} · semana {int(week)}"
        row["Año"] = int(y)
        row["Semana ISO"] = int(week)
        row["Desde"] = start
        row["Hasta"] = end
        rows.append(row)

    return pd.DataFrame(rows)



def pct_diff_text(base, val):
    if pd.isna(base) or pd.isna(val):
        return "sin dato comparable"
    diff = val - base
    if base == 0:
        return f"{diff:+.2f} de diferencia"
    pct = diff / base * 100
    return f"{diff:+.2f} ({pct:+.1f} %)"


def value_text(v, suffix=""):
    if pd.isna(v):
        return "sin dato"
    try:
        return f"{float(v):.2f}{suffix}"
    except Exception:
        return f"{v}{suffix}"


def render_week_comparison_explanation(cmp_df):
    """
    Explicación narrativa para comparación de semanas ISO.
    Muestra todos los años disponibles y resalta máximos/mínimos por variable.
    """
    if cmp_df.empty:
        st.info("No hay datos para generar una explicación comparativa.")
        return

    if len(cmp_df) < 2:
        st.info("Selecciona al menos dos años para generar una explicación comparativa.")
        return

    st.subheader("Lectura interpretada de la comparación")
    st.write(
        "La comparación se interpreta entre todos los años seleccionados. "
        "Para cada variable se indica el año con mayor valor, el año con menor valor y la diferencia entre ambos."
    )

    variables = [
        ("Temp. media ºC", "temperatura media", " ºC"),
        ("Temp. máx ºC", "temperatura máxima", " ºC"),
        ("Temp. mín ºC", "temperatura mínima", " ºC"),
        ("HR media %", "humedad relativa media", " %"),
        ("Lluvia total mm", "lluvia acumulada", " mm"),
        ("Horas con lluvia", "horas con lluvia", " h"),
        ("Horas HR ≥90%", "horas con humedad relativa ≥90%", " h"),
        ("Horas hoja húmeda", "horas de hoja húmeda", " h"),
        ("Horas húmedas equivalentes", "horas húmedas equivalentes", " h"),
        ("Eventos hoja mojada", "eventos de hoja mojada", ""),
        ("Viento medio", "viento medio", ""),
        ("Ráfaga máxima", "ráfaga máxima", ""),
        ("Radiación acumulada estimada MJ/m²", "radiación acumulada", " MJ/m²"),
        ("Radiación acumulada estimada kWh/m²", "radiación acumulada", " kWh/m²"),
        ("Índice evaporativo ajustado suelo", "índice evaporativo ajustado al suelo", "/100"),
        ("Horas favorables polinización", "horas favorables para polinización", " h"),
        ("% horas favorables polinización", "porcentaje favorable para polinización", " %"),
        ("Horas favorables moteado", "horas favorables para moteado", " h"),
        ("Eventos moteado medio/alto", "eventos de moteado medio/alto", ""),
        ("Eventos monilia medio/alto", "eventos de monilia medio/alto", ""),
        ("Horas favorables oídio", "horas favorables para oídio", " h"),
        ("Horas favorables monilia", "horas favorables para monilia", " h"),
    ]

    for col, name, suffix in variables:
        if col not in cmp_df.columns:
            continue

        valid = cmp_df[["Comparación", col]].copy()
        valid[col] = pd.to_numeric(valid[col], errors="coerce")
        valid = valid.dropna(subset=[col])

        if len(valid) < 2:
            continue

        max_row = valid.loc[valid[col].idxmax()]
        min_row = valid.loc[valid[col].idxmin()]
        max_val = float(max_row[col])
        min_val = float(min_row[col])
        diff = max_val - min_val
        pct = (diff / min_val * 100) if min_val != 0 else np.nan

        if pd.notna(pct):
            st.write(
                f"- **{name.capitalize()}**: el valor más alto fue **{value_text(max_val, suffix)}** en "
                f"**{max_row['Comparación']}**; el más bajo fue **{value_text(min_val, suffix)}** en "
                f"**{min_row['Comparación']}**. Diferencia: **{diff:.2f}{suffix}** (**{pct:.1f} %** sobre el menor)."
            )
        else:
            st.write(
                f"- **{name.capitalize()}**: el valor más alto fue **{value_text(max_val, suffix)}** en "
                f"**{max_row['Comparación']}**; el más bajo fue **{value_text(min_val, suffix)}** en "
                f"**{min_row['Comparación']}**. Diferencia: **{diff:.2f}{suffix}**."
            )

    # Lectura agronómica general
    notes = []

    if "Lluvia total mm" in cmp_df.columns:
        valid = cmp_df[["Comparación", "Lluvia total mm"]].dropna()
        if len(valid) >= 2:
            wet = valid.loc[valid["Lluvia total mm"].idxmax()]
            dry = valid.loc[valid["Lluvia total mm"].idxmin()]
            notes.append(
                f"La semana más lluviosa fue **{wet['Comparación']}** y la más seca fue **{dry['Comparación']}**."
            )

    if "Temp. media ºC" in cmp_df.columns:
        valid = cmp_df[["Comparación", "Temp. media ºC"]].dropna()
        if len(valid) >= 2:
            warm = valid.loc[valid["Temp. media ºC"].idxmax()]
            cool = valid.loc[valid["Temp. media ºC"].idxmin()]
            notes.append(
                f"La semana más cálida fue **{warm['Comparación']}** y la más fría fue **{cool['Comparación']}**."
            )

    if "Índice evaporativo ajustado suelo" in cmp_df.columns:
        valid = cmp_df[["Comparación", "Índice evaporativo ajustado suelo"]].dropna()
        if len(valid) >= 2:
            high = valid.loc[valid["Índice evaporativo ajustado suelo"].idxmax()]
            low = valid.loc[valid["Índice evaporativo ajustado suelo"].idxmin()]
            notes.append(
                f"La mayor demanda evaporativa ajustada al suelo aparece en **{high['Comparación']}**; la menor en **{low['Comparación']}**."
            )

    if notes:
        st.markdown("**Lectura agronómica general:** " + " ".join(notes))

    missing = cmp_df[cmp_df.get("Aviso", pd.Series(index=cmp_df.index, dtype=object)).eq("Sin datos")]
    if not missing.empty:
        st.warning(
            "Algunos años seleccionados no tienen datos para esa semana ISO: "
            + ", ".join(missing["Comparación"].astype(str).tolist())
        )


def render_chill_comparison_explanation(cmp_df, monthly_df=None):
    """
    Explicación narrativa sin fijar una campaña como única base.
    Resume máximos, mínimos y diferencias entre campañas seleccionadas.
    """
    if cmp_df.empty or len(cmp_df) < 2:
        st.info("Selecciona al menos dos campañas para generar una explicación comparativa.")
        return

    st.subheader("Lectura interpretada de las campañas de frío")
    st.write(
        "La comparación se interpreta entre todas las campañas seleccionadas, sin fijar un año obligatorio como base. "
        "Para cada modelo se identifica qué campaña acumuló más frío, cuál acumuló menos y la diferencia entre ambas."
    )

    variables = [
        ("Horas frío <7 ºC", "horas frío <7 ºC", " h"),
        ("Horas frío 0-7,2 ºC", "horas frío 0-7,2 ºC", " h"),
        ("Utah Chill Units", "Utah Chill Units", ""),
        ("Chill Portions", "Chill Portions", ""),
    ]

    for col, label, suffix in variables:
        if col not in cmp_df.columns:
            continue

        valid = cmp_df[["Comparación", col]].dropna()
        if valid.empty:
            continue

        idx_max = valid[col].idxmax()
        idx_min = valid[col].idxmin()
        max_row = cmp_df.loc[idx_max]
        min_row = cmp_df.loc[idx_min]
        max_val = max_row[col]
        min_val = min_row[col]
        diff = max_val - min_val
        pct = (diff / min_val * 100) if min_val not in [0, np.nan] and pd.notna(min_val) and min_val != 0 else np.nan

        if pd.notna(pct):
            st.write(
                f"- En **{label}**, la campaña con mayor acumulación fue **{max_row['Comparación']}** "
                f"con **{value_text(max_val, suffix)}**. La menor fue **{min_row['Comparación']}** "
                f"con **{value_text(min_val, suffix)}**. La diferencia fue de **{diff:.2f}{suffix}** "
                f"(**{pct:.1f} %** sobre la campaña menor)."
            )
        else:
            st.write(
                f"- En **{label}**, la campaña con mayor acumulación fue **{max_row['Comparación']}** "
                f"con **{value_text(max_val, suffix)}**. La menor fue **{min_row['Comparación']}** "
                f"con **{value_text(min_val, suffix)}**. La diferencia fue de **{diff:.2f}{suffix}**."
            )

    # Comparación par a par — tabla ancha con una columna por métrica
    st.markdown("#### Diferencias entre campañas")
    st.caption("Cada fila compara dos campañas. El signo indica si la segunda tuvo más (+) o menos (−) frío que la primera.")
    rows = []
    for i in range(len(cmp_df)):
        for j in range(i + 1, len(cmp_df)):
            a = cmp_df.iloc[i]
            b = cmp_df.iloc[j]
            row = {"Campaña A → B": f"{a.get('Comparación', a.get('Campaña frío', '?'))}  →  {b.get('Comparación', b.get('Campaña frío', '?'))}"}
            for col, label, suffix in variables:
                if col in cmp_df.columns and pd.notna(a.get(col, np.nan)) and pd.notna(b.get(col, np.nan)):
                    diff = b[col] - a[col]
                    row[f"Δ {label}"] = f"{diff:+.1f}{suffix}"
                else:
                    row[f"Δ {label}"] = "—"
            rows.append(row)

    if rows:
        _diff_df   = pd.DataFrame(rows).reset_index(drop=True)
        _diff_cols = list(_diff_df.columns)
        _d_th      = ("background:#1a2e1e;color:white;padding:8px 12px;"
                      "white-space:nowrap;font-weight:600;font-size:13px;")
        _d_ths     = "position:sticky;left:0;z-index:2;" + _d_th
        _d_hdr     = "".join(
            f'<th style="{_d_ths if i == 0 else _d_th}">{c}</th>'
            for i, c in enumerate(_diff_cols)
        )
        _d_body = ""
        for _, _r in _diff_df.iterrows():
            _cells = ""
            for _i, _c in enumerate(_diff_cols):
                _v    = str(_r[_c])
                # Verde suave si positivo, rojo suave si negativo (solo columnas Δ)
                if _i > 0 and _v.startswith("+"):
                    _cell_bg = "#e8f5e9"
                elif _i > 0 and _v.startswith("-"):
                    _cell_bg = "#ffebee"
                else:
                    _cell_bg = "#eef2ee" if _i == 0 else "white"
                _td = (f"{'position:sticky;left:0;z-index:1;' if _i == 0 else ''}"
                       f"background:{_cell_bg};padding:7px 12px;"
                       f"border-bottom:1px solid #e8e8e8;white-space:nowrap;font-size:13px;")
                _cells += f"<td style='{_td}'>{_v}</td>"
            _d_body += f"<tr>{_cells}</tr>"
        st.markdown(
            f'<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;'
            f'border-radius:8px;border:1px solid #ddd;margin-bottom:1rem;">'
            f'<table style="border-collapse:collapse;width:100%;">'
            f'<thead><tr>{_d_hdr}</tr></thead>'
            f'<tbody>{_d_body}</tbody>'
            f'</table></div>',
            unsafe_allow_html=True,
        )

    if monthly_df is not None and not monthly_df.empty:
        st.markdown("#### Meses que más aportaron frío")

        for model_col, label in [
            ("Horas frío <7 ºC", "horas <7 ºC"),
            ("Horas frío 0-7,2 ºC", "horas 0-7,2 ºC"),
            ("Utah Chill Units", "Utah Chill Units"),
            ("Chill Portions", "Chill Portions"),
        ]:
            if model_col not in monthly_df.columns:
                continue

            st.markdown(f"**Según {label}:**")
            lines = []
            group_col = "Campaña" if "Campaña" in monthly_df.columns else ("Campaña frío" if "Campaña frío" in monthly_df.columns else None)
            if group_col is None:
                st.info("No hay columna de campaña para resumir el desglose mensual.")
                continue
            for campaign, g in monthly_df.groupby(group_col):
                valid = g.dropna(subset=[model_col])
                if valid.empty:
                    lines.append(f"- **{campaign}**: sin datos mensuales suficientes.")
                    continue
                best = valid.loc[valid[model_col].idxmax()]
                lines.append(
                    f"- **{campaign}** acumuló más frío en **{best['Mes']}**, "
                    f"con **{value_text(best[model_col])}**."
                )
            st.markdown("\n".join(lines))

        st.markdown("#### Tabla mensual de frío")
        sort_cols = [c for c in ["Año análisis", "Mes orden", "Orden mes campaña"] if c in monthly_df.columns]
        monthly_show = monthly_df.sort_values(sort_cols).copy() if sort_cols else monthly_df.copy()

        # Columnas internas de orden → solo mostrar las relevantes
        _m_drop = [c for c in ["Campaña frío", "Año análisis", "Mes número",
                                "Orden mes campaña", "Mes orden"] if c in monthly_show.columns]
        monthly_show = monthly_show.drop(columns=_m_drop).reset_index(drop=True)

        # Campaña primera (sticky)
        if "Campaña" in monthly_show.columns:
            monthly_show = monthly_show[
                ["Campaña"] + [c for c in monthly_show.columns if c != "Campaña"]
            ]

        _m_cols = list(monthly_show.columns)
        _m_th   = ("background:#1a2e1e;color:white;padding:8px 12px;"
                   "white-space:nowrap;font-weight:600;font-size:13px;")
        _m_ths  = "position:sticky;left:0;z-index:2;" + _m_th
        _m_hdr  = "".join(
            f'<th style="{_m_ths if i == 0 else _m_th}">{c}</th>'
            for i, c in enumerate(_m_cols)
        )
        _m_body = ""
        for _, _r in monthly_show.iterrows():
            _cells = ""
            for _i, _c in enumerate(_m_cols):
                _v = _r[_c]
                _disp = (f"{_v:.1f}" if isinstance(_v, float) and not pd.isna(_v)
                         else ("—" if (isinstance(_v, float) and pd.isna(_v)) else str(_v)))
                _bg = "#eef2ee" if _i == 0 else "white"
                _td = (f"{'position:sticky;left:0;z-index:1;' if _i == 0 else ''}"
                       f"background:{_bg};padding:7px 12px;"
                       f"border-bottom:1px solid #e8e8e8;white-space:nowrap;font-size:13px;")
                _cells += f"<td style='{_td}'>{_disp}</td>"
            _m_body += f"<tr>{_cells}</tr>"
        st.markdown(
            f'<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;'
            f'border-radius:8px;border:1px solid #ddd;margin-bottom:1rem;">'
            f'<table style="border-collapse:collapse;width:100%;">'
            f'<thead><tr>{_m_hdr}</tr></thead>'
            f'<tbody>{_m_body}</tbody>'
            f'</table></div>',
            unsafe_allow_html=True,
        )




# Base limpia de campos revisada manualmente desde Agroptima.
FIELDS_BASE_ROWS = [
    {"Campo": "Campazón", "Superficie ha": 1.99, "Variedades actuales": "Durona de Tresali, Raxao, Regona"},
    {"Campo": "GY", "Superficie ha": 1.92, "Variedades actuales": "Amariega, Gallinal"},
    {"Campo": "Huertona", "Superficie ha": 0.80, "Variedades actuales": "Regona"},
    {"Campo": "Los Pinos 1", "Superficie ha": 0.80, "Variedades actuales": "Collaos, Raxona Dulce"},
    {"Campo": "Los Pinos 2", "Superficie ha": 0.68, "Variedades actuales": "Durona de Tresali, Regona"},
    {"Campo": "Los Pinos 3", "Superficie ha": 0.20, "Variedades actuales": "Carrió"},
    {"Campo": "Los Pinos 4", "Superficie ha": 0.52, "Variedades actuales": "Gallinal, Verdialona"},
    {"Campo": "Los Pinos 5", "Superficie ha": 0.74, "Variedades actuales": "Carrió, Collaos"},
    {"Campo": "Piedrona 1", "Superficie ha": 1.15, "Variedades actuales": "Durona de Tresali, Regona, Xuanina"},
    {"Campo": "Piedrona 2", "Superficie ha": 0.19, "Variedades actuales": "Madiedo"},
    {"Campo": "Piedrona Rincón", "Superficie ha": 1.68, "Variedades actuales": "Durona de Tresali, Regona"},
    {"Campo": "Sector 1", "Superficie ha": 1.06, "Variedades actuales": "De la Riega, Verdialona"},
    {"Campo": "Sector 10", "Superficie ha": 1.66, "Variedades actuales": "De la Riega, Verdialona"},
    {"Campo": "Sector 10-B", "Superficie ha": 0.72, "Variedades actuales": "Carrió"},
    {"Campo": "Sector 11", "Superficie ha": 1.43, "Variedades actuales": "Madiedo, Regona, Xuanina"},
    {"Campo": "Sector 12", "Superficie ha": 1.48, "Variedades actuales": "De la Riega, Verdialona, Xuanina"},
    {"Campo": "Sector 2", "Superficie ha": 0.87, "Variedades actuales": "Durona de Tresali, Raxao, Regona"},
    {"Campo": "Sector 3", "Superficie ha": 0.92, "Variedades actuales": "Durona de Tresali, Raxao, Regona"},
    {"Campo": "Sector 4", "Superficie ha": 1.77, "Variedades actuales": "Durona de Tresali, Raxao, Regona"},
    {"Campo": "Sector 5", "Superficie ha": 1.34, "Variedades actuales": "Durona de Tresali, Raxao, Regona"},
    {"Campo": "Sector 6", "Superficie ha": 1.97, "Variedades actuales": "Durona de Tresali, Regona, Verdialona, Xuanina"},
    {"Campo": "Sector 7", "Superficie ha": 0.34, "Variedades actuales": "Experimental"},
    {"Campo": "Sector 8", "Superficie ha": 0.77, "Variedades actuales": "Durona de Tresali"},
    {"Campo": "Sector 9", "Superficie ha": 0.31, "Variedades actuales": "Raxao"},
    {"Campo": "Viaducto", "Superficie ha": 1.19, "Variedades actuales": "De la Riega, Verdialona, Xuanina"},
]


def get_fields_base_df():
    return pd.DataFrame(FIELDS_BASE_ROWS)


def clean_agroptima_bullet_text(value):
    if pd.isna(value):
        return ""
    txt = str(value).replace("\r", "\n")
    parts = []
    for part in txt.split("\n"):
        part = part.strip()
        part = re.sub(r"^[·•\-\s]+", "", part).strip()
        if part:
            parts.append(part)
    return ", ".join(parts)


def extract_field_names_from_agroptima(value):
    if pd.isna(value):
        return []
    txt = str(value).replace("\r", "\n")
    names = []
    for part in txt.split("\n"):
        part = re.sub(r"^[·•\-\s]+", "", part).strip()
        if not part:
            continue
        part = re.sub(r"\s*\([0-9]+(?:[.,][0-9]+)?\s*ha\)\s*$", "", part).strip()
        if part:
            names.append(part)
    return names


def normalize_agroptima_columns(df):
    # Limpia nombres de columnas, saltos y espacios.
    out = df.copy()
    out.columns = [str(c).strip().replace("\n", " ") for c in out.columns]
    return out


def filter_only_fitosanitario(df):
    """Mantiene solo las filas cuyo Trabajo es un tratamiento fitosanitario.
    Descarta herbicidas, abonados, podas y cualquier otro trabajo, que no son
    relevantes para el análisis sanitario (carpocapsa, moteado, monilia…).
    Si no existe la columna Trabajo, devuelve el df sin tocar (no rompe nada)."""
    if df is None or df.empty:
        return df
    _col = "Trabajo" if "Trabajo" in df.columns else ("trabajo" if "trabajo" in df.columns else None)
    if _col is None:
        return df
    mask = df[_col].astype(str).str.contains("fitosanitario", case=False, na=False)
    return df[mask].reset_index(drop=True)


def detect_field_treatment_duplicates(df):
    """Detecta posibles duplicados de importación: un mismo CAMPO recibe el mismo
    PRODUCTO el mismo DÍA en más de un registro distinto (p. ej. una vez como
    aplicación combinada de varios campos y otra vez por separado, por haber
    editado la actuación en Agroptima y reimportar).

    No borra nada: solo devuelve un resumen para avisar al usuario.
    Devuelve un DataFrame con columnas Campo, Producto, Fecha, "Aparece en",
    "Nº registros" (vacío si no hay duplicados)."""
    if df is None or df.empty:
        return pd.DataFrame()
    _campos_col = "Campos reconocidos" if "Campos reconocidos" in df.columns else (
                  "Campos" if "Campos" in df.columns else None)
    if _campos_col is None or "Producto" not in df.columns or "Fecha" not in df.columns:
        return pd.DataFrame()

    exp = []
    for _, r in df.iterrows():
        fecha = str(r.get("Fecha", "")).strip()
        prod  = str(r.get("Producto", "")).strip()
        campos_reg = str(r.get(_campos_col, "") or "")
        if not fecha or not prod or prod.lower() == "nan":
            continue
        for campo in [c.strip() for c in campos_reg.split(",") if c.strip()]:
            exp.append({
                "Campo": campo, "Producto": prod, "Fecha": fecha,
                "_registro": campos_reg.strip(),
            })
    if not exp:
        return pd.DataFrame()

    ex = pd.DataFrame(exp)
    out = []
    for (campo, prod, fecha), g in ex.groupby(["Campo", "Producto", "Fecha"]):
        # Duplicado real solo si proviene de registros DISTINTOS (combinada vs suelta)
        registros = sorted(g["_registro"].unique())
        if len(registros) > 1:
            out.append({
                "Campo": campo, "Producto": prod, "Fecha": fecha,
                "Aparece en": "  ·  ".join(registros),
                "Nº registros": len(registros),
            })
    if not out:
        return pd.DataFrame()
    return pd.DataFrame(out).sort_values(["Fecha", "Campo", "Producto"]).reset_index(drop=True)


def parse_agroptima_activities_excel(uploaded_file):
    """Lee un Excel de actividades de Agroptima y lo convierte a tabla limpia."""
    if uploaded_file is None:
        return pd.DataFrame(), [], {}

    diagnostics = {
        "Hojas detectadas": "",
        "Columnas detectadas": "",
        "Registros leídos": 0,
    }
    warnings = []

    try:
        file_name = getattr(uploaded_file, "name", "").lower()
        diagnostics["Archivo recibido"] = getattr(uploaded_file, "name", "")

        # CSV opcional, por si en el futuro se sube el histórico limpio descargado.
        if file_name.endswith(".csv"):
            raw = pd.read_csv(uploaded_file)
            diagnostics["Hojas detectadas"] = "CSV"
        else:
            # Los archivos .xlsx/.xlsm necesitan openpyxl. Está declarado en requirements.txt.
            # Forzamos openpyxl para xlsx/xlsm. Si el archivo es un .xls antiguo real, se avisará.
            excel = pd.ExcelFile(uploaded_file, engine="openpyxl")
            diagnostics["Hojas detectadas"] = ", ".join(excel.sheet_names)
            sheet = "Actividades" if "Actividades" in excel.sheet_names else excel.sheet_names[0]
            raw = pd.read_excel(excel, sheet_name=sheet)
    except ImportError:
        return pd.DataFrame(), [
            "No se pudo leer el Excel porque falta la librería openpyxl. "
            "Vuelve a desplegar la app asegurándote de subir también requirements.txt, "
            "o reinicia el despliegue para que instale openpyxl."
        ], diagnostics
    except Exception as e:
        return pd.DataFrame(), [
            f"No se pudo leer el archivo de Agroptima: {e}. "
            "Comprueba que sea el Excel original exportado por Agroptima. "
            "Si el archivo tiene extensión .xls antigua, prueba a abrirlo en Excel y guardarlo como .xlsx."
        ], diagnostics

    raw = normalize_agroptima_columns(raw)
    diagnostics["Columnas detectadas"] = ", ".join(list(raw.columns))
    diagnostics["Registros leídos"] = int(len(raw))

    # Agroptima exporta actividades multi-producto con filas de continuación:
    # la primera fila tiene Fecha+Campos etc., las siguientes solo tienen el producto
    # con None/NaN en esos campos. Forward-fill propaga el contexto de actividad
    # a todas las filas del mismo tratamiento.
    # IMPORTANTE: NO ffill la columna "ID" — cada producto continúa en su propia
    # fila de continuación sin ID (None). Si se ffill el ID, ambas filas (FLINT y
    # BACTUR) tendrían el mismo "ID Agroptima" y la deduplicación en
    # merge_activities_history descartaría una de ellas (normalmente la primera).
    _ACTIVITY_FILL_COLS = [
        "Fecha", "Campos", "ha totales", "Trabajos",
        "Cultivos / variedades", "Personal", "Cuadrillas",
        "Personal Externo", "Máquinas", "Comentarios",
        # "ID" excluido intencionalmente — ver nota arriba
    ]
    for _col in _ACTIVITY_FILL_COLS:
        if _col in raw.columns:
            raw[_col] = raw[_col].ffill()

    required = ["Fecha", "Campos", "ha totales", "Trabajos", "Productos", "Cantidad", "Unidades de la cantidad", "Dosis o rendimiento", "Unidades de dosis", "Comentarios"]
    for col in required:
        if col not in raw.columns:
            warnings.append(f"No se encontró la columna esperada: {col}")

    rows = []
    valid_fields = set(get_fields_base_df()["Campo"].tolist())

    for _, r in raw.iterrows():
        fecha = pd.to_datetime(r.get("Fecha", pd.NaT), errors="coerce")
        campos = extract_field_names_from_agroptima(r.get("Campos", ""))
        campos_reconocidos = [c for c in campos if c in valid_fields]
        campos_no_reconocidos = [c for c in campos if c not in valid_fields]

        productos = clean_agroptima_bullet_text(r.get("Productos", ""))
        trabajos = clean_agroptima_bullet_text(r.get("Trabajos", ""))
        maquinas = clean_agroptima_bullet_text(r.get("Máquinas", ""))
        personal = clean_agroptima_bullet_text(r.get("Personal", ""))
        cultivos = clean_agroptima_bullet_text(r.get("Cultivos / variedades", ""))
        comentarios = clean_agroptima_bullet_text(r.get("Comentarios", ""))

        cantidad = pd.to_numeric(r.get("Cantidad", np.nan), errors="coerce")
        dosis = pd.to_numeric(r.get("Dosis o rendimiento", np.nan), errors="coerce")
        sup = pd.to_numeric(r.get("ha totales", np.nan), errors="coerce")

        rows.append({
            "Fecha": fecha.date().isoformat() if pd.notna(fecha) else "",
            "Campos": ", ".join(campos),
            "Campos reconocidos": ", ".join(campos_reconocidos),
            "Campos no reconocidos": ", ".join(campos_no_reconocidos),
            "Superficie tratada ha": round(float(sup), 4) if pd.notna(sup) else np.nan,
            "Trabajo": trabajos,
            "Producto": productos,
            "Cantidad": round(float(cantidad), 4) if pd.notna(cantidad) else np.nan,
            "Unidad cantidad": r.get("Unidades de la cantidad", ""),
            "Dosis": round(float(dosis), 4) if pd.notna(dosis) else np.nan,
            "Unidad dosis": r.get("Unidades de dosis", ""),
            "Cultivos / variedades Agroptima": cultivos,
            "Personal": personal,
            "Máquinas": maquinas,
            "Comentarios": comentarios,
            "ID Agroptima": r.get("ID", ""),
        })

    clean = pd.DataFrame(rows)

    # ── Filtrar SOLO tratamientos fitosanitarios ──────────────────────────────
    # No interesan herbicidas, abonados, podas, etc. para el análisis sanitario.
    clean = filter_only_fitosanitario(clean)

    if not clean.empty:
        clean = clean.sort_values(["Fecha", "Campos"], ascending=[False, True]).reset_index(drop=True)

    return clean, warnings, diagnostics


def fields_tab():
    st.subheader("Campos / parcelas")

    fields_df = get_fields_base_df()
    st.info("Base de campos limpia revisada desde Agroptima. Se han eliminado Sector 13, Mayador Oles y Faba 2023. Sector 7 queda como variedad Experimental.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Campos activos", len(fields_df))
    c2.metric("Superficie total", f"{fields_df['Superficie ha'].sum():.2f} ha")
    c3.metric("Variedades distintas", len(sorted({v.strip() for txt in fields_df["Variedades actuales"] for v in str(txt).split(",") if v.strip()})))

    st.dataframe(fields_df, use_container_width=True)

    st.download_button(
        "Descargar base limpia de campos",
        data=fields_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="campos_finca_gallinal_limpios.csv",
        mime="text/csv",
    )




ACTIVITY_COLUMNS = [
    "Fecha",
    "Campos",
    "Campos reconocidos",
    "Campos no reconocidos",
    "Superficie tratada ha",
    "Trabajo",
    "Producto",
    "Cantidad",
    "Unidad cantidad",
    "Dosis",
    "Unidad dosis",
    "Cultivos / variedades Agroptima",
    "Personal",
    "Máquinas",
    "Comentarios",
    "ID Agroptima",
]


def normalize_activities_df(df):
    """Normaliza una tabla de actuaciones para evitar duplicados y ordenar fechas."""
    if df is None:
        df = pd.DataFrame(columns=ACTIVITY_COLUMNS)

    out = df.copy()

    for col in ACTIVITY_COLUMNS:
        if col not in out.columns:
            out[col] = ""

    out = out[ACTIVITY_COLUMNS].copy()

    # Aunque el histórico esté vacío, creamos siempre las columnas internas.
    if out.empty:
        out["_clave_fallback"] = pd.Series(dtype="object")
        out["_clave_importacion"] = pd.Series(dtype="object")
        return out

    out["Fecha"] = pd.to_datetime(out["Fecha"], errors="coerce").dt.date.astype(str)
    out["ID Agroptima"] = out["ID Agroptima"].astype(str).str.strip()
    out["ID Agroptima"] = out["ID Agroptima"].replace({"nan": "", "None": "", "<NA>": ""})

    numeric_cols = ["Superficie tratada ha", "Cantidad", "Dosis"]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    # Clave alternativa para casos sin ID Agroptima real.
    # Incluye Cantidad además de Superficie/Dosis para distinguir productos
    # distintos de la misma mezcla con misma dosis pero distinta cantidad.
    # IMPORTANTE: conversión robusta a NaN. En pandas, `serie_float.round(4).astype(str)`
    # puede dejar el NaN como float, y al concatenar `"a|" + NaN = NaN`, colapsando
    # TODA la clave a "nan". Eso haría que todas las filas con cantidad/dosis vacía
    # compartieran la misma clave y se fusionaran (pérdida de tratamientos). Por eso
    # convertimos cada componente a cadena de forma segura (NaN → "").
    def _num_key(series):
        s = pd.to_numeric(series, errors="coerce")
        return s.map(lambda x: "" if pd.isna(x) else str(round(float(x), 4)))

    def _txt_key(series):
        return series.fillna("").astype(str).str.strip()

    out["_clave_fallback"] = (
        _txt_key(out["Fecha"]) + "|" +
        _txt_key(out["Campos"]) + "|" +
        _txt_key(out["Producto"]) + "|" +
        _num_key(out["Superficie tratada ha"]) + "|" +
        _num_key(out["Cantidad"]) + "|" +
        _num_key(out["Dosis"])
    )

    # ID "real" = tiene contenido y NO es un id sintético (los sintéticos
    # empiezan por "FB:" y se generan para las filas de continuación sin ID).
    _id_str = out["ID Agroptima"].astype(str).str.strip()
    _is_real_id = (_id_str.str.len() > 0) & (~_id_str.str.startswith("FB:"))

    # Si hay ID real, manda el ID. Si no (vacío o sintético), usa clave alternativa.
    # Así una fila de continuación guardada con id sintético "FB:<clave>" y una
    # versión antigua sin id (id vacío) colapsan a la MISMA _clave_importacion,
    # evitando duplicados en pantalla y en los cálculos.
    out["_clave_importacion"] = np.where(
        _is_real_id,
        "ID:" + _id_str,
        "FB:" + out["_clave_fallback"].astype(str),
    )

    # Deduplicación dura por clave de importación (ID exacto o FB exacto).
    out = out.drop_duplicates(subset=["_clave_importacion"], keep="first")

    # Deduplicación por CONTENIDO. Dos filas que describen el MISMO tratamiento
    # (misma fecha, campo, producto, superficie, cantidad y dosis) son la misma
    # aplicación aunque su ID esté en formatos distintos:
    #   · ID numérico float vs int  → "4350677.0" y "4350677"
    #   · ID compuesto heredado     → "3977680.0" y "3977680.0|BACTUR 2X (19856)"
    #   · ID real frente a sintético → "4402039" y "FB:2026-06-01|Sector 1|FLINT…"
    # Como la clave de contenido incluye el PRODUCTO, los productos distintos de
    # una misma mezcla (p. ej. BACTUR + FLINT) NUNCA se fusionan: solo se elimina
    # el verdadero duplicado. Se conserva la fila con ID real (no sintético).
    _id_norm = out["ID Agroptima"].astype(str).str.strip()
    out["_tiene_id_real"] = (_id_norm.str.len() > 0) & (~_id_norm.str.startswith("FB:"))
    out = (
        out.sort_values("_tiene_id_real", ascending=False, kind="stable")
           .drop_duplicates(subset=["_clave_fallback"], keep="first")
           .drop(columns=["_tiene_id_real"])
    )

    out = out.sort_values(["Fecha", "_clave_importacion"], ascending=[False, True]).reset_index(drop=True)
    return out


def merge_activities_history(existing_df, new_df, mode):
    """
    Fusiona actuaciones existentes con nuevas.
    mode:
    - replace
    - append_new
    - update_by_id
    """
    existing = normalize_activities_df(existing_df)
    new = normalize_activities_df(new_df)

    before = len(existing)
    incoming = len(new)

    if new.empty:
        return existing.drop(columns=[c for c in ["_clave_fallback", "_clave_importacion"] if c in existing.columns]), {
            "Registros antes": before,
            "Registros en Excel": incoming,
            "Registros después": before,
            "Nuevas añadidas": 0,
            "Actualizadas/reemplazadas": 0,
            "Duplicadas ignoradas": 0,
            "Modo": mode,
        }

    if mode == "replace":
        merged = new.copy()
        added = len(merged)
        updated = 0
        ignored = 0

    elif mode == "append_new":
        existing_keys = set(existing["_clave_importacion"].astype(str))
        to_add = new[~new["_clave_importacion"].astype(str).isin(existing_keys)].copy()
        merged = pd.concat([existing, to_add], ignore_index=True)
        added = len(to_add)
        updated = 0
        ignored = incoming - added

    else:  # update_by_id
        # Base primero y Excel nuevo después: si coincide clave, queda la fila nueva.
        combined = pd.concat([existing, new], ignore_index=True)
        duplicated_existing_keys = set(existing["_clave_importacion"].astype(str)).intersection(
            set(new["_clave_importacion"].astype(str))
        )
        merged = combined.drop_duplicates(subset=["_clave_importacion"], keep="last").copy()
        added = int(incoming - len(duplicated_existing_keys))
        updated = int(len(duplicated_existing_keys))
        ignored = 0

    merged = normalize_activities_df(merged)
    after = len(merged)

    stats = {
        "Registros antes": int(before),
        "Registros en Excel": int(incoming),
        "Registros después": int(after),
        "Nuevas añadidas": int(max(added, 0)),
        "Actualizadas/reemplazadas": int(max(updated, 0)),
        "Duplicadas ignoradas": int(max(ignored, 0)),
        "Modo": mode,
    }

    clean = merged.drop(columns=[c for c in ["_clave_fallback", "_clave_importacion"] if c in merged.columns])
    return clean, stats




# Catálogo de productos específicos para carpocapsa
# Separado del catálogo de fungicidas para no mezclarlos
CARPOCAPSA_PRODUCTS_CATALOG = {
    "Bactur": {
        "aliases": ["bactur", "bacillus thuringiensis", "bt ", "b.t.", "bactur 2x", "bactur 2"],
        "tipo": "Biológico - Bt",
        "materia_activa": "Bacillus thuringiensis var. kurstaki",
        "comentario": "Biológico, actúa por ingestión. Ventana de acción 3-5 días. Sensible a lluvia.",
    },
    "Madex": {
        "aliases": ["madex", "granulosis", "granulovirus", "cydia pomonella granulovirus", "cpgv"],
        "tipo": "Biológico - Virus",
        "materia_activa": "Cydia pomonella Granulovirus",
        "comentario": "Virus específico de carpocapsa. Muy selectivo. Sensible a luz UV y lluvia.",
    },
    "Coragen": {
        "aliases": ["coragen", "chlorantraniliprole", "clorantraniliprole"],
        "tipo": "Diamida",
        "materia_activa": "Clorantraniliprol",
        "comentario": "Diamida. Acción por contacto e ingestión. Buena persistencia.",
    },
    "Calypso": {
        "aliases": ["calypso", "thiacloprid", "tiacloprid"],
        "tipo": "Neonicotinoide",
        "materia_activa": "Tiacloprid",
        "comentario": "Neonicotinoide. Acción sistémica.",
    },
    "Exirel": {
        "aliases": ["exirel", "cyantraniliprole", "ciantraniliprol"],
        "tipo": "Diamida",
        "materia_activa": "Ciantraniliprol",
        "comentario": "Diamida de nueva generación.",
    },
}

# Abonos y otros productos que pueden aparecer mezclados — no son ni fungicidas ni carpocapsa
FOLIAR_NUTRITION_KEYWORDS = [
    "stimulan", "stimulan k", "abono", "fertilizante", "aminoacid",
    "calcio", "magnesio", "potasio foliar", "boro", "zinc",
    "nutricion", "nutrición", "micronutriente",
]

CARPOCAPSA_TREATMENT_KEYWORDS = [
    # Específicos de carpocapsa
    "carpocapsa", "codling moth", "cydia pomonella", "cydia",
    "tratamiento carpocapsa",
    # Productos biológicos selectivos de lepidópteros
    "bactur", "bacillus thuringiensis", "bt var. kurstaki",
    "madex", "granulosis", "granulovirus", "cpgv", "xentari", "dipel",
    # Materias activas insecticidas usadas principalmente para carpocapsa
    "clorpirifos", "chlorpyrifos", "fosmet", "phosmet",
    "indoxacarb", "spinetoram", "spinosad",
    "lambdacialotrina", "lambda-cyhalothrin",
    "deltametrina", "deltamethrin",
    # "insecticida" eliminado — demasiado genérico, capturaba cualquier spray
]


def text_contains_any_keyword(text, keywords):
    """Devuelve True si el texto contiene alguna de las palabras clave (insensible a mayúsculas)."""
    if not isinstance(text, str):
        return False
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def classify_product(product_str):
    """
    Clasifica un producto como 'carpocapsa', 'fungicida', 'abono' o 'otro'.
    Evalua cada producto de la mezcla individualmente.
    """
    if not isinstance(product_str, str) or not product_str.strip():
        return "otro"
    p = product_str.lower()
    # Primero comprobar carpocapsa (más específico)
    for prod_name, prod_data in CARPOCAPSA_PRODUCTS_CATALOG.items():
        if any(alias in p for alias in prod_data["aliases"]):
            return "carpocapsa"
    # Comprobar abonos foliares
    if text_contains_any_keyword(p, FOLIAR_NUTRITION_KEYWORDS):
        return "abono"
    # Comprobar fungicidas del catálogo
    catalog = get_treatment_product_catalog()
    for prod_name, prod_data in catalog.items():
        if any(alias in p for alias in prod_data.get("aliases", [])):
            return "fungicida"
    # Palabras clave generales de carpocapsa
    if text_contains_any_keyword(p, CARPOCAPSA_TREATMENT_KEYWORDS):
        return "carpocapsa"
    return "otro"


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

def render_activities_summaries(activities_df):
    if activities_df is None or activities_df.empty:
        st.info("Todavía no hay actuaciones en el histórico.")
        return

    df = normalize_activities_df(activities_df)
    visible = df.drop(columns=[c for c in ["_clave_fallback", "_clave_importacion"] if c in df.columns])

    known = visible["Campos reconocidos"].fillna("").str.len() > 0
    unknown = visible["Campos no reconocidos"].fillna("").str.len() > 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Actuaciones histórico", len(visible))
    c2.metric("Con campo reconocido", int(known.sum()))
    c3.metric("Con campo no reconocido", int(unknown.sum()))
    c4.metric("Productos detectados", visible["Producto"].replace("", np.nan).dropna().nunique())

    fechas = pd.to_datetime(visible["Fecha"], errors="coerce").dropna()
    if not fechas.empty:
        st.caption(f"Rango de fechas del histórico: {fechas.min().date()} → {fechas.max().date()}")

    # ── Aviso de posibles duplicados (no destructivo) ─────────────────────────
    _dups = detect_field_treatment_duplicates(visible)
    if not _dups.empty:
        _n = len(_dups)
        st.warning(
            f"⚠️ Detectados **{_n} posible(s) duplicado(s)**: un mismo campo recibe el "
            f"mismo producto el mismo día en varios registros (suele pasar al editar "
            f"una actuación en Agroptima — combinarla/separarla — y reimportar). "
            f"No afecta a los cálculos (los pases se deduplican automáticamente), pero "
            f"puedes corregirlo en Agroptima y reimportar si quieres dejarlo limpio."
        )
        with st.expander(f"Ver los {_n} posibles duplicados", expanded=False):
            st.dataframe(_dups, use_container_width=True, hide_index=True)

    st.markdown("#### Histórico de actuaciones")
    st.dataframe(visible, use_container_width=True)

    st.download_button(
        "Descargar histórico maestro de actuaciones",
        data=visible.to_csv(index=False).encode("utf-8-sig"),
        file_name="historico_actuaciones_agroptima.csv",
        mime="text/csv",
    )

    st.markdown("#### Productos detectados")
    product_summary = (
        visible.groupby("Producto", dropna=False)
        .agg(
            Actividades=("Producto", "size"),
            Superficie_tratada_ha=("Superficie tratada ha", "sum"),
            Primera_fecha=("Fecha", "min"),
            Ultima_fecha=("Fecha", "max"),
        )
        .reset_index()
    )
    st.dataframe(product_summary, use_container_width=True)

    st.markdown("#### Último tratamiento por campo reconocido")
    expanded_rows = []
    for _, row in visible.iterrows():
        for campo in [c.strip() for c in str(row.get("Campos reconocidos", "")).split(",") if c.strip()]:
            expanded_rows.append({
                "Campo": campo,
                "Última fecha": row.get("Fecha", ""),
                "Producto": row.get("Producto", ""),
                "Trabajo": row.get("Trabajo", ""),
                "Superficie tratada ha": row.get("Superficie tratada ha", np.nan),
                "Comentarios": row.get("Comentarios", ""),
            })

    if expanded_rows:
        expanded = pd.DataFrame(expanded_rows)
        expanded["Fecha orden"] = pd.to_datetime(expanded["Última fecha"], errors="coerce")
        last_by_field = expanded.sort_values("Fecha orden").groupby("Campo", as_index=False).tail(1)
        last_by_field = last_by_field.drop(columns=["Fecha orden"]).sort_values("Campo")
        st.dataframe(last_by_field, use_container_width=True)
    else:
        st.info("No se han reconocido campos contra la base limpia.")

    not_recognized = sorted({
        c.strip()
        for txt in visible["Campos no reconocidos"].fillna("")
        for c in str(txt).split(",")
        if c.strip()
    })
    if not_recognized:
        st.warning("Campos no reconocidos frente a la base limpia:")
        for c in not_recognized:
            st.write(f"- {c}")
    else:
        st.success("Todos los campos del histórico se reconocen contra la base limpia.")



def coverage_advice_from_post_treatment(rain_mm, max_scab_ratio, max_monilia_ratio, days_since):
    """Aviso orientativo simple según lluvia/eventos posteriores al último tratamiento."""
    rain_mm = 0.0 if pd.isna(rain_mm) else float(rain_mm)
    max_scab_ratio = 0.0 if pd.isna(max_scab_ratio) else float(max_scab_ratio)
    max_monilia_ratio = 0.0 if pd.isna(max_monilia_ratio) else float(max_monilia_ratio)
    max_ratio = max(max_scab_ratio, max_monilia_ratio)

    if max_ratio >= 1.5 and rain_mm >= 10:
        return "Priorizar revisión: evento sanitario fuerte posterior y lluvia acumulada relevante."
    if max_ratio >= 1.0 and rain_mm >= 5:
        return "Revisar cobertura: hubo evento compatible con infección después del tratamiento."
    if max_ratio >= 1.0:
        return "Vigilar: hubo evento sanitario posterior, aunque la lluvia acumulada no es alta."
    if rain_mm >= 20:
        return "Revisar cobertura por lluvia acumulada posterior al tratamiento."
    if days_since is not None and days_since >= 10 and rain_mm >= 10:
        return "Revisar evolución: han pasado varios días y hay lluvia acumulada."
    return "Seguimiento normal: no se detectan eventos críticos posteriores en los datos cargados."


def build_treatment_sanitary_cross(history_df, activities_df, soil_type=None, hoja_threshold=None):
    """
    Cruza último tratamiento reconocido por campo con lluvia y eventos sanitarios posteriores.
    Usa el histórico climático general como referencia para todos los campos.
    """
    if activities_df is None or activities_df.empty:
        return pd.DataFrame()
    if history_df is None or history_df.empty:
        return pd.DataFrame()

    acts = normalize_activities_df(activities_df)
    acts_visible = acts.drop(columns=[c for c in ["_clave_fallback", "_clave_importacion"] if c in acts.columns]).copy()
    hist = history_df.copy()
    hist["fecha_hora"] = pd.to_datetime(hist["fecha_hora"], errors="coerce")
    hist = hist.dropna(subset=["fecha_hora"]).sort_values("fecha_hora")

    if hist.empty:
        return pd.DataFrame()

    expanded = []
    for _, row in acts_visible.iterrows():
        fecha = pd.to_datetime(row.get("Fecha", ""), errors="coerce")
        if pd.isna(fecha):
            continue
        for campo in [c.strip() for c in str(row.get("Campos reconocidos", "")).split(",") if c.strip()]:
            expanded.append({
                "Campo": campo,
                "Fecha tratamiento": fecha,
                "Producto": row.get("Producto", ""),
                "Trabajo": row.get("Trabajo", ""),
                "Superficie tratada ha": row.get("Superficie tratada ha", np.nan),
                "Dosis": row.get("Dosis", np.nan),
                "Unidad dosis": row.get("Unidad dosis", ""),
                "Comentarios tratamiento": row.get("Comentarios", ""),
                "Variedades tratadas": row.get("Cultivos / variedades Agroptima", "") or row.get("Variedades", "") or "",
                "ID Agroptima": row.get("ID Agroptima", ""),
            })

    if not expanded:
        return pd.DataFrame()

    exp = pd.DataFrame(expanded)
    exp = exp.sort_values("Fecha tratamiento")
    last = exp.groupby("Campo", as_index=False).tail(1).copy()

    rows = []
    hist_end = hist["fecha_hora"].max()

    for _, tr in last.iterrows():
        fecha_tr = pd.to_datetime(tr["Fecha tratamiento"], errors="coerce")
        if pd.isna(fecha_tr):
            continue

        # Como Agroptima no da hora, tomamos la fecha desde las 00:00 como aproximación.
        after = hist[hist["fecha_hora"] >= fecha_tr].copy()
        rain_after = pd.to_numeric(after.get("lluvia_mm", 0), errors="coerce").fillna(0).sum() if not after.empty else 0.0

        if has_sensor(after, "Humectación de hoja"):
            events = detect_leaf_wetness_events(after)
        else:
            events = pd.DataFrame()

        if not events.empty:
            events_after = events[pd.to_datetime(events["Inicio"], errors="coerce") >= fecha_tr].copy()
        else:
            events_after = pd.DataFrame()

        if events_after.empty:
            num_events = 0
            max_scab = 0.0
            max_monilia = 0.0
            events_scab_ge1 = 0
            events_monilia_ge1 = 0
            first_event = ""
            worst_event = ""
        else:
            num_events = len(events_after)
            max_scab = pd.to_numeric(events_after.get("Ratio moteado", 0), errors="coerce").fillna(0).max()
            max_monilia = pd.to_numeric(events_after.get("Ratio monilia", 0), errors="coerce").fillna(0).max()
            events_scab_ge1 = int((pd.to_numeric(events_after.get("Ratio moteado", 0), errors="coerce").fillna(0) >= 1.0).sum())
            events_monilia_ge1 = int((pd.to_numeric(events_after.get("Ratio monilia", 0), errors="coerce").fillna(0) >= 1.0).sum())

            first_dt = pd.to_datetime(events_after["Inicio"], errors="coerce").min()
            first_event = first_dt.strftime("%Y-%m-%d %H:%M") if pd.notna(first_dt) else ""

            events_after["_max_ratio"] = pd.concat([
                pd.to_numeric(events_after.get("Ratio moteado", 0), errors="coerce").fillna(0),
                pd.to_numeric(events_after.get("Ratio monilia", 0), errors="coerce").fillna(0),
            ], axis=1).max(axis=1)
            worst = events_after.sort_values("_max_ratio").tail(1).iloc[0]
            worst_dt = pd.to_datetime(worst.get("Inicio", pd.NaT), errors="coerce")
            worst_event = (
                f"{worst_dt.strftime('%Y-%m-%d %H:%M') if pd.notna(worst_dt) else ''} · "
                f"moteado {worst.get('Ratio moteado', 0)} · monilia {worst.get('Ratio monilia', 0)}"
            )

        days_since = int((hist_end.normalize() - fecha_tr.normalize()).days) if pd.notna(hist_end) else None
        advice = coverage_advice_from_post_treatment(rain_after, max_scab, max_monilia, days_since)

        rows.append({
            "Campo": tr["Campo"],
            "Último tratamiento": fecha_tr.date().isoformat(),
            "Días hasta último dato climático": days_since,
            "Producto": tr.get("Producto", ""),
            "Variedades tratadas": tr.get("Variedades tratadas", "") or "Agroptima no especifica variedad; revisar si fue campo completo o parcial.",
            "Superficie tratada ha": tr.get("Superficie tratada ha", np.nan),
            "Dosis": tr.get("Dosis", np.nan),
            "Unidad dosis": tr.get("Unidad dosis", ""),
            "Lluvia posterior mm": round(float(rain_after), 1),
            "Eventos hoja mojada posteriores": int(num_events),
            "Eventos moteado ratio >= 1": int(events_scab_ge1),
            "Eventos monilia ratio >= 1": int(events_monilia_ge1),
            "Máx ratio moteado posterior": round(float(max_scab), 2),
            "Máx ratio monilia posterior": round(float(max_monilia), 2),
            "Primer evento posterior": first_event,
            "Evento más crítico posterior": worst_event,
            "Aviso orientativo": advice,
            "ID Agroptima": tr.get("ID Agroptima", ""),
        })

    return pd.DataFrame(rows).sort_values(["Aviso orientativo", "Campo"]).reset_index(drop=True)


def render_treatment_sanitary_cross():
    st.markdown("#### Cruce tratamientos + riesgo sanitario")

    history_df = st.session_state.get("history_df", pd.DataFrame(columns=CANONICAL_COLUMNS))
    activities_df = st.session_state.get("activities_df", pd.DataFrame(columns=ACTIVITY_COLUMNS))

    if history_df.empty:
        st.info("Carga primero el histórico climático para calcular lluvia y eventos posteriores al tratamiento.")
        return
    if activities_df.empty:
        st.info("Importa primero el histórico de actuaciones de Agroptima.")
        return

    cross = build_treatment_sanitary_cross(history_df, activities_df)
    if cross.empty:
        st.warning("No se ha podido cruzar tratamientos con sanidad. Revisa que las actuaciones tengan campos reconocidos y fechas válidas.")
        return

    st.caption(
        "El cruce usa el clima registrado como referencia general para todos los campos. "
        "Como Agroptima no aporta hora del tratamiento, la lluvia y los eventos se calculan desde la fecha del tratamiento."
    )

    critical = cross[cross["Aviso orientativo"].str.contains("Priorizar|Revisar", case=False, na=False)]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Campos con tratamiento", len(cross))
    c2.metric("Campos con aviso revisar/priorizar", len(critical))
    c3.metric("Máx lluvia posterior", f"{cross['Lluvia posterior mm'].max():.1f} mm")
    c4.metric("Máx ratio posterior", f"{max(cross['Máx ratio moteado posterior'].max(), cross['Máx ratio monilia posterior'].max()):.2f}")

    st.dataframe(cross, use_container_width=True)

    st.download_button(
        "Descargar cruce tratamientos-riesgo sanitario",
        data=cross.to_csv(index=False).encode("utf-8-sig"),
        file_name="cruce_tratamientos_riesgo_sanitario.csv",
        mime="text/csv",
    )

    with st.expander("Lectura rápida por campo", expanded=True):
        for _, row in cross.iterrows():
            st.markdown(
                f"**{row['Campo']}** · último tratamiento: **{row['Último tratamiento']}** "
                f"con **{row['Producto']}**. "
                f"Lluvia posterior: **{row['Lluvia posterior mm']} mm**. "
                f"Máx ratio moteado: **{row['Máx ratio moteado posterior']}**; "
                f"máx ratio monilia: **{row['Máx ratio monilia posterior']}**. "
                f"**{row['Aviso orientativo']}**"
            )




def advisory_priority_label(text):
    """Convierte el aviso orientativo en una prioridad sencilla."""
    txt = str(text or "").lower()
    if "priorizar" in txt:
        return "Alta"
    if "revisar" in txt:
        return "Media-alta"
    if "vigilar" in txt:
        return "Media"
    return "Baja"


def render_field_sanitary_report():
    st.markdown("#### Informe sanitario por campo")

    history_df = st.session_state.get("history_df", pd.DataFrame(columns=CANONICAL_COLUMNS))
    activities_df = st.session_state.get("activities_df", pd.DataFrame(columns=ACTIVITY_COLUMNS))

    if history_df.empty:
        st.info("Carga primero el histórico climático para generar el informe sanitario por campo.")
        return
    if activities_df.empty:
        st.info("Importa primero el histórico de actuaciones de Agroptima.")
        return

    cross = build_treatment_sanitary_cross(history_df, activities_df)
    if cross.empty:
        st.warning("No hay datos suficientes para generar el informe por campo.")
        return

    fields_df = get_fields_base_df()
    if fields_df is not None and not fields_df.empty and "Campo" in fields_df.columns:
        all_fields = fields_df["Campo"].dropna().astype(str).unique().tolist()
        treated_fields = set(cross["Campo"].dropna().astype(str).tolist())
        missing_fields = [f for f in all_fields if f not in treated_fields]
        if missing_fields:
            extra_rows = []
            for f in missing_fields:
                extra_rows.append({
                    "Campo": f,
                    "Último tratamiento": "Sin tratamiento registrado",
                    "Días hasta último dato climático": np.nan,
                    "Producto": "Sin tratamiento registrado",
                    "Variedades tratadas": "Sin tratamiento registrado",
                    "Superficie tratada ha": np.nan,
                    "Dosis": np.nan,
                    "Unidad dosis": "",
                    "Lluvia posterior mm": 0.0,
                    "Eventos hoja mojada posteriores": 0,
                    "Eventos moteado ratio >= 1": 0,
                    "Eventos monilia ratio >= 1": 0,
                    "Máx ratio moteado posterior": 0.0,
                    "Máx ratio monilia posterior": 0.0,
                    "Primer evento posterior": "",
                    "Evento más crítico posterior": "",
                    "Aviso orientativo": "Priorizar revisión si el periodo climático ha sido desfavorable: campo sin tratamiento registrado en Agroptima.",
                    "ID Agroptima": "",
                })
            cross = pd.concat([cross, pd.DataFrame(extra_rows)], ignore_index=True)
        cross = cross.merge(fields_df, on="Campo", how="left")
    cross["Prioridad"] = cross["Aviso orientativo"].apply(advisory_priority_label)
    cross["Días hasta último dato climático"] = pd.to_numeric(
        cross["Días hasta último dato climático"], errors="coerce"
    )
    cross["Lluvia posterior mm"] = pd.to_numeric(cross["Lluvia posterior mm"], errors="coerce").fillna(0)
    cross["Máx ratio moteado posterior"] = pd.to_numeric(cross["Máx ratio moteado posterior"], errors="coerce").fillna(0)
    cross["Máx ratio monilia posterior"] = pd.to_numeric(cross["Máx ratio monilia posterior"], errors="coerce").fillna(0)

    st.caption(
        "Vista rápida para priorizar revisión de campos. Usa el último tratamiento reconocido por campo y el clima posterior cargado en la app."
    )

    colf1, colf2, colf3 = st.columns(3)

    priority_options = ["Todas", "Alta", "Media-alta", "Media", "Baja"]
    priority_filter = colf1.selectbox("Prioridad", priority_options, index=0)

    products = ["Todos"] + sorted([p for p in cross["Producto"].dropna().unique().tolist() if str(p).strip()])
    product_filter = colf2.selectbox("Producto", products, index=0)

    field_options = ["Todos"] + sorted(cross["Campo"].dropna().unique().tolist())
    field_filter = colf3.selectbox("Campo", field_options, index=0)

    colf4, colf5, colf6 = st.columns(3)
    only_with_warning = colf4.checkbox("Ver solo campos con aviso de vigilar/revisar/priorizar", value=False)

    max_days = int(cross["Días hasta último dato climático"].dropna().max()) if not cross["Días hasta último dato climático"].dropna().empty else 0
    quick_days = colf5.selectbox(
        "Periodo desde último tratamiento",
        ["Todos", "Últimos 7 días", "Últimos 10 días", "Últimos 15 días", "Últimos 30 días", "Personalizado"],
        index=0,
        help="Por defecto se muestran todos los campos. Usa este filtro solo si quieres centrarte en tratamientos recientes.",
    )

    if quick_days == "Todos":
        days_filter = max(max_days, 1)
    elif quick_days == "Últimos 7 días":
        days_filter = 7
    elif quick_days == "Últimos 10 días":
        days_filter = 10
    elif quick_days == "Últimos 15 días":
        days_filter = 15
    elif quick_days == "Últimos 30 días":
        days_filter = 30
    else:
        days_filter = colf5.slider(
            "Máximo de días desde el tratamiento",
            min_value=0,
            max_value=max(max_days, 1),
            value=max(max_days, 1),
            help="Filtra campos según los días transcurridos entre el tratamiento y el último dato climático cargado.",
        )

    min_rain = colf6.number_input("Lluvia posterior mínima mm", min_value=0.0, value=0.0, step=1.0)

    filtered = cross.copy()

    if quick_days == "Todos":
        st.caption("Mostrando todos los campos por defecto. El filtro de días solo se aplica si eliges un periodo concreto.")

    if priority_filter != "Todas":
        filtered = filtered[filtered["Prioridad"].eq(priority_filter)]

    if product_filter != "Todos":
        filtered = filtered[filtered["Producto"].eq(product_filter)]

    if field_filter != "Todos":
        filtered = filtered[filtered["Campo"].eq(field_filter)]

    if only_with_warning:
        filtered = filtered[filtered["Prioridad"].isin(["Alta", "Media-alta", "Media"])]

    filtered = filtered[
        (filtered["Días hasta último dato climático"].fillna(0) <= days_filter)
        & (filtered["Lluvia posterior mm"] >= min_rain)
    ]

    priority_order = {"Alta": 0, "Media-alta": 1, "Media": 2, "Baja": 3}
    filtered["_orden_prioridad"] = filtered["Prioridad"].map(priority_order).fillna(9)
    filtered = filtered.sort_values(
        ["_orden_prioridad", "Máx ratio moteado posterior", "Máx ratio monilia posterior", "Lluvia posterior mm"],
        ascending=[True, False, False, False],
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Campos mostrados", len(filtered))
    c2.metric("Prioridad alta", int((filtered["Prioridad"] == "Alta").sum()))
    c3.metric("Revisar/vigilar", int(filtered["Prioridad"].isin(["Alta", "Media-alta", "Media"]).sum()))
    c4.metric("Máx lluvia posterior", f"{filtered['Lluvia posterior mm'].max():.1f} mm" if not filtered.empty else "0.0 mm")

    if filtered.empty:
        st.info("No hay campos que cumplan los filtros seleccionados.")
        return

    st.markdown("##### Tarjetas de prioridad")
    for _, row in filtered.drop(columns=["_orden_prioridad"], errors="ignore").iterrows():
        prioridad = row.get("Prioridad", "Baja")
        if prioridad == "Alta":
            icon = "🔴"
        elif prioridad == "Media-alta":
            icon = "🟠"
        elif prioridad == "Media":
            icon = "🟡"
        else:
            icon = "🟢"

        max_ratio = max(
            float(row.get("Máx ratio moteado posterior", 0) or 0),
            float(row.get("Máx ratio monilia posterior", 0) or 0),
        )
        variedades = row.get("Variedades actuales", "")
        superficie = row.get("Superficie ha", np.nan)
        sup_txt = f"{float(superficie):.2f} ha" if pd.notna(superficie) else "sup. no disponible"

        with st.container(border=True):
            st.markdown(f"### {icon} {row['Campo']} · Prioridad {prioridad}")
            st.markdown(
                f"**Último tratamiento:** {row['Último tratamiento']} · **{row['Producto']}**  \n"
                f"**Variedades:** {variedades if str(variedades).strip() else 'No indicadas'} · **Superficie campo:** {sup_txt}"
            )

            cc1, cc2, cc3, cc4 = st.columns(4)
            cc1.metric("Días desde tratamiento", int(row["Días hasta último dato climático"]) if pd.notna(row["Días hasta último dato climático"]) else 0)
            cc2.metric("Lluvia posterior", f"{row['Lluvia posterior mm']:.1f} mm")
            cc3.metric("Máx ratio posterior", f"{max_ratio:.2f}")
            cc4.metric("Eventos ratio ≥ 1", int(row.get("Eventos moteado ratio >= 1", 0)) + int(row.get("Eventos monilia ratio >= 1", 0)))

            st.markdown(f"**Aviso:** {row['Aviso orientativo']}")
            if str(row.get("Evento más crítico posterior", "")).strip():
                st.caption(f"Evento más crítico posterior: {row['Evento más crítico posterior']}")

    st.markdown("##### Tabla del informe filtrado")
    visible_cols = [
        "Campo",
        "Prioridad",
        "Último tratamiento",
        "Días hasta último dato climático",
        "Producto",
        "Variedades tratadas",
        "Variedades actuales",
        "Lluvia posterior mm",
        "Eventos hoja mojada posteriores",
        "Eventos moteado ratio >= 1",
        "Eventos monilia ratio >= 1",
        "Máx ratio moteado posterior",
        "Máx ratio monilia posterior",
        "Aviso orientativo",
    ]
    visible_cols = [c for c in visible_cols if c in filtered.columns]
    st.dataframe(filtered[visible_cols], use_container_width=True)

    st.download_button(
        "Descargar informe sanitario por campo",
        data=filtered.drop(columns=["_orden_prioridad"], errors="ignore").to_csv(index=False).encode("utf-8-sig"),
        file_name="informe_sanitario_por_campo.csv",
        mime="text/csv",
        key="download_field_sanitary_report",
    )




SUPABASE_ACTIVITIES_TABLE = "agroptima_activities"
SUPABASE_TREATMENT_CATALOG_TABLE = "treatment_product_catalog"

ACTIVITY_TO_SUPABASE = {
    "Fecha": "fecha",
    "Campos": "campos",
    "Campos reconocidos": "campos_reconocidos",
    "Campos no reconocidos": "campos_no_reconocidos",
    "Superficie tratada ha": "superficie_tratada_ha",
    "Trabajo": "trabajo",
    "Producto": "producto",
    "Cantidad": "cantidad",
    "Unidad cantidad": "unidad_cantidad",
    "Dosis": "dosis",
    "Unidad dosis": "unidad_dosis",
    "Cultivos / variedades Agroptima": "cultivos_variedades_agroptima",
    "Personal": "personal",
    "Máquinas": "maquinas",
    "Comentarios": "comentarios",
    "ID Agroptima": "id_agroptima",
}
SUPABASE_TO_ACTIVITY = {v: k for k, v in ACTIVITY_TO_SUPABASE.items()}


def activities_dataframe_for_supabase(df):
    """Convierte actuaciones al formato JSON esperado por Supabase."""
    if df is None or df.empty:
        return []

    normalized = normalize_activities_df(df)
    out = normalized.drop(columns=[c for c in ["_clave_importacion"] if c in normalized.columns], errors="ignore").copy()

    # clave_fallback sí se guarda como respaldo para registros sin ID Agroptima.
    if "_clave_fallback" not in out.columns:
        out["_clave_fallback"] = ""

    records = []
    for _, row in out.iterrows():
        rec = {}
        for app_col, db_col in ACTIVITY_TO_SUPABASE.items():
            value = row.get(app_col, None)
            if pd.isna(value):
                value = None
            rec[db_col] = value

        fecha = pd.to_datetime(row.get("Fecha", None), errors="coerce")
        rec["fecha"] = fecha.date().isoformat() if pd.notna(fecha) else None

        for app_col, db_col in {
            "Superficie tratada ha": "superficie_tratada_ha",
            "Cantidad": "cantidad",
            "Dosis": "dosis",
        }.items():
            value = pd.to_numeric(row.get(app_col, np.nan), errors="coerce")
            rec[db_col] = None if pd.isna(value) else float(value)

        # Limpieza de ID. Si no hay ID real, generamos un ID SINTÉTICO determinista
        # a partir de la clave_fallback ("FB:" + fecha|campos|producto|sup|cant|dosis).
        # Así CADA producto (incluidas las filas de continuación de una mezcla) tiene
        # un id_agroptima único y estable → el upsert por id_agroptima es idempotente
        # y nunca se duplican filas al volver a guardar.
        id_agro = str(row.get("ID Agroptima", "") or "").strip()
        _clave_fb = str(row.get("_clave_fallback", "") or "").strip()
        if id_agro and id_agro.lower() not in ("nan", "none", "<na>") and not id_agro.startswith("FB:"):
            rec["id_agroptima"] = id_agro
        elif _clave_fb:
            rec["id_agroptima"] = "FB:" + _clave_fb
        else:
            rec["id_agroptima"] = None
        rec["clave_fallback"] = _clave_fb or None

        records.append(rec)

    return records


def upsert_activities_to_supabase(df, chunk_size=500):
    """Guarda actuaciones Agroptima en Supabase usando upsert por id_agroptima."""
    if not supabase_is_configured():
        return False, "Supabase no está configurado. Revisa SUPABASE_URL y SUPABASE_KEY en Secrets."

    records = activities_dataframe_for_supabase(df)
    if not records:
        return False, "No hay actuaciones válidas para guardar."

    # De momento usamos upsert por ID Agroptima para las filas que lo tengan.
    # Las filas sin ID se insertan mediante fallback, pero si no tienen ID único pueden duplicarse.
    with_id = [r for r in records if r.get("id_agroptima")]
    without_id = [r for r in records if not r.get("id_agroptima")]

    endpoint = supabase_table_url(SUPABASE_ACTIVITIES_TABLE)
    headers = supabase_headers()
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

    total = 0

    for dataset, conflict_col in [(with_id, "id_agroptima")]:
        for i in range(0, len(dataset), chunk_size):
            chunk = dataset[i:i + chunk_size]
            response = requests.post(
                endpoint,
                headers=headers,
                params={"on_conflict": conflict_col},
                json=chunk,
                timeout=60,
            )
            if response.status_code not in (200, 201, 204):
                return False, f"Error guardando actuaciones en Supabase: {response.status_code} · {response.text[:500]} · Endpoint: {endpoint}"
            total += len(chunk)

    # Si hay registros sin ID, intentamos insertarlos; para evitar duplicados de verdad habría que crear unique(clave_fallback).
    if without_id:
        for i in range(0, len(without_id), chunk_size):
            chunk = without_id[i:i + chunk_size]
            response = requests.post(
                endpoint,
                headers=headers,
                json=chunk,
                timeout=60,
            )
            if response.status_code not in (200, 201, 204):
                return False, f"Error guardando actuaciones sin ID en Supabase: {response.status_code} · {response.text[:500]} · Endpoint: {endpoint}"
            total += len(chunk)

    msg = f"Actuaciones guardadas en Supabase: {total} registros enviados."
    if without_id:
        msg += f" Aviso: {len(without_id)} registros no tenían ID Agroptima; se han insertado usando clave alternativa solo como referencia."
    return True, msg


def load_activities_from_supabase(page_size=1000, max_pages=100):
    """Carga actuaciones Agroptima desde Supabase."""
    if not supabase_is_configured():
        return pd.DataFrame(columns=ACTIVITY_COLUMNS), "Supabase no está configurado. Revisa SUPABASE_URL y SUPABASE_KEY en Secrets."

    endpoint = supabase_table_url(SUPABASE_ACTIVITIES_TABLE)
    headers = supabase_headers()
    headers.pop("Prefer", None)

    frames = []
    offset = 0

    select_cols = list(SUPABASE_TO_ACTIVITY.keys()) + ["clave_fallback"]
    for _ in range(max_pages):
        response = requests.get(
            endpoint,
            headers=headers,
            params={
                "select": ",".join(select_cols),
                "order": "fecha.desc",
                "limit": str(page_size),
                "offset": str(offset),
            },
            timeout=60,
        )
        if response.status_code != 200:
            return pd.DataFrame(columns=ACTIVITY_COLUMNS), f"Error cargando actuaciones desde Supabase: {response.status_code} · {response.text[:500]} · Endpoint: {endpoint}"

        data = response.json()
        if not data:
            break

        frames.append(pd.DataFrame(data))
        if len(data) < page_size:
            break
        offset += page_size

    if not frames:
        return pd.DataFrame(columns=ACTIVITY_COLUMNS), "Supabase no contiene actuaciones todavía."

    db_df = pd.concat(frames, ignore_index=True)
    out = pd.DataFrame()
    for db_col, app_col in SUPABASE_TO_ACTIVITY.items():
        out[app_col] = db_df[db_col] if db_col in db_df.columns else ""

    out = normalize_activities_df(out)
    # Filtrar herbicidas/otros: la app solo trabaja con tratamientos fitosanitarios.
    # (Limpia también los herbicidas que pudieran estar ya guardados en Supabase.)
    out = filter_only_fitosanitario(out)
    visible = out.drop(columns=[c for c in ["_clave_fallback", "_clave_importacion"] if c in out.columns], errors="ignore")
    return visible, f"Actuaciones cargadas desde Supabase: {len(visible)} registros."


def test_supabase_activities_connection():
    """Prueba simple de lectura contra la tabla agroptima_activities."""
    if not supabase_is_configured():
        return False, "Supabase no está configurado.", ""

    endpoint = supabase_table_url(SUPABASE_ACTIVITIES_TABLE)
    headers = supabase_headers()
    headers.pop("Prefer", None)

    try:
        response = requests.get(
            endpoint,
            headers=headers,
            params={"select": "id_agroptima", "limit": "1"},
            timeout=30,
        )
    except Exception as exc:
        return False, f"No se pudo conectar con Supabase: {exc}", endpoint

    if response.status_code == 200:
        return True, "Conexión correcta con Supabase y tabla agroptima_activities.", endpoint

    return False, f"Error de conexión: {response.status_code} · {response.text[:500]}", endpoint


def render_supabase_activities_panel():
    st.markdown("### Modo nube Supabase · Actuaciones")

    if supabase_is_configured():
        st.success("Supabase configurado correctamente en Secrets.")
    else:
        st.warning("Supabase todavía no está configurado. Añade SUPABASE_URL y SUPABASE_KEY en Secrets.")

    with st.expander("Comprobar conexión Supabase actuaciones", expanded=False):
        normalized_url, _ = get_supabase_credentials()
        st.write(f"URL normalizada usada por la app: `{normalized_url or 'No configurada'}`")
        st.write(f"Endpoint esperado: `{supabase_table_url(SUPABASE_ACTIVITIES_TABLE) if normalized_url else 'No disponible'}`")
        if st.button("Probar conexión con agroptima_activities", use_container_width=True):
            ok, msg, endpoint = test_supabase_activities_connection()
            if ok:
                st.success(msg)
            else:
                st.error(msg)
                st.caption(f"Endpoint probado: {endpoint}")

    with st.expander("Cómo usar Supabase con actuaciones Agroptima", expanded=False):
        st.markdown(
            """
            **Flujo recomendado:**

            1. Pulsa **Cargar actuaciones desde Supabase** al abrir la app.
            2. Si tienes un Excel nuevo de Agroptima, súbelo e impórtalo como hasta ahora.
            3. Pulsa **Guardar actuaciones actuales en Supabase**.
            4. La próxima vez podrás recuperar las actuaciones sin cargar el CSV maestro.

            La tabla usa `id_agroptima` para actualizar sin duplicar. Si algún registro no trae ID, la app lo guarda con una clave alternativa como referencia.
            """
        )

    st.markdown("#### Carga desde tabla REST")
    st.caption("Uso avanzado/respaldo. Para cargar todo el histórico es preferible usar el snapshot comprimido.")

    col_cloud_1, col_cloud_2 = st.columns(2)

    with col_cloud_1:
        if st.button("Cargar actuaciones desde Supabase", use_container_width=True):
            cloud_df, msg = load_activities_from_supabase()
            if cloud_df.empty:
                st.warning(msg)
            else:
                st.session_state.activities_df = cloud_df
                st.session_state.last_activities_import_stats = {}
                st.success(msg)
                st.rerun()

    with col_cloud_2:
        activities_df = st.session_state.get("activities_df", pd.DataFrame(columns=ACTIVITY_COLUMNS))
        if st.button("Guardar actuaciones actuales en Supabase", use_container_width=True, type="primary"):
            ok, msg = upsert_activities_to_supabase(activities_df)
            if ok:
                st.success(msg)
            else:
                st.error(msg)




# ═══════════════════════════════════════════════════════════════════════════════
# AGROPTIMA · Integración directa via sesión web
# ═══════════════════════════════════════════════════════════════════════════════

AGROPTIMA_BASE = "https://app.agroptima.com"


def agroptima_is_configured():
    try:
        csrf  = st.secrets.get("AGROPTIMA_CSRF_TOKEN", "")
        sesid = st.secrets.get("AGROPTIMA_SESSION_ID", "")
        return bool(csrf and sesid)
    except Exception:
        return False


def agroptima_get_headers():
    """Construye las cabeceras y cookies de sesión para Agroptima."""
    try:
        csrf  = st.secrets.get("AGROPTIMA_CSRF_TOKEN", "").strip()
        sesid = st.secrets.get("AGROPTIMA_SESSION_ID", "").strip()
    except Exception:
        return None, "No se encontraron credenciales de Agroptima en Secrets."
    headers = {
        "User-Agent":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer":     f"{AGROPTIMA_BASE}/es/agroreports/notifications/",
        "Origin":      AGROPTIMA_BASE,
        "X-CSRFToken": csrf,
        "Cookie":      f"csrftoken={csrf}; sessionid={sesid}",
    }
    return headers, None


def agroptima_get_products(headers):
    """
    Obtiene la lista de productos fitosanitarios disponibles en la cuenta.
    Hace una petición a la página de actividades y extrae los IDs de productos.
    """
    try:
        r = requests.get(
            f"{AGROPTIMA_BASE}/es/agroreports/notifications/",
            headers=headers,
            timeout=30,
        )
        if r.status_code != 200:
            return [], f"Error {r.status_code} obteniendo productos"

        # Extraer IDs de productos fitosanitarios del HTML
        import re
        products = re.findall(r'value="(phytosanitary_\d+)"', r.text)
        products = list(dict.fromkeys(products))  # eliminar duplicados
        return products, None
    except Exception as e:
        return [], f"Error: {e}"


def agroptima_download_excel(headers, products, start_date, end_date, pre_season=None):
    """
    Descarga el Excel de actividades de Agroptima.
    Agroptima usa un sistema asincrono: POST devuelve task_id,
    luego hay que hacer polling hasta que el archivo este listo.
    """
    try:
        csrf = st.secrets.get("AGROPTIMA_CSRF_TOKEN", "").strip()
    except Exception:
        return None, "No se encontraron credenciales."

    if not pre_season:
        # Incluir la temporada del año de inicio y la del año de fin por si cruzan años
        year_start = pd.Timestamp(start_date).year
        year_end   = pd.Timestamp(end_date).year
        if year_start == year_end:
            pre_season = f"{year_start}0101_{year_start}1231"
        else:
            # Multiples temporadas
            pre_season = ",".join(f"{y}0101_{y}1231" for y in range(year_start, year_end + 1))

    data = [
        ("order_by",           ""),
        ("page",               "1"),
        ("csrfmiddlewaretoken", csrf),
        ("start_date",         pd.Timestamp(start_date).strftime("%Y-%m-%d")),
        # Forzar end_date a fin del dia para incluir todas las actividades
        ("end_date",           pd.Timestamp(end_date).strftime("%Y-%m-%d")),
        ("pre_seasons",        pre_season),
        ("notes",              ""),
    ]
    for p in products:
        data.append(("products", p))

    # Paso 1: Solicitar generacion del Excel
    try:
        r = requests.post(
            f"{AGROPTIMA_BASE}/es/agroreports/notifications/xls/",
            headers=headers,
            data=data,
            timeout=60,
        )
        if r.status_code != 200:
            return None, f"Error {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return None, f"Error solicitando Excel: {e}"

    # Paso 2: Extraer task_id
    try:
        resp_json = r.json()
        task_id = resp_json.get("task_id")
        if not task_id:
            return None, f"No se obtuvo task_id: {r.text[:200]}"
    except Exception:
        # Si no es JSON, puede que ya sea el Excel directamente
        if len(r.content) > 100:
            return r.content, None
        return None, f"Respuesta inesperada: {r.text[:200]}"

    # Paso 3: Polling hasta que la tarea este lista (max 60 segundos)
    import time
    last_status = {}
    for attempt in range(20):
        time.sleep(3)
        try:
            r_status = requests.get(
                f"{AGROPTIMA_BASE}/es/api/queue/async_task_status/",
                headers=headers,
                params={"task_id": task_id},
                timeout=30,
            )
            last_status = {"status_code": r_status.status_code, "text": r_status.text[:300]}
            if r_status.status_code != 200:
                continue
            status_data = r_status.json()
            last_status["json"] = status_data
            # Agroptima usa "status" no "state", y el valor es "success" en minusculas
            state = (status_data.get("status") or status_data.get("state") or "").lower()
            if state == "success":
                file_url = status_data.get("result") or status_data.get("file_url") or status_data.get("url")
                if file_url:
                    if not file_url.startswith("http"):
                        file_url = AGROPTIMA_BASE + file_url
                    r_file = requests.get(file_url, headers=headers, timeout=60)
                    if r_file.status_code == 200 and len(r_file.content) > 100:
                        return r_file.content, None
                    return None, f"Error descargando archivo: {r_file.status_code}"
                if len(r_status.content) > 1000:
                    return r_status.content, None
                return None, f"Tarea completada pero sin URL: {status_data}"
            elif state in ("failure", "error", "revoked"):
                return None, f"La tarea falló: {status_data}"
        except Exception as e:
            last_status["exception"] = str(e)
            continue

    return None, f"Tiempo de espera agotado. Último estado: {last_status}"


def render_agroptima_panel():
    """Panel de importación directa desde Agroptima."""
    st.markdown("### 🌿 Importar actuaciones directamente desde Agroptima")

    if not agroptima_is_configured():
        st.warning(
            "Para activar la importación directa desde Agroptima, añade en **Secrets** de Streamlit:\n\n"
            "```toml\n"
            "AGROPTIMA_CSRF_TOKEN = \"valor de csrftoken\"\n"
            "AGROPTIMA_SESSION_ID = \"valor de sessionid\"\n"
            "```\n\n"
            "Encuéntralos en el navegador: F12 → Application → Cookies → app.agroptima.com"
        )
        return

    st.success("✅ Credenciales Agroptima detectadas en Secrets.")
    st.caption("⚠️ Las cookies de sesión caducan. Si da error, renuévalas en Secrets.")

    today      = pd.Timestamp.today().date()
    year_start = pd.Timestamp(today.year, 1, 1).date()

    col1, col2 = st.columns(2)
    with col1:
        agro_start = st.date_input("Desde", value=year_start, key="agro_start")
    with col2:
        agro_end = st.date_input("Hasta", value=today, key="agro_end")

    if st.button("⬇️ Descargar e importar actuaciones de Agroptima",
                 type="primary", use_container_width=True, key="agro_download_btn"):

        headers, err = agroptima_get_headers()
        if err:
            st.error(err)
            return

        with st.spinner("Obteniendo lista de productos fitosanitarios..."):
            products, err = agroptima_get_products(headers)

        if err:
            st.error(err)
            return
        if not products:
            st.error("No se encontraron productos fitosanitarios en tu cuenta de Agroptima. "
                     "Es posible que la sesión haya caducado — renueva las cookies en Secrets.")
            return

        st.caption(f"Se encontraron {len(products)} productos fitosanitarios.")

        with st.spinner(f"Generando y descargando Excel de actuaciones ({agro_start} → {agro_end})... puede tardar unos segundos"):
            excel_bytes, err = agroptima_download_excel(
                headers, products, agro_start, agro_end
            )

        if err:
            st.error(err)
            return

        # Procesar el Excel igual que la subida manual
        try:
            import io as _io
            excel_file = _io.BytesIO(excel_bytes)
            activities_df_new, warnings, diagnostics = parse_agroptima_activities_excel(excel_file)

            if warnings:
                for w in warnings:
                    st.warning(w)

            if activities_df_new.empty:
                st.warning("El Excel descargado no contiene actividades reconocibles.")
            else:
                # Fusionar con el histórico existente (sin duplicar por id_agroptima)
                existing = st.session_state.get("activities_df", pd.DataFrame(columns=ACTIVITY_COLUMNS))
                merged, stats = merge_activities_history(existing, activities_df_new, "upsert")
                st.session_state.activities_df = merged
                st.session_state.last_activities_import_stats = stats
                # Las claves reales que devuelve merge_activities_history son en
                # español; antes se leían "inserted"/"updated" (inexistentes) y por
                # eso SIEMPRE salía "0 nuevas, 0 actualizadas".
                n_new  = stats.get("Nuevas añadidas", 0)
                n_upd  = stats.get("Actualizadas/reemplazadas", 0)
                st.success(f"✅ {len(activities_df_new)} actividades procesadas — {n_new} nuevas, {n_upd} ya existentes (actualizadas).")
                # Guardado automático en Supabase (sin pasos manuales)
                autosave_activities_to_supabase()
        except Exception as e:
            st.error(f"Error procesando el Excel: {e}")

def activities_tab():
    st.subheader("Actuaciones Agroptima")

    render_agroptima_panel()

    st.divider()

    st.info(
        "Sube aquí el **Excel XLSX de Agroptima** con las actividades del año. "
        "La app actualizará el histórico sin duplicar tratamientos usando el ID Agroptima."
    )

    render_supabase_activities_panel()

    st.divider()

    with st.expander("Cómo funciona la actualización", expanded=False):
        st.markdown(
            """
            **Modo recomendado:** actualizar histórico reemplazando coincidencias por **ID Agroptima**.

            - Si el **ID Agroptima ya existe**, la fila nueva del Excel reemplaza a la anterior.
            - Si el **ID Agroptima no existe**, se añade como nueva actuación.
            - Si algún registro no trae ID, la app usa una clave alternativa: fecha + campos + producto + superficie + dosis.

            Así puedes descargar de Agroptima el Excel de todo lo que llevas de año y subirlo de nuevo sin duplicar tratamientos.
            """
        )

    st.markdown("### 1. Excel de Agroptima")
    uploaded = st.file_uploader(
        "Subir Excel de actividades de Agroptima (.xlsx)",
        type=None,
        accept_multiple_files=False,
        key="agroptima_activities_file",
        help="Este es el archivo XLSX que descargas desde Agroptima. No subas aquí el histórico CSV descargado desde la app.",
    )

    mode_label = st.radio(
        "Modo de importación del Excel de Agroptima",
        [
            "Actualizar histórico reemplazando coincidencias por ID Agroptima",
            "Añadir solo actuaciones nuevas, sin sobrescribir",
            "Reemplazar histórico de actuaciones con el Excel subido",
        ],
        index=0,
    )
    mode_map = {
        "Actualizar histórico reemplazando coincidencias por ID Agroptima": "update_by_id",
        "Añadir solo actuaciones nuevas, sin sobrescribir": "append_new",
        "Reemplazar histórico de actuaciones con el Excel subido": "replace",
    }
    mode = mode_map[mode_label]

    if uploaded is not None:
        activities_df, warnings, diagnostics = parse_agroptima_activities_excel(uploaded)

        st.markdown("#### Diagnóstico del Excel subido")
        diag_rows = [{"Dato": k, "Valor": v} for k, v in diagnostics.items()]
        st.dataframe(pd.DataFrame(diag_rows), use_container_width=True)

        if warnings:
            st.warning("Avisos de lectura:")
            for w in warnings:
                st.write(f"- {w}")

        if activities_df.empty:
            st.warning("No se han podido interpretar actividades.")
        else:
            st.markdown("#### Vista previa del Excel interpretado")
            st.dataframe(activities_df, use_container_width=True)

            if st.button("Importar / actualizar histórico de actuaciones", type="primary"):
                existing = st.session_state.get("activities_df", pd.DataFrame(columns=ACTIVITY_COLUMNS))
                merged, stats = merge_activities_history(existing, activities_df, mode)
                st.session_state.activities_df = merged
                st.session_state.last_activities_import_stats = stats
                st.success("Histórico de actuaciones actualizado.")
                # Guardado automático en Supabase (sin pasos manuales)
                autosave_activities_to_supabase()

    with st.expander("Opción avanzada: cargar histórico maestro CSV descargado desde la app", expanded=False):
        st.caption(
            "Usa esta opción solo si ya descargaste antes desde esta app el archivo "
            "`historico_actuaciones_agroptima.csv` y quieres recuperarlo en una nueva sesión."
        )
        master_file = st.file_uploader(
            "Subir histórico maestro de actuaciones de la app (.csv)",
            type=["csv"],
            accept_multiple_files=False,
            key="agroptima_master_activities_file",
        )

        if master_file is not None:
            try:
                master_df = pd.read_csv(master_file)
                normalized_master = normalize_activities_df(master_df)
                st.session_state.activities_df = normalized_master.drop(
                    columns=[c for c in ["_clave_fallback", "_clave_importacion"] if c in normalized_master.columns]
                )
                st.success(f"Histórico maestro cargado: {len(st.session_state.activities_df)} actuaciones.")
            except Exception as e:
                st.error(f"No se pudo cargar el histórico maestro de actuaciones: {e}")

    if "last_activities_import_stats" in st.session_state and st.session_state.last_activities_import_stats:
        st.markdown("#### Resultado de la última importación")
        stats_df = pd.DataFrame([
            {"Dato": k, "Valor": v}
            for k, v in st.session_state.last_activities_import_stats.items()
        ])
        st.dataframe(stats_df, use_container_width=True)

    st.divider()
    render_activities_summaries(st.session_state.get("activities_df", pd.DataFrame(columns=ACTIVITY_COLUMNS)))

    st.divider()
    with st.expander("Plan orientativo de rotación FRAC para próxima campaña", expanded=True):
        render_frac_rotation_plan(st.session_state.get("activities_df", pd.DataFrame(columns=ACTIVITY_COLUMNS)), key_suffix="activities")

    st.divider()
    render_treatment_sanitary_cross()

    st.divider()
    render_field_sanitary_report()




def parse_user_date(value, fallback, min_allowed, max_allowed):
    """Acepta YYYY-MM-DD o DD/MM/YYYY."""
    if value is None or str(value).strip() == "":
        return pd.Timestamp(fallback).date(), None

    txt = str(value).strip()
    parsed = pd.to_datetime(txt, errors="coerce", dayfirst=False)
    if pd.isna(parsed):
        parsed = pd.to_datetime(txt, errors="coerce", dayfirst=True)

    if pd.isna(parsed):
        return pd.Timestamp(fallback).date(), f"No se pudo interpretar la fecha '{value}'. Usa YYYY-MM-DD o DD/MM/YYYY."

    d = parsed.date()
    if d < min_allowed:
        return min_allowed, f"La fecha {d} es anterior al histórico. Se ha ajustado a {min_allowed}."
    if d > max_allowed:
        return max_allowed, f"La fecha {d} es posterior al histórico. Se ha ajustado a {max_allowed}."

    return d, None




SUPABASE_CLIMATE_TABLE = "climate_hourly"
SUPABASE_SNAPSHOT_BUCKET = "climate-snapshots"
SUPABASE_FULL_CLIMATE_SNAPSHOT = "historico_clima_completo.parquet"


def normalize_supabase_url(raw_url):
    """Normaliza distintas URLs copiadas por error desde Supabase."""
    url = str(raw_url or "").strip().strip("\'").strip('\"')
    if not url:
        return ""

    # Si se pegó la URL del dashboard, intenta extraer el project ref:
    # https://supabase.com/dashboard/project/<ref>/...
    m = re.search(r"supabase\.com/dashboard/project/([a-zA-Z0-9]+)", url)
    if m:
        return f"https://{m.group(1)}.supabase.co"

    # Si se pegó una URL que ya contenía /rest/v1, la dejamos como base del proyecto.
    url = re.sub(r"/rest/v1/?$", "", url)
    url = re.sub(r"/rest/v1/.*$", "", url)

    # Quita barras finales.
    url = url.rstrip("/")

    return url


def get_supabase_credentials():
    """Lee credenciales Supabase desde Streamlit Secrets."""
    try:
        raw_url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
    except Exception:
        raw_url, key = "", ""
    return normalize_supabase_url(raw_url), str(key).strip()


def supabase_is_configured():
    url, key = get_supabase_credentials()
    return bool(url and key)


def supabase_headers():
    url, key = get_supabase_credentials()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def supabase_table_url(table=SUPABASE_CLIMATE_TABLE):
    url, _ = get_supabase_credentials()
    return f"{url.rstrip('/')}/rest/v1/{table}"


def dataframe_for_supabase(df):
    """Convierte el histórico climático al formato JSON esperado por Supabase."""
    if df is None or df.empty:
        return []

    out = compact_history(df).copy()

    for col in CANONICAL_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan

    out = out[CANONICAL_COLUMNS].copy()
    out["fecha_hora"] = pd.to_datetime(out["fecha_hora"], errors="coerce")
    out = out.dropna(subset=["fecha_hora"]).sort_values("fecha_hora")

    # Supabase/PostgREST entiende ISO sin zona para timestamp without time zone.
    out["fecha_hora"] = out["fecha_hora"].dt.strftime("%Y-%m-%dT%H:%M:%S")

    # NaN -> None para JSON válido.
    out = out.replace({np.nan: None})
    return out.to_dict(orient="records")


def upsert_climate_to_supabase(df, chunk_size=500):
    """Guarda el histórico climático en Supabase usando upsert por fecha_hora."""
    if not supabase_is_configured():
        return False, "Supabase no está configurado. Revisa SUPABASE_URL y SUPABASE_KEY en Secrets."

    records = dataframe_for_supabase(df)
    if not records:
        return False, "No hay registros climáticos válidos para guardar."

    endpoint = supabase_table_url()
    headers = supabase_headers()
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

    total = 0
    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        response = requests.post(
            endpoint,
            headers=headers,
            params={"on_conflict": "fecha_hora"},
            json=chunk,
            timeout=60,
        )
        if response.status_code not in (200, 201, 204):
            return False, f"Error guardando en Supabase: {response.status_code} · {response.text[:500]} · Endpoint: {endpoint}"
        total += len(chunk)

    return True, f"Histórico guardado en Supabase: {total} registros enviados."


@st.cache_data(ttl=600, show_spinner=False)
def cached_load_climate_from_supabase(normalized_url, key, page_size=1000, max_pages=500):
    """
    Carga histórico climático con paginación por fecha_hora.
    Evita offset, que se vuelve lento con históricos grandes.
    """
    if not normalized_url or not key:
        return [], "Supabase no está configurado."

    endpoint = f"{normalized_url.rstrip('/')}/rest/v1/{SUPABASE_CLIMATE_TABLE}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    rows = []
    last_fecha = None

    for page in range(max_pages):
        params = {
            "select": ",".join(CANONICAL_COLUMNS),
            "order": "fecha_hora.asc",
            "limit": str(page_size),
        }
        if last_fecha:
            params["fecha_hora"] = f"gt.{last_fecha}"

        response = requests.get(
            endpoint,
            headers=headers,
            params=params,
            timeout=60,
        )

        if response.status_code != 200:
            return [], f"Error cargando desde Supabase: {response.status_code} · {response.text[:500]} · Endpoint: {endpoint}"

        data = response.json()
        if not data:
            break

        rows.extend(data)
        new_last = data[-1].get("fecha_hora")
        if not new_last or new_last == last_fecha:
            break
        last_fecha = new_last

        if len(data) < page_size:
            break

    if not rows:
        return [], "Supabase no contiene registros climáticos todavía."

    return rows, f"Histórico cargado desde Supabase: {len(rows)} registros."


def load_climate_from_supabase(page_size=1000, max_pages=500, use_cache=True):
    """Carga todo el histórico climático desde Supabase usando paginación eficiente por fecha_hora."""
    if not supabase_is_configured():
        return pd.DataFrame(columns=CANONICAL_COLUMNS), "Supabase no está configurado. Revisa SUPABASE_URL y SUPABASE_KEY en Secrets."

    normalized_url, key = get_supabase_credentials()

    if use_cache:
        rows, msg = cached_load_climate_from_supabase(normalized_url, key, page_size, max_pages)
    else:
        cached_load_climate_from_supabase.clear()
        rows, msg = cached_load_climate_from_supabase(normalized_url, key, page_size, max_pages)

    if not rows:
        return pd.DataFrame(columns=CANONICAL_COLUMNS), msg

    df = pd.DataFrame(rows)
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    df = df[CANONICAL_COLUMNS].copy()
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"], errors="coerce")
    for col in CANONICAL_COLUMNS:
        if col != "fecha_hora":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = compact_history(df)
    return df, msg



def test_supabase_climate_connection():
    """Prueba simple de lectura contra la tabla climate_hourly."""
    if not supabase_is_configured():
        return False, "Supabase no está configurado.", ""

    endpoint = supabase_table_url()
    headers = supabase_headers()
    headers.pop("Prefer", None)

    try:
        response = requests.get(
            endpoint,
            headers=headers,
            params={"select": "fecha_hora", "limit": "1"},
            timeout=30,
        )
    except Exception as exc:
        return False, f"No se pudo conectar con Supabase: {exc}", endpoint

    if response.status_code == 200:
        return True, "Conexión correcta con Supabase y tabla climate_hourly.", endpoint

    return False, f"Error de conexión: {response.status_code} · {response.text[:500]}", endpoint





def climate_snapshot_storage_url(path=SUPABASE_FULL_CLIMATE_SNAPSHOT):
    url, _ = get_supabase_credentials()
    return f"{url.rstrip('/')}/storage/v1/object/{SUPABASE_SNAPSHOT_BUCKET}/{path.lstrip('/')}"


def climate_snapshot_metadata_url(path=SUPABASE_FULL_CLIMATE_SNAPSHOT):
    url, _ = get_supabase_credentials()
    return f"{url.rstrip('/')}/storage/v1/object/info/{SUPABASE_SNAPSHOT_BUCKET}/{path.lstrip('/')}"


def climate_df_to_parquet_bytes(df):
    """Convierte el histórico climático a Parquet comprimido."""
    if df is None or df.empty:
        return None

    out = compact_history(df).copy()

    for col in CANONICAL_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan

    out = out[CANONICAL_COLUMNS].copy()
    out["fecha_hora"] = pd.to_datetime(out["fecha_hora"], errors="coerce")
    out = out.dropna(subset=["fecha_hora"]).sort_values("fecha_hora")

    for col in CANONICAL_COLUMNS:
        if col != "fecha_hora":
            out[col] = pd.to_numeric(out[col], errors="coerce")

    buffer = io.BytesIO()
    out.to_parquet(buffer, index=False, compression="snappy", engine="pyarrow")
    buffer.seek(0)
    return buffer.getvalue()


def parquet_bytes_to_climate_df(content):
    """Lee Parquet comprimido y lo convierte al histórico climático interno."""
    buffer = io.BytesIO(content)
    df = pd.read_parquet(buffer, engine="pyarrow")

    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    df = df[CANONICAL_COLUMNS].copy()
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"], errors="coerce")
    for col in CANONICAL_COLUMNS:
        if col != "fecha_hora":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return compact_history(df)


def upload_climate_snapshot_to_supabase(df, status_box=None):
    """Sube un snapshot Parquet comprimido rápido a Supabase Storage."""
    if not supabase_is_configured():
        return False, "Supabase no está configurado. Revisa SUPABASE_URL y SUPABASE_KEY en Secrets."

    if df is None or df.empty:
        return False, "No hay histórico climático válido para crear el snapshot."

    if status_box is not None:
        status_box.info(f"Preparando snapshot de {len(df):,} registros...".replace(",", "."))

    try:
        content = climate_df_to_parquet_bytes(df)
    except Exception as exc:
        return False, f"No se pudo crear el Parquet comprimido: {exc}"

    if not content:
        return False, "No hay histórico climático válido para crear el snapshot."

    size_mb = len(content) / (1024 * 1024)

    if status_box is not None:
        status_box.info(f"Snapshot creado en memoria: {size_mb:.2f} MB. Subiendo a Supabase Storage...")

    endpoint = climate_snapshot_storage_url()
    headers = supabase_headers()
    headers["Content-Type"] = "application/octet-stream"
    headers["x-upsert"] = "true"

    try:
        response = requests.post(endpoint, headers=headers, data=content, timeout=120)
    except Exception as exc:
        return False, f"No se pudo subir el snapshot a Supabase Storage: {exc}"

    if response.status_code not in (200, 201):
        return False, f"Error subiendo snapshot a Supabase Storage: {response.status_code} · {response.text[:500]} · Endpoint: {endpoint}"

    return True, f"Snapshot climático comprimido creado/actualizado correctamente: {size_mb:.2f} MB."


@st.cache_data(ttl=600, show_spinner=False)
def cached_download_climate_snapshot(normalized_url, key, bucket, path, cache_buster=0):
    """Descarga el snapshot comprimido desde Storage. cache_buster fuerza recarga cuando cambia."""
    endpoint = f"{normalized_url.rstrip('/')}/storage/v1/object/{bucket}/{path.lstrip('/')}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }

    response = requests.get(endpoint, headers=headers, timeout=180)
    if response.status_code != 200:
        return None, f"Error descargando snapshot: {response.status_code} · {response.text[:500]} · Endpoint: {endpoint}"

    return response.content, f"Snapshot descargado correctamente: {len(response.content) / (1024 * 1024):.2f} MB."


def load_climate_snapshot_from_supabase(use_cache=True):
    """Carga el histórico climático completo desde el snapshot comprimido."""
    if not supabase_is_configured():
        return pd.DataFrame(columns=CANONICAL_COLUMNS), "Supabase no está configurado. Revisa SUPABASE_URL y SUPABASE_KEY en Secrets."

    normalized_url, key = get_supabase_credentials()

    if not use_cache:
        cached_download_climate_snapshot.clear()

    content, msg = cached_download_climate_snapshot(
        normalized_url,
        key,
        SUPABASE_SNAPSHOT_BUCKET,
        SUPABASE_FULL_CLIMATE_SNAPSHOT,
        int(time.time()) if not use_cache else 0,
    )

    if not content:
        return pd.DataFrame(columns=CANONICAL_COLUMNS), msg

    try:
        df = parquet_bytes_to_climate_df(content)
    except Exception as exc:
        return pd.DataFrame(columns=CANONICAL_COLUMNS), f"Snapshot descargado, pero no se pudo leer como Parquet: {exc}"

    return df, f"{msg} · Histórico cargado desde snapshot: {len(df)} registros."


def get_climate_snapshot_info():
    """Obtiene metadatos básicos del objeto snapshot si existe."""
    if not supabase_is_configured():
        return False, "Supabase no está configurado.", ""

    endpoint = climate_snapshot_metadata_url()
    headers = supabase_headers()
    headers.pop("Prefer", None)

    try:
        response = requests.get(endpoint, headers=headers, timeout=30)
    except Exception as exc:
        return False, f"No se pudo consultar el snapshot: {exc}", endpoint

    if response.status_code == 200:
        try:
            data = response.json()
        except Exception:
            data = {}
        size = data.get("metadata", {}).get("size") or data.get("size")
        updated = data.get("updated_at") or data.get("last_accessed_at") or ""
        size_txt = f"{float(size) / (1024 * 1024):.2f} MB" if size else "tamaño no disponible"
        return True, f"Snapshot existente: {size_txt}. Última actualización: {updated or 'no disponible'}", endpoint

    return False, f"No se encontró snapshot o no hay permisos de lectura: {response.status_code} · {response.text[:300]}", endpoint


def build_climate_snapshot_preview(df):
    """Crea el snapshot en memoria para comprobar tamaño/tiempo sin subirlo."""
    if df is None or df.empty:
        return False, "No hay histórico climático válido para crear el snapshot.", None

    start_time = time.time()
    try:
        content = climate_df_to_parquet_bytes(df)
    except Exception as exc:
        return False, f"No se pudo crear el snapshot local: {exc}", None

    elapsed = time.time() - start_time
    if not content:
        return False, "No se generó contenido para el snapshot.", None

    size_mb = len(content) / (1024 * 1024)
    return True, f"Snapshot local creado: {len(df):,} registros · {size_mb:.2f} MB · {elapsed:.1f} s".replace(",", "."), content


def render_climate_snapshot_panel():
    st.markdown("### Snapshot comprimido del histórico climático")

    st.caption(
        "Este sistema carga todo el histórico desde un único archivo Parquet comprimido en Supabase Storage. "
        "Es mucho más eficiente que descargar miles de filas por la API REST."
    )

    with st.expander("Estado del snapshot comprimido", expanded=False):
        st.write(f"Bucket esperado: `{SUPABASE_SNAPSHOT_BUCKET}`")
        st.write(f"Archivo esperado: `{SUPABASE_FULL_CLIMATE_SNAPSHOT}`")
        if st.button("Comprobar snapshot climático", use_container_width=True):
            ok, msg, endpoint = get_climate_snapshot_info()
            if ok:
                st.success(msg)
            else:
                st.warning(msg)
                st.caption(f"Endpoint consultado: {endpoint}")

    col_snap_1, col_snap_2 = st.columns(2)

    with col_snap_1:
        hist = st.session_state.get("history_df", pd.DataFrame(columns=CANONICAL_COLUMNS))

        if st.button("Probar creación local del snapshot", use_container_width=True):
            with st.spinner("Creando snapshot local de prueba..."):
                ok, msg, content = build_climate_snapshot_preview(hist)
            if ok:
                st.success(msg)
                st.download_button(
                    "Descargar snapshot local de prueba",
                    data=content,
                    file_name=SUPABASE_FULL_CLIMATE_SNAPSHOT,
                    mime="application/octet-stream",
                    use_container_width=True,
                )
            else:
                st.error(msg)

        if st.button("Crear/actualizar snapshot climático comprimido", use_container_width=True):
            status_box = st.empty()
            with st.spinner("Creando y subiendo snapshot climático comprimido..."):
                ok, msg = upload_climate_snapshot_to_supabase(hist, status_box=status_box)
                cached_download_climate_snapshot.clear()
            if ok:
                status_box.success(msg)
            else:
                status_box.error(msg)

    with col_snap_2:
        if st.button("Cargar histórico completo desde snapshot", use_container_width=True, type="primary"):
            with st.spinner("Descargando y leyendo snapshot climático comprimido..."):
                cloud_df, msg = load_climate_snapshot_from_supabase(use_cache=True)
            if cloud_df.empty:
                st.warning(msg)
            else:
                st.session_state.history_df = cloud_df
                st.session_state.applied_period = None
                st.success(msg)
                st.rerun()

        if st.button("Limpiar caché y recargar snapshot", use_container_width=True):
            with st.spinner("Forzando descarga nueva del snapshot climático..."):
                cloud_df, msg = load_climate_snapshot_from_supabase(use_cache=False)
            if cloud_df.empty:
                st.warning(msg)
            else:
                st.session_state.history_df = cloud_df
                st.session_state.applied_period = None
                st.success(msg)
                st.rerun()



def render_supabase_climate_panel():
    st.markdown("### Modo nube Supabase")

    if supabase_is_configured():
        st.success("Supabase configurado correctamente en Secrets.")
    else:
        st.warning(
            "Supabase todavía no está configurado. Añade SUPABASE_URL y SUPABASE_KEY en los Secrets de Streamlit."
        )

    with st.expander("Comprobar conexión Supabase", expanded=False):
        normalized_url, _ = get_supabase_credentials()
        st.write(f"URL normalizada usada por la app: `{normalized_url or 'No configurada'}`")
        st.write(f"Endpoint esperado: `{supabase_table_url() if normalized_url else 'No disponible'}`")
        if st.button("Probar conexión con climate_hourly", use_container_width=True):
            ok, msg, endpoint = test_supabase_climate_connection()
            if ok:
                st.success(msg)
            else:
                st.error(msg)
                st.caption(f"Endpoint probado: {endpoint}")

    # ── Selector: Snapshot vs Supabase REST ──────────────────────────────────
    st.markdown("#### ¿Cómo quieres cargar el histórico climático?")
    metodo_carga = st.radio(
        "Método de carga",
        [
            "📦 Snapshot comprimido (rápido, recomendado)",
            "🔗 Tabla Supabase REST (completo, más lento)",
        ],
        horizontal=True,
        key="supabase_climate_load_method",
        label_visibility="collapsed",
        help=(
            "Snapshot: descarga un Parquet comprimido desde Supabase Storage. "
            "Tabla REST: descarga directamente de la tabla climate_hourly fila a fila."
        ),
    )

    if metodo_carga.startswith("📦"):
        render_climate_snapshot_panel()
    else:
        st.caption("Descarga directamente de la tabla `climate_hourly` en Supabase. Útil como respaldo o para depuración.")

        col_cloud_1, col_cloud_2 = st.columns(2)

        with col_cloud_1:
            if st.button("Cargar histórico desde tabla Supabase REST", use_container_width=True, type="primary"):
                with st.spinner("Cargando histórico climático desde Supabase..."):
                    cloud_df, msg = load_climate_from_supabase(use_cache=True)
                if cloud_df.empty:
                    st.warning(msg)
                else:
                    st.session_state.history_df = cloud_df
                    st.session_state.applied_period = None
                    st.success(msg)
                    st.rerun()

        with col_cloud_2:
            if st.button("Limpiar caché y recargar desde tabla REST", use_container_width=True):
                with st.spinner("Limpiando caché y recargando histórico climático desde Supabase..."):
                    cached_load_climate_from_supabase.clear()
                    cloud_df, msg = load_climate_from_supabase(use_cache=False)
                if cloud_df.empty:
                    st.warning(msg)
                else:
                    st.session_state.history_df = cloud_df
                    st.session_state.applied_period = None
                    st.success(msg)
                    st.rerun()

    with st.expander("Cómo usar Supabase con el histórico climático", expanded=False):
        st.markdown(
            """
            **Flujo recomendado para histórico completo:**

            1. Después de importar o guardar datos nuevos, pulsa **Crear/actualizar snapshot climático comprimido**.
            2. En próximas sesiones, usa **Cargar histórico completo desde snapshot**.
            3. Deja la carga desde tabla `climate_hourly` como respaldo o para depuración.

            **Flujo recomendado para actualizaciones:**

            1. Sube CSV nuevos de Sencrop como siempre.
            2. Pulsa **Guardar histórico actual en Supabase** para actualizar la tabla.
            3. Pulsa **Crear/actualizar snapshot climático comprimido** para regenerar el archivo rápido.

            La tabla usa `fecha_hora` como clave principal. Si una hora ya existe, se actualiza; si no existe, se añade.
            """
        )

    st.divider()
    hist = st.session_state.get("history_df", pd.DataFrame(columns=CANONICAL_COLUMNS))
    if st.button("Guardar histórico actual en Supabase", use_container_width=True, type="primary"):
        ok, msg = upsert_climate_to_supabase(hist)
        if ok:
            st.success(msg)
        else:
            st.error(msg)




# ═══════════════════════════════════════════════════════════════════════════════
# SENCROP · Integración directa via API
# ═══════════════════════════════════════════════════════════════════════════════

SENCROP_API_BASE = "https://api.sencrop.com/v1"
SENCROP_API_INFRA = "https://sencrop-api-production.infra.sencrop.com"

# Mapa de medidas Sencrop → columnas internas de la app
# El endpoint devuelve sub-metricas: temperature:interpolated, temperature:min, temperature:max
# humidity:interpolated, rain:sum, etc.
SENCROP_MEASURE_MAP = {
    "temperature":          "temp_media",
    "temperature_min":      "temp_min",
    "temperature_max":      "temp_max",
    "relativeHumidity":     "hr_media",
    "relativeHumidity_min": "hr_min",
    "relativeHumidity_max": "hr_max",
    "irradiance":           "irradiancia",
    "windSpeed":            "viento_velocidad",
    "windGust":             "viento_rafaga",
    "windDirection":        "viento_direccion",
    "leafWetness":          "humectacion_hoja",
    "rainfall":             "lluvia_mm",
}

SENCROP_SENSORS = [
    {
        "id":       "11653",
        "ref":      "RC0028091",
        "nombre":   "Temperatura / Humedad / Lluvia",
        "measures": ["temperature", "relativeHumidity", "rainfall"],
    },
    {
        "id":       "26768",
        "ref":      "WC007301",
        "nombre":   "Viento",
        # windGust primero: si la estación expone la ráfaga real, tiene prioridad
        # sobre el máximo de windSpeed para rellenar viento_rafaga.
        "measures": ["windGust", "windSpeed", "windDirection"],
    },
    {
        "id":       "16899",
        "ref":      "LC001544",
        "nombre":   "Humectacion de hoja",
        "measures": ["leafWetness"],
    },
    {
        "id":       "59258",
        "ref":      "SL001609",
        "nombre":   "Radiacion solar",
        "measures": ["irradiance"],
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# Predicción meteorológica — Sencrop (endpoint /app/forecast/sencrop-mode-data)
# ═══════════════════════════════════════════════════════════════════════════════

SENCROP_FORECAST_URL = f"https://sencrop-api-production.infra.sencrop.com/app/forecast/sencrop-mode-data"
SENCROP_MODELS_URL   = f"https://sencrop-api-production.infra.sencrop.com/app/forecast/models-mode-data"

# Organización e ID del sensor principal (temperatura/lluvia/HR de Finca Gallinal)
_FC_ORG_ID    = "17094"
_FC_STATION   = "11653"   # SENCROP_SENSORS[0]["id"]


def sencrop_download_forecast(token, model="sencrop"):
    """
    Descarga la predicción meteorológica horaria de Sencrop.

    model="sencrop"   → endpoint sencrop-mode-data  (Previsión Sencrop, fusión de modelos)
    model="meteoblue" → endpoint models-mode-data    (Meteoblue BASIC_MLM)

    Estructura de respuesta (confirmada via DevTools):
      data.scaledForecasts.hourly.days[i].timeSeries[j]:
        date                      → "2026-05-17T11:00:00+02:00"
        metrics.temperatureInCelsius
        metrics.relativeHumidityInPercent
        metrics.rainfallSumInMm
        metrics.windSpeedInKmh
        metrics.windGustInKmh       (puede estar ausente)
        metrics.leafWetnessInPercent (puede estar ausente — sensor 16899)

    Devuelve (df, error) con columnas CANONICAL_COLUMNS.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Origin":        "https://app.sencrop.com",
        "Referer":       "https://app.sencrop.com/",
        "User-Agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":        "application/json",
    }

    if model == "meteoblue":
        url    = SENCROP_MODELS_URL
        params = {
            "organisationId": _FC_ORG_ID,
            "modelId":        "BASIC_MLM",
            "type":           "station",
            "stationId":      _FC_STATION,
        }
    else:
        url    = SENCROP_FORECAST_URL
        params = {
            "organisationId": _FC_ORG_ID,
            "stationId":      _FC_STATION,
        }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=25)
    except Exception as e:
        return pd.DataFrame(), f"Error de conexión con Sencrop: {e}"

    if r.status_code in (401, 403) or "JWT_EXPIRED" in r.text:
        return pd.DataFrame(), "TOKEN_EXPIRED"
    if r.status_code != 200:
        return pd.DataFrame(), f"Sencrop respondió HTTP {r.status_code}: {r.text[:300]}"

    try:
        data = r.json()
    except Exception as e:
        return pd.DataFrame(), f"Error parseando JSON de Sencrop: {e}"

    inner      = data.get("data", {})
    hourly_days = inner.get("scaledForecasts", {}).get("hourly", {}).get("days", [])

    if not hourly_days:
        return pd.DataFrame(), "La respuesta de Sencrop no contiene datos horarios (scaledForecasts.hourly.days vacío)."

    rows = []
    for day in hourly_days:
        for item in day.get("timeSeries", []):
            date_str = item.get("date")
            if not date_str:
                continue
            try:
                dt = pd.to_datetime(date_str, utc=True).tz_convert("Europe/Madrid").tz_localize(None)
            except Exception:
                continue

            m = item.get("metrics", {})
            # Campos confirmados via DevTools (17/05/2026):
            #   maxWindGustInKmh, rainfallSumInMm, relativeHumidityInPercent,
            #   temperatureInCelsius, windDirectionInDegree, windSpeedInKmh
            # leafWetnessInPercent NO está en este endpoint → se estimará después
            rows.append({
                "fecha_hora":        dt,
                "temp_media":        m.get("temperatureInCelsius"),
                "hr_media":          m.get("relativeHumidityInPercent"),
                "lluvia_mm":         m.get("rainfallSumInMm"),
                "viento_velocidad":  m.get("windSpeedInKmh"),
                "viento_rafaga":     m.get("maxWindGustInKmh"),
                "viento_direccion":  m.get("windDirectionInDegree"),
                "humectacion_hoja":  None,   # se estimará en forecast_build_risk_table
            })

    if not rows:
        return pd.DataFrame(), "timeSeries vacío en todos los días de la predicción."

    df = pd.DataFrame(rows)
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    df = df[CANONICAL_COLUMNS].copy()

    # Solo filas desde ahora-2h en adelante
    cutoff = pd.Timestamp.now() - pd.Timedelta(hours=2)
    df = df[df["fecha_hora"] >= cutoff]

    df = df.sort_values("fecha_hora").drop_duplicates("fecha_hora").reset_index(drop=True)
    return df, None


# ── Modelos de riesgo aplicados sobre datos de predicción ─────────────────────

def forecast_build_risk_table(forecast_df, history_df, base_temp=10.0, upper_temp=31.1):
    """
    Aplica los modelos de riesgo (Mills moteado, Monilia, DD carpocapsa)
    sobre el DataFrame de predicción fusionado con el histórico reciente.
    Devuelve un DataFrame diario con columnas de riesgo para los próximos días.
    """
    if forecast_df is None or forecast_df.empty:
        return pd.DataFrame()

    # Fusionar: últimas 72h de histórico real + predicción
    if history_df is not None and not history_df.empty:
        cutoff = pd.Timestamp.now() - pd.Timedelta(hours=72)
        hist_recent = history_df[pd.to_datetime(history_df["fecha_hora"]) >= cutoff].copy()
        combined = pd.concat([hist_recent, forecast_df], ignore_index=True)
        combined = combined.drop_duplicates("fecha_hora", keep="last")
        combined = combined.sort_values("fecha_hora").reset_index(drop=True)
    else:
        combined = forecast_df.copy()

    combined["fecha_hora"] = pd.to_datetime(combined["fecha_hora"])
    combined["_fecha"] = combined["fecha_hora"].dt.date

    rows = []
    for fecha, grupo in combined.groupby("_fecha"):
        if pd.Timestamp(fecha) < pd.Timestamp.now().normalize():
            continue  # Solo días futuros/hoy

        temp_med  = pd.to_numeric(grupo["temp_media"],  errors="coerce").mean()
        temp_min  = pd.to_numeric(grupo["temp_min"],    errors="coerce").min()
        temp_max  = pd.to_numeric(grupo["temp_max"],    errors="coerce").max()
        hr_med    = pd.to_numeric(grupo["hr_media"],    errors="coerce").mean()
        lluvia    = pd.to_numeric(grupo["lluvia_mm"],   errors="coerce").sum()
        horas_hum = int(pd.to_numeric(grupo["humectacion_hoja"], errors="coerce").fillna(0).gt(0).sum())
        # Estimar horas mojadura desde lluvia + HR si no hay sensor de hoja
        if horas_hum == 0 and (lluvia > 0 or (pd.notna(hr_med) and hr_med > 90)):
            horas_hum_est = int(lluvia > 0) * min(int(lluvia * 1.5), 8) + (2 if pd.notna(hr_med) and hr_med > 90 else 0)
        else:
            horas_hum_est = horas_hum

        # ── Riesgo moteado (tabla de Mills simplificada) ──────────────────────
        # Temp media durante período húmedo + horas mojadura
        riesgo_moteado = _mills_risk(temp_med, horas_hum_est)

        # ── Riesgo monilia ────────────────────────────────────────────────────
        # Condición: T > 15°C + HR > 85% + lluvia o humedad hoja
        riesgo_monilia = _monilia_risk(temp_med, hr_med, lluvia, horas_hum_est)

        # ── DD carpocapsa del día ─────────────────────────────────────────────
        dd_dia = 0.0
        if pd.notna(temp_med):
            dd_dia = max(0.0, min(float(temp_med), float(upper_temp)) - base_temp)

        rows.append({
            "Fecha":                   fecha,
            "T. min/máx (°C)":         f"{temp_min:.1f}/{temp_max:.1f}" if pd.notna(temp_min) and pd.notna(temp_max) else "—",
            "T. media (°C)":           round(float(temp_med), 1) if pd.notna(temp_med) else None,
            "HR media (%)":            round(float(hr_med),   1) if pd.notna(hr_med)   else None,
            "Lluvia prev. (mm)":       round(float(lluvia),   1) if pd.notna(lluvia)   else 0.0,
            "Horas mojadura":          horas_hum if horas_hum > 0 else horas_hum_est,
            "Fuente mojadura":         "sensor" if horas_hum > 0 else "estimada",
            "Riesgo moteado":          riesgo_moteado,
            "Riesgo monilia":          riesgo_monilia,
            "DD carpocapsa previstos": round(dd_dia, 1),
        })

    return pd.DataFrame(rows)


def _mills_risk(temp_c, horas_mojadura):
    """Tabla de Mills simplificada: devuelve nivel de riesgo de infección primaria."""
    if pd.isna(temp_c) or horas_mojadura == 0:
        return "🟢 Sin riesgo"
    t = float(temp_c)
    h = int(horas_mojadura)
    # Tabla Mills: (T °C) → horas mínimas de mojadura para infección ligera / moderada / grave
    # Fuente: Mills & Laplante 1951, adaptación práctica
    if t < 6 or t > 28:
        return "🟢 Sin riesgo"
    mills = [
        (6,  28, 18),   # T ≥ 6°C: 28h ligera / 18h moderada   (ojo: poco probable con lluvia)
        (7,  21, 14),
        (8,  18, 12),
        (9,  15, 11),
        (10, 12, 9),
        (11, 11, 8),
        (12, 10, 7),
        (13, 9,  6),
        (14, 8,  6),
        (15, 8,  5),
        (16, 7,  5),
        (17, 7,  5),
        (18, 6,  5),
        (19, 6,  4),
        (20, 6,  4),
        (21, 6,  4),
        (22, 7,  4),
        (23, 8,  5),
        (24, 9,  6),
        (25, 10, 7),
        (26, 12, 8),
        (27, 15, 10),
    ]
    row = next((r for r in mills if int(r[0]) == int(round(t))), None)
    if row is None:
        return "🟢 Sin riesgo"
    _, h_ligera, h_grave = row
    if h >= h_ligera:
        return "🔴 Infección grave"
    if h >= h_grave:
        return "🟠 Infección moderada"
    if h >= max(h_grave - 2, 1):
        return "🟡 Riesgo ligero"
    return "🟢 Sin riesgo"


def _monilia_risk(temp_c, hr, lluvia_mm, horas_mojadura):
    """Riesgo de monilia basado en temperatura, humedad y mojadura."""
    if pd.isna(temp_c):
        return "🟢 Sin riesgo"
    t   = float(temp_c)
    h   = float(hr)   if pd.notna(hr)       else 0.0
    ll  = float(lluvia_mm) if pd.notna(lluvia_mm) else 0.0
    hm  = int(horas_mojadura)

    if t < 15 or t > 30:
        return "🟢 Sin riesgo"
    if h > 90 and hm >= 6 and 18 <= t <= 28:
        return "🔴 Riesgo alto"
    if (h > 85 and hm >= 3) or (ll > 3 and 18 <= t <= 28):
        return "🟠 Riesgo moderado"
    if h > 80 or ll > 0:
        return "🟡 Riesgo ligero"
    return "🟢 Sin riesgo"


def forecast_cumulative_dd(forecast_df, history_df, biofix_date, base_temp=10.0, upper_temp=31.1):
    """
    Calcula DD acumulados desde biofix incluyendo la predicción.
    Devuelve un DataFrame con Fecha y DD_acumulados para mostrar la evolución prevista.
    """
    if forecast_df is None or forecast_df.empty:
        return pd.DataFrame()

    # Histórico desde biofix
    if history_df is not None and not history_df.empty and biofix_date is not None:
        hist_desde_biofix = history_df[
            pd.to_datetime(history_df["fecha_hora"]) >= pd.Timestamp(biofix_date)
        ].copy()
        combined = pd.concat([hist_desde_biofix, forecast_df], ignore_index=True)
        combined = combined.drop_duplicates("fecha_hora", keep="last")
    else:
        combined = forecast_df.copy()

    combined["fecha_hora"] = pd.to_datetime(combined["fecha_hora"])
    combined["temp_media"] = pd.to_numeric(combined["temp_media"], errors="coerce")
    combined["_fecha"] = combined["fecha_hora"].dt.date

    daily = (
        combined.groupby("_fecha")["temp_media"]
        .mean()
        .reset_index()
        .rename(columns={"_fecha": "Fecha", "temp_media": "_T_media"})
    )
    daily["_T_media"] = daily["_T_media"].clip(upper=float(upper_temp))
    daily["DD_dia"] = (daily["_T_media"] - base_temp).clip(lower=0)
    daily["DD_acumulados"] = daily["DD_dia"].cumsum().round(1)

    # Marcar qué días son predicción
    today = pd.Timestamp.now().normalize().date()
    daily["Tipo"] = daily["Fecha"].apply(lambda d: "Predicción" if d >= today else "Real")

    return daily[["Fecha", "DD_dia", "DD_acumulados", "Tipo"]].copy()


def sencrop_is_configured():
    try:
        app_id     = st.secrets.get("SENCROP_APP_ID", "")
        app_secret = st.secrets.get("SENCROP_APP_SECRET", "")
        # Compatibilidad con token manual antiguo
        token = st.secrets.get("SENCROP_TOKEN", "")
        return bool((app_id and app_secret) or token)
    except Exception:
        return False


def sencrop_get_token_from_secrets():
    """
    Obtiene token de acceso oficial via OAuth2 client_credentials.
    Usa APPLICATION_ID + APPLICATION_SECRET para obtener un Bearer token
    que no caduca en horas sino en semanas.
    Fallback: token manual SENCROP_TOKEN si existe.
    """
    try:
        app_id     = st.secrets.get("SENCROP_APP_ID", "").strip()
        app_secret = st.secrets.get("SENCROP_APP_SECRET", "").strip()

        if app_id and app_secret:
            # Cachear token en session_state para no pedir uno nuevo en cada rerun
            cached = st.session_state.get("_sencrop_oauth_token")
            if cached:
                return cached
            try:
                r = requests.post(
                    "https://api.sencrop.com/v1/oauth2/token",
                    auth=(app_id, app_secret),
                    json={"grant_type": "client_credentials", "scope": "user"},
                    timeout=30,
                )
                if r.status_code == 200:
                    token = r.json().get("access_token", "")
                    if token:
                        st.session_state["_sencrop_oauth_token"] = token
                        return token
            except Exception:
                pass

        # Fallback: token manual
        token = st.secrets.get("SENCROP_TOKEN", "").strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        return token if token else None
    except Exception:
        return None


def _sencrop_user_from_jwt(token: str) -> str:
    """
    Extrae el user_id del payload JWT de Sencrop sin verificar la firma
    (solo lectura del campo 'sub', que Sencrop usa como ID numérico de usuario).
    Devuelve cadena vacía si el token no es un JWT válido.
    """
    try:
        import base64 as _b64, json as _json
        parts = token.split(".")
        if len(parts) < 2:
            return ""
        payload_b64 = parts[1]
        # Restaurar padding Base64url → Base64
        padding = (4 - len(payload_b64) % 4) % 4
        payload_b64 += "=" * padding
        payload = _json.loads(_b64.b64decode(payload_b64))
        # Sencrop usa 'sub' como ID numérico de usuario
        uid = payload.get("sub") or payload.get("userId") or payload.get("user_id") or ""
        return str(uid) if uid else ""
    except Exception:
        return ""


def render_sencrop_panel():
    """Panel de integración directa con Sencrop en la pestaña Importación."""
    st.markdown("### 🌦️ Importar datos directamente desde Sencrop")

    if not sencrop_is_configured():
        st.warning(
            "Para activar la importación directa desde Sencrop, añade en **Secrets** de Streamlit:\n\n"
            "**Opción A — Token directo (recomendado):**\n"
            "```toml\n"
            "SENCROP_TOKEN = \"tu_token_aqui\"\n"
            "SENCROP_USER_ID = \"tu_user_id\"\n"
            "```\n\n"
            "**Opción B — Usuario y contraseña:**\n"
            "```toml\n"
            "SENCROP_EMAIL = \"tu_email@ejemplo.com\"\n"
            "SENCROP_PASSWORD = \"tu_contraseña\"\n"
            "```"
        )
        return

    if "sencrop_token"   not in st.session_state: st.session_state.sencrop_token   = None
    if "sencrop_user_id" not in st.session_state: st.session_state.sencrop_user_id = None
    if "sencrop_devices" not in st.session_state: st.session_state.sencrop_devices = []

    # ── Auto-conectar: siempre relee el token de Secrets ─────────────────────
    # Esto permite que al actualizar el token en Secrets y pulsar recargar,
    # la app lo recoja sin necesidad de reiniciar el servidor.
    direct_token = sencrop_get_token_from_secrets()
    if direct_token:
        st.session_state.sencrop_token = direct_token
        # Intentar leer user_id de Secrets
        _stored_uid = ""
        try:
            _stored_uid = str(st.secrets.get("SENCROP_USER_ID", "")).strip()
        except Exception:
            pass
        # Decodificar JWT para obtener el user_id real del token (sin llamada de red)
        _jwt_uid = _sencrop_user_from_jwt(direct_token)
        if _jwt_uid:
            # El JWT tiene user_id → tiene prioridad sobre el guardado en Secrets
            st.session_state.sencrop_user_id = _jwt_uid
            if _stored_uid and _stored_uid != _jwt_uid:
                st.warning(
                    f"⚠️ El User ID en Secrets (`{_stored_uid}`) no coincide con el del token "
                    f"(`{_jwt_uid}`). La app usará `{_jwt_uid}` automáticamente. "
                    f"Actualiza `SENCROP_USER_ID = \"{_jwt_uid}\"` en Secrets para eliminar este aviso."
                )
        else:
            st.session_state.sencrop_user_id = _stored_uid or None

    # ── Estado de conexión ────────────────────────────────────────────────────
    if st.session_state.sencrop_token and direct_token:
        st.success("✅ Conectado con Sencrop via token (Secrets). La descarga de datos está operativa.")
    elif st.session_state.sencrop_token:
        st.success("✅ Conectado con Sencrop.")

    col1, col2 = st.columns(2)
    with col1:
        # Solo mostrar botón de login si NO hay token directo en Secrets
        if not direct_token:
            if st.button("🔌 Conectar con Sencrop (email+contraseña)", use_container_width=True, type="primary"):
                with st.spinner("Autenticando en Sencrop..."):
                    auth, err = sencrop_login()
                if err:
                    st.error(err)
                else:
                    st.session_state.sencrop_token   = auth["token"]
                    st.session_state.sencrop_user_id = auth["user_id"]
                    devices, err2 = sencrop_get_devices(auth["token"], auth["user_id"])
                    st.session_state.sencrop_devices = devices if not err2 else []
                    if err2:
                        st.warning(f"Conectado, pero no se listaron estaciones: {err2}")
                    else:
                        st.success(f"Conectado. {len(devices)} estación(es) detectada(s).")

    with col2:
        if st.session_state.sencrop_token and not direct_token:
            if st.button("🔓 Desconectar", use_container_width=True):
                st.session_state.sencrop_token   = None
                st.session_state.sencrop_user_id = None
                st.session_state.sencrop_devices = []
                st.rerun()

    if not st.session_state.sencrop_token:
        st.info("Añade SENCROP_TOKEN en Secrets para conectar automáticamente.")
        return

    # ── Obtener user_id si no lo tenemos ─────────────────────────────────────
    if not st.session_state.sencrop_user_id:
        with st.spinner("Obteniendo datos de usuario..."):
            try:
                r = requests.get(
                    f"{SENCROP_API_BASE}/users/me",
                    headers={"Authorization": f"Bearer {st.session_state.sencrop_token}"},
                    timeout=15,
                )
                if r.status_code == 200:
                    data = r.json()
                    uid = (data.get("userId") or data.get("id")
                           or (data.get("user") or {}).get("id"))
                    st.session_state.sencrop_user_id = str(uid) if uid else None
                else:
                    st.warning(f"No se pudo obtener el user_id automáticamente ({r.status_code}). "
                               "Añade SENCROP_USER_ID en Secrets.")
            except Exception as e:
                st.warning(f"Error obteniendo user_id: {e}")

    if not st.session_state.sencrop_user_id:
        st.error("Falta el User ID de Sencrop. Añade `SENCROP_USER_ID = \"tu_id\"` en Secrets.")
        st.caption("Puedes encontrar tu User ID en la URL de Sencrop cuando navegas por la app, "
                   "por ejemplo: api.sencrop.com/v1/users/**12345**/devices")
        return

    # ── Cargar estaciones si no las tenemos ───────────────────────────────────
    if not st.session_state.sencrop_devices:
        with st.spinner("Cargando estaciones..."):
            devices, err = sencrop_get_devices(
                st.session_state.sencrop_token,
                st.session_state.sencrop_user_id,
            )
        if err:
            # Con token de aplicación (OAuth2) el listado de dispositivos falla
            # (E_USER_MISMATCH / E_NON_REENTRANT_NUMBER) pero la descarga de datos
            # funciona perfectamente porque usa los IDs hardcodeados de SENCROP_SENSORS.
            # Solo mostrar advertencia si no es un error de tipo de token esperado.
            _err_str = str(err)
            _token_type_error = any(
                k in _err_str for k in ("E_USER_MISMATCH", "E_NON_REENTRANT", "401", "400")
            )
            if not _token_type_error:
                st.warning(f"No se listaron estaciones automáticamente: {err}")
            # Fallback: usar station IDs conocidas (la descarga sigue funcionando)
            st.session_state.sencrop_devices = [{"id": "11653", "name": "Finca Gallinal"}]
        else:
            st.session_state.sencrop_devices = devices

    # ── Info sensores + diagnóstico ──────────────────────────────────────────
    with st.expander("📡 Sensores configurados", expanded=False):
        for s in SENCROP_SENSORS:
            st.write(f"- **{s['nombre']}** (ID: `{s['id']}`) → {', '.join(s['measures'])}")

    with st.expander("🔍 Diagnóstico: listar mis dispositivos en Sencrop", expanded=False):
        st.caption("Muestra todos los dispositivos asociados a tu cuenta con sus IDs reales.")
        # Mostrar user_id detectado vs almacenado
        _diag_jwt_uid = _sencrop_user_from_jwt(st.session_state.sencrop_token or "")
        _diag_stored  = ""
        try:
            _diag_stored = str(st.secrets.get("SENCROP_USER_ID", "")).strip()
        except Exception:
            pass
        st.markdown(
            f"- **User ID en Secrets:** `{_diag_stored or '—'}`\n"
            f"- **User ID detectado del JWT:** `{_diag_jwt_uid or '(no disponible)'}`\n"
            f"- **User ID activo en sesión:** `{st.session_state.get('sencrop_user_id', '—')}`"
        )
        if _diag_jwt_uid and _diag_stored and _diag_jwt_uid != _diag_stored:
            st.error(
                f"❌ **E_USER_MISMATCH**: El token pertenece al usuario `{_diag_jwt_uid}` "
                f"pero Secrets tiene `SENCROP_USER_ID = \"{_diag_stored}\"`. "
                f"Actualiza Secrets con `SENCROP_USER_ID = \"{_diag_jwt_uid}\"` o elimina esa línea."
            )
        if st.button("Consultar mis dispositivos", key="sencrop_list_devices"):
            headers_dbg = {"Authorization": f"Bearer {st.session_state.sencrop_token}"}
            uid = st.session_state.sencrop_user_id
            for url in [
                f"{SENCROP_API_BASE}/users/{uid}/devices",
                f"{SENCROP_API_BASE}/users/me",
                f"{SENCROP_API_INFRA}/app/station/measurement-page/measurements/hourly"
                f"?organisationId=17094&stationId=11653&measures=temperature"
                f"&startDatetime=2026-05-28T00:00:00.000%2B02:00"
                f"&endDatetime=2026-05-28T23:59:59.999%2B02:00&enableFilling=true",
            ]:
                try:
                    r = requests.get(url, headers=headers_dbg, timeout=30)
                    st.write(f"**URL:** `{url[:80]}...` → Status: {r.status_code}")
                    if r.status_code == 200:
                        try:
                            data = r.json()
                            st.json(data if isinstance(data, dict) else {"devices": data[:5]})
                        except Exception:
                            st.code(r.text[:500])
                    else:
                        try:
                            resp_json = r.json()
                            err_code = (resp_json.get("error") or {}).get("code", "")
                            if err_code == "E_USER_MISMATCH":
                                st.error(f"❌ E_USER_MISMATCH — actualiza SENCROP_USER_ID a `{_diag_jwt_uid}`")
                            elif err_code == "JWT_EXPIRED" or r.status_code == 401:
                                st.error("❌ Token caducado — actualiza SENCROP_TOKEN en Secrets")
                            else:
                                st.json(resp_json)
                        except Exception:
                            st.code(r.text[:300])
                except Exception as e:
                    st.write(f"Error: {e}")

    st.info("ℹ️ Para descargar datos, ve a la pestaña **⬇️ Actualizar datos**.")



def render_sencrop_forecast_panel():
    """Panel de predicción meteorológica Sencrop + modelos de riesgo sanitario."""
    st.markdown("### 🔭 Predicción meteorológica — Próximos días")

    if not st.session_state.get("sencrop_token"):
        st.info("ℹ️ Conecta Sencrop arriba para acceder a la predicción.")
        return

    st.caption(
        "Predicción horaria de **Sencrop** (fusión de múltiples modelos meteorológicos, "
        "calibrada con los datos de tu estación). "
        "Se aplican modelos de riesgo agronómico: Mills moteado, Monilia y DD carpocapsa. "
        "La hoja mojada se toma del sensor si está disponible; si no, se estima desde lluvia y HR previstas."
    )

    modelo_fc = st.radio(
        "Modelo de predicción",
        ["⭐ Previsión Sencrop (fusión de modelos)", "📊 Meteoblue BASIC_MLM"],
        horizontal=True,
        key="forecast_model_selector",
        label_visibility="collapsed",
    )
    model_key = "sencrop" if modelo_fc.startswith("⭐") else "meteoblue"
    base_temp_fc  = 10.0
    upper_temp_fc = 31.1

    label_btn = "⭐ Previsión Sencrop" if model_key == "sencrop" else "📊 Meteoblue BASIC_MLM"
    if st.button(f"⬇️ Descargar {label_btn}", type="primary", use_container_width=True, key="btn_download_forecast"):
        with st.spinner(f"Consultando predicción Sencrop ({label_btn})..."):
            forecast_df, err = sencrop_download_forecast(
                token=st.session_state.sencrop_token,
                model=model_key,
            )
        if err == "TOKEN_EXPIRED":
            st.error("🔑 Token caducado. Actualiza SENCROP_TOKEN en Secrets y recarga la app.")
            return
        if err:
            st.error(f"No se pudo obtener la predicción: {err}")
            return

        st.session_state["forecast_df"]    = forecast_df
        st.session_state["forecast_model"] = label_btn
        st.success(
            f"✅ Predicción descargada ({label_btn}): {len(forecast_df)} registros horarios · "
            f"Período: {pd.to_datetime(forecast_df['fecha_hora']).min().strftime('%d/%m %Hh')} → "
            f"{pd.to_datetime(forecast_df['fecha_hora']).max().strftime('%d/%m %Hh')}"
        )
        st.rerun()

    # ── Mostrar resultados si ya hay predicción en sesión ─────────────────────
    forecast_df = st.session_state.get("forecast_df", pd.DataFrame())
    if forecast_df.empty:
        st.info("Pulsa el botón para descargar la predicción y calcular el riesgo.")
        return

    history_df = st.session_state.get("history_df", pd.DataFrame())

    # ── Tabla de riesgo diario ────────────────────────────────────────────────
    risk_df = forecast_build_risk_table(
        forecast_df, history_df,
        base_temp=float(base_temp_fc),
        upper_temp=float(upper_temp_fc),
    )

    if risk_df.empty:
        st.warning("No se pudo calcular el riesgo. Revisa que el histórico climático esté cargado.")
        return

    st.markdown("#### 🗓️ Riesgo sanitario previsto")

    # Semáforo resumen
    max_moteado = _max_risk_level(risk_df["Riesgo moteado"].tolist())
    max_monilia = _max_risk_level(risk_df["Riesgo monilia"].tolist())
    sm1, sm2, sm3 = st.columns(3)
    sm1.metric("Peor riesgo moteado (7d)",  max_moteado)
    sm2.metric("Peor riesgo monilia (7d)",  max_monilia)
    sm3.metric("DD carpocapsa previstos",
               f"{risk_df['DD carpocapsa previstos'].sum():.1f} DD")

    # Alerta proactiva
    high_risk_days = risk_df[risk_df["Riesgo moteado"].str.contains("🔴|🟠")]
    if not high_risk_days.empty:
        dias_alerta = ", ".join(str(d) for d in high_risk_days["Fecha"].head(3))
        st.error(
            f"⚠️ **Período de infección probable:** {dias_alerta}. "
            "Considera tratar antes del primer día de riesgo alto."
        )

    # Tabla HTML con primera columna sticky (funciona en móvil al hacer scroll horizontal)
    def _risk_bg(val):
        s = str(val)
        if "🔴" in s: return "#ffe0e0"
        if "🟠" in s: return "#fff0d0"
        if "🟡" in s: return "#ffffd0"
        return ""

    _cols_risk = list(risk_df.columns)
    _th_base = ("background:#1a2e1e;color:white;padding:8px 12px;"
                "white-space:nowrap;font-weight:600;font-size:13px;")
    _th_sticky = "position:sticky;left:0;z-index:2;" + _th_base

    _header_html = "".join(
        f'<th style="{_th_sticky if i == 0 else _th_base}">{c}</th>'
        for i, c in enumerate(_cols_risk)
    )

    _body_html = ""
    for _, _r in risk_df.iterrows():
        _cells = ""
        for _i, _c in enumerate(_cols_risk):
            _v = _r[_c]
            # Formato: float → 1 decimal, resto → str
            _disp = (f"{_v:.1f}" if isinstance(_v, float) and not pd.isna(_v)
                     else ("—" if (isinstance(_v, float) and pd.isna(_v)) else str(_v)))
            _col_bg = _risk_bg(_v) if _c in ("Riesgo moteado", "Riesgo monilia") else (
                "#eef2ee" if _i == 0 else "white"
            )
            _td_style = (
                f"{'position:sticky;left:0;z-index:1;' if _i == 0 else ''}"
                f"background:{_col_bg};"
                f"padding:7px 12px;border-bottom:1px solid #e8e8e8;"
                f"white-space:nowrap;font-size:13px;"
            )
            _cells += f"<td style='{_td_style}'>{_disp}</td>"
        _body_html += f"<tr>{_cells}</tr>"

    st.markdown(
        f'<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;'
        f'border-radius:8px;border:1px solid #ddd;margin-bottom:1rem;">'
        f'<table style="border-collapse:collapse;width:100%;">'
        f'<thead><tr>{_header_html}</tr></thead>'
        f'<tbody>{_body_html}</tbody>'
        f'</table></div>',
        unsafe_allow_html=True,
    )

    # ── Datos horarios crudos ─────────────────────────────────────────────────
    def _deg_to_cardinal(deg):
        try:
            if pd.isna(deg): return "—"
            # 8 puntos cardinales/intercardinales: más intuitivos para el usuario
            dirs = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
            return dirs[round(float(deg) / 45) % 8]
        except Exception:
            return str(deg)

    with st.expander("📋 Datos horarios de predicción (raw)", expanded=False):
        cols_show = [c for c in CANONICAL_COLUMNS if c in forecast_df.columns and
                     not forecast_df[c].isna().all()]
        display_fc = forecast_df[cols_show].copy()
        # Dirección del viento: grados → cardinal
        if "viento_direccion" in display_fc.columns:
            display_fc["viento_direccion"] = display_fc["viento_direccion"].apply(_deg_to_cardinal)
        # Redondear a 1 decimal: temperatura y viento
        for _col in ("temp_media", "temp_min", "temp_max", "viento_velocidad", "viento_rafaga"):
            if _col in display_fc.columns:
                display_fc[_col] = display_fc[_col].round(1)
        st.dataframe(display_fc, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Descargar predicción CSV",
            data=forecast_df[cols_show].to_csv(index=False).encode("utf-8-sig"),
            file_name=f"prediccion_sencrop_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
        )


def _max_risk_level(risk_list):
    """Devuelve el nivel de riesgo más alto de una lista."""
    for level in ["🔴 Infección grave", "🔴 Riesgo alto", "🟠 Infección moderada",
                  "🟠 Riesgo moderado", "🟡 Riesgo ligero", "🟡 Riesgo ligero"]:
        if any(level in r for r in risk_list):
            return level
    return "🟢 Sin riesgo"


def sencrop_get_devices(token, user_id):
    """Lista los dispositivos del usuario."""
    # Intentar con Authorization Bearer primero, luego con cookie
    headers = {
        "Authorization": f"Bearer {token}",
        "Origin": "https://app.sencrop.com",
        "Referer": "https://app.sencrop.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    # También añadir como cookie por si acaso
    try:
        sencrop_cookies = st.secrets.get("SENCROP_COOKIES", "")
        if sencrop_cookies:
            headers["Cookie"] = sencrop_cookies
    except Exception:
        pass
    try:
        r = requests.get(
            f"{SENCROP_API_BASE}/users/{user_id}/devices",
            headers=headers, timeout=30,
        )
    except Exception as e:
        return [], f"Error obteniendo dispositivos: {e}"
    if r.status_code != 200:
        return [], f"Error {r.status_code}: {r.text[:300]}"
    data = r.json()
    devices = data.get("devices", data if isinstance(data, list) else [])
    return devices, None


def sencrop_get_statistics(token, user_id, device_id, start_date, end_date, measures=None):
    """
    Descarga datos horarios usando el endpoint interno de Sencrop.
    Nombres de medidas confirmados: temperature, relativeHumidity, irradiance,
    windSpeed, windGust, windDirection, leafWetness.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Origin": "https://app.sencrop.com",
        "Referer": "https://app.sencrop.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    if measures is None:
        measures = list(dict.fromkeys(  # sin duplicados
            m for s in SENCROP_SENSORS for m in s["measures"]
        ))

    start_ts    = pd.Timestamp(start_date)
    end_ts      = pd.Timestamp(end_date)
    # Sencrop devuelve VACÍO si se le pide un rango muy estrecho (1-2 días) de fechas
    # recientes, aunque haya datos. Por eso pedimos a la API un rango de al menos
    # 7 días (req_start_ts) y luego recortamos la salida al rango solicitado
    # (start_ts/end_ts). Esto hace fiable tanto la descarga manual como la automática.
    req_start_ts = min(start_ts, end_ts - pd.Timedelta(days=6))
    chunk_size  = 30
    date_map    = {}
    current_end = end_ts

    # Columnas para sub-metricas :min y :max por medida
    measure_min_col = {
        "temperature":      "temp_min",
        "relativeHumidity": "hr_min",
    }
    measure_max_col = {
        "temperature":      "temp_max",
        "relativeHumidity": "hr_max",
        # La ráfaga es, por definición, el pico de viento del intervalo. Sencrop
        # suele exponerla como el máximo: tanto si llega como "windGust:max" como
        # "windSpeed:max", la guardamos en viento_rafaga (antes se descartaba y por
        # eso la ráfaga salía siempre vacía/nan).
        "windGust":         "viento_rafaga",
        "windSpeed":        "viento_rafaga",
    }

    while current_end >= req_start_ts:
        days_chunk  = min(chunk_size, (current_end - req_start_ts).days + 1)
        chunk_start = current_end - pd.Timedelta(days=days_chunk - 1)
        tz_offset   = "+02:00"

        for measure in measures:
            app_col = SENCROP_MEASURE_MAP.get(measure)
            if not app_col:
                continue

            params = [
                ("organisationId", "17094"),
                ("stationId",      device_id),
                ("startDatetime",  chunk_start.strftime(f"%Y-%m-%dT00:00:00.000{tz_offset}")),
                ("endDatetime",    current_end.strftime(f"%Y-%m-%dT23:59:59.999{tz_offset}")),
                ("measures",       measure),
                ("enableFilling",  "true"),
            ]

            try:
                r = requests.get(
                    f"{SENCROP_API_INFRA}/app/station/measurement-page/measurements/hourly",
                    headers=headers, params=params, timeout=60,
                )
            except Exception:
                continue

            if r.status_code == 401:
                if "E_USER_MISMATCH" in r.text:
                    return pd.DataFrame(), "USER_MISMATCH"
                return pd.DataFrame(), "TOKEN_EXPIRED"
            if "JWT_EXPIRED" in r.text:
                return pd.DataFrame(), "TOKEN_EXPIRED"
            if r.status_code != 200:
                continue

            try:
                data = r.json()
            except Exception:
                continue

            station_data = (data.get("response") or data).get("stationMeasurements") or {}
            # La clave en stationMeasurements coincide con el nombre de medida
            metric_list  = station_data.get(measure, [])

            for metric_block in metric_list:
                if not isinstance(metric_block, dict):
                    continue
                metric_name = metric_block.get("metric", "")

                # Determinar columna destino segun sufijo
                if metric_name.endswith(":min"):
                    col = measure_min_col.get(measure)
                elif metric_name.endswith(":max"):
                    col = measure_max_col.get(measure)
                else:
                    # interpolated, sum, u otro → columna media
                    col = app_col

                if not col:
                    continue

                for item in metric_block.get("timeseries", []):
                    ts_ms = item.get("timestamp")
                    val   = item.get("value")
                    if ts_ms is None:
                        continue
                    ts_key = str(ts_ms)
                    if ts_key not in date_map:
                        date_map[ts_key] = {"fecha_hora": pd.to_datetime(int(ts_ms), unit="ms", utc=True)}
                    if val is not None and col not in date_map[ts_key]:
                        date_map[ts_key][col] = pd.to_numeric(val, errors="coerce")

        current_end -= pd.Timedelta(days=days_chunk)

    if not date_map:
        return pd.DataFrame(), None

    df = pd.DataFrame(list(date_map.values()))
    df["fecha_hora"] = (pd.to_datetime(df["fecha_hora"], utc=True)
                        .dt.tz_convert("Europe/Madrid")
                        .dt.tz_localize(None))
    df = df[(df["fecha_hora"] >= start_ts) &
            (df["fecha_hora"] <= end_ts + pd.Timedelta(hours=23))]
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    df = df[CANONICAL_COLUMNS].copy()
    return df.sort_values("fecha_hora").drop_duplicates("fecha_hora").reset_index(drop=True), None

def sencrop_download_all_sensors(token, user_id, start_date, end_date, status_placeholder=None):
    """
    Descarga los 4 sensores de Finca Gallinal y los combina en un unico DataFrame horario.
    Cada sensor aporta sus columnas; se fusionan por fecha_hora.
    """
    frames = []
    errors = []
    for sensor in SENCROP_SENSORS:
        if status_placeholder:
            status_placeholder.info(f"Descargando {sensor['nombre']}...")
        df, err = sencrop_get_statistics(
            token, user_id,
            sensor["id"], start_date, end_date,
            measures=sensor["measures"],
        )
        if err in ("TOKEN_EXPIRED", "USER_MISMATCH"):
            return pd.DataFrame(), [err]
        elif err:
            errors.append(f"Aviso {sensor['nombre']}: {err}")
        elif not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame(), errors

    combined = pd.concat(frames, ignore_index=True)
    merged = combined.groupby("fecha_hora", as_index=False).agg(
        {col: "last" for col in CANONICAL_COLUMNS if col != "fecha_hora"}
    )
    merged = merged.sort_values("fecha_hora").reset_index(drop=True)
    return merged, errors


def import_panel():
    # ── Inicialización silenciosa: auto-conectar desde Secrets ───────────────
    if "sencrop_token"   not in st.session_state: st.session_state.sencrop_token   = None
    if "sencrop_user_id" not in st.session_state: st.session_state.sencrop_user_id = None
    if "sencrop_devices" not in st.session_state: st.session_state.sencrop_devices = []
    if sencrop_is_configured():
        _direct = sencrop_get_token_from_secrets()
        if _direct:
            st.session_state.sencrop_token = _direct
            _imp_stored_uid = ""
            try:
                _imp_stored_uid = str(st.secrets.get("SENCROP_USER_ID", "")).strip()
            except Exception:
                pass
            # Priorizar el user_id extraído del JWT sobre el guardado en Secrets
            _imp_jwt_uid = _sencrop_user_from_jwt(_direct)
            if _imp_jwt_uid:
                st.session_state.sencrop_user_id = _imp_jwt_uid
            else:
                st.session_state.sencrop_user_id = _imp_stored_uid or None

    tab_prev, tab_act, tab_con = st.tabs(["📡 Previsión", "⬇️ Actualizar datos", "⚙️ Conexión"])

    # ── TAB 1: PREVISIÓN ──────────────────────────────────────────────────────
    with tab_prev:
        render_sencrop_forecast_panel()

    # ── TAB 2: ACTUALIZAR DATOS ───────────────────────────────────────────────
    with tab_act:
        token   = st.session_state.get("sencrop_token")
        user_id = st.session_state.get("sencrop_user_id")

        # ── Sección Sencrop ──────────────────────────────────────────────────
        st.markdown("#### 🌦️ Descargar desde Sencrop")
        if not token:
            st.info("ℹ️ Conecta Sencrop en la pestaña ⚙️ **Conexión** para descargar datos.")
        elif not user_id:
            st.info("ℹ️ Configura el User ID en la pestaña ⚙️ **Conexión**.")
        else:
            hist  = st.session_state.get("history_df", pd.DataFrame(columns=CANONICAL_COLUMNS))
            today = pd.Timestamp.today().date()
            if not hist.empty and "fecha_hora" in hist.columns:
                last_date     = pd.to_datetime(hist["fecha_hora"]).max().date()
                default_start = last_date
                st.caption(f"Último dato en histórico: **{last_date}**. Por defecto se descarga desde esa fecha.")
            else:
                default_start = today - pd.Timedelta(days=30)
                st.caption("Sin histórico cargado. Se descargarán los últimos 30 días por defecto.")

            quick = st.selectbox(
                "Periodo rápido",
                ["Personalizado", "Últimos 7 días", "Últimos 15 días", "Últimos 30 días",
                 "Últimos 3 meses", "Últimos 6 meses", "Año actual completo"],
                key="sencrop_quick_period",
            )
            if   quick == "Últimos 7 días":      dl_start, dl_end = today - pd.Timedelta(days=7),   today
            elif quick == "Últimos 15 días":     dl_start, dl_end = today - pd.Timedelta(days=15),  today
            elif quick == "Últimos 30 días":     dl_start, dl_end = today - pd.Timedelta(days=30),  today
            elif quick == "Últimos 3 meses":     dl_start, dl_end = today - pd.Timedelta(days=90),  today
            elif quick == "Últimos 6 meses":     dl_start, dl_end = today - pd.Timedelta(days=180), today
            elif quick == "Año actual completo": dl_start, dl_end = pd.Timestamp(today.year, 1, 1).date(), today
            else:
                dc3, dc4 = st.columns(2)
                with dc3: dl_start = st.date_input("Desde", value=default_start, key="sencrop_start")
                with dc4: dl_end   = st.date_input("Hasta", value=today,         key="sencrop_end")

            st.caption(f"Se descargarán datos del **{dl_start}** al **{dl_end}** de los 4 sensores.")

            merge_mode_sc = st.radio(
                "Modo",
                ["Actualizar reemplazando fechas existentes", "Añadir solo datos nuevos"],
                horizontal=True, key="sencrop_merge_mode",
            )

            if st.button("⬇️ Descargar e importar los 4 sensores de Sencrop", type="primary", use_container_width=True):
                status = st.empty()
                df_sencrop, sensor_errors = sencrop_download_all_sensors(
                    token, user_id, dl_start, dl_end, status_placeholder=status,
                )
                status.empty()
                if sensor_errors == ["USER_MISMATCH"]:
                    _mismatch_jwt = _sencrop_user_from_jwt(token or "")
                    st.error(
                        f"❌ **E_USER_MISMATCH** — El token pertenece a un usuario diferente al configurado. "
                        + (f"El token corresponde al usuario `{_mismatch_jwt}`. " if _mismatch_jwt else "")
                        + f"Actualiza `SENCROP_USER_ID = \"{_mismatch_jwt or '???'}\"` en Secrets."
                    )
                    if st.button("🔄 Ya actualicé Secrets — recargar ahora", use_container_width=True, key="sencrop_reload_mismatch"):
                        st.rerun()
                elif sensor_errors == ["TOKEN_EXPIRED"]:
                    st.error("🔑 El token de Sencrop ha caducado. Actualiza SENCROP_TOKEN en Secrets y pulsa el botón de abajo.")
                    st.session_state.sencrop_token = None
                    if st.button("🔄 Ya actualicé el token en Secrets — recargar ahora", use_container_width=True, key="sencrop_reload_token"):
                        st.rerun()
                elif sensor_errors:
                    for e in sensor_errors:
                        st.warning(e)
                elif df_sencrop.empty:
                    st.warning("No se obtuvieron datos de ningún sensor para ese periodo.")
                else:
                    base = st.session_state.get("history_df", pd.DataFrame(columns=CANONICAL_COLUMNS))
                    if base.empty:
                        final_sc = compact_history(df_sencrop)
                    elif merge_mode_sc == "Añadir solo datos nuevos":
                        existing = set(pd.to_datetime(base["fecha_hora"]).dropna())
                        only_new = df_sencrop[~pd.to_datetime(df_sencrop["fecha_hora"]).isin(existing)]
                        final_sc = compact_history(pd.concat([base, only_new], ignore_index=True))
                    else:
                        final_sc = compact_history(pd.concat([base, df_sencrop], ignore_index=True))
                    st.session_state.history_df     = final_sc
                    st.session_state.applied_period = None
                    rng_min = pd.to_datetime(final_sc["fecha_hora"]).min().date()
                    rng_max = pd.to_datetime(final_sc["fecha_hora"]).max().date()
                    st.success(
                        f"✅ {len(df_sencrop)} registros combinados de los 4 sensores. "
                        f"Histórico total: **{len(final_sc)}** registros ({rng_min} → {rng_max})."
                    )
                    # Guardado automático del snapshot en Supabase (sin pasos manuales)
                    autosave_climate_snapshot_to_supabase()

        # ── Sección Supabase ─────────────────────────────────────────────────
        st.divider()
        with st.expander("☁️ Guardar/cargar desde Supabase (nube)", expanded=False):
            st.caption("La app carga el histórico automáticamente al abrirse. Usa estos botones solo si necesitas forzar una actualización o guardar datos nuevos importados.")
            render_supabase_climate_panel()

        # ── Sección CSV ──────────────────────────────────────────────────────
        st.divider()
        st.markdown("#### 📁 Importar desde CSV")
        master_file = st.file_uploader(
            "Opcional: subir histórico maestro",
            type=["csv"],
            accept_multiple_files=False,
            key="master_history_tab",
        )
        new_files = st.file_uploader(
            "Subir nuevos CSV de sensores",
            type=["csv"],
            accept_multiple_files=True,
            key="new_sensor_files_tab",
        )
        import_mode = st.radio(
            "Modo de importación",
            [
                "Reemplazar histórico actual con los archivos subidos",
                "Añadir solo datos nuevos, sin sobrescribir fechas existentes",
                "Actualizar histórico reemplazando coincidencias por fecha/hora",
            ],
            index=2,
            help=(
                "Para trabajar con el mes actual completo, usa la tercera opción. "
                "Si una fecha/hora ya existe, se conserva el dato del CSV nuevo. "
                "Si no existe, se añade."
            ),
        )
        with st.expander("Qué hace cada modo", expanded=False):
            st.markdown(
                """
                **Reemplazar histórico actual con los archivos subidos**
                Borra el histórico de la sesión y usa solo el histórico maestro y/o los CSV que subas ahora.

                **Añadir solo datos nuevos, sin sobrescribir fechas existentes**
                Añade únicamente las horas que no existen todavía. Si una fecha/hora ya existe, se conserva el dato antiguo.

                **Actualizar histórico reemplazando coincidencias por fecha/hora**
                Recomendado para subir el mes actual completo. Si una fecha/hora ya existe, se reemplaza por el dato del CSV nuevo. Si no existe, se añade.
                """
            )

        col1, col2 = st.columns(2)
        with col1:
            do_import = st.button("Importar / actualizar histórico", type="primary")
        with col2:
            clear = st.button("Limpiar histórico de esta sesión")

        if clear:
            st.session_state.history_df = pd.DataFrame(columns=CANONICAL_COLUMNS)
            st.session_state.last_import_errors = []
            st.session_state.last_import_diagnostics = []
            st.session_state.applied_period = None
            st.rerun()

        if do_import:
            errors = []
            diagnostics = []
            before_df    = st.session_state.history_df.copy()
            before_count = len(before_df)
            before_hours = set(before_df["fecha_hora"].dropna()) if not before_df.empty and "fecha_hora" in before_df.columns else set()

            master_df, master_errors = load_master_history(master_file)
            errors.extend(master_errors)
            if master_file is not None:
                diagnostics.append(diagnose_csv_file(master_file.name, master_file.getvalue()))

            new_df, new_errors = merge_new_files(new_files or [])
            errors.extend(new_errors)
            for f in new_files or []:
                diagnostics.append(diagnose_csv_file(f.name, f.getvalue()))

            master_df = compact_history(master_df) if not master_df.empty else pd.DataFrame(columns=CANONICAL_COLUMNS)
            new_df    = compact_history(new_df)    if not new_df.empty    else pd.DataFrame(columns=CANONICAL_COLUMNS)
            new_hours = set(new_df["fecha_hora"].dropna()) if not new_df.empty and "fecha_hora" in new_df.columns else set()

            if not master_df.empty:
                base_df = master_df
            else:
                base_df = before_df
            base_df    = compact_history(base_df) if not base_df.empty else pd.DataFrame(columns=CANONICAL_COLUMNS)
            base_hours = set(base_df["fecha_hora"].dropna()) if not base_df.empty and "fecha_hora" in base_df.columns else set()

            if import_mode == "Reemplazar histórico actual con los archivos subidos":
                frames = []
                if not master_df.empty: frames.append(master_df)
                if not new_df.empty:    frames.append(new_df)
                final_df = compact_history(pd.concat(frames, ignore_index=True)) if frames else pd.DataFrame(columns=CANONICAL_COLUMNS)
            elif import_mode == "Añadir solo datos nuevos, sin sobrescribir fechas existentes":
                frames = [base_df] if not base_df.empty else []
                if not new_df.empty:
                    only_new = new_df[~new_df["fecha_hora"].isin(base_hours)].copy()
                    if not only_new.empty: frames.append(only_new)
                final_df = compact_history(pd.concat(frames, ignore_index=True)) if frames else pd.DataFrame(columns=CANONICAL_COLUMNS)
            else:
                frames = []
                if not base_df.empty: frames.append(base_df)
                if not new_df.empty:  frames.append(new_df)
                final_df = compact_history(pd.concat(frames, ignore_index=True)) if frames else pd.DataFrame(columns=CANONICAL_COLUMNS)

            after_hours    = set(final_df["fecha_hora"].dropna()) if not final_df.empty and "fecha_hora" in final_df.columns else set()
            added_hours    = len(after_hours - base_hours)
            updated_hours  = len(new_hours & base_hours) if import_mode == "Actualizar histórico reemplazando coincidencias por fecha/hora" else 0
            ignored_existing = len(new_hours & base_hours) if import_mode == "Añadir solo datos nuevos, sin sobrescribir fechas existentes" else 0

            st.session_state.history_df            = final_df
            st.session_state.last_import_errors    = errors
            st.session_state.last_import_diagnostics = diagnostics
            st.session_state.applied_period        = None

            st.success("Importación finalizada.")
            st.write(f"Registros antes: **{before_count}** · registros después: **{len(final_df)}**.")
            if import_mode == "Actualizar histórico reemplazando coincidencias por fecha/hora":
                st.write(f"Horas nuevas añadidas: **{added_hours}** · horas existentes actualizadas/reemplazadas: **{updated_hours}**.")
            elif import_mode == "Añadir solo datos nuevos, sin sobrescribir fechas existentes":
                st.write(f"Horas nuevas añadidas: **{added_hours}** · horas ya existentes ignoradas: **{ignored_existing}**.")
            else:
                st.write("El histórico de la sesión ha sido sustituido por los archivos subidos.")

    # ── TAB 3: CONEXIÓN ───────────────────────────────────────────────────────
    with tab_con:
        render_sencrop_panel()


def period_selector(history):
    min_dt = history["fecha_hora"].min()
    max_dt = history["fecha_hora"].max()
    years_available = sorted(history["fecha_hora"].dt.year.unique())

    # ── Auto-análisis al abrir la app: últimos 7 días disponibles ────────────
    if st.session_state.get("applied_period") is None:
        st.session_state.applied_period = {
            "mode": "Última semana disponible",
            "start_ts": max_dt - pd.Timedelta(days=6),
            "end_ts": max_dt,
            "selected_chill_year": None,
            "selected_season": None,
        }

    # ── Modo FUERA del form → rerender instantáneo al cambiar (solo UI, sin análisis) ──
    st.markdown("#### Selección de periodo")
    mode_input = st.selectbox(
        "Modo de selección",
        ["Periodo personalizado", "Última semana disponible", "Último mes disponible", "Año natural"],
        index=1,
        key="ps_mode_selector",
    )

    # Qué campos están activos según el modo
    is_custom   = mode_input == "Periodo personalizado"
    is_year     = mode_input == "Año natural"
    dates_off   = not is_custom   # fechas desactivadas si no es personalizado
    year_off    = not is_year     # año desactivado si no es año natural

    with st.form("period_selection_form_v60"):
        col_a, col_b = st.columns(2)
        with col_a:
            start_date_input = st.date_input(
                "Fecha inicio",
                value=(max_dt - pd.Timedelta(days=6)).date(),
                min_value=min_dt.date(),
                max_value=max_dt.date(),
                disabled=dates_off,
            )
        with col_b:
            end_date_input = st.date_input(
                "Fecha fin",
                value=max_dt.date(),
                min_value=min_dt.date(),
                max_value=max_dt.date(),
                disabled=dates_off,
            )

        selected_year_input = st.selectbox(
            "Año natural",
            years_available,
            index=len(years_available) - 1,
            disabled=year_off,
        )

        submitted = st.form_submit_button("Analizar periodo", type="primary")

    if submitted:
        if mode_input == "Periodo personalizado":
            start_ts = pd.Timestamp(start_date_input)
            end_ts   = pd.Timestamp(end_date_input) + pd.Timedelta(hours=23)

        elif mode_input == "Última semana disponible":
            end_ts   = max_dt
            start_ts = max_dt - pd.Timedelta(days=6)

        elif mode_input == "Último mes disponible":
            end_ts   = max_dt
            start_ts = max_dt - pd.Timedelta(days=30)

        else:  # Año natural
            start_ts = pd.Timestamp(int(selected_year_input), 1, 1)
            end_ts   = pd.Timestamp(int(selected_year_input), 12, 31, 23)

        if end_ts < start_ts:
            st.error("La fecha final no puede ser anterior a la fecha inicial.")
            return None

        st.session_state.applied_period = {
            "mode": mode_input,
            "start_ts": start_ts,
            "end_ts":   end_ts,
            "selected_chill_year": None,
            "selected_season":     None,
        }

    return st.session_state.applied_period


def get_period_data(history, soil_type, hoja_threshold):
    period = st.session_state.applied_period
    if period is None:
        return None, None, None, None, None

    start_ts = period["start_ts"]
    end_ts = period["end_ts"]

    period_df = history[(history["fecha_hora"] >= start_ts) & (history["fecha_hora"] <= end_ts)].copy()
    if period_df.empty:
        return period, period_df, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    period_df = add_risk_columns(period_df, hoja_humeda_threshold=hoja_threshold)
    avail = availability_table(period_df, start_ts, end_ts)
    summary = weekly_summary(period_df, soil_type)
    global_summary = period_summary(period_df, soil_type, start_ts, end_ts)
    return period, period_df, avail, summary, global_summary



def instructions_tab():
    st.subheader("Instrucciones de uso · Finca Gallinal")

    st.markdown(
        """
        ## 1. Al abrir la app — carga automática

        Desde la versión actual la app **carga automáticamente al arrancar** (si Supabase está configurado):

        - 📦 **Histórico climático** — snapshot comprimido desde Supabase Storage
        - 🧾 **Agroptima** — actuaciones / tratamientos desde la tabla Supabase
        - 🍎 **Producción** — histórico de producción desde Supabase Storage
        - 🐛 **Carpocapsa** — capturas, biofix y daños desde Supabase Storage

        No hay que pulsar ningún botón para cargar estos datos en una sesión normal.
        Si algo no cargó, ir a la pestaña correspondiente y usar el botón de carga manual.
        """
    )

    with st.expander("¿Qué es el snapshot climático?", expanded=False):
        st.markdown(
            """
            El snapshot climático es un archivo Parquet comprimido con todo el histórico.
            Es mucho más rápido que descargar filas de la tabla REST.

            - **Snapshot (recomendado):** descarga el archivo comprimido de una vez.
            - **Tabla Supabase REST:** descarga fila a fila; útil como respaldo o para depuración.

            En la pestaña **Sencrop** puedes elegir entre ambos métodos con el selector de carga.
            """
        )

    st.markdown(
        """
        ## 2. Actualizar el histórico climático con datos nuevos de Sencrop

        Cuando haya datos nuevos de la estación:

        1. Ir a la pestaña **🌦️ Sencrop**.
        2. Seleccionar el periodo a descargar (o usar "Últimos 7 días").
        3. Pulsar **⬇️ Descargar e importar los 4 sensores de Sencrop**.
        4. Pulsar **Guardar histórico actual en Supabase**.
        5. Pulsar **Crear/actualizar snapshot climático comprimido**.

        El orden importa: actualizar tabla y después regenerar el snapshot para que la próxima carga automática use los datos nuevos.
        """
    )

    with st.expander("Botones de la sección Supabase en Sencrop", expanded=False):
        st.markdown(
            """
            | Botón | Para qué sirve | Cuándo usarlo |
            |---|---|---|
            | **Cargar histórico completo desde snapshot** | Carga el Parquet comprimido. | Carga manual si no arrancó sola. |
            | **Limpiar caché y recargar snapshot** | Fuerza descarga nueva del snapshot. | Si sospechas datos desactualizados. |
            | **Crear/actualizar snapshot climático comprimido** | Sube el histórico actualizado como Parquet. | Después de añadir datos nuevos. |
            | **Guardar histórico actual en Supabase** | Guarda en la tabla `climate_hourly`. | Después de importar datos nuevos. |
            | **Cargar histórico desde tabla Supabase REST** | Carga directa de la tabla, fila a fila. | Respaldo o depuración. |
            """
        )

    st.markdown(
        """
        ## 3. Agroptima (actuaciones y tratamientos)

        La pestaña **🧾 Agroptima** gestiona el histórico de tratamientos y actuaciones importado desde Agroptima.

        Flujo recomendado cuando hay un Excel nuevo de Agroptima:

        1. Ir a **🧾 Agroptima**.
        2. Subir el Excel de Agroptima en el apartado de importación.
        3. Revisar la vista previa y pulsar **Importar / actualizar histórico de actuaciones**.
        4. Pulsar **Guardar actuaciones actuales en Supabase**.

        Las actuaciones se usan en:

        - **🍄 Sanidad** — cruza humectaciones y riesgo con tratamientos recientes.
        - **🐛 Carpocapsa** — detecta tratamientos de carpocapsa y calcula DD entre captura y tratamiento.
        - **Informe semanal** — incluye tratamientos del periodo.
        """
    )

    st.markdown(
        """
        ## 4. Carpocapsa

        La pestaña **🐛 Carpocapsa** integra capturas de trampas, biofix, grados-día y tratamientos.

        **Lógica de DD entre lectura y tratamiento (sección 6):**

        - Se busca cada lectura de trampa con capturas ≥ umbral configurado.
        - Para cada una, se localiza el **primer tratamiento de carpocapsa** registrado en Agroptima para ese campo, **estrictamente posterior** a la fecha de lectura.
        - Se acumulan los DD desde la lectura hasta el tratamiento.
        - Los DD se dejan de contar a partir del tratamiento.
        - **Rango esperado:** 90–140 DD. Valores fuera de 80–160 DD son excepcionales.

        La detección de tratamientos de carpocapsa usa keywords específicas (Bactur, Madex, Cydia, etc.).
        Tratamientos genéricos (fungicidas, herbicidas, abonos) no se cuentan como tratamientos de carpocapsa.

        Flujo habitual de campaña:

        1. Importar el Excel de capturas (pestaña 0 de Carpocapsa).
        2. Configurar o revisar el biofix.
        3. Revisar la sección de grados-día acumulados desde biofix.
        4. Revisar la sección DD entre lectura y tratamiento.
        5. Guardar snapshot en Supabase al finalizar la campaña.
        """
    )

    st.markdown(
        """
        ## 5. Producción

        La pestaña **🍎 Producción** carga el histórico de producción automáticamente desde Supabase.

        Para añadir un año nuevo:

        1. Ir a **🍎 Producción**.
        2. Subir el Excel de producción (una hoja por año).
        3. Pulsar **⬆️ Guardar en Supabase**.
        """
    )

    st.markdown(
        """
        ## 6. Sanidad y recomendaciones de tratamiento

        En **🍄 Sanidad** la app muestra:

        - Eventos de hoja mojada y humectación.
        - Riesgo de moteado (Venturia inaequalis).
        - Riesgo de monilia y oídio.
        - Cruce con tratamientos recientes de Agroptima.
        - Recomendación técnica de tratamiento por campo y fase fenológica.

        Las recomendaciones tienen en cuenta grupo FRAC, rotación y último tratamiento por campo.
        """
    )

    st.warning(
        "Las recomendaciones de tratamiento son orientativas. "
        "Antes de aplicar cualquier producto verifica etiqueta, registro oficial, dosis, plazo de seguridad, "
        "número máximo de aplicaciones, compatibilidad de mezclas y normativa vigente."
    )

    with st.expander("Resumen de pestañas", expanded=True):
        st.markdown(
            """
            | Pestaña | Función principal |
            |---|---|
            | **📘 Instrucciones** | Flujo de uso de la app. |
            | **📊 Dashboard** | Vista general del histórico climático y sensores. |
            | **🌦️ Sencrop** | Importar datos de la estación + gestión Supabase climático. |
            | **🔎 Análisis** | Resumen climático-agronómico por periodo seleccionado. |
            | **🌱 Fenología** | Configuración y lectura de fases fenológicas de campaña. |
            | **❄️ Frío** | Horas frío, unidades Utah y porciones de frío por campaña. |
            | **📈 Comparador** | Comparación entre campañas, semanas o meses. |
            | **🍄 Sanidad** | Humectaciones, riesgo sanitario y recomendaciones de tratamiento. |
            | **🐛 Carpocapsa** | Capturas, biofix, grados-día y cruce con tratamientos. |
            | **💧 Riego** | Demanda evaporativa y recomendación orientativa de riego. |
            | **🌳 Campos** | Base de campos, superficies y variedades. |
            | **🧾 Agroptima** | Histórico de actuaciones y tratamientos desde Agroptima. |
            | **🍎 Producción** | Histórico y análisis de producción por variedad y campo. |
            | **📝 Informe semanal** | Generación de informe semanal en PDF con logo. |
            | **⚙️ Configuración** | Suelo, umbrales, catálogo de productos y parámetros. |
            """
        )

    st.markdown(
        """
        ## 7. Flujo semanal recomendado

        1. Abrir la app — los datos se cargan automáticamente.
        2. Ir a **🌦️ Sencrop** → descargar los últimos días → guardar en Supabase → actualizar snapshot.
        3. Si hay Excel nuevo de Agroptima → importarlo en **🧾 Agroptima** → guardar en Supabase.
        4. Revisar **📊 Dashboard** — comprobar fecha final del histórico.
        5. Revisar **🔎 Análisis** del periodo semanal.
        6. Revisar **🍄 Sanidad** y recomendaciones por campo.
        7. Revisar **🐛 Carpocapsa** si es temporada de vuelo.
        8. Generar **📝 Informe semanal** PDF.
        """
    )

    with st.expander("Problemas frecuentes", expanded=False):
        st.markdown(
            """
            **El histórico climático está vacío al abrir la app**
            Ve a **Sencrop** → elige "Snapshot comprimido" → pulsa "Cargar histórico completo desde snapshot".

            **Los datos de Agroptima no aparecen en Carpocapsa o Sanidad**
            Ve a **Agroptima** → pulsa "Cargar actuaciones desde Supabase". Si ya hay datos en sesión, comprueba que la campaña del selector coincide.

            **Los DD entre lectura y tratamiento parecen incorrectos**
            Verifica que el tratamiento está guardado en Agroptima con un nombre de producto de carpocapsa reconocido (Bactur, Madex, Cydia, etc.). Tratamientos genéricos no se cuentan.

            **La carga desde tabla Supabase REST es lenta**
            Es normal con muchos registros. Usa el snapshot (método por defecto).

            **El informe PDF no refleja datos nuevos**
            Comprueba que el Dashboard muestra la fecha final correcta antes de generar el informe.
            """
        )

    st.caption("v8.9.7 · Finca Gallinal · Plataforma agroclimática")



def dashboard_tab(history, soil_type, hoja_threshold):
    st.subheader("Dashboard general")

    if history.empty:
        st.info("Carga primero el histórico en la pestaña Importación.")
        return

    min_dt = history["fecha_hora"].min()
    max_dt = history["fecha_hora"].max()

    c1, c2, c3 = st.columns(3)
    c1.metric("Registros horarios", len(history))
    c2.metric("Desde", str(min_dt))
    c3.metric("Hasta", str(max_dt))

    with st.expander("🔍 Calidad del dato", expanded=False):
        avail_global = availability_table(history, min_dt, max_dt)
        st.dataframe(avail_global, use_container_width=True)

    st.markdown("#### Resumen últimos 30 días")
    last_start = max_dt - pd.Timedelta(days=30)
    last_df = history[(history["fecha_hora"] >= last_start) & (history["fecha_hora"] <= max_dt)].copy()
    if not last_df.empty:
        last_df = add_risk_columns(last_df, hoja_humeda_threshold=hoja_threshold)
        last_summary = period_summary(last_df, soil_type, last_start, max_dt)
        # Tabla vertical: transponer para evitar el scroll horizontal
        _summary_v = last_summary.T.reset_index()
        _summary_v.columns = ["Indicador", "Valor"]
        st.dataframe(_summary_v, use_container_width=True, hide_index=True)


def analysis_tab(history, soil_type, hoja_threshold):
    st.subheader("Análisis por periodo")

    if history.empty:
        st.info("Carga primero el histórico.")
        return

    period_selector(history)
    period, period_df, avail, summary, global_summary = get_period_data(history, soil_type, hoja_threshold)

    if period is None:
        st.info("Configura un periodo y pulsa **Analizar periodo**.")
        return

    st.write(f"Periodo analizado: **{period['start_ts']}** a **{period['end_ts']}**")

    if period_df.empty:
        st.warning("No hay datos en el periodo seleccionado.")
        return

    with st.expander("🔍 Calidad de datos", expanded=False):
        st.dataframe(avail, use_container_width=True)

    st.markdown("#### Resumen global del periodo")
    # Tabla HTML con primera columna sticky + cabecera verde (igual que Previsión)
    if not global_summary.empty:
        _gs_cols = list(global_summary.columns)
        _gs_th = ("background:#1a2e1e;color:white;padding:8px 12px;"
                  "white-space:nowrap;font-weight:600;font-size:13px;")
        _gs_th_sticky = "position:sticky;left:0;z-index:2;" + _gs_th
        _gs_header = "".join(
            f'<th style="{_gs_th_sticky if i == 0 else _gs_th}">{c}</th>'
            for i, c in enumerate(_gs_cols)
        )
        _gs_body = ""
        for _, _r in global_summary.iterrows():
            _cells = ""
            for _i, _c in enumerate(_gs_cols):
                _v = _r[_c]
                _disp = (f"{_v:.1f}" if isinstance(_v, float) and not pd.isna(_v)
                         else ("—" if (isinstance(_v, float) and pd.isna(_v)) else str(_v)))
                _bg = "#eef2ee" if _i == 0 else "white"
                _td = (f"{'position:sticky;left:0;z-index:1;' if _i == 0 else ''}"
                       f"background:{_bg};padding:7px 12px;"
                       f"border-bottom:1px solid #e8e8e8;white-space:nowrap;font-size:13px;")
                _cells += f"<td style='{_td}'>{_disp}</td>"
            _gs_body += f"<tr>{_cells}</tr>"
        st.markdown(
            f'<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;'
            f'border-radius:8px;border:1px solid #ddd;margin-bottom:1rem;">'
            f'<table style="border-collapse:collapse;width:100%;">'
            f'<thead><tr>{_gs_header}</tr></thead>'
            f'<tbody>{_gs_body}</tbody>'
            f'</table></div>',
            unsafe_allow_html=True,
        )
    else:
        st.dataframe(global_summary, use_container_width=True)

    render_interpreted_report(global_summary, avail, soil_type)

    with st.expander("Resumen semanal dentro del periodo", expanded=False):
        _sw_df = summary.reset_index(drop=True) if (summary is not None and not summary.empty) else pd.DataFrame()
        if _sw_df.empty:
            st.info("No hay datos semanales para el periodo seleccionado.")
        else:
            _sw_cols = list(_sw_df.columns)
            _sw_th_base   = ("background:#1a2e1e;color:white;padding:8px 12px;"
                             "white-space:nowrap;font-weight:600;font-size:13px;")
            _sw_th_sticky = "position:sticky;left:0;z-index:2;" + _sw_th_base
            _sw_header = "".join(
                f'<th style="{_sw_th_sticky if i == 0 else _sw_th_base}">{c}</th>'
                for i, c in enumerate(_sw_cols)
            )
            _sw_body = ""
            for _, _r in _sw_df.iterrows():
                _cells = ""
                for _i, _c in enumerate(_sw_cols):
                    _v = _r[_c]
                    _disp = (f"{_v:.1f}" if isinstance(_v, float) and not pd.isna(_v)
                             else ("—" if (isinstance(_v, float) and pd.isna(_v)) else str(_v)))
                    _bg = "#eef2ee" if _i == 0 else "white"
                    _td = (f"{'position:sticky;left:0;z-index:1;' if _i == 0 else ''}"
                           f"background:{_bg};padding:7px 12px;"
                           f"border-bottom:1px solid #e8e8e8;white-space:nowrap;font-size:13px;")
                    _cells += f"<td style='{_td}'>{_disp}</td>"
                _sw_body += f"<tr>{_cells}</tr>"
            st.markdown(
                f'<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;'
                f'border-radius:8px;border:1px solid #ddd;margin-bottom:1rem;">'
                f'<table style="border-collapse:collapse;width:100%;">'
                f'<thead><tr>{_sw_header}</tr></thead>'
                f'<tbody>{_sw_body}</tbody>'
                f'</table></div>',
                unsafe_allow_html=True,
            )
        st.download_button(
            "Descargar resumen semanal del periodo",
            data=summary.to_csv(index=False).encode("utf-8-sig"),
            file_name="resumen_periodo_finca_gallinal.csv",
            mime="text/csv",
        )


def cold_tab(history):
    st.subheader("Campañas de frío")

    if history.empty:
        st.info("Carga primero el histórico.")
        return

    chill_years = available_chill_analysis_years(history)
    if not chill_years:
        st.info("No hay datos suficientes para calcular campañas de frío.")
        return

    selected_chill_year = st.selectbox(
        "Año de análisis del frío",
        chill_years,
        index=max(0, len(chill_years)-1),
        help="Ejemplo: 2020 = campaña 2019/2020.",
    )
    if selected_chill_year is None:
        st.info("Selecciona un año de análisis.")
        return
    selected_season = winter_label_from_analysis_year(selected_chill_year)

    if st.button("Calcular campaña de frío", type="primary"):
        chill_summary, chill_daily, chill_start, chill_end = winter_chill_summary(history, selected_chill_year)

        st.write(f"Campaña seleccionada: **{selected_season}** ({chill_start.strftime('%d/%m/%Y')} - {chill_end.strftime('%d/%m/%Y')})")
        if chill_summary.empty:
            st.warning("No hay datos de temperatura para esa campaña.")
        else:
            # ── Preparar tabla ────────────────────────────────────────────────
            _cs = chill_summary.copy()
            _cs_drop = [c for c in ["Horas esperadas", "Horas con datos temperatura"]
                        if c in _cs.columns]
            _cs = _cs.drop(columns=_cs_drop)
            if "Cobertura temperatura %" in _cs.columns:
                _cs = _cs.rename(columns={"Cobertura temperatura %": "Calidad del dato %"})
            if "Campaña frío" in _cs.columns:
                _cs = _cs[["Campaña frío"] + [c for c in _cs.columns if c != "Campaña frío"]]
            _cs = _cs.reset_index(drop=True)

            # ── Tabla HTML sticky ─────────────────────────────────────────────
            _cs_cols = list(_cs.columns)
            _cs_th   = ("background:#1a2e1e;color:white;padding:8px 12px;"
                        "white-space:nowrap;font-weight:600;font-size:13px;")
            _cs_ths  = "position:sticky;left:0;z-index:2;" + _cs_th
            _cs_hdr  = "".join(
                f'<th style="{_cs_ths if i == 0 else _cs_th}">{c}</th>'
                for i, c in enumerate(_cs_cols)
            )
            _cs_body = ""
            for _, _r in _cs.iterrows():
                _cells = ""
                for _i, _c in enumerate(_cs_cols):
                    _v = _r[_c]
                    if isinstance(_v, float) and not pd.isna(_v):
                        _disp = f"{_v:.1f}"
                    elif isinstance(_v, float) and pd.isna(_v):
                        _disp = "—"
                    elif hasattr(_v, "strftime"):
                        _disp = _v.strftime("%d/%m/%Y")
                    else:
                        _disp = str(_v)
                    _bg = "#eef2ee" if _i == 0 else "white"
                    _td = (f"{'position:sticky;left:0;z-index:1;' if _i == 0 else ''}"
                           f"background:{_bg};padding:7px 12px;"
                           f"border-bottom:1px solid #e8e8e8;white-space:nowrap;font-size:13px;")
                    _cells += f"<td style='{_td}'>{_disp}</td>"
                _cs_body += f"<tr>{_cells}</tr>"
            st.markdown(
                f'<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;'
                f'border-radius:8px;border:1px solid #ddd;margin-bottom:1rem;">'
                f'<table style="border-collapse:collapse;width:100%;">'
                f'<thead><tr>{_cs_hdr}</tr></thead>'
                f'<tbody>{_cs_body}</tbody>'
                f'</table></div>',
                unsafe_allow_html=True,
            )

            comparison_df = chill_column_comparison(history, selected_chill_year)
            st.markdown("#### Comprobación por columna de temperatura")

            # ── Preparar tabla comparación ────────────────────────────────────
            _cmp = comparison_df.copy()
            _cmp_drop = [c for c in ["Horas esperadas campaña", "Horas con dato"]
                         if c in _cmp.columns]
            _cmp = _cmp.drop(columns=_cmp_drop).reset_index(drop=True)

            # ── Tabla HTML sticky ─────────────────────────────────────────────
            _cmp_cols = list(_cmp.columns)
            _cmp_th   = ("background:#1a2e1e;color:white;padding:8px 12px;"
                         "white-space:nowrap;font-weight:600;font-size:13px;")
            _cmp_ths  = "position:sticky;left:0;z-index:2;" + _cmp_th
            _cmp_hdr  = "".join(
                f'<th style="{_cmp_ths if i == 0 else _cmp_th}">{c}</th>'
                for i, c in enumerate(_cmp_cols)
            )
            _cmp_body = ""
            for _, _r in _cmp.iterrows():
                _cells = ""
                for _i, _c in enumerate(_cmp_cols):
                    _v = _r[_c]
                    if isinstance(_v, float) and not pd.isna(_v):
                        _disp = f"{_v:.1f}"
                    elif isinstance(_v, float) and pd.isna(_v):
                        _disp = "—"
                    else:
                        _disp = str(_v)
                    _bg = "#eef2ee" if _i == 0 else "white"
                    _td = (f"{'position:sticky;left:0;z-index:1;' if _i == 0 else ''}"
                           f"background:{_bg};padding:7px 12px;"
                           f"border-bottom:1px solid #e8e8e8;white-space:nowrap;font-size:13px;")
                    _cells += f"<td style='{_td}'>{_disp}</td>"
                _cmp_body += f"<tr>{_cells}</tr>"
            st.markdown(
                f'<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;'
                f'border-radius:8px;border:1px solid #ddd;margin-bottom:1rem;">'
                f'<table style="border-collapse:collapse;width:100%;">'
                f'<thead><tr>{_cmp_hdr}</tr></thead>'
                f'<tbody>{_cmp_body}</tbody>'
                f'</table></div>',
                unsafe_allow_html=True,
            )

            if not chill_daily.empty:
                chart_df = chill_daily.set_index("fecha_hora")[["horas_menor_7_acum", "utah_acum", "chill_portions_acum"]]
                st.line_chart(chart_df)

            st.download_button(
                "Descargar frío invernal",
                data=chill_summary.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"frio_invernal_{selected_season.replace('/', '_')}.csv",
                mime="text/csv",
            )

            with st.expander("📖 Explicación de modelos de frío", expanded=False):
                st.markdown("""
**Los tres modelos cuantifican el frío acumulado durante el invierno, pero con distintos criterios:**

---

#### ❄️ Horas frío < 7 ºC — Modelo clásico
Cuenta simplemente el número de horas en las que la temperatura es inferior a 7 ºC.
- **Sencillo e intuitivo**, utilizado históricamente en España y en la mayoría de recomendaciones varietales antiguas.
- **Limitación:** No tiene en cuenta que las temperaturas cálidas durante el día pueden revertir parte del frío acumulado, lo que lo hace menos preciso en climas mediterráneos con inviernos suaves y días soleados.
- **Referencia orientativa:** La mayoría de variedades de manzana y pera en zonas frías necesitan entre 800 y 1 400 horas frío.

---

#### 🌡️ Utah Chill Units — Modelo de Richardson
Desarrollado en 1974, asigna a cada hora un valor positivo o negativo según la temperatura:

| Temperatura | Valor hora |
|---|---|
| < 1,4 ºC | 0 |
| 1,4 – 2,4 ºC | +0,5 |
| 2,5 – 9,1 ºC | +1,0 |
| 9,2 – 12,4 ºC | +0,5 |
| 12,5 – 15,9 ºC | 0 |
| 16,0 – 18,0 ºC | −0,5 |
| > 18,0 ºC | −1,0 |

- **Ventaja:** Penaliza los días cálidos que destruyen frío ya acumulado.
- **Limitación:** En zonas muy cálidas puede dar valores negativos que no reflejan bien la realidad fisiológica del árbol.

---

#### 🔬 Chill Portions — Modelo dinámico (Fishman & Erez)
El modelo más avanzado y preciso para climas mediterráneos y subtropicales, desarrollado en los años 90. Simula el proceso bioquímico real que ocurre en las yemas en dos fases:
1. **Fase de inducción:** el frío genera un intermediario reversible (precursor).
2. **Fase de estabilización:** ese precursor se convierte de forma irreversible en una Chill Portion (unidad de frío).

- **Ventaja clave:** El frío estabilizado **no se puede revertir** con calor posterior, lo que lo hace mucho más fiel al comportamiento real del árbol en inviernos variables.
- **Ideal para Finca Gallinal:** Al ser el modelo más robusto en inviernos cálidos e irregulares, es el que mejor predice la salida del reposo.
- **Referencia orientativa:** Variedades de manzana como Golden Delicious necesitan entre 40 y 60 Chill Portions.

---

> 💡 **¿Cuál usar?** Para tomar decisiones agronómicas en zonas con inviernos suaves, se recomienda dar más peso a las **Chill Portions**. Las horas frío < 7 ºC son útiles para comparar con recomendaciones históricas de catálogos varietales.
                """)




MONTH_NAMES_ES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}

MONTH_NUMBER_BY_NAME_ES = {v: k for k, v in MONTH_NAMES_ES.items()}


def month_week_period(year, month, week_in_month):
    """
    Devuelve el periodo de la semana N de un mes concreto.

    Criterio práctico:
    - Semana 1 = días 1-7 del mes
    - Semana 2 = días 8-14
    - Semana 3 = días 15-21
    - Semana 4 = días 22-28
    - Semana 5 = días 29-fin de mes

    Es más intuitivo para uso agronómico que obligar a recordar la semana ISO.
    """
    import calendar

    year = int(year)
    month = int(month)
    week_in_month = int(week_in_month)

    start_day = 1 + (week_in_month - 1) * 7
    last_day = calendar.monthrange(year, month)[1]
    if start_day > last_day:
        return None, None

    end_day = min(start_day + 6, last_day)
    start = pd.Timestamp(year=year, month=month, day=start_day, hour=0, minute=0)
    end = pd.Timestamp(year=year, month=month, day=end_day, hour=23, minute=59, second=59)
    return start, end


def current_month_week_info(reference=None):
    """Devuelve año, mes y semana práctica del mes para la fecha actual."""
    ref = pd.Timestamp.today() if reference is None else pd.Timestamp(reference)
    week_in_month = int(((ref.day - 1) // 7) + 1)
    return int(ref.year), int(ref.month), int(week_in_month)


def compare_month_weeks(history, years, month, week_in_month, soil_type, hoja_threshold):
    """Compara la misma semana práctica de un mes entre varios años."""
    rows = []
    for y in years:
        start, end = month_week_period(int(y), int(month), int(week_in_month))
        if start is None:
            rows.append({
                "Comparación": f"{int(y)} · {MONTH_NAMES_ES[int(month)]} · semana {int(week_in_month)}",
                "Año": int(y),
                "Mes": MONTH_NAMES_ES[int(month)],
                "Semana del mes": int(week_in_month),
                "Desde": "",
                "Hasta": "",
                "Aviso": "Semana inexistente en ese mes",
            })
            continue

        period = history[(history["fecha_hora"] >= start) & (history["fecha_hora"] <= end)].copy()
        if period.empty:
            rows.append({
                "Comparación": f"{int(y)} · {MONTH_NAMES_ES[int(month)]} · semana {int(week_in_month)}",
                "Año": int(y),
                "Mes": MONTH_NAMES_ES[int(month)],
                "Semana del mes": int(week_in_month),
                "Desde": start,
                "Hasta": end,
                "Aviso": "Sin datos",
            })
            continue

        period = add_risk_columns(period, hoja_humeda_threshold=hoja_threshold)
        row_df = period_summary(period, soil_type, start, end)
        row = row_df.iloc[0].to_dict() if not row_df.empty else {}
        row["Comparación"] = f"{int(y)} · {MONTH_NAMES_ES[int(month)]} · semana {int(week_in_month)}"
        row["Año"] = int(y)
        row["Mes"] = MONTH_NAMES_ES[int(month)]
        row["Semana del mes"] = int(week_in_month)
        row["Desde"] = start
        row["Hasta"] = end
        rows.append(row)

    return pd.DataFrame(rows)


def month_fortnight_period(year, month, fortnight):
    """
    Devuelve el periodo de la quincena N de un mes concreto.
    - Primera quincena (1) = días 1-15 del mes
    - Segunda quincena (2) = días 16-fin del mes
    """
    import calendar

    year = int(year)
    month = int(month)
    fortnight = int(fortnight)
    last_day = calendar.monthrange(year, month)[1]
    if fortnight == 1:
        start_day, end_day = 1, 15
    else:
        start_day, end_day = 16, last_day
    start = pd.Timestamp(year=year, month=month, day=start_day, hour=0, minute=0)
    end   = pd.Timestamp(year=year, month=month, day=end_day,   hour=23, minute=59, second=59)
    return start, end


def compare_month_fortnights(history, years, month, fortnight, soil_type, hoja_threshold):
    """Compara la misma quincena de un mes entre varios años."""
    fortnight_label = "1ª quincena" if int(fortnight) == 1 else "2ª quincena"
    rows = []
    for y in years:
        start, end = month_fortnight_period(int(y), int(month), int(fortnight))
        period = history[(history["fecha_hora"] >= start) & (history["fecha_hora"] <= end)].copy()
        if period.empty:
            rows.append({
                "Comparación": f"{int(y)} · {MONTH_NAMES_ES[int(month)]} · {fortnight_label}",
                "Año": int(y),
                "Mes": MONTH_NAMES_ES[int(month)],
                "Quincena": int(fortnight),
                "Desde": start,
                "Hasta": end,
                "Aviso": "Sin datos",
            })
            continue
        period = add_risk_columns(period, hoja_humeda_threshold=hoja_threshold)
        row_df = period_summary(period, soil_type, start, end)
        row = row_df.iloc[0].to_dict() if not row_df.empty else {}
        row["Comparación"] = f"{int(y)} · {MONTH_NAMES_ES[int(month)]} · {fortnight_label}"
        row["Año"] = int(y)
        row["Mes"] = MONTH_NAMES_ES[int(month)]
        row["Quincena"] = int(fortnight)
        row["Desde"] = start
        row["Hasta"] = end
        rows.append(row)
    return pd.DataFrame(rows)


def compact_comparison_report_table(cmp_df):
    """
    Crea una tabla vertical y visual, pensada para no hacer scroll horizontal.
    Cada fila es un año/periodo y las columnas son solo las variables clave.
    """
    if cmp_df is None or cmp_df.empty:
        return pd.DataFrame()

    df = cmp_df.copy()

    def pick(col, default=np.nan):
        return df[col] if col in df.columns else default

    out = pd.DataFrame()
    out["Año"] = pick("Año", "")
    out["Periodo"] = pick("Comparación", "")
    if "Desde" in df.columns and "Hasta" in df.columns:
        desde = pd.to_datetime(df["Desde"], errors="coerce").dt.strftime("%d/%m")
        hasta = pd.to_datetime(df["Hasta"], errors="coerce").dt.strftime("%d/%m")
        out["Fechas"] = desde.fillna("") + " - " + hasta.fillna("")
    else:
        out["Fechas"] = ""

    metrics = {
        "Temp media ºC": "Temp. media ºC",
        "Temp máx ºC": "Temp. máx ºC",
        "Temp mín ºC": "Temp. mín ºC",
        "Lluvia mm": "Lluvia total mm",
        "Horas lluvia": "Horas con lluvia",
        "HR media %": "HR media %",
        "Hoja húmeda h": "Horas hoja húmeda",
        "Eventos hoja": "Eventos hoja mojada",
        "Moteado medio/alto": "Eventos moteado medio/alto",
        "Monilia medio/alto": "Eventos monilia medio/alto",
        "Viento medio": "Viento medio",
        "Ráfaga máx": "Ráfaga máxima",
        "Radiación MJ/m²": "Radiación acumulada estimada MJ/m²",
        "Evaporativo suelo": "Índice evaporativo ajustado suelo",
    }

    for label, source in metrics.items():
        if source in df.columns:
            out[label] = pd.to_numeric(df[source], errors="coerce").round(2)

    # Etiqueta rápida por año.
    notes = []
    rain_col = "Lluvia total mm"
    temp_col = "Temp. media ºC"
    hr_col = "HR media %"
    evap_col = "Índice evaporativo ajustado suelo"

    rain = pd.to_numeric(df[rain_col], errors="coerce") if rain_col in df.columns else pd.Series(np.nan, index=df.index)
    temp = pd.to_numeric(df[temp_col], errors="coerce") if temp_col in df.columns else pd.Series(np.nan, index=df.index)
    hr = pd.to_numeric(df[hr_col], errors="coerce") if hr_col in df.columns else pd.Series(np.nan, index=df.index)
    evap = pd.to_numeric(df[evap_col], errors="coerce") if evap_col in df.columns else pd.Series(np.nan, index=df.index)

    for i in df.index:
        bits = []
        if rain.notna().sum() >= 2:
            if i == rain.idxmax():
                bits.append("más lluvioso")
            if i == rain.idxmin():
                bits.append("más seco")
        if temp.notna().sum() >= 2:
            if i == temp.idxmax():
                bits.append("más cálido")
            if i == temp.idxmin():
                bits.append("más fresco")
        if hr.notna().sum() >= 2:
            if i == hr.idxmax():
                bits.append("más húmedo")
            if i == hr.idxmin():
                bits.append("HR más baja")
        if evap.notna().sum() >= 2:
            if i == evap.idxmax():
                bits.append("más demanda evaporativa")
        notes.append(", ".join(bits) if bits else "valor intermedio")

    out["Lectura rápida"] = notes

    # Quita columnas enteras vacías para evitar ancho innecesario.
    for col in list(out.columns):
        if col not in ["Año", "Periodo", "Fechas", "Lectura rápida"]:
            if pd.to_numeric(out[col], errors="coerce").isna().all():
                out = out.drop(columns=[col])

    return out


def render_visual_comparison_report(cmp_df, title="Informe comparativo visual"):
    """Muestra resumen vertical, rankings rápidos y tabla pensada para lectura sin scroll horizontal."""
    if cmp_df is None or cmp_df.empty:
        st.info("No hay datos para crear el informe comparativo visual.")
        return

    st.subheader(title)

    report = compact_comparison_report_table(cmp_df)
    if report.empty:
        st.info("No hay datos suficientes para crear la tabla visual.")
        return

    # Ranking/resumen rápido arriba.
    c1, c2, c3 = st.columns(3)

    def metric_winner(col, label="", suffix=""):
        if col not in cmp_df.columns:
            return "Sin dato"
        _cols = ["Año"] if "Año" in cmp_df.columns else ["Comparación"]
        valid = cmp_df[_cols + [col]].copy()
        valid[col] = pd.to_numeric(valid[col], errors="coerce")
        valid = valid.dropna(subset=[col])
        if valid.empty:
            return "Sin dato"
        row = valid.loc[valid[col].idxmax()]
        _yl = row["Año"] if "Año" in valid.columns else row["Comparación"]
        try:
            _yl = int(_yl)
        except Exception:
            pass
        return f"{_yl} · {float(row[col]):.1f}{suffix}"

    with c1:
        st.metric("Más lluvioso", metric_winner("Lluvia total mm", suffix=" mm"))
    with c2:
        st.metric("Más cálido", metric_winner("Temp. media ºC", suffix=" ºC"))
    with c3:
        st.metric("Mayor demanda evap.", metric_winner("Índice evaporativo ajustado suelo"))

    # ── Tabla HTML sticky ─────────────────────────────────────────────────────
    _rpt = report.reset_index(drop=True)
    _rpt_cols = list(_rpt.columns)
    _rpt_th  = ("background:#1a2e1e;color:white;padding:8px 12px;"
                "white-space:nowrap;font-weight:600;font-size:13px;")
    _rpt_ths = "position:sticky;left:0;z-index:2;" + _rpt_th
    _rpt_hdr = "".join(
        f'<th style="{_rpt_ths if i == 0 else _rpt_th}">{c}</th>'
        for i, c in enumerate(_rpt_cols)
    )
    _rpt_body = ""
    for _, _r in _rpt.iterrows():
        _cells = ""
        for _i, _c in enumerate(_rpt_cols):
            _v = _r[_c]
            if isinstance(_v, float) and not pd.isna(_v):
                _disp = f"{_v:.1f}"
            elif isinstance(_v, float) and pd.isna(_v):
                _disp = "—"
            else:
                _disp = str(_v)
            _bg = "#eef2ee" if _i == 0 else "white"
            _td = (f"{'position:sticky;left:0;z-index:1;' if _i == 0 else ''}"
                   f"background:{_bg};padding:7px 12px;"
                   f"border-bottom:1px solid #e8e8e8;white-space:nowrap;font-size:13px;")
            _cells += f"<td style='{_td}'>{_disp}</td>"
        _rpt_body += f"<tr>{_cells}</tr>"
    st.markdown(
        f'<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;'
        f'border-radius:8px;border:1px solid #ddd;margin-bottom:1rem;">'
        f'<table style="border-collapse:collapse;width:100%;">'
        f'<thead><tr>{_rpt_hdr}</tr></thead>'
        f'<tbody>{_rpt_body}</tbody>'
        f'</table></div>',
        unsafe_allow_html=True,
    )

    st.download_button(
        "Descargar informe comparativo visual",
        data=report.to_csv(index=False).encode("utf-8-sig"),
        file_name="informe_comparativo_visual.csv",
        mime="text/csv",
    )



def comparator_tab(history, soil_type, hoja_threshold):
    st.subheader("Comparador climático")

    if history.empty:
        st.info("Carga primero el histórico.")
        return

    with st.expander("Comparar campañas de frío", expanded=False):
        chill_years_cmp = available_chill_analysis_years(history)
        selected_chill_years_cmp = st.multiselect(
            "Campañas de frío a comparar",
            options=chill_years_cmp,
            default=chill_years_cmp[-3:] if len(chill_years_cmp) >= 3 else chill_years_cmp,
            help="Año 2020 = campaña 2019/2020.",
        )

        if st.button("Comparar campañas de frío", key="btn_cmp_chill_v83"):
            if not selected_chill_years_cmp:
                st.warning("Selecciona al menos una campaña de frío.")
            else:
                cmp_chill = compare_chill_campaigns(history, selected_chill_years_cmp)

                # ── Preparar tabla de visualización ──────────────────────────
                _cols_drop = [c for c in ["Comparación", "Año análisis",
                                          "Horas esperadas", "Horas con datos temperatura"]
                              if c in cmp_chill.columns]
                _cd = cmp_chill.drop(columns=_cols_drop).copy()
                if "Cobertura temperatura %" in _cd.columns:
                    _cd = _cd.rename(columns={"Cobertura temperatura %": "Calidad del dato %"})
                # Campaña frío primera
                if "Campaña frío" in _cd.columns:
                    _cd = _cd[["Campaña frío"] + [c for c in _cd.columns if c != "Campaña frío"]]
                _cd = _cd.reset_index(drop=True)

                # ── Tabla HTML sticky ─────────────────────────────────────────
                _cd_cols = list(_cd.columns)
                _cd_th   = ("background:#1a2e1e;color:white;padding:8px 12px;"
                            "white-space:nowrap;font-weight:600;font-size:13px;")
                _cd_ths  = "position:sticky;left:0;z-index:2;" + _cd_th
                _cd_hdr  = "".join(
                    f'<th style="{_cd_ths if i == 0 else _cd_th}">{c}</th>'
                    for i, c in enumerate(_cd_cols)
                )
                _cd_body = ""
                for _, _r in _cd.iterrows():
                    _cells = ""
                    for _i, _c in enumerate(_cd_cols):
                        _v = _r[_c]
                        _disp = (f"{_v:.1f}" if isinstance(_v, float) and not pd.isna(_v)
                                 else ("—" if (isinstance(_v, float) and pd.isna(_v)) else str(_v)))
                        _bg = "#eef2ee" if _i == 0 else "white"
                        _td = (f"{'position:sticky;left:0;z-index:1;' if _i == 0 else ''}"
                               f"background:{_bg};padding:7px 12px;"
                               f"border-bottom:1px solid #e8e8e8;white-space:nowrap;font-size:13px;")
                        _cells += f"<td style='{_td}'>{_disp}</td>"
                    _cd_body += f"<tr>{_cells}</tr>"
                st.markdown(
                    f'<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;'
                    f'border-radius:8px;border:1px solid #ddd;margin-bottom:1rem;">'
                    f'<table style="border-collapse:collapse;width:100%;">'
                    f'<thead><tr>{_cd_hdr}</tr></thead>'
                    f'<tbody>{_cd_body}</tbody>'
                    f'</table></div>',
                    unsafe_allow_html=True,
                )

                monthly_chill = monthly_chill_breakdown(history, selected_chill_years_cmp)
                render_chill_comparison_explanation(cmp_chill, monthly_chill)
                st.download_button(
                    "Descargar comparación de campañas de frío",
                    data=cmp_chill.to_csv(index=False).encode("utf-8-sig"),
                    file_name="comparacion_campanas_frio.csv",
                    mime="text/csv",
                )

    with st.expander("Comparar por mes y semana del mes", expanded=True):
        years_cmp = [int(y) for y in sorted(history["fecha_hora"].dt.year.unique())]
        current_year, current_month, current_week = current_month_week_info()

        st.info(
            f"Semana actual orientativa: **{MONTH_NAMES_ES.get(current_month, current_month)} · semana {current_week}** "
            f"del año **{current_year}**. Criterio usado: semana 1 = días 1-7, semana 2 = 8-14, semana 3 = 15-21, semana 4 = 22-28, semana 5 = 29-fin de mes."
        )

        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            month_name = st.selectbox(
                "Mes a comparar",
                options=list(MONTH_NUMBER_BY_NAME_ES.keys()),
                index=max(0, current_month - 1),
            )
            month_cmp = MONTH_NUMBER_BY_NAME_ES[month_name]

        with col_m2:
            week_cmp = st.selectbox(
                "Semana del mes",
                options=[1, 2, 3, 4, 5],
                index=max(0, min(4, current_week - 1)),
                format_func=lambda x: f"{x}ª semana" if x != 1 else "1ª semana",
            )

        with col_m3:
            usar_todos_los_anos_mes = st.checkbox(
                "Comparar todos los años disponibles",
                value=False,
                key="cmp_month_all_years_v83",
            )

        selected_years_month_manual = st.multiselect(
            "Años a comparar",
            options=years_cmp,
            default=years_cmp[-4:] if len(years_cmp) >= 4 else years_cmp,
            help="Si activas 'Comparar todos los años disponibles', esta selección se ignora.",
            key="cmp_month_years_v83",
        )

        selected_years_month = years_cmp if usar_todos_los_anos_mes else selected_years_month_manual
        selected_years_month = [int(y) for y in selected_years_month]

        if selected_years_month:
            previews = []
            for y in selected_years_month:
                s, e = month_week_period(y, month_cmp, week_cmp)
                if s is not None:
                    previews.append(f"{y}: {s.strftime('%d/%m/%Y')} - {e.strftime('%d/%m/%Y')}")
            st.caption("Periodos que se compararán: " + " · ".join(previews[:8]) + (" ..." if len(previews) > 8 else ""))

        if st.button("Comparar mes y semana del mes", key="btn_cmp_month_week_v83", type="primary"):
            if not selected_years_month:
                st.warning("Selecciona al menos un año.")
            else:
                cmp_month = compare_month_weeks(
                    history,
                    selected_years_month,
                    int(month_cmp),
                    int(week_cmp),
                    soil_type,
                    hoja_threshold,
                )

                order_map = {int(y): i for i, y in enumerate(selected_years_month)}
                if "Año" in cmp_month.columns:
                    cmp_month["_orden"] = cmp_month["Año"].map(order_map)
                    cmp_month = cmp_month.sort_values("_orden").drop(columns=["_orden"])

                render_visual_comparison_report(
                    cmp_month,
                    title=f"Informe visual · {month_name} · semana {int(week_cmp)}",
                )

                with st.expander("Tabla completa técnica", expanded=False):
                    st.dataframe(cmp_month, use_container_width=True)

                render_week_comparison_explanation(cmp_month)

                st.download_button(
                    "Descargar comparación completa",
                    data=cmp_month.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"comparacion_{month_name.lower()}_semana_{int(week_cmp)}.csv",
                    mime="text/csv",
                )

    with st.expander("Comparar por quincenas", expanded=False):
        years_cmp_q = [int(y) for y in sorted(history["fecha_hora"].dt.year.unique())]
        _today = pd.Timestamp.today()
        current_month_q = _today.month
        current_fortnight_q = 1 if _today.day <= 15 else 2

        st.info(
            "Primera quincena = días 1-15 del mes · Segunda quincena = días 16-fin de mes."
        )

        col_q1, col_q2, col_q3 = st.columns(3)
        with col_q1:
            month_name_q = st.selectbox(
                "Mes a comparar",
                options=list(MONTH_NUMBER_BY_NAME_ES.keys()),
                index=max(0, current_month_q - 1),
                key="cmp_fortnight_month_v83",
            )
            month_cmp_q = MONTH_NUMBER_BY_NAME_ES[month_name_q]
        with col_q2:
            fortnight_cmp = st.selectbox(
                "Quincena",
                options=[1, 2],
                index=current_fortnight_q - 1,
                format_func=lambda x: "1ª quincena (días 1-15)" if x == 1 else "2ª quincena (días 16-fin)",
                key="cmp_fortnight_half_v83",
            )
        with col_q3:
            usar_todos_anos_q = st.checkbox(
                "Comparar todos los años disponibles",
                value=False,
                key="cmp_fortnight_all_years_v83",
            )

        selected_years_q_manual = st.multiselect(
            "Años a comparar",
            options=years_cmp_q,
            default=years_cmp_q[-4:] if len(years_cmp_q) >= 4 else years_cmp_q,
            help="Si activas 'Comparar todos los años disponibles', esta selección se ignora.",
            key="cmp_fortnight_years_v83",
        )

        selected_years_q = years_cmp_q if usar_todos_anos_q else selected_years_q_manual
        selected_years_q = [int(y) for y in selected_years_q]

        if selected_years_q:
            _fort_label_prev = "1ª quincena" if fortnight_cmp == 1 else "2ª quincena"
            previews_q = []
            for y in selected_years_q:
                s_q, e_q = month_fortnight_period(y, month_cmp_q, fortnight_cmp)
                previews_q.append(f"{y}: {s_q.strftime('%d/%m/%Y')} - {e_q.strftime('%d/%m/%Y')}")
            st.caption("Periodos que se compararán: " + " · ".join(previews_q[:8]) + (" ..." if len(previews_q) > 8 else ""))

        if st.button("Comparar quincenas", key="btn_cmp_fortnight_v83", type="primary"):
            if not selected_years_q:
                st.warning("Selecciona al menos un año.")
            else:
                _fort_label = "1ª quincena" if fortnight_cmp == 1 else "2ª quincena"
                cmp_fortnight = compare_month_fortnights(
                    history,
                    selected_years_q,
                    int(month_cmp_q),
                    int(fortnight_cmp),
                    soil_type,
                    hoja_threshold,
                )

                order_map_q = {int(y): i for i, y in enumerate(selected_years_q)}
                if "Año" in cmp_fortnight.columns:
                    cmp_fortnight["_orden"] = cmp_fortnight["Año"].map(order_map_q)
                    cmp_fortnight = cmp_fortnight.sort_values("_orden").drop(columns=["_orden"])

                render_visual_comparison_report(
                    cmp_fortnight,
                    title=f"Informe visual · {month_name_q} · {_fort_label}",
                )

                with st.expander("Tabla completa técnica", expanded=False):
                    st.dataframe(cmp_fortnight, use_container_width=True)

                render_week_comparison_explanation(cmp_fortnight)

                st.download_button(
                    "Descargar comparación completa",
                    data=cmp_fortnight.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"comparacion_{month_name_q.lower()}_{_fort_label.replace(' ', '_')}.csv",
                    mime="text/csv",
                    key="dl_fortnight_v83",
                )

    with st.expander("Comparar por semana ISO entre años", expanded=False):
        years_cmp = [int(y) for y in sorted(history["fecha_hora"].dt.year.unique())]

        col_w1, col_w2 = st.columns(2)
        with col_w1:
            iso_week_cmp = st.number_input("Semana ISO a comparar", min_value=1, max_value=53, value=32, step=1)
            usar_todos_los_anos = st.checkbox(
                "Comparar todos los años disponibles",
                value=False,
                help="Actívalo para evitar seleccionar años uno a uno.",
                key="cmp_iso_all_years_v83",
            )

        with col_w2:
            selected_years_cmp_manual = st.multiselect(
                "Años a comparar",
                options=years_cmp,
                default=years_cmp[-3:] if len(years_cmp) >= 3 else years_cmp,
                help="Si activas 'Comparar todos los años disponibles', esta selección se ignora.",
                key="cmp_iso_years_v83",
            )

        selected_years_cmp = years_cmp if usar_todos_los_anos else selected_years_cmp_manual
        selected_years_cmp = [int(y) for y in selected_years_cmp]

        st.info(
            "Años que entrarán en la comparación: "
            + (", ".join(map(str, selected_years_cmp)) if selected_years_cmp else "ninguno")
        )

        if st.button("Comparar semana ISO", key="btn_cmp_iso_v83"):
            if not selected_years_cmp:
                st.warning("Selecciona al menos un año.")
            else:
                cmp_week = compare_iso_weeks(history, selected_years_cmp, int(iso_week_cmp), soil_type, hoja_threshold)

                order_map = {int(y): i for i, y in enumerate(selected_years_cmp)}
                if "Año" in cmp_week.columns:
                    cmp_week["_orden"] = cmp_week["Año"].map(order_map)
                    cmp_week = cmp_week.sort_values("_orden").drop(columns=["_orden"])

                render_visual_comparison_report(
                    cmp_week,
                    title=f"Informe visual · Semana ISO {int(iso_week_cmp)}",
                )

                with st.expander("Tabla completa técnica", expanded=False):
                    st.dataframe(cmp_week, use_container_width=True)

                render_week_comparison_explanation(cmp_week)

                st.download_button(
                    "Descargar comparación de semanas ISO",
                    data=cmp_week.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"comparacion_semana_iso_{int(iso_week_cmp)}.csv",
                    mime="text/csv",
                )






def first_existing_col(df, candidates):
    """Devuelve la primera columna existente entre varias opciones."""
    for c in candidates:
        if c and c in df.columns:
            return c
    return None


def get_numeric_series(df, candidates, default=0.0):
    """Devuelve una serie numérica segura aunque la columna no exista."""
    col = first_existing_col(df, candidates)
    if col is None:
        return pd.Series(default, index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def get_sensor_columns_safe(df):
    """
    Detección defensiva de columnas para recomendaciones.

    Prioriza las columnas canónicas internas de la app:
    - lluvia_mm
    - temp_media
    - hr_media
    - humectacion_hoja
    - irradiancia
    - viento_velocidad

    Esto evita que las explicaciones sanitarias muestren 0 mm o sin temperatura cuando sí hay datos.
    """
    return {
        "temp": first_existing_col(df, [
            "temp_media", "Temperatura", "Temperatura media", "Temperatura ºC", "Temp", "temp", "temperature"
        ]),
        "hum": first_existing_col(df, [
            "hr_media", "Humedad", "Humedad relativa", "HR", "Humidity", "humedad", "humidity"
        ]),
        "rain": first_existing_col(df, [
            "lluvia_mm", "Precipitación", "Precipitacion", "Lluvia", "Lluvia mm", "Rain", "rain", "precipitation"
        ]),
        "leaf": first_existing_col(df, [
            "humectacion_hoja", "humectacion_importante", "humectacion_moderada",
            "Humectación de hoja", "Humectacion de hoja", "Hoja mojada", "Leaf Wetness",
            "leaf_wetness", "leaf wetness"
        ]),
        "rad": first_existing_col(df, [
            "irradiancia", "Radiación solar", "Radiacion solar", "Radiación", "Radiacion", "Solar Radiation",
            "radiation", "Radiación MJ/m²", "Radiacion MJ/m²"
        ]),
        "wind": first_existing_col(df, [
            "viento_velocidad", "Velocidad del viento", "Viento", "Wind Speed", "wind_speed", "wind"
        ]),
    }


def current_phenology_phase_for_period(start_ts, end_ts):
    """
    Devuelve fases fenológicas que se solapan con el periodo analizado.
    Usa la tabla editable de Fenología si existe en session_state.
    """
    pheno = st.session_state.get("phenology_df", pd.DataFrame())
    if pheno is None or pheno.empty:
        return []

    pheno = normalize_phenology_df(pheno).dropna(subset=["Año", "Inicio", "Fin"])
    phases = []
    for _, row in pheno.iterrows():
        p_start = pd.to_datetime(row["Inicio"], errors="coerce")
        p_end = pd.to_datetime(row["Fin"], errors="coerce") + pd.Timedelta(hours=23)
        if pd.isna(p_start) or pd.isna(p_end):
            continue
        if p_start <= end_ts and p_end >= start_ts:
            phases.append(str(row["Fase"]))
    return sorted(set(phases))


def phase_sensitivity_text(phases):
    if not phases:
        return "No hay fase fenológica real asociada al periodo. La lectura se hace solo con clima."

    lower = " ".join(phases).lower()
    if any(w in lower for w in ["brot", "flor", "cuaj"]):
        return "El periodo coincide con una fase sensible: brotación, floración o cuajado. Conviene ser más prudente con sanidad y estrés hídrico."
    if any(w in lower for w in ["fruto", "madur"]):
        return "El periodo coincide con crecimiento o maduración del fruto. Conviene vigilar estrés hídrico, golpes de calor, monilia y calidad de fruto."
    if any(w in lower for w in ["cosecha"]):
        return "El periodo coincide con cosecha. Conviene priorizar manejo cuidadoso de humedad, estado del fruto y transitabilidad."
    if any(w in lower for w in ["reposo", "caída"]):
        return "El periodo coincide con reposo o caída de hoja. La lectura sanitaria y de riego suele ser menos crítica que en primavera-verano."
    return "El periodo tiene fase fenológica registrada, pero no se clasifica como una de las fases más sensibles."


def render_health_recommendation(period_df, soil_type, hoja_threshold, start_ts=None, end_ts=None):
    """Recomendación sanitaria orientativa alineada con el semáforo sanitario."""
    st.subheader("Recomendación sanitaria orientativa")

    if period_df is None or period_df.empty:
        st.info("No hay datos suficientes para generar una recomendación sanitaria.")
        return

    df = add_risk_columns(period_df.copy(), hoja_humeda_threshold=hoja_threshold)

    if start_ts is None:
        start_ts = df["fecha_hora"].min()
    if end_ts is None:
        end_ts = df["fecha_hora"].max()

    cols = get_sensor_columns_safe(df)
    phases = current_phenology_phase_for_period(pd.Timestamp(start_ts), pd.Timestamp(end_ts))
    phases_text = ", ".join(phases) if phases else "sin fase fenológica registrada"

    sem = build_sanitary_semaphore_table(df, soil_type, hoja_threshold, start_ts=start_ts, end_ts=end_ts)

    if sem is None or sem.empty:
        st.info("No hay suficientes datos para generar el semáforo sanitario.")
        return

    # Usamos el mismo criterio que el semáforo para evitar contradicciones internas.
    disease_rows = sem[~sem["Riesgo"].astype(str).str.contains("Estrés", case=False, na=False)].copy()
    if disease_rows.empty:
        disease_rows = sem.copy()

    dominant = disease_rows.sort_values("Puntuación", ascending=False).iloc[0]
    level = str(dominant.get("Nivel", "Bajo"))
    risk_name = str(dominant.get("Riesgo", "Riesgo sanitario"))

    box = st.success
    if level == "Alto":
        box = st.error
    elif level == "Medio":
        box = st.warning
    elif level == "Bajo-medio":
        box = st.info

    box(f"Riesgo sanitario orientativo: **{level}** · factor principal: **{risk_name}**")

    st.caption(
        "Esta recomendación usa el mismo criterio que el semáforo sanitario para evitar contradicciones: "
        "prioriza eventos continuos de humectación/temperatura frente a sumas semanales aisladas."
    )

    st.write(f"**Fase fenológica detectada:** {phases_text}.")
    st.write(phase_sensitivity_text(phases))

    st.write("**Motivos principales del factor dominante:** " + str(dominant.get("Indicadores", "sin señales relevantes")) + ".")
    if "Explicación climática" in dominant.index:
        st.markdown("**Explicación:**")
        st.markdown(str(dominant.get("Explicación climática", "")))

    # Datos generales del periodo, para que se vea que no se ignoran lluvia/humedad.
    rain = float(get_numeric_series(df, [cols["rain"]]).sum()) if cols["rain"] else 0.0
    wet_hours = float((get_numeric_series(df, [cols["leaf"]]) >= hoja_threshold).sum()) if cols["leaf"] else 0.0
    hr90 = float((get_numeric_series(df, [cols["hum"]]) >= 90).sum()) if cols["hum"] else 0.0
    temp_mean = float(get_numeric_series(df, [cols["temp"]], default=np.nan).mean()) if cols["temp"] else float("nan")

    st.write(
        f"**Resumen climático del periodo:** lluvia {rain:.1f} mm; "
        f"{wet_hours:.0f} h con hoja mojada según umbral simple; "
        f"{hr90:.0f} h con HR ≥90 %; "
        f"temperatura media {temp_mean:.1f} ºC." if pd.notna(temp_mean) else
        f"**Resumen climático del periodo:** lluvia {rain:.1f} mm; "
        f"{wet_hours:.0f} h con hoja mojada según umbral simple; "
        f"{hr90:.0f} h con HR ≥90 %; temperatura media sin dato."
    )

    with st.expander("Criterios numéricos de evento usados por la app", expanded=True):
        st.markdown(
            """
            La app diferencia entre **humedad acumulada en la semana** y **evento continuo de infección**.

            Un evento se forma cuando hay horas consecutivas con hoja mojada. El evento se cierra tras varias horas secas.
            Para cada evento se calcula:

            - horas húmedas equivalentes,
            - temperatura media del evento,
            - umbral de horas húmedas para esa temperatura,
            - ratio = horas húmedas equivalentes / umbral.
            """
        )
        st.markdown(sanitary_event_thresholds_text(temp_mean))
        st.markdown(
            """
            Lectura del ratio:

            - **Bajo:** ratio < 0,75.
            - **Medio:** ratio ≥ 0,75.
            - **Medio-alto:** ratio ≥ 1,00.
            - **Alto:** ratio ≥ 1,25.

            Por eso puede haber muchos milímetros de lluvia o muchas horas de humedad acumuladas en una semana,
            pero seguir sin evento medio/alto si esa humedad no se concentró en un episodio continuo con temperatura compatible.
            """
        )

    missing = []
    if not cols["rain"]:
        missing.append("precipitación")
    if not cols["leaf"]:
        missing.append("humectación de hoja")
    if not cols["temp"]:
        missing.append("temperatura")
    if missing:
        st.caption("Aviso: la recomendación es más limitada porque faltan columnas de " + ", ".join(missing) + ".")

    st.markdown("#### Recomendación práctica")

    recs = []

    if level in ["Alto", "Medio"]:
        recs.append("Revisar la finca visualmente, especialmente zonas con poca ventilación, variedades sensibles y áreas donde la hoja permanezca más tiempo mojada.")
        recs.append("Comprobar previsión de lluvia y humedad para los próximos días antes de decidir una intervención.")
        recs.append("Valorar si el cultivo mantiene cobertura preventiva suficiente, especialmente en brotación, floración, cuajado y crecimiento inicial del fruto.")
        recs.append("Si hubo lluvia relevante tras un tratamiento anterior, revisar si pudo reducirse la persistencia de la protección.")
    elif level == "Bajo-medio":
        recs.append("Mantener vigilancia, especialmente si se esperan nuevas lluvias o noches con humedad alta.")
        recs.append("Revisar hojas jóvenes, flores/frutos y zonas húmedas antes de decidir una intervención.")
        recs.append("No es una alarma alta por eventos, pero sí conviene seguir la evolución en los próximos días.")
    else:
        recs.append("No se aprecia necesidad climática clara de intervención sanitaria por eventos del periodo.")
        recs.append("Mantener seguimiento normal y revisar de nuevo si aparecen lluvias, humectación prolongada o subida de temperaturas.")

    for rec in recs:
        st.write(f"- {rec}")

    st.caption(
        "Recomendación orientativa basada en clima, humectación y fenología registrada. "
        "No sustituye la revisión de campo ni la normativa vigente sobre productos fitosanitarios autorizados."
    )


def render_irrigation_recommendation(period_df, soil_type, hoja_threshold, start_ts=None, end_ts=None):
    st.subheader("Recomendación de riego orientativa")

    if period_df is None or period_df.empty:
        st.info("No hay datos suficientes para generar una recomendación de riego.")
        return

    df = period_df.copy()
    if start_ts is None:
        start_ts = df["fecha_hora"].min()
    if end_ts is None:
        end_ts = df["fecha_hora"].max()

    cols = get_sensor_columns_safe(df)

    phases = current_phenology_phase_for_period(pd.Timestamp(start_ts), pd.Timestamp(end_ts))
    phases_text = ", ".join(phases) if phases else "sin fase fenológica registrada"

    rain_s = get_numeric_series(df, [cols["rain"]]) if cols["rain"] else pd.Series(0.0, index=df.index)
    temp_s = get_numeric_series(df, [cols["temp"]], default=np.nan) if cols["temp"] else pd.Series(np.nan, index=df.index)
    hum_s = get_numeric_series(df, [cols["hum"]], default=np.nan) if cols["hum"] else pd.Series(np.nan, index=df.index)
    rad_s = get_numeric_series(df, [cols["rad"]]) if cols["rad"] else pd.Series(0.0, index=df.index)
    wind_s = get_numeric_series(df, [cols["wind"]], default=np.nan) if cols["wind"] else pd.Series(np.nan, index=df.index)

    rain = float(rain_s.sum())
    temp_mean = float(temp_s.mean()) if temp_s.notna().any() else float("nan")
    temp_max = float(temp_s.max()) if temp_s.notna().any() else float("nan")
    hr_mean = float(hum_s.mean()) if hum_s.notna().any() else float("nan")
    rad_mj = float(rad_s.sum()) if rad_s.notna().any() else 0.0
    wind_mean = float(wind_s.mean()) if wind_s.notna().any() else float("nan")

    try:
        tmp = df.copy()
        evap_index = evaporation_index(tmp, soil_type)
    except Exception:
        evap_index = np.nan

    if isinstance(evap_index, pd.Series):
        evap_value = float(evap_index.mean())
    else:
        evap_value = float(evap_index) if pd.notna(evap_index) else np.nan

    soil_lower = str(soil_type).lower()
    fast_soil = any(w in soil_lower for w in ["aren", "franco-aren"])
    heavy_soil = any(w in soil_lower for w in ["arcill"])

    phase_lower = " ".join(phases).lower()
    water_sensitive = any(w in phase_lower for w in ["cuaj", "fruto", "madur"])
    low_sensitive = any(w in phase_lower for w in ["reposo", "caída"])

    score = 0
    reasons = []

    if rain < 2:
        score += 2
        reasons.append(f"lluvia muy baja ({rain:.1f} mm)")
    elif rain < 8:
        score += 1
        reasons.append(f"lluvia escasa ({rain:.1f} mm)")
    elif rain >= 25:
        score -= 2
        reasons.append(f"lluvia suficiente/alta ({rain:.1f} mm)")
    elif rain >= 12:
        score -= 1
        reasons.append(f"lluvia moderada ({rain:.1f} mm)")

    if pd.notna(evap_value):
        if evap_value >= 65:
            score += 3
            reasons.append(f"demanda evaporativa alta ({evap_value:.0f}/100)")
        elif evap_value >= 45:
            score += 2
            reasons.append(f"demanda evaporativa media-alta ({evap_value:.0f}/100)")
        elif evap_value >= 30:
            score += 1
            reasons.append(f"demanda evaporativa moderada ({evap_value:.0f}/100)")

    if pd.notna(temp_max) and temp_max >= 30:
        score += 1
        reasons.append(f"temperatura máxima elevada ({temp_max:.1f} ºC)")
    if pd.notna(hr_mean) and hr_mean < 55:
        score += 1
        reasons.append(f"humedad relativa media baja ({hr_mean:.0f} %)")

    if rad_mj >= 120:
        score += 1
        reasons.append(f"radiación acumulada alta ({rad_mj:.1f} MJ/m²)")

    if pd.notna(wind_mean) and wind_mean >= 15:
        score += 1
        reasons.append(f"viento medio relevante ({wind_mean:.1f})")

    if fast_soil:
        score += 1
        reasons.append("suelo con menor retención de agua")
    if heavy_soil and rain >= 12:
        score -= 1
        reasons.append("suelo con mayor retención y lluvia reciente")

    if water_sensitive:
        score += 1
        reasons.append("fase sensible a estrés hídrico")
    if low_sensitive:
        score -= 1
        reasons.append("fase de menor demanda hídrica")

    if score >= 6:
        need = "Alta"
        box = st.error
    elif score >= 3:
        need = "Moderada"
        box = st.warning
    elif score >= 1:
        need = "Baja-moderada"
        box = st.info
    else:
        need = "Baja"
        box = st.success

    box(f"Necesidad orientativa de riego: **{need}**")

    st.write(f"**Fase fenológica detectada:** {phases_text}.")
    st.write(phase_sensitivity_text(phases))

    if reasons:
        st.write("**Motivos principales:** " + "; ".join(reasons) + ".")
    else:
        st.write("No se detecta una demanda hídrica relevante con los datos del periodo.")

    missing = []
    if not cols["rain"]:
        missing.append("precipitación")
    if not cols["temp"]:
        missing.append("temperatura")
    if not cols["hum"]:
        missing.append("humedad relativa")
    if not cols["rad"]:
        missing.append("radiación")
    if missing:
        st.caption("Aviso: la recomendación de riego es más limitada porque faltan columnas de " + ", ".join(missing) + ".")

    st.markdown("#### Recomendación práctica")

    recs = []
    if need == "Alta":
        recs.append("Revisar humedad real del suelo cuanto antes y valorar riego si no hay lluvia prevista.")
        recs.append("En suelos arenosos o franco-arenosos, priorizar riegos más cortos y repartidos para evitar pérdidas por drenaje.")
        recs.append("Evitar estrés hídrico prolongado si el cultivo está en cuajado, crecimiento de fruto o maduración.")
    elif need == "Moderada":
        recs.append("Comprobar humedad del suelo antes de regar. Si el suelo está seco en profundidad útil, valorar un riego moderado.")
        recs.append("Si hay previsión de lluvia próxima, puede ser preferible esperar o reducir dosis.")
        recs.append("En crecimiento de fruto, evitar alternancia fuerte entre sequía y riegos abundantes.")
    elif need == "Baja-moderada":
        recs.append("No parece urgente regar, pero conviene vigilar si continúan días secos, soleados o con viento.")
        recs.append("Revisar zonas más ligeras del suelo o árboles con más carga de fruto.")
    else:
        recs.append("No se aprecia necesidad clara de riego con los datos del periodo.")
        recs.append("Mantener seguimiento normal y reevaluar si suben temperaturas, radiación o viento, o si pasan varios días sin lluvia.")

    if heavy_soil:
        recs.append("En suelo arcilloso o franco-arcilloso, evitar riegos largos si el perfil aún conserva humedad para no favorecer asfixia radicular o exceso de humedad.")
    if fast_soil:
        recs.append("En suelo arenoso o franco-arenoso, la reserva útil se agota antes; es mejor vigilar con más frecuencia.")

    for rec in recs:
        st.write(f"- {rec}")

    st.caption(
        "Recomendación orientativa basada en clima, tipo de suelo y fenología registrada. "
        "Debe contrastarse con humedad real del suelo, previsión meteorológica y estado visual del cultivo."
    )



def sanitary_level_from_score(score):
    """Convierte una puntuación sanitaria en nivel y prioridad."""
    try:
        score = float(score)
    except Exception:
        score = 0.0

    if score >= 75:
        return "Alto", "🔴", "Revisar / priorizar"
    if score >= 45:
        return "Medio", "🟠", "Vigilancia alta"
    if score >= 20:
        return "Bajo-medio", "🟡", "Observar"
    return "Bajo", "🟢", "Seguimiento normal"


def recent_treatment_context_for_period(start_ts, end_ts, disease_keywords=None, max_days_before=21):
    """
    Busca tratamientos recientes en actuaciones de Agroptima alrededor del periodo analizado.
    Es orientativo porque Agroptima puede no indicar exactamente enfermedad objetivo.
    """
    activities = st.session_state.get("activities_df", pd.DataFrame())
    if activities is None or activities.empty:
        return {
            "tiene_actuaciones": False,
            "ultimo_tratamiento": "Sin actuaciones cargadas",
            "dias_desde": np.nan,
            "producto": "",
            "comentario": "No hay actuaciones Agroptima cargadas para cruzar cobertura reciente.",
        }

    acts = normalize_activities_df(activities)
    acts["Fecha"] = pd.to_datetime(acts.get("Fecha", pd.NaT), errors="coerce")
    acts = acts.dropna(subset=["Fecha"]).sort_values("Fecha")

    start_ts = pd.Timestamp(start_ts)
    end_ts = pd.Timestamp(end_ts)
    lower = start_ts - pd.Timedelta(days=int(max_days_before))
    recent = acts[(acts["Fecha"] >= lower) & (acts["Fecha"] <= end_ts)].copy()

    if disease_keywords:
        pattern = "|".join([re.escape(k) for k in disease_keywords if k])
        if pattern:
            text = (
                recent.get("Producto", "").astype(str) + " " +
                recent.get("Trabajo", "").astype(str) + " " +
                recent.get("Comentarios", "").astype(str)
            )
            matched = recent[text.str.contains(pattern, case=False, na=False)].copy()
            if not matched.empty:
                recent = matched

    if recent.empty:
        return {
            "tiene_actuaciones": True,
            "ultimo_tratamiento": f"No consta tratamiento relacionado en los {max_days_before} días previos",
            "dias_desde": np.nan,
            "producto": "",
            "comentario": "Sin cobertura reciente identificada en Agroptima para esta lectura.",
        }

    last = recent.iloc[-1]
    days_since = (end_ts.normalize() - pd.Timestamp(last["Fecha"]).normalize()).days
    producto = str(last.get("Producto", "") or "").strip()
    trabajo = str(last.get("Trabajo", "") or "").strip()
    fecha_txt = pd.Timestamp(last["Fecha"]).strftime("%d/%m/%Y")

    return {
        "tiene_actuaciones": True,
        "ultimo_tratamiento": f"{fecha_txt} · {producto or trabajo or 'actuación registrada'}",
        "dias_desde": days_since,
        "producto": producto,
        "comentario": f"Última actuación localizada: {fecha_txt}. Días hasta fin del periodo: {days_since}.",
    }




def sanitary_event_thresholds_text(temp_mean):
    """Devuelve explicación numérica de umbrales de evento para la temperatura media indicada."""
    if pd.isna(temp_mean):
        return (
            "- Criterio de evento: la app agrupa horas consecutivas con hoja mojada y cierra el evento tras varias horas secas.\n"
            "- No se pueden calcular umbrales numéricos porque falta temperatura media.\n"
            "- La app necesita temperatura del evento, horas húmedas equivalentes y humectación continua."
        )

    t = float(temp_mean)
    scab_th = scab_mills_threshold_hours(t)
    monilia_th = monilia_threshold_hours(t)

    def fmt_threshold(name, th):
        if pd.isna(th) or not th:
            return f"- {name}: umbral no calculable con esta temperatura."
        medium = 0.75 * th
        medium_high = 1.00 * th
        high = 1.25 * th
        return (
            f"- {name}: con {t:.1f} ºC, el umbral orientativo usado es {th:.1f} h húmedas equivalentes continuas. "
            f"Riesgo medio desde aprox. {medium:.1f} h (ratio ≥0,75), "
            f"medio-alto desde {medium_high:.1f} h (ratio ≥1,00) y alto desde {high:.1f} h (ratio ≥1,25)."
        )

    return "\n".join([
        "- Criterio de evento: la app agrupa horas consecutivas con hoja mojada y cierra el evento tras varias horas secas.",
        "- No usa solo la suma semanal, sino la duración húmeda continua dentro de cada episodio.",
        fmt_threshold("Moteado", scab_th),
        fmt_threshold("Monilia", monilia_th),
    ])


def explain_disease_climate_reason(disease, level, rain, wet_hours, hr90, temp_mean, events_count=0, high_events=0, oidium_hours=0, phases=None):
    """Explica por qué el riesgo climático justifica o no tratamiento y qué faltó para subir de nivel."""
    phases = phases or []
    phase_txt = ", ".join(phases) if phases else "sin fase fenológica registrada"
    level = str(level or "")
    thresholds = sanitary_event_thresholds_text(temp_mean)

    def temp_txt():
        return f"{temp_mean:.1f} ºC" if pd.notna(temp_mean) else "sin dato de temperatura"

    disease_low = str(disease).lower()

    if "moteado" in disease_low:
        if level in ["Alto", "Medio"]:
            lines = [
                f"- Por qué: riesgo climático {level.lower()} para moteado por {events_count} evento(s) medio/alto, {high_events} alto(s).",
                f"- {wet_hours:.0f} h de hoja húmeda acumulada en el periodo.",
                f"- {rain:.1f} mm de lluvia y temperatura media de {temp_txt()}.",
                f"- Fase: {phase_txt}.",
                "- Para que moteado pase a riesgo medio debe detectarse al menos un evento continuo que alcance alrededor del 75 % del umbral de moteado para la temperatura del episodio.",
                "- Para medio-alto o alto, el evento debe alcanzar o superar el 100–125 % del umbral.",
                thresholds,
            ]
        else:
            lines = [
                f"- Por qué: no se justifica tratamiento directo frente a moteado porque no se detectaron eventos continuos suficientes.",
                f"- Eventos detectados: {events_count} medio/alto y {high_events} alto(s).",
                f"- {wet_hours:.0f} h de hoja húmeda acumulada en el periodo.",
                f"- {rain:.1f} mm de lluvia y temperatura media de {temp_txt()}.",
                f"- Fase: {phase_txt}.",
                "- Para que moteado pase a riesgo medio debe detectarse al menos un evento continuo que alcance alrededor del 75 % del umbral de moteado para la temperatura del episodio.",
                "- Para medio-alto o alto, el evento debe alcanzar o superar el 100–125 % del umbral.",
                thresholds,
            ]
        return "\n".join(lines)

    if "monilia" in disease_low:
        if level in ["Alto", "Medio"]:
            lines = [
                f"- Por qué: riesgo climático {level.lower()} para monilia por {events_count} evento(s) medio/alto, {high_events} alto(s).",
                f"- {wet_hours:.0f} h de humectación acumulada en el periodo.",
                f"- {hr90:.0f} h con HR ≥90 %.",
                f"- {rain:.1f} mm de lluvia y temperatura media de {temp_txt()}.",
                f"- Fase: {phase_txt}.",
                "- Para que monilia pase a riesgo medio no basta con que la semana sea húmeda en total: debe aparecer un episodio continuo de humectación que alcance alrededor del 75 % del umbral calculado para la temperatura del evento.",
                "- Para medio-alto o alto, el evento debe alcanzar o superar el 100–125 % del umbral, con floración/fruto sensible y humedad/lluvia coincidiendo en el tiempo.",
                thresholds,
            ]
        else:
            lines = [
                f"- Por qué: riesgo bajo para monilia porque no se detectaron eventos continuos suficientes.",
                f"- Eventos detectados: {events_count} medio/alto y {high_events} alto(s).",
                f"- {wet_hours:.0f} h de humectación acumulada en el periodo.",
                f"- {hr90:.0f} h con HR ≥90 %.",
                f"- {rain:.1f} mm de lluvia y temperatura media de {temp_txt()}.",
                f"- Fase: {phase_txt}.",
                "- Para que monilia pase a riesgo medio no basta con que la semana sea húmeda en total: debe aparecer un episodio continuo de humectación que alcance alrededor del 75 % del umbral calculado para la temperatura del evento.",
                "- Para medio-alto o alto, el evento debe alcanzar o superar el 100–125 % del umbral, con floración/fruto sensible y humedad/lluvia coincidiendo en el tiempo.",
                thresholds,
            ]
        return "\n".join(lines)

    if "oídio" in disease_low or "oidio" in disease_low:
        if level in ["Alto", "Medio"]:
            lines = [
                f"- Por qué: riesgo climático {level.lower()} para oídio por {oidium_hours:.0f} h favorables.",
                f"- {hr90:.0f} h con HR ≥90 % y temperatura media de {temp_txt()}.",
                f"- Fase: {phase_txt}.",
                "- Para pasar a riesgo medio deben acumularse suficientes horas favorables para oídio, normalmente con temperaturas suaves y tejido activo.",
                "- Para riesgo alto, esas horas favorables deben ser persistentes.",
            ]
        else:
            lines = [
                f"- Por qué: no se justifica tratamiento directo frente a oídio.",
                f"- Se estiman {oidium_hours:.0f} h favorables.",
                f"- {hr90:.0f} h con HR ≥90 % y temperatura media de {temp_txt()}.",
                f"- Fase: {phase_txt}.",
                "- Para pasar a riesgo medio deben acumularse suficientes horas favorables para oídio, normalmente con temperaturas suaves y tejido activo.",
                "- Para riesgo alto, esas horas favorables deben ser persistentes.",
            ]
        return "\n".join(lines)

    if "estrés" in disease_low or "estres" in disease_low:
        if level in ["Alto", "Medio"]:
            lines = [
                f"- Por qué: demanda hídrica {level.lower()}.",
                f"- Lluvia del periodo: {rain:.1f} mm.",
                f"- Temperatura media: {temp_txt()}.",
                "- Para riesgo medio debe combinarse poca lluvia con demanda evaporativa moderada/alta.",
                "- Para riesgo alto, varios días con alta demanda evaporativa, temperaturas elevadas, escasa lluvia y suelo seco.",
            ]
        else:
            lines = [
                "- Por qué: no se aprecia estrés hídrico relevante.",
                f"- Lluvia del periodo: {rain:.1f} mm.",
                f"- Temperatura media: {temp_txt()}.",
                "- Para riesgo medio debe combinarse poca lluvia con demanda evaporativa moderada/alta.",
                "- Para riesgo alto, varios días con alta demanda evaporativa, temperaturas elevadas, escasa lluvia y suelo seco.",
            ]
        return "\n".join(lines)

    return "- Lectura climática no disponible para este riesgo."


def treatment_context_text_for_field(row):
    """Texto claro sobre tratamiento/variedad a partir de última actuación de campo."""
    if not row:
        return "Sin tratamiento registrado para este campo."
    fecha = pd.to_datetime(row.get("Fecha"), errors="coerce")
    fecha_txt = fecha.strftime("%d/%m/%Y") if pd.notna(fecha) else "fecha no disponible"
    prod = str(row.get("Producto", "") or "").strip() or "producto no especificado"
    variedades = str(row.get("Variedades tratadas", "") or "").strip()
    if not variedades:
        variedades = "variedades no especificadas en Agroptima"
    return f"{fecha_txt} · {prod} · {variedades}"



def build_sanitary_semaphore_table(period_df, soil_type, hoja_threshold, start_ts=None, end_ts=None):
    """Construye semáforo visual por enfermedad/riesgo para el periodo seleccionado."""
    if period_df is None or period_df.empty:
        return pd.DataFrame()

    df = add_risk_columns(period_df.copy(), hoja_humeda_threshold=hoja_threshold)
    if start_ts is None:
        start_ts = df["fecha_hora"].min()
    if end_ts is None:
        end_ts = df["fecha_hora"].max()

    cols = get_sensor_columns_safe(df)
    phases = current_phenology_phase_for_period(pd.Timestamp(start_ts), pd.Timestamp(end_ts))
    phase_lower = " ".join(phases).lower()
    sensitive_general = any(w in phase_lower for w in ["brot", "flor", "cuaj", "fruto", "madur"])
    flowering_sensitive = any(w in phase_lower for w in ["flor", "cuaj", "madur"])

    try:
        events = detect_leaf_wetness_events(df)
    except Exception:
        events = pd.DataFrame()

    if events is not None and not events.empty:
        events_exp = add_event_interpretation_columns(events, phases=phases)
    else:
        events_exp = pd.DataFrame()

    rain = float(get_numeric_series(df, [cols["rain"]]).sum()) if cols["rain"] else 0.0
    wet_hours = float((get_numeric_series(df, [cols["leaf"]]) >= hoja_threshold).sum()) if cols["leaf"] else 0.0
    hr90 = float((get_numeric_series(df, [cols["hum"]]) >= 90).sum()) if cols["hum"] else 0.0
    temp = get_numeric_series(df, [cols["temp"]], default=np.nan) if cols["temp"] else pd.Series(np.nan, index=df.index)
    temp_mean = float(temp.mean()) if temp.notna().any() else np.nan

    # Eventos por enfermedad.
    scab_events = 0
    scab_high = 0
    monilia_events = 0
    monilia_high = 0
    if not events_exp.empty:
        if "Riesgo moteado evento" in events_exp.columns:
            scab_events = int(events_exp["Riesgo moteado evento"].astype(str).str.contains("Medio|Alto", case=False, na=False).sum())
            scab_high = int(events_exp["Riesgo moteado evento"].astype(str).str.contains("Alto", case=False, na=False).sum())
        if "Riesgo monilia evento" in events_exp.columns:
            monilia_events = int(events_exp["Riesgo monilia evento"].astype(str).str.contains("Medio|Alto", case=False, na=False).sum())
            monilia_high = int(events_exp["Riesgo monilia evento"].astype(str).str.contains("Alto", case=False, na=False).sum())

    oidium_hours = float(df.get("riesgo_oidio", pd.Series(False, index=df.index)).sum()) if "riesgo_oidio" in df.columns else 0.0
    evap = float(df.get("indice_evaporativo_suelo", pd.Series(np.nan, index=df.index)).mean()) if "indice_evaporativo_suelo" in df.columns else np.nan

    rows = []

    # Moteado
    score = 0
    reasons = []
    if scab_high >= 1:
        score += 45
        reasons.append(f"{scab_high} evento(s) alto(s)")
    if scab_events >= 1:
        score += min(30, scab_events * 12)
        reasons.append(f"{scab_events} evento(s) medio/alto")
    if wet_hours >= 24:
        score += 15
        reasons.append(f"{wet_hours:.0f} h de hoja húmeda")
    elif wet_hours >= 8:
        score += 8
        reasons.append(f"{wet_hours:.0f} h de hoja húmeda")
    if rain >= 20:
        score += 10
        reasons.append(f"{rain:.1f} mm de lluvia")
    elif rain >= 5:
        score += 5
        reasons.append(f"{rain:.1f} mm de lluvia")
    if sensitive_general:
        score += 8
        reasons.append("fase sensible")

    level, icon, action = sanitary_level_from_score(score)
    treatment = recent_treatment_context_for_period(start_ts, end_ts, ["moteado", "folicur", "fungicida", "tebuconazol", "captan", "dodina", "cobre"])
    rows.append({
        "Semáforo": icon,
        "Riesgo": "Moteado",
        "Nivel": level,
        "Puntuación": round(min(score, 100), 1),
        "Indicadores": "; ".join(reasons) if reasons else "sin señales relevantes",
        "Explicación climática": explain_disease_climate_reason("Moteado", level, rain, wet_hours, hr90, temp_mean, scab_events, scab_high, oidium_hours, phases),
        "Tratamiento reciente": treatment["ultimo_tratamiento"],
        "Acción orientativa": "Priorizar revisión de hoja joven y cobertura preventiva." if level in ["Alto", "Medio"] else "Seguimiento normal salvo nuevas lluvias.",
        "Prioridad": action,
    })

    # Monilia
    score = 0
    reasons = []
    if monilia_high >= 1:
        score += 40
        reasons.append(f"{monilia_high} evento(s) alto(s)")
    if monilia_events >= 1:
        score += min(28, monilia_events * 12)
        reasons.append(f"{monilia_events} evento(s) medio/alto")
    if wet_hours >= 18:
        score += 14
        reasons.append(f"{wet_hours:.0f} h de humectación")
    if hr90 >= 24:
        score += 8
        reasons.append(f"{hr90:.0f} h con HR ≥90 %")
    if rain >= 10:
        score += 8
        reasons.append(f"{rain:.1f} mm de lluvia")
    if flowering_sensitive:
        score += 12
        reasons.append("fase especialmente sensible")

    level, icon, action = sanitary_level_from_score(score)
    treatment = recent_treatment_context_for_period(start_ts, end_ts, ["monilia", "folicur", "fungicida", "tebuconazol"])
    rows.append({
        "Semáforo": icon,
        "Riesgo": "Monilia",
        "Nivel": level,
        "Puntuación": round(min(score, 100), 1),
        "Indicadores": "; ".join(reasons) if reasons else "sin señales relevantes",
        "Explicación climática": explain_disease_climate_reason("Monilia", level, rain, wet_hours, hr90, temp_mean, monilia_events, monilia_high, oidium_hours, phases),
        "Tratamiento reciente": treatment["ultimo_tratamiento"],
        "Acción orientativa": "Revisar flor/fruto y zonas húmedas si coincide con fase sensible." if level in ["Alto", "Medio"] else "Seguimiento normal.",
        "Prioridad": action,
    })

    # Oídio
    score = 0
    reasons = []
    if oidium_hours >= 48:
        score += 45
        reasons.append(f"{oidium_hours:.0f} h favorables")
    elif oidium_hours >= 24:
        score += 30
        reasons.append(f"{oidium_hours:.0f} h favorables")
    elif oidium_hours >= 8:
        score += 15
        reasons.append(f"{oidium_hours:.0f} h favorables")
    if pd.notna(temp_mean) and 15 <= temp_mean <= 25:
        score += 10
        reasons.append(f"temperatura media favorable ({temp_mean:.1f} ºC)")
    if hr90 >= 12:
        score += 8
        reasons.append(f"{hr90:.0f} h con HR ≥90 %")
    if sensitive_general:
        score += 8
        reasons.append("tejido activo/sensible")

    level, icon, action = sanitary_level_from_score(score)
    treatment = recent_treatment_context_for_period(start_ts, end_ts, ["oidio", "oídio", "azufre", "folicur", "fungicida", "tebuconazol"])
    rows.append({
        "Semáforo": icon,
        "Riesgo": "Oídio",
        "Nivel": level,
        "Puntuación": round(min(score, 100), 1),
        "Indicadores": "; ".join(reasons) if reasons else "sin señales relevantes",
        "Explicación climática": explain_disease_climate_reason("Oídio", level, rain, wet_hours, hr90, temp_mean, 0, 0, oidium_hours, phases),
        "Tratamiento reciente": treatment["ultimo_tratamiento"],
        "Acción orientativa": "Vigilar brotes tiernos y variedades sensibles." if level in ["Alto", "Medio", "Bajo-medio"] else "Seguimiento normal.",
        "Prioridad": action,
    })

    # Estrés hídrico / demanda evaporativa
    score = 0
    reasons = []
    if pd.notna(evap):
        if evap >= 70:
            score += 45
            reasons.append(f"índice evaporativo alto ({evap:.0f})")
        elif evap >= 45:
            score += 25
            reasons.append(f"índice evaporativo medio ({evap:.0f})")
    if rain < 2 and pd.notna(evap) and evap >= 45:
        score += 20
        reasons.append("poca lluvia en el periodo")
    if pd.notna(temp_mean) and temp_mean >= 24:
        score += 12
        reasons.append(f"temperatura media elevada ({temp_mean:.1f} ºC)")
    if any(w in phase_lower for w in ["fruto", "madur", "cuaj"]):
        score += 8
        reasons.append("fase con demanda hídrica relevante")

    level, icon, action = sanitary_level_from_score(score)
    rows.append({
        "Semáforo": icon,
        "Riesgo": "Estrés hídrico",
        "Nivel": level,
        "Puntuación": round(min(score, 100), 1),
        "Indicadores": "; ".join(reasons) if reasons else "sin señales relevantes",
        "Explicación climática": explain_disease_climate_reason("Estrés hídrico", level, rain, wet_hours, hr90, temp_mean, 0, 0, oidium_hours, phases),
        "Tratamiento reciente": "No aplica",
        "Acción orientativa": "Comprobar humedad real de suelo y evolución de demanda." if level in ["Alto", "Medio", "Bajo-medio"] else "Sin necesidad clara de actuación.",
        "Prioridad": action,
    })

    return pd.DataFrame(rows)


def render_sanitary_semaphore(period_df, soil_type, hoja_threshold, start_ts=None, end_ts=None):
    """Renderiza panel visual de sanidad por semáforo."""
    st.markdown("#### Semáforo sanitario del periodo")

    sem = build_sanitary_semaphore_table(period_df, soil_type, hoja_threshold, start_ts=start_ts, end_ts=end_ts)
    if sem.empty:
        st.info("No hay datos suficientes para generar el semáforo sanitario.")
        return

    # Métricas superiores.
    levels = sem["Nivel"].astype(str)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Riesgos altos", int((levels == "Alto").sum()))
    c2.metric("Riesgos medios", int((levels == "Medio").sum()))
    c3.metric("Bajo-medio", int((levels == "Bajo-medio").sum()))
    c4.metric("Seguimiento normal", int((levels == "Bajo").sum()))

    st.caption(
        "El semáforo valora el riesgo climático del periodo. El tratamiento reciente mostrado es contexto general de Agroptima, "
        "no significa que todos los campos o todas las variedades estén cubiertos."
    )

    st.dataframe(
        sem[["Semáforo", "Riesgo", "Nivel", "Puntuación", "Indicadores", "Tratamiento reciente", "Acción orientativa"]],
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Lectura rápida del semáforo", expanded=True):
        for _, row in sem.sort_values("Puntuación", ascending=False).iterrows():
            st.markdown(f"**{row['Semáforo']} {row['Riesgo']} · {row['Nivel']}**")
            st.write(f"- Indicadores: {row['Indicadores']}")
            st.markdown(str(row.get("Explicación climática", "")))
            st.write(f"- Tratamiento reciente de contexto: {row['Tratamiento reciente']}")
            st.write(f"- Acción: {row['Acción orientativa']}")

    st.download_button(
        "Descargar semáforo sanitario",
        data=sem.to_csv(index=False).encode("utf-8-sig"),
        file_name="semaforo_sanitario_periodo.csv",
        mime="text/csv",
    )




# ---------------------------------------------------------------------------
# Motor inicial de recomendación técnica de tratamientos.
# No filtra por autorización legal del producto para manzano.
# ---------------------------------------------------------------------------

TREATMENT_PRODUCT_CATALOG = {
    "Signum": {
        "aliases": ["signum", "sigmun"],
        "materias_activas": "boscalida + piraclostrobin",
        "frac": ["7", "11"],
        "familia": "SDHI + QoI/estrobilurina",
        "eficacia": {
            "Moteado": 86,
            "Monilia": 78,
            "Oídio": 68,
        },
        "comentario": "Producto amplio, pero comparte FRAC 7 con Luna Experience y FRAC 11 con Flint.",
    },
    "Folicur": {
        "aliases": ["folicur", "tebuconazol", "tebuconazole"],
        "materias_activas": "tebuconazol",
        "frac": ["3"],
        "familia": "DMI / triazol",
        "eficacia": {
            "Moteado": 58,
            "Monilia": 72,
            "Oídio": 74,
        },
        "comentario": "DMI/triazol. Comparte FRAC 3 con Luna Experience.",
    },
    "Luna Experience": {
        "aliases": ["luna experience", "luna", "fluopyram", "fluopiram"],
        "materias_activas": "fluopyram + tebuconazol",
        "frac": ["7", "3"],
        "familia": "SDHI + DMI/triazol",
        "eficacia": {
            "Moteado": 82,
            "Monilia": 84,
            "Oídio": 86,
        },
        "comentario": "Amplio espectro. Comparte FRAC 7 con Signum y FRAC 3 con Folicur.",
    },
    "Flint": {
        "aliases": ["flint", "trifloxystrobin", "trifloxistrobin"],
        "materias_activas": "trifloxistrobin",
        "frac": ["11"],
        "familia": "QoI / estrobilurina",
        "eficacia": {
            "Moteado": 74,
            "Monilia": 55,
            "Oídio": 82,
        },
        "comentario": "QoI/estrobilurina. Comparte FRAC 11 con Signum.",
    },
}


def default_treatment_catalog_copy():
    """Devuelve una copia independiente del catálogo base, sin depender de variables globales."""
    base_catalog = {
    "Signum": {
        "aliases": ["signum", "sigmun"],
        "materias_activas": "boscalida + piraclostrobin",
        "frac": ["7", "11"],
        "familia": "SDHI + QoI/estrobilurina",
        "eficacia": {
            "Moteado": 86,
            "Monilia": 78,
            "Oídio": 68,
        },
        "comentario": "Producto amplio, pero comparte FRAC 7 con Luna Experience y FRAC 11 con Flint.",
    },
    "Folicur": {
        "aliases": ["folicur", "tebuconazol", "tebuconazole"],
        "materias_activas": "tebuconazol",
        "frac": ["3"],
        "familia": "DMI / triazol",
        "eficacia": {
            "Moteado": 58,
            "Monilia": 72,
            "Oídio": 74,
        },
        "comentario": "DMI/triazol. Comparte FRAC 3 con Luna Experience.",
    },
    "Luna Experience": {
        "aliases": ["luna experience", "luna", "fluopyram", "fluopiram"],
        "materias_activas": "fluopyram + tebuconazol",
        "frac": ["7", "3"],
        "familia": "SDHI + DMI/triazol",
        "eficacia": {
            "Moteado": 82,
            "Monilia": 84,
            "Oídio": 86,
        },
        "comentario": "Amplio espectro. Comparte FRAC 7 con Signum y FRAC 3 con Folicur.",
    },
    "Flint": {
        "aliases": ["flint", "trifloxystrobin", "trifloxistrobin"],
        "materias_activas": "trifloxistrobin",
        "frac": ["11"],
        "familia": "QoI / estrobilurina",
        "eficacia": {
            "Moteado": 74,
            "Monilia": 55,
            "Oídio": 82,
        },
        "comentario": "QoI/estrobilurina. Comparte FRAC 11 con Signum.",
    },
}
    return copy.deepcopy(base_catalog)


def get_treatment_product_catalog():
    """
    Catálogo activo de productos.
    Permite que en el futuro se incorporen nuevos fungicidas sin tocar código.
    """
    current = st.session_state.get("treatment_product_catalog", None)
    if not isinstance(current, dict) or not current:
        st.session_state.treatment_product_catalog = default_treatment_catalog_copy()
    return st.session_state.treatment_product_catalog


def treatment_catalog_to_dataframe(catalog=None):
    catalog = catalog or get_treatment_product_catalog()
    rows = []
    for product, info in catalog.items():
        rows.append({
            "Producto": product,
            "Alias": ", ".join(info.get("aliases", [])),
            "Materias activas": info.get("materias_activas", ""),
            "FRAC": "+".join([str(x) for x in info.get("frac", [])]),
            "Familia": info.get("familia", ""),
            "Eficacia moteado": info.get("eficacia", {}).get("Moteado", 50),
            "Eficacia monilia": info.get("eficacia", {}).get("Monilia", 50),
            "Eficacia oídio": info.get("eficacia", {}).get("Oídio", 50),
            "Comentario": info.get("comentario", ""),
            "Activo": bool(info.get("activo", True)),
        })
    return pd.DataFrame(rows)


def dataframe_to_treatment_catalog(df):
    """Convierte tabla editable en catálogo interno."""
    catalog = {}
    if df is None or df.empty:
        return catalog

    for _, row in df.iterrows():
        product = str(row.get("Producto", "") or "").strip()
        if not product:
            continue

        aliases = [a.strip().lower() for a in str(row.get("Alias", "") or "").split(",") if a.strip()]
        aliases.append(product.lower())
        aliases = sorted(set(aliases))

        frac_raw = str(row.get("FRAC", "") or "").replace(",", "+").replace("/", "+")
        frac = [f.strip() for f in frac_raw.split("+") if f.strip()]

        def safe_float(value, default=50):
            try:
                return float(value)
            except Exception:
                return default

        catalog[product] = {
            "aliases": aliases,
            "materias_activas": str(row.get("Materias activas", "") or "").strip(),
            "frac": frac,
            "familia": str(row.get("Familia", "") or "").strip(),
            "eficacia": {
                "Moteado": safe_float(row.get("Eficacia moteado", 50), 50),
                "Monilia": safe_float(row.get("Eficacia monilia", 50), 50),
                "Oídio": safe_float(row.get("Eficacia oídio", 50), 50),
            },
            "comentario": str(row.get("Comentario", "") or "").strip(),
            "activo": bool(row.get("Activo", True)),
        }

    return catalog



def treatment_catalog_dataframe_for_supabase(df):
    """Convierte el editor del catálogo al esquema de Supabase."""
    if df is None or df.empty:
        return []

    records = []
    for _, row in df.iterrows():
        product = str(row.get("Producto", "") or "").strip()
        if not product:
            continue

        def safe_float(value, default=50):
            value = pd.to_numeric(value, errors="coerce")
            return float(default) if pd.isna(value) else float(value)

        active_value = row.get("Activo", True)
        if isinstance(active_value, str):
            active = active_value.strip().lower() not in ["false", "0", "no", "no activo", "nan", "none"]
        else:
            active = bool(active_value)

        records.append({
            "product": product,
            "alias": str(row.get("Alias", "") or "").strip(),
            "materias_activas": str(row.get("Materias activas", "") or "").strip(),
            "frac": str(row.get("FRAC", "") or "").strip(),
            "familia": str(row.get("Familia", "") or "").strip(),
            "eficacia_moteado": safe_float(row.get("Eficacia moteado", 50), 50),
            "eficacia_monilia": safe_float(row.get("Eficacia monilia", 50), 50),
            "eficacia_oidio": safe_float(row.get("Eficacia oídio", 50), 50),
            "comentario": str(row.get("Comentario", "") or "").strip(),
            "activo": active,
        })

    return records


def supabase_rows_to_treatment_catalog_dataframe(rows):
    """Convierte filas de Supabase al formato del editor del catálogo."""
    if not rows:
        return pd.DataFrame(columns=[
            "Producto", "Alias", "Materias activas", "FRAC", "Familia",
            "Eficacia moteado", "Eficacia monilia", "Eficacia oídio",
            "Comentario", "Activo"
        ])

    out = []
    for row in rows:
        out.append({
            "Producto": row.get("product", ""),
            "Alias": row.get("alias", ""),
            "Materias activas": row.get("materias_activas", ""),
            "FRAC": row.get("frac", ""),
            "Familia": row.get("familia", ""),
            "Eficacia moteado": row.get("eficacia_moteado", 50),
            "Eficacia monilia": row.get("eficacia_monilia", 50),
            "Eficacia oídio": row.get("eficacia_oidio", 50),
            "Comentario": row.get("comentario", ""),
            "Activo": bool(row.get("activo", True)),
        })

    return pd.DataFrame(out)


def load_treatment_catalog_from_supabase():
    """Carga catálogo de productos desde Supabase."""
    if not supabase_is_configured():
        return False, "Supabase no está configurado. Revisa SUPABASE_URL y SUPABASE_KEY en Secrets.", pd.DataFrame()

    endpoint = supabase_table_url(SUPABASE_TREATMENT_CATALOG_TABLE)
    headers = supabase_headers()
    response = requests.get(
        endpoint,
        headers=headers,
        params={
            "select": "product,alias,materias_activas,frac,familia,eficacia_moteado,eficacia_monilia,eficacia_oidio,comentario,activo",
            "order": "product.asc",
        },
        timeout=60,
    )
    if response.status_code != 200:
        return False, f"Error cargando catálogo desde Supabase: {response.status_code} · {response.text[:500]}", pd.DataFrame()

    df = supabase_rows_to_treatment_catalog_dataframe(response.json())
    return True, f"Catálogo cargado desde Supabase: {len(df)} productos.", df


def save_treatment_catalog_to_supabase(df):
    """Guarda el catálogo completo en Supabase reemplazando la tabla actual."""
    if not supabase_is_configured():
        return False, "Supabase no está configurado. Revisa SUPABASE_URL y SUPABASE_KEY en Secrets."

    records = treatment_catalog_dataframe_for_supabase(df)
    if not records:
        return False, "No hay productos válidos para guardar."

    endpoint = supabase_table_url(SUPABASE_TREATMENT_CATALOG_TABLE)
    headers = supabase_headers()

    # Reemplazo completo para que si se borra un producto en el editor, también desaparezca en Supabase.
    delete_headers = headers.copy()
    delete_headers["Prefer"] = "return=minimal"
    delete_response = requests.delete(
        endpoint,
        headers=delete_headers,
        params={"product": "not.is.null"},
        timeout=60,
    )
    if delete_response.status_code not in (200, 204):
        return False, f"Error limpiando catálogo anterior en Supabase: {delete_response.status_code} · {delete_response.text[:500]}"

    post_headers = headers.copy()
    post_headers["Prefer"] = "return=minimal"
    response = requests.post(
        endpoint,
        headers=post_headers,
        json=records,
        timeout=60,
    )
    if response.status_code not in (200, 201, 204):
        return False, f"Error guardando catálogo en Supabase: {response.status_code} · {response.text[:500]}"

    return True, f"Catálogo guardado en Supabase: {len(records)} productos."




def reset_treatment_catalog_to_default():
    st.session_state.treatment_product_catalog = default_treatment_catalog_copy()


def detect_unknown_products_from_activities(activities_df, catalog=None):
    """Detecta productos presentes en Agroptima que no están reconocidos en el catálogo."""
    columns = ["Producto Agroptima", "Veces", "Primera fecha", "Última fecha", "Campos"]

    if activities_df is None or activities_df.empty:
        return pd.DataFrame(columns=columns)

    catalog = catalog or get_treatment_product_catalog()
    acts = normalize_activities_df(activities_df)
    if acts is None or acts.empty or "Producto" not in acts.columns:
        return pd.DataFrame(columns=columns)

    acts["Fecha"] = pd.to_datetime(acts.get("Fecha", pd.NaT), errors="coerce")

    rows = []
    for product, group in acts.groupby(acts["Producto"].astype(str)):
        product_clean = str(product or "").strip()
        if not product_clean or product_clean.lower() in ["nan", "none"]:
            continue

        recognized = ""
        txt = product_clean.lower()
        for cat_product, info in catalog.items():
            if any(str(alias).lower() in txt for alias in info.get("aliases", [])):
                recognized = cat_product
                break

        if recognized:
            continue

        if "Campos reconocidos" in group.columns:
            campos = sorted(set(
                c.strip()
                for val in group["Campos reconocidos"].astype(str)
                for c in val.split(",")
                if c.strip() and c.strip().lower() not in ["nan", "none"]
            ))
        else:
            campos = []

        rows.append({
            "Producto Agroptima": product_clean,
            "Veces": int(len(group)),
            "Primera fecha": group["Fecha"].min().strftime("%d/%m/%Y") if group["Fecha"].notna().any() else "",
            "Última fecha": group["Fecha"].max().strftime("%d/%m/%Y") if group["Fecha"].notna().any() else "",
            "Campos": ", ".join(campos[:8]) + ("..." if len(campos) > 8 else ""),
        })

    if not rows:
        return pd.DataFrame(columns=columns)

    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values(["Veces", "Producto Agroptima"], ascending=[False, True])
        .reset_index(drop=True)
    )


def treatment_usage_by_product_and_frac(activities_df, catalog=None):
    """Resumen de usos de productos y FRAC por campaña/campo a partir de Agroptima."""
    if activities_df is None or activities_df.empty:
        return pd.DataFrame()

    catalog = catalog or get_treatment_product_catalog()
    exp = expand_activities_by_field_for_recommendation(activities_df)
    if exp.empty:
        return pd.DataFrame()

    rows = []
    for _, row in exp.iterrows():
        product_norm = normalize_product_name_for_recommendation(row.get("Producto normalizado") or row.get("Producto"))
        info = catalog.get(product_norm, {})
        fecha = pd.to_datetime(row.get("Fecha"), errors="coerce")
        year = int(fecha.year) if pd.notna(fecha) else np.nan
        frac = "+".join(info.get("frac", [])) if info else "No catalogado"
        rows.append({
            "Año": year,
            "Campo": row.get("Campo", ""),
            "Producto Agroptima": row.get("Producto", ""),
            "Producto catalogado": product_norm if product_norm in catalog else "No catalogado",
            "FRAC": frac,
            "Materias activas": info.get("materias_activas", ""),
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    summary = (
        out.groupby(["Año", "Campo", "Producto catalogado", "FRAC", "Materias activas"], dropna=False)
        .size()
        .reset_index(name="Número tratamientos")
        .sort_values(["Año", "Campo", "Número tratamientos"], ascending=[True, True, False])
    )
    return summary



def frac_tokens_from_text(frac_text):
    """Extrae grupos FRAC simples desde texto tipo '7+11'."""
    txt = str(frac_text or "").replace(",", "+").replace("/", "+").replace(";", "+")
    return [x.strip() for x in txt.split("+") if x.strip()]


def build_frac_rotation_plan(activities_df, catalog=None, season_year=None):
    """
    Genera un plan orientativo de rotación FRAC para la próxima campaña.

    No valida autorización legal ni etiqueta. Solo analiza repetición de productos/grupos FRAC
    y propone alternancia a partir del catálogo activo.
    """
    fields_df = get_fields_base_df()
    catalog = catalog or get_treatment_product_catalog()

    if fields_df is None or fields_df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    if activities_df is None or activities_df.empty:
        # Todos los campos sin actuaciones.
        rows = []
        for _, frow in fields_df.iterrows():
            rows.append({
                "Campo": frow.get("Campo", ""),
                "Variedades actuales": frow.get("Variedades actuales", ""),
                "Superficie ha": frow.get("Superficie ha", np.nan),
                "Campaña analizada": season_year or "",
                "Tratamientos campaña": 0,
                "Productos usados": "Sin actuaciones",
                "FRAC usados": "Sin actuaciones",
                "FRAC más usado": "",
                "Riesgo repetición FRAC": "Sin datos",
                "Productos a descansar": "Sin datos",
                "Producto/FRAC preferente próxima campaña": "Cargar actuaciones para recomendar.",
                "Alternativas del catálogo": "",
                "Comentario técnico": "No hay actuaciones Agroptima cargadas para calcular presión FRAC.",
            })
        return pd.DataFrame(rows), pd.DataFrame(), pd.DataFrame()

    exp = expand_activities_by_field_for_recommendation(activities_df)
    if exp.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    exp["Fecha"] = pd.to_datetime(exp["Fecha"], errors="coerce")
    exp = exp.dropna(subset=["Fecha"])
    if exp.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    available_years = sorted(exp["Fecha"].dt.year.dropna().astype(int).unique().tolist())
    if season_year is None:
        season_year = max(available_years) if available_years else pd.Timestamp.today().year

    data = exp[exp["Fecha"].dt.year.astype(int) == int(season_year)].copy()
    if data.empty:
        data = exp.copy()

    # Enriquecer cada actuación con catálogo y FRAC.
    enriched = []
    for _, row in data.iterrows():
        product_raw = str(row.get("Producto", "") or "").strip()
        product_norm = normalize_product_name_for_recommendation(row.get("Producto normalizado") or product_raw)
        info = catalog.get(product_norm, {})
        fracs = info.get("frac", []) if info else []
        if not fracs and product_norm not in catalog:
            fracs = ["No catalogado"]
        for frac in fracs or ["Sin FRAC"]:
            enriched.append({
                "Campo": row.get("Campo", ""),
                "Fecha": row.get("Fecha"),
                "Producto Agroptima": product_raw,
                "Producto catalogado": product_norm if product_norm in catalog else "No catalogado",
                "FRAC": str(frac),
                "Materias activas": info.get("materias_activas", "") if info else "",
                "Variedades tratadas": row.get("Variedades tratadas", "") or "Agroptima no especifica variedad",
            })

    enriched_df = pd.DataFrame(enriched)
    if enriched_df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    frac_summary = (
        enriched_df.groupby(["FRAC"], dropna=False)
        .agg(
            Tratamientos=("FRAC", "size"),
            Campos=("Campo", lambda s: ", ".join(sorted(set([str(x) for x in s if str(x).strip()]))[:12])),
            Productos=("Producto catalogado", lambda s: ", ".join(sorted(set([str(x) for x in s if str(x).strip()])))),
        )
        .reset_index()
        .sort_values("Tratamientos", ascending=False)
    )

    product_summary = (
        enriched_df.groupby(["Producto catalogado", "FRAC", "Materias activas"], dropna=False)
        .agg(
            Tratamientos=("Producto catalogado", "size"),
            Campos=("Campo", lambda s: ", ".join(sorted(set([str(x) for x in s if str(x).strip()]))[:12])),
        )
        .reset_index()
        .sort_values("Tratamientos", ascending=False)
    )

    # Productos activos alternativos por FRAC.
    catalog_rows = []
    for prod, info in catalog.items():
        if not info.get("activo", True):
            continue
        catalog_rows.append({
            "Producto": prod,
            "FRAC set": set([str(x) for x in info.get("frac", [])]),
            "FRAC": "+".join([str(x) for x in info.get("frac", [])]),
            "Materias activas": info.get("materias_activas", ""),
            "Familia": info.get("familia", ""),
        })
    catalog_alt = pd.DataFrame(catalog_rows)

    rows = []
    for _, frow in fields_df.iterrows():
        campo = str(frow.get("Campo", "") or "").strip()
        if not campo:
            continue

        d = enriched_df[enriched_df["Campo"].astype(str) == campo].copy()
        if d.empty:
            rows.append({
                "Campo": campo,
                "Variedades actuales": frow.get("Variedades actuales", ""),
                "Superficie ha": frow.get("Superficie ha", np.nan),
                "Campaña analizada": int(season_year),
                "Tratamientos campaña": 0,
                "Productos usados": "Sin tratamiento registrado",
                "FRAC usados": "Sin tratamiento registrado",
                "FRAC más usado": "",
                "Riesgo repetición FRAC": "Sin presión registrada",
                "Productos a descansar": "Ninguno por datos registrados",
                "Producto/FRAC preferente próxima campaña": "No hay presión FRAC registrada; elegir según riesgo climático y revisión de campo.",
                "Alternativas del catálogo": ", ".join(catalog_alt["Producto"].tolist()[:4]) if not catalog_alt.empty else "",
                "Comentario técnico": "Campo sin tratamientos registrados en la campaña analizada.",
            })
            continue

        product_counts = d.groupby("Producto catalogado").size().sort_values(ascending=False)
        frac_counts = d.groupby("FRAC").size().sort_values(ascending=False)
        products_used = "; ".join([f"{p} ({int(n)})" for p, n in product_counts.items()])
        fracs_used = "; ".join([f"{f} ({int(n)})" for f, n in frac_counts.items()])
        most_frac = str(frac_counts.index[0])
        most_frac_n = int(frac_counts.iloc[0])

        overused_products = [p for p, n in product_counts.items() if int(n) >= 2 and str(p) != "No catalogado"]
        overused_fracs = [f for f, n in frac_counts.items() if int(n) >= 2 and str(f) not in ["No catalogado", "Sin FRAC"]]

        used_frac_set = set([str(x) for x in d["FRAC"].dropna().astype(str).tolist()])
        if catalog_alt.empty:
            alternatives = []
        else:
            alt = catalog_alt[
                catalog_alt["FRAC set"].apply(lambda s: len(set(s) & used_frac_set) == 0 if isinstance(s, set) else False)
            ].copy()
            if alt.empty:
                alt = catalog_alt[
                    catalog_alt["FRAC set"].apply(lambda s: str(most_frac) not in set(s) if isinstance(s, set) else False)
                ].copy()
            alternatives = alt["Producto"].tolist()[:4]

        if overused_fracs or most_frac_n >= 3:
            risk = "Alto"
            recommendation = (
                f"Descansar FRAC {', '.join(overused_fracs) if overused_fracs else most_frac} y evitar repetir productos usados dos o más veces."
            )
        elif most_frac_n == 2:
            risk = "Medio"
            recommendation = f"Evitar empezar la próxima campaña repitiendo FRAC {most_frac}; alternar modo de acción."
        else:
            risk = "Bajo-medio"
            recommendation = "Mantener alternancia y evitar repetir el mismo producto consecutivamente."

        if alternatives:
            recommendation += f" Alternativas del catálogo con otro FRAC: {', '.join(alternatives)}."
        else:
            recommendation += " No hay alternativa clara en el catálogo actual; ampliar catálogo o revisar estrategia."

        rows.append({
            "Campo": campo,
            "Variedades actuales": frow.get("Variedades actuales", ""),
            "Superficie ha": frow.get("Superficie ha", np.nan),
            "Campaña analizada": int(season_year),
            "Tratamientos campaña": int(len(d.drop_duplicates(subset=["Fecha", "Producto Agroptima"]))),
            "Productos usados": products_used,
            "FRAC usados": fracs_used,
            "FRAC más usado": f"{most_frac} ({most_frac_n})",
            "Riesgo repetición FRAC": risk,
            "Productos a descansar": ", ".join(overused_products) if overused_products else "Ninguno con 2+ usos",
            "Producto/FRAC preferente próxima campaña": recommendation,
            "Alternativas del catálogo": ", ".join(alternatives),
            "Comentario técnico": (
                "Si Agroptima no especifica variedad tratada, revisar si la cobertura fue de todo el campo o solo parcial."
            ),
        })

    plan = pd.DataFrame(rows)
    if not plan.empty:
        order = {"Alto": 0, "Medio": 1, "Bajo-medio": 2, "Sin presión registrada": 3}
        plan["_orden"] = plan["Riesgo repetición FRAC"].map(order).fillna(9)
        plan = plan.sort_values(["_orden", "Campo"]).drop(columns=["_orden"], errors="ignore").reset_index(drop=True)

    return plan, frac_summary, product_summary


def render_frac_rotation_plan(activities_df=None, key_suffix='main'):
    """Renderiza plan orientativo de rotación FRAC para próxima campaña."""
    st.markdown("#### Plan orientativo de rotación FRAC para próxima campaña")

    st.warning(
        "Plan orientativo basado en actuaciones registradas y catálogo activo. "
        "No valida autorización legal, etiqueta, dosis, plazo de seguridad ni número máximo de aplicaciones."
    )

    if activities_df is None:
        activities_df = st.session_state.get("activities_df", pd.DataFrame(columns=ACTIVITY_COLUMNS))

    if activities_df is None or activities_df.empty:
        st.info("Carga actuaciones Agroptima para generar el plan de rotación.")
        return

    acts = normalize_activities_df(activities_df)
    fechas = pd.to_datetime(acts.get("Fecha", pd.Series(dtype=str)), errors="coerce")
    years = sorted(fechas.dropna().dt.year.astype(int).unique().tolist())
    if not years:
        st.info("No hay fechas válidas en las actuaciones para generar la campaña.")
        return

    selected_year = st.selectbox(
        "Campaña/año de actuaciones a analizar",
        options=years,
        index=len(years) - 1,
        key=f"frac_rotation_year_v892_{key_suffix}",
        help="Analiza los tratamientos de ese año y propone qué FRAC conviene descansar o alternar.",
    )

    plan, frac_summary, product_summary = build_frac_rotation_plan(
        activities_df,
        get_treatment_product_catalog(),
        season_year=int(selected_year),
    )

    if plan.empty:
        st.info("No hay datos suficientes para generar el plan de rotación.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Campos analizados", len(plan))
    c2.metric("Riesgo FRAC alto", int((plan["Riesgo repetición FRAC"] == "Alto").sum()))
    c3.metric("Riesgo FRAC medio", int((plan["Riesgo repetición FRAC"] == "Medio").sum()))
    c4.metric("Sin presión registrada", int((plan["Riesgo repetición FRAC"] == "Sin presión registrada").sum()))

    st.markdown("##### Prioridad por campo")
    visible_cols = [
        "Campo", "Riesgo repetición FRAC", "Tratamientos campaña", "Productos usados", "FRAC usados",
        "FRAC más usado", "Productos a descansar", "Producto/FRAC preferente próxima campaña",
        "Variedades actuales", "Comentario técnico",
    ]
    visible_cols = [c for c in visible_cols if c in plan.columns]
    st.dataframe(plan[visible_cols], use_container_width=True, hide_index=True)

    st.download_button(
        "Descargar plan de rotación FRAC por campo",
        data=plan.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"plan_rotacion_frac_{selected_year}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    with st.expander("Resumen de presión por grupo FRAC", expanded=True):
        if frac_summary.empty:
            st.info("Sin resumen FRAC.")
        else:
            st.dataframe(frac_summary, use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar resumen FRAC",
                data=frac_summary.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"resumen_frac_{selected_year}.csv",
                mime="text/csv",
            )

    with st.expander("Resumen por producto", expanded=False):
        if product_summary.empty:
            st.info("Sin resumen por producto.")
        else:
            st.dataframe(product_summary, use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar resumen productos",
                data=product_summary.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"resumen_productos_frac_{selected_year}.csv",
                mime="text/csv",
            )



def render_treatment_catalog_manager():
    """Panel editable para mantener catálogo de fungicidas y reconocer productos de Agroptima."""
    st.markdown("#### Catálogo ampliable de productos fitosanitarios")

    st.caption(
        "Este catálogo permite que la app reconozca productos nuevos importados desde Agroptima. "
        "Si el año que viene se incorporan otros fungicidas, añádelos aquí con materias activas, FRAC y eficacia orientativa."
    )

    catalog = get_treatment_product_catalog()
    catalog_df = treatment_catalog_to_dataframe(catalog)

    edited = st.data_editor(
        catalog_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="treatment_catalog_editor_v87",
        column_config={
            "Activo": st.column_config.CheckboxColumn("Activo"),
            "Eficacia moteado": st.column_config.NumberColumn("Eficacia moteado", min_value=0, max_value=100, step=1),
            "Eficacia monilia": st.column_config.NumberColumn("Eficacia monilia", min_value=0, max_value=100, step=1),
            "Eficacia oídio": st.column_config.NumberColumn("Eficacia oídio", min_value=0, max_value=100, step=1),
        },
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Guardar catálogo en la sesión", use_container_width=True):
            new_catalog = dataframe_to_treatment_catalog(edited)
            if not new_catalog:
                st.error("El catálogo no puede quedar vacío.")
            else:
                st.session_state.treatment_product_catalog = new_catalog
                st.success("Catálogo actualizado en la sesión.")

    with c2:
        if st.button("Restaurar catálogo base", use_container_width=True):
            reset_treatment_catalog_to_default()
            st.success("Catálogo restaurado a los productos base.")
            st.rerun()

    with c3:
        st.download_button(
            "Descargar catálogo CSV",
            data=edited.to_csv(index=False).encode("utf-8-sig"),
            file_name="catalogo_fungicidas_finca_gallinal.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("##### Persistencia en Supabase")
    st.caption(
        "Usa estos botones para que el catálogo quede guardado en la nube y no dependa solo de la sesión actual."
    )
    sc1, sc2 = st.columns(2)
    with sc1:
        if st.button("Cargar catálogo desde Supabase", use_container_width=True):
            ok, msg, df_cloud = load_treatment_catalog_from_supabase()
            if ok:
                new_catalog = dataframe_to_treatment_catalog(df_cloud)
                if new_catalog:
                    st.session_state.treatment_product_catalog = new_catalog
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning("Supabase respondió, pero no hay productos válidos en el catálogo.")
            else:
                st.error(msg)

    with sc2:
        if st.button("Guardar catálogo en Supabase", use_container_width=True):
            ok, msg = save_treatment_catalog_to_supabase(edited)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    uploaded_catalog = st.file_uploader(
        "Importar catálogo CSV actualizado",
        type=["csv"],
        key="upload_treatment_catalog_v87",
        help="Debe tener columnas similares a las del catálogo editable.",
    )
    if uploaded_catalog is not None:
        try:
            new_df = pd.read_csv(uploaded_catalog)
            new_catalog = dataframe_to_treatment_catalog(new_df)
            if new_catalog:
                st.session_state.treatment_product_catalog = new_catalog
                st.success("Catálogo importado correctamente.")
                st.rerun()
            else:
                st.error("No se han encontrado productos válidos en el CSV.")
        except Exception as exc:
            st.error(f"No se pudo importar el catálogo: {exc}")

    with st.expander("SQL necesario para Supabase · Catálogo de productos", expanded=False):
        st.code("""
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
""", language="sql")

    activities_df = st.session_state.get("activities_df", pd.DataFrame(columns=ACTIVITY_COLUMNS))

    with st.expander("Productos de Agroptima no reconocidos", expanded=True):
        unknown = detect_unknown_products_from_activities(activities_df, get_treatment_product_catalog())
        if activities_df is None or activities_df.empty:
            st.info("Carga actuaciones Agroptima para detectar productos no catalogados.")
        elif unknown.empty:
            st.success("Todos los productos de Agroptima están reconocidos por el catálogo activo.")
        else:
            st.warning("Hay productos en Agroptima que todavía no están catalogados. Añádelos arriba para que la app pueda analizarlos por FRAC.")
            st.dataframe(unknown, use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar productos no reconocidos",
                data=unknown.to_csv(index=False).encode("utf-8-sig"),
                file_name="productos_agroptima_no_reconocidos.csv",
                mime="text/csv",
            )

    with st.expander("Resumen de uso por producto y FRAC", expanded=False):
        usage = treatment_usage_by_product_and_frac(activities_df, get_treatment_product_catalog())
        if usage.empty:
            st.info("No hay actuaciones suficientes para generar el resumen.")
        else:
            st.dataframe(usage, use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar resumen producto FRAC",
                data=usage.to_csv(index=False).encode("utf-8-sig"),
                file_name="resumen_usos_producto_frac.csv",
                mime="text/csv",
            )




def normalize_product_name_for_recommendation(name):
    txt = str(name or "").lower().strip()
    if not txt:
        return ""
    try:
        catalog = get_treatment_product_catalog()
    except Exception:
        catalog = default_treatment_catalog_copy()
    for product, info in catalog.items():
        if any(str(alias).lower() in txt for alias in info.get("aliases", [])):
            return product
    return str(name or "").strip()


def expand_activities_by_field_for_recommendation(activities_df):
    """Expande actuaciones Agroptima a una fila por campo reconocido."""
    if activities_df is None or activities_df.empty:
        return pd.DataFrame(columns=["Campo", "Fecha", "Producto normalizado", "Producto", "Trabajo", "Comentarios"])

    acts = normalize_activities_df(activities_df)
    rows = []
    for _, row in acts.iterrows():
        fecha = pd.to_datetime(row.get("Fecha", ""), errors="coerce")
        if pd.isna(fecha):
            continue
        campos = [c.strip() for c in str(row.get("Campos reconocidos", "")).split(",") if c.strip()]
        prod = str(row.get("Producto", "") or "").strip()
        for campo in campos:
            rows.append({
                "Campo": campo,
                "Fecha": fecha,
                "Producto": prod,
                "Producto normalizado": normalize_product_name_for_recommendation(prod),
                "Trabajo": row.get("Trabajo", ""),
                "Comentarios": row.get("Comentarios", ""),
                "Variedades tratadas": row.get("Cultivos / variedades Agroptima", "") or row.get("Variedades", "") or "",
            })
    if not rows:
        return pd.DataFrame(columns=["Campo", "Fecha", "Producto normalizado", "Producto", "Trabajo", "Comentarios"])
    return pd.DataFrame(rows).sort_values(["Campo", "Fecha"])


def field_product_use_counts(acts_expanded, field, campaign_start, campaign_end):
    """Cuenta usos por producto y campo dentro de la campaña seleccionada."""
    if acts_expanded is None or acts_expanded.empty:
        return {}
    data = acts_expanded[
        (acts_expanded["Campo"].astype(str) == str(field)) &
        (acts_expanded["Fecha"] >= pd.Timestamp(campaign_start)) &
        (acts_expanded["Fecha"] <= pd.Timestamp(campaign_end))
    ].copy()
    counts = {}
    for product in get_treatment_product_catalog().keys():
        counts[product] = int((data["Producto normalizado"] == product).sum())
    return counts


def last_field_treatment(acts_expanded, field, end_ts=None):
    """Devuelve última actuación de un campo antes del final del periodo."""
    if acts_expanded is None or acts_expanded.empty:
        return None
    data = acts_expanded[acts_expanded["Campo"].astype(str) == str(field)].copy()
    if end_ts is not None:
        data = data[data["Fecha"] <= pd.Timestamp(end_ts)]
    if data.empty:
        return None
    return data.sort_values("Fecha").iloc[-1].to_dict()


def last_frac_use_for_field(acts_expanded, field, end_ts=None):
    last = last_field_treatment(acts_expanded, field, end_ts=end_ts)
    if not last:
        return [], "", np.nan
    product = normalize_product_name_for_recommendation(last.get("Producto normalizado") or last.get("Producto"))
    info = get_treatment_product_catalog().get(product, {})
    fracs = info.get("frac", [])
    fecha = pd.to_datetime(last.get("Fecha"), errors="coerce")
    return fracs, product, fecha


def dominant_disease_from_semaphore(sem_df):
    """Selecciona enfermedad dominante del semáforo, excluyendo estrés hídrico."""
    if sem_df is None or sem_df.empty:
        return "Moteado", "Bajo", 0.0
    data = sem_df[~sem_df["Riesgo"].astype(str).str.contains("Estrés", case=False, na=False)].copy()
    if data.empty:
        return "Moteado", "Bajo", 0.0
    data["Puntuación"] = pd.to_numeric(data["Puntuación"], errors="coerce").fillna(0)
    row = data.sort_values("Puntuación", ascending=False).iloc[0]
    return str(row["Riesgo"]), str(row["Nivel"]), float(row["Puntuación"])


def treatment_need_from_level(level, score):
    """Decide si conviene recomendar tratamiento, esperar o solo revisar."""
    level = str(level)
    try:
        score = float(score)
    except Exception:
        score = 0.0

    if level == "Alto" or score >= 75:
        return "Aplicar si la revisión de campo lo confirma"
    if level == "Medio" or score >= 45:
        return "Revisar y valorar tratamiento"
    if level == "Bajo-medio" or score >= 20:
        return "Observar / no tratar de entrada"
    return "No tratar / seguimiento normal"


def score_product_for_field(product, disease, counts, last_product, last_fracs, days_since_last, min_interval_days=15):
    """Puntúa un producto teniendo en cuenta eficacia, usos, alternancia y plazo entre tratamientos."""
    info = get_treatment_product_catalog()[product]
    score = float(info.get("eficacia", {}).get(disease, 50))
    warnings = []
    blocks = []

    used = int(counts.get(product, 0))
    if used >= 2:
        score -= 100
        blocks.append(f"ya usado {used} veces en la campaña")
    elif used == 1:
        score -= 12
        warnings.append("ya usado 1 vez en la campaña")

    if product == last_product and product:
        score -= 30
        warnings.append("evitar repetir el mismo producto consecutivamente")

    overlap = sorted(set(info.get("frac", [])) & set(last_fracs or []))
    if overlap:
        score -= 25
        warnings.append("comparte FRAC reciente: " + "+".join(overlap))

    if pd.notna(days_since_last) and days_since_last < min_interval_days:
        score -= 45
        blocks.append(f"solo han pasado {int(days_since_last)} días desde el último tratamiento")

    return score, warnings, blocks


def recommend_products_for_field(field, disease, disease_level, disease_score, climate_explanation, acts_expanded, campaign_start, campaign_end, min_interval_days=15):
    """Devuelve recomendación de producto para un campo concreto."""
    counts = field_product_use_counts(acts_expanded, field, campaign_start, campaign_end)
    last = last_field_treatment(acts_expanded, field, end_ts=campaign_end)
    last_product = ""
    last_date = pd.NaT
    last_original = "Sin tratamiento registrado"
    last_varieties = "Sin tratamiento registrado"
    if last:
        last_product = normalize_product_name_for_recommendation(last.get("Producto normalizado") or last.get("Producto"))
        last_date = pd.to_datetime(last.get("Fecha"), errors="coerce")
        last_original = f"{last_date.strftime('%d/%m/%Y') if pd.notna(last_date) else ''} · {last.get('Producto', '')}"
        last_varieties = str(last.get("Variedades tratadas", "") or "").strip() or "Agroptima no especifica variedad; revisar si fue campo completo o solo algunas variedades."

    last_fracs = get_treatment_product_catalog().get(last_product, {}).get("frac", [])
    today = pd.Timestamp.now().normalize()
    days_since_last = (today - pd.Timestamp(last_date).normalize()).days if pd.notna(last_date) else np.nan

    need = treatment_need_from_level(disease_level, disease_score)

    scored = []
    for product in get_treatment_product_catalog().keys():
        score, warnings, blocks = score_product_for_field(
            product,
            disease,
            counts,
            last_product,
            last_fracs,
            days_since_last,
            min_interval_days=min_interval_days,
        )
        scored.append({
            "product": product,
            "score": score,
            "warnings": warnings,
            "blocks": blocks,
        })

    scored = sorted(scored, key=lambda x: x["score"], reverse=True)
    allowed = [s for s in scored if not s["blocks"] and s["score"] > -20]

    if "No tratar" in need or "Observar" in need:
        product_choice = "No aplicar de entrada"
        alternative = allowed[0]["product"] if allowed else "Sin alternativa clara"
        reason = "El nivel climático general no justifica tratamiento directo en este campo. Revisar visualmente y actuar solo si la observación de campo lo confirma."
        frac_warning = "Sin presión de tratamiento. Mantener alternancia FRAC si finalmente se aplica."
    elif pd.notna(days_since_last) and days_since_last < min_interval_days:
        product_choice = "Esperar / revisar"
        alternative = allowed[0]["product"] if allowed else "Sin alternativa clara"
        reason = f"No se recomienda nuevo tratamiento automático: solo han pasado {int(days_since_last)} días desde el último tratamiento."
        frac_warning = "Respetar intervalo mínimo entre tratamientos y alternar modos de acción."
    elif allowed:
        product_choice = allowed[0]["product"]
        alternative = allowed[1]["product"] if len(allowed) > 1 else "Sin alternativa preferente"
        info = get_treatment_product_catalog()[product_choice]
        reason = (
            f"Mejor encaje para {disease.lower()} dentro de los productos disponibles, "
            f"teniendo en cuenta usos por campaña, último tratamiento y alternancia FRAC."
        )
        frac_warning = info.get("comentario", "")
        if allowed[0]["warnings"]:
            frac_warning += " Avisos: " + "; ".join(allowed[0]["warnings"]) + "."
    else:
        product_choice = "Sin producto recomendable"
        alternative = "Revisar manualmente"
        reason = "Todos los productos quedan penalizados por uso máximo, intervalo o repetición de FRAC."
        frac_warning = "Conviene revisar estrategia y alternativas de distinto modo de acción."

    used_txt = "; ".join([f"{p}: {counts.get(p, 0)}" for p in get_treatment_product_catalog().keys()])

    if "Aplicar" in need and not last:
        field_priority = "Alta: sin tratamiento previo registrado"
    elif "valorar" in need and not last:
        field_priority = "Media-alta: sin tratamiento previo registrado"
    elif pd.notna(days_since_last) and days_since_last < min_interval_days:
        field_priority = "Baja temporal: tratamiento reciente"
    elif "No tratar" in need or "Observar" in need:
        field_priority = "Baja: sin presión climática suficiente"
    else:
        field_priority = "Media"

    return {
        "Campo": field,
        "Riesgo dominante": disease,
        "Nivel riesgo": disease_level,
        "Puntuación riesgo": round(float(disease_score), 1),
        "Prioridad de campo": field_priority,
        "Decisión": need,
        "Producto recomendado": product_choice,
        "Alternativa": alternative,
        "Último tratamiento": last_original,
        "Variedades tratadas último tratamiento": last_varieties,
        "Días desde último tratamiento": "" if pd.isna(days_since_last) else int(days_since_last),
        "Usos campaña por producto": used_txt,
        "Motivo climático": str(climate_explanation),
        "Motivo": reason,
        "Advertencia FRAC": frac_warning,
    }


def build_field_treatment_recommendations(history_df, activities_df, period_df, soil_type, hoja_threshold, start_ts=None, end_ts=None, min_interval_days=15):
    """Genera tabla de recomendaciones técnicas por campo y producto."""
    if period_df is None or period_df.empty:
        return pd.DataFrame()

    if start_ts is None:
        start_ts = period_df["fecha_hora"].min()
    if end_ts is None:
        end_ts = period_df["fecha_hora"].max()

    sem = build_sanitary_semaphore_table(period_df, soil_type, hoja_threshold, start_ts=start_ts, end_ts=end_ts)
    disease, level, score = dominant_disease_from_semaphore(sem)
    if sem is not None and not sem.empty and "Riesgo" in sem.columns:
        match = sem[sem["Riesgo"].astype(str).str.lower() == str(disease).lower()]
        climate_explanation = match.iloc[0].get("Explicación climática", "") if not match.empty else ""
    else:
        climate_explanation = ""

    acts_expanded = expand_activities_by_field_for_recommendation(activities_df)

    fields_base = get_fields_base_df()
    if fields_base is not None and not fields_base.empty and "Campo" in fields_base.columns:
        fields = fields_base["Campo"].dropna().astype(str).sort_values().unique().tolist()
    elif not acts_expanded.empty:
        fields = acts_expanded["Campo"].dropna().astype(str).sort_values().unique().tolist()
    else:
        fields = []

    if not fields:
        return pd.DataFrame()

    campaign_year = int(pd.Timestamp(end_ts).year)
    campaign_start = pd.Timestamp(year=campaign_year, month=1, day=1)
    # Usar siempre hasta hoy como límite de búsqueda de tratamientos,
    # aunque los datos climáticos no lleguen tan lejos.
    campaign_end = max(pd.Timestamp(end_ts), pd.Timestamp.now().normalize())

    rows = []
    for field in fields:
        rows.append(recommend_products_for_field(
            field,
            disease,
            level,
            score,
            climate_explanation,
            acts_expanded,
            campaign_start,
            campaign_end,
            min_interval_days=int(min_interval_days),
        ))

    out = pd.DataFrame(rows)
    priority_order = {
        "Aplicar si la revisión de campo lo confirma": 0,
        "Revisar y valorar tratamiento": 1,
        "Observar / no tratar de entrada": 2,
        "No tratar / seguimiento normal": 3,
    }
    if not out.empty:
        out["_orden"] = out["Decisión"].map(priority_order).fillna(9)
        out["_sin_tratamiento"] = out["Último tratamiento"].astype(str).str.contains("Sin tratamiento", case=False, na=False).astype(int)
        out = out.sort_values(["_orden", "_sin_tratamiento", "Campo"], ascending=[True, False, True]).drop(columns=["_orden", "_sin_tratamiento"]).reset_index(drop=True)
    return out


def render_field_treatment_recommendations(period_df, soil_type, hoja_threshold, start_ts=None, end_ts=None):
    """Renderiza recomendación técnica por campo con productos disponibles."""
    st.markdown("#### Recomendación técnica de tratamiento por campo")

    st.warning(
        "Motor orientativo en fase inicial. No filtra autorización legal por cultivo. "
        "Antes de aplicar, verificar siempre etiqueta, registro oficial, dosis, plazo de seguridad, número máximo de aplicaciones, mezclas y normativa vigente."
    )

    activities_df = st.session_state.get("activities_df", pd.DataFrame(columns=ACTIVITY_COLUMNS))
    if activities_df is None or activities_df.empty:
        st.info("Carga actuaciones Agroptima para que la recomendación tenga en cuenta productos usados por campo.")
        return

    with st.expander("Productos configurados y grupos FRAC", expanded=False):
        product_rows = []
        for p, info in get_treatment_product_catalog().items():
            product_rows.append({
                "Producto": p,
                "Materias activas": info["materias_activas"],
                "FRAC": "+".join(info["frac"]),
                "Familia": info["familia"],
                "Comentario": info["comentario"],
            })
        st.dataframe(pd.DataFrame(product_rows), use_container_width=True, hide_index=True)

    min_interval = st.number_input(
        "Intervalo mínimo entre tratamientos por campo",
        min_value=7,
        max_value=45,
        value=15,
        step=1,
        help="Regla de trabajo configurada por ti. La app la usa para evitar recomendar tratamientos demasiado seguidos.",
        key="treatment_min_interval_v85",
    )

    recs = build_field_treatment_recommendations(
        st.session_state.get("history_df", pd.DataFrame(columns=CANONICAL_COLUMNS)),
        activities_df,
        period_df,
        soil_type,
        hoja_threshold,
        start_ts=start_ts,
        end_ts=end_ts,
        min_interval_days=int(min_interval),
    )

    if recs.empty:
        st.info("No se han podido generar recomendaciones por campo.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Campos evaluados", len(recs))
    c2.metric("Aplicar/valorar", int(recs["Decisión"].astype(str).str.contains("Aplicar|valorar", case=False, na=False).sum()))
    c3.metric("Sin tratamiento directo", int(recs["Decisión"].astype(str).str.contains("Observar|No tratar", case=False, na=False).sum()))

    st.dataframe(
        recs[[
            "Campo",
            "Riesgo dominante",
            "Nivel riesgo",
            "Prioridad de campo",
            "Decisión",
            "Producto recomendado",
            "Alternativa",
            "Último tratamiento",
            "Variedades tratadas último tratamiento",
            "Días desde último tratamiento",
            "Usos campaña por producto",
            "Motivo",
            "Advertencia FRAC",
        ]],
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Lectura rápida campo a campo", expanded=True):
        for _, row in recs.iterrows():
            st.markdown(f"**{row['Campo']} · {row['Riesgo dominante']} · {row['Nivel riesgo']}**")
            st.write(f"- Prioridad: {row.get('Prioridad de campo', '')}")
            st.write(f"- Decisión: {row['Decisión']}")
            st.write(f"- Producto recomendado: **{row['Producto recomendado']}**. Alternativa: {row['Alternativa']}")
            st.write(f"- Último tratamiento: {row['Último tratamiento']}")
            st.write(f"- Variedades tratadas: {row.get('Variedades tratadas último tratamiento', '')}")
            st.write(f"- Motivo de recomendación: {row['Motivo']}")
            st.write(f"- FRAC: {row['Advertencia FRAC']}")

    st.download_button(
        "Descargar recomendaciones de tratamiento por campo",
        data=recs.to_csv(index=False).encode("utf-8-sig"),
        file_name="recomendaciones_tratamiento_por_campo.csv",
        mime="text/csv",
    )



def health_tab(history, soil_type, hoja_threshold):
    st.subheader("Sanidad vegetal")

    if history.empty:
        st.info("Carga primero el histórico.")
        return

    period, period_df, avail, summary, global_summary = get_period_data(history, soil_type, hoja_threshold)
    if period is None:
        st.info("Selecciona primero un periodo en la pestaña **Análisis**.")
        return
    if period_df.empty:
        st.warning("No hay datos en el periodo seleccionado.")
        return

    explain_sanitary_concepts_box()

    period_start = period_df["fecha_hora"].min()
    period_end = period_df["fecha_hora"].max()
    active_phases = current_phenology_phase_for_period(pd.Timestamp(period_start), pd.Timestamp(period_end))

    render_sanitary_semaphore(
        period_df,
        soil_type,
        hoja_threshold,
        start_ts=period_start,
        end_ts=period_end,
    )

    render_field_treatment_recommendations(
        period_df,
        soil_type,
        hoja_threshold,
        start_ts=period_start,
        end_ts=period_end,
    )

    with st.expander("Plan de rotación FRAC para próxima campaña", expanded=False):
        st.info("El plan de rotación FRAC está disponible en la pestaña **Actuaciones**, para evitar duplicar controles internos de Streamlit.")

    st.markdown("#### Eventos de humectación foliar")
    if has_sensor(period_df, "Humectación de hoja"):
        events_df = detect_leaf_wetness_events(period_df)
        if events_df.empty:
            st.info("No se han detectado eventos de hoja mojada en el periodo seleccionado.")
        else:
            events_explained = add_event_interpretation_columns(events_df, phases=active_phases)
            st.dataframe(events_explained, use_container_width=True)
            st.download_button(
                "Descargar eventos de humectación foliar explicados",
                data=events_explained.to_csv(index=False).encode("utf-8-sig"),
                file_name="eventos_humectacion_foliar_explicados.csv",
                mime="text/csv",
            )

            with st.expander("Resumen de actuación sugerida por evento", expanded=True):
                for i, row in events_explained.iterrows():
                    inicio = row.get("Inicio", "")
                    fin = row.get("Fin", "")
                    st.markdown(f"**Evento {i + 1}:** {inicio} → {fin}")
                    if "Ratio moteado" in row:
                        st.write(
                            f"- **Moteado:** ratio {row.get('Ratio moteado', 's/d')} · "
                            f"{row.get('Interpretación ratio moteado', '')}"
                        )
                        st.write(f"  - Acción: {row.get('Acción sugerida moteado', '')}")
                    if "Ratio monilia" in row:
                        st.write(
                            f"- **Monilia:** ratio {row.get('Ratio monilia', 's/d')} · "
                            f"{row.get('Interpretación ratio monilia', '')}"
                        )
                        st.write(f"  - Acción: {row.get('Acción sugerida monilia', '')}")
    else:
        st.warning("Para este periodo no disponemos de datos de humectación de hoja.")

    st.markdown("#### Riesgos resumidos del periodo")
    st.dataframe(global_summary[[
        c for c in global_summary.columns
        if c in [
            "Horas favorables moteado", "Eventos moteado medio/alto", "Eventos moteado alto",
            "Horas favorables oídio", "Horas favorables monilia",
            "Eventos monilia medio/alto", "Eventos monilia alto",
            "Horas húmedas equivalentes", "Eventos hoja mojada"
        ]
    ]], use_container_width=True)

    st.divider()
    render_health_recommendation(
        period_df,
        soil_type,
        hoja_threshold,
        start_ts=period_df["fecha_hora"].min(),
        end_ts=period_df["fecha_hora"].max(),
    )


def irrigation_tab(history, soil_type, hoja_threshold):
    st.subheader("Riego y demanda evaporativa")

    with st.expander("Cómo interpretar la recomendación de riego", expanded=False):
        st.markdown(
            """
            **Índice evaporativo**  
            Es una escala orientativa que resume la demanda de agua del ambiente. Tiene en cuenta temperatura, humedad, radiación y, cuando está disponible, viento.

            **Tipo de suelo**  
            Un suelo arenoso o franco-arenoso suele perder agua antes y tiene menor reserva útil. Un suelo arcilloso o franco-arcilloso retiene más agua, pero también puede tener problemas si se riega en exceso.

            **Recomendación de riego**  
            La app cruza lluvia, demanda evaporativa, tipo de suelo y fase fenológica. La recomendación es una ayuda para decidir si conviene observar, comprobar humedad real o valorar riego.
            """
        )
        st.caption(
            "Base técnica: programación de riego por balance hídrico, evapotranspiración, lluvia, suelo y estado del cultivo. "
            "Siempre conviene contrastar con humedad real del suelo."
        )

    if history.empty:
        st.info("Carga primero el histórico.")
        return

    period, period_df, avail, summary, global_summary = get_period_data(history, soil_type, hoja_threshold)
    if period is None:
        st.info("Selecciona primero un periodo en la pestaña **Análisis**.")
        return
    if period_df.empty:
        st.warning("No hay datos en el periodo seleccionado.")
        return

    cols = [
        "Lluvia total mm", "Lluvia efectiva estimada mm",
        "Radiación acumulada estimada MJ/m²", "Radiación acumulada estimada kWh/m²",
        "Índice evaporativo medio", "Índice evaporativo ajustado suelo",
        "Horas demanda evaporativa alta", "Orientación riego"
    ]
    st.dataframe(global_summary[[c for c in cols if c in global_summary.columns]], use_container_width=True)

    st.divider()
    render_irrigation_recommendation(
        period_df,
        soil_type,
        hoja_threshold,
        start_ts=period_df["fecha_hora"].min(),
        end_ts=period_df["fecha_hora"].max(),
    )

    st.info("Este módulo sigue siendo orientativo. El siguiente salto sería integrar humedad real del suelo por parcela.")




# ── Fenología v2: por Campo × Variedad ────────────────────────────────────────

PHENOLOGY_PHASES = [
    "Reposo invernal",
    "Yema hinchada",
    "Brotación",
    "Floración",
    "Cuajado",
    "Crecimiento del fruto",
    "Maduración",
    "Cosecha",
    "Caída de hoja",
]
PHENOLOGY_PHASE_ORDER = {p: i + 1 for i, p in enumerate(PHENOLOGY_PHASES)}


def get_campo_variedad_pairs():
    """Devuelve todas las combinaciones (Campo, Variedad) de la base de campos."""
    pairs = []
    for row in FIELDS_BASE_ROWS:
        campo = row["Campo"]
        for v in str(row.get("Variedades actuales", "")).split(","):
            v = v.strip()
            if v:
                pairs.append((campo, v))
    return pairs


def normalize_phenology_df(df):
    required = ["Campo", "Variedad", "Año", "Fase", "Inicio", "Fin", "Observaciones"]
    out = df.copy()
    for col in required:
        if col not in out.columns:
            out[col] = ""
    out = out[required].copy()
    out["Campo"]         = out["Campo"].fillna("").astype(str)
    out["Variedad"]      = out["Variedad"].fillna("").astype(str)
    out["Año"]           = pd.to_numeric(out["Año"], errors="coerce").astype("Int64")
    out["Fase"]          = out["Fase"].astype(str)
    out["Inicio"]        = pd.to_datetime(out["Inicio"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["Fin"]           = pd.to_datetime(out["Fin"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["Observaciones"] = out["Observaciones"].fillna("").astype(str)
    return out


def phenology_phase_summary(history, phenology_df, soil_type, hoja_threshold,
                             campo=None, variedad=None, selected_year=None):
    rows = []
    if history.empty or phenology_df.empty:
        return pd.DataFrame()

    pheno = normalize_phenology_df(phenology_df).dropna(subset=["Año", "Inicio", "Fin"])
    if campo is not None:
        pheno = pheno[pheno["Campo"].str.strip() == str(campo).strip()]
    if variedad is not None:
        pheno = pheno[pheno["Variedad"].str.strip() == str(variedad).strip()]
    if selected_year is not None:
        pheno = pheno[pheno["Año"].astype(int) == int(selected_year)]

    for _, phase in pheno.iterrows():
        start_ts = pd.Timestamp(phase["Inicio"])
        end_ts   = pd.Timestamp(phase["Fin"]) + pd.Timedelta(hours=23)

        period = history[(history["fecha_hora"] >= start_ts) & (history["fecha_hora"] <= end_ts)].copy()

        if period.empty:
            rows.append({
                "Campo": phase.get("Campo", ""),
                "Variedad": phase.get("Variedad", ""),
                "Año": int(phase["Año"]) if pd.notna(phase["Año"]) else np.nan,
                "Fase": phase["Fase"],
                "Inicio": phase["Inicio"],
                "Fin": phase["Fin"],
                "Aviso": "Sin datos climáticos en el periodo",
            })
            continue

        period = add_risk_columns(period, hoja_humeda_threshold=hoja_threshold)
        summary = period_summary(period, soil_type, start_ts, end_ts)

        row = summary.iloc[0].to_dict() if not summary.empty else {}
        row["Campo"]    = phase.get("Campo", "")
        row["Variedad"] = phase.get("Variedad", "")
        row["Año"]      = int(phase["Año"]) if pd.notna(phase["Año"]) else np.nan
        row["Fase"]     = phase["Fase"]
        row["Inicio"]   = phase["Inicio"]
        row["Fin"]      = phase["Fin"]
        row["Observaciones fenología"] = phase.get("Observaciones", "")
        row["Aviso"]    = ""
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    leading = ["Campo", "Variedad", "Año", "Fase", "Inicio", "Fin",
               "Observaciones fenología", "Aviso"]
    remaining = [c for c in df.columns if c not in leading]
    return df[leading + remaining]


def render_phenology_interpretation(phase_df):
    if phase_df.empty:
        st.info("No hay fases fenológicas para interpretar.")
        return

    st.subheader("Lectura interpretada por fase fenológica")

    for _, row in phase_df.iterrows():
        fase     = row.get("Fase", "Fase")
        year     = row.get("Año", "")
        inicio   = row.get("Inicio", "")
        fin      = row.get("Fin", "")
        campo    = str(row.get("Campo", "")).strip()
        variedad = str(row.get("Variedad", "")).strip()

        title_parts = [str(fase), str(year)]
        if campo:
            title_parts.append(campo)
        if variedad:
            title_parts.append(variedad)

        with st.container(border=True):
            st.markdown(f"#### {' · '.join(title_parts)}")
            st.caption(f"{inicio} → {fin}")

            if row.get("Aviso", ""):
                st.warning(row["Aviso"])
                continue

            lines = []

            if pd.notna(row.get("Temp. media ºC", np.nan)):
                lines.append(
                    f"Temperatura media de **{row['Temp. media ºC']} ºC**, "
                    f"con máxima de **{row.get('Temp. máx ºC', 's/d')} ºC** "
                    f"y mínima de **{row.get('Temp. mín ºC', 's/d')} ºC**."
                )

            if pd.notna(row.get("Lluvia total mm", np.nan)):
                lines.append(
                    f"Lluvia acumulada de **{row['Lluvia total mm']} mm**, "
                    f"con **{row.get('Horas con lluvia', 0)} h** con lluvia."
                )

            if pd.notna(row.get("Horas hoja húmeda", np.nan)):
                lines.append(
                    f"Hoja húmeda simple: **{row['Horas hoja húmeda']} h**. "
                    f"Eventos de hoja mojada: **{row.get('Eventos hoja mojada', 0)}**, "
                    f"con **{row.get('Horas húmedas equivalentes', 0)} h equivalentes**."
                )

            if pd.notna(row.get("Índice evaporativo ajustado suelo", np.nan)):
                lines.append(
                    f"Índice evaporativo ajustado al suelo: **{row['Índice evaporativo ajustado suelo']}/100**. "
                    f"{row.get('Orientación riego', '')}"
                )

            if str(fase).lower().find("flor") >= 0:
                lines.append(
                    f"En fase de floración, la app estima **{row.get('Horas favorables polinización', 0)} h** "
                    f"favorables para polinización, equivalentes al **{row.get('% horas favorables polinización', 0)} %** "
                    f"de la ventana analizada."
                )

            if any(word in str(fase).lower() for word in ["brot", "flor", "cuaj", "fruto", "madur", "cosecha"]):
                lines.append(
                    f"Riesgo sanitario orientativo: moteado **{row.get('Eventos moteado medio/alto', 0)} eventos medio/alto**, "
                    f"monilia **{row.get('Eventos monilia medio/alto', 0)} eventos medio/alto**, "
                    f"oídio **{row.get('Horas favorables oídio', 0)} h favorables**."
                )

            if lines:
                st.write(" ".join(lines))

            obs = row.get("Observaciones fenología", "")
            if isinstance(obs, str) and obs.strip():
                st.info(f"Observación de campo: {obs}")


def default_phenology_rows_for_campo_variedad_year(campo, variedad, year):
    y = int(year)
    return [
        {"Campo": campo, "Variedad": variedad, "Año": y, "Fase": "Reposo invernal",
         "Inicio": f"{y}-01-01", "Fin": f"{y}-03-15", "Observaciones": ""},
        {"Campo": campo, "Variedad": variedad, "Año": y, "Fase": "Yema hinchada",
         "Inicio": f"{y}-03-16", "Fin": f"{y}-03-31", "Observaciones": ""},
        {"Campo": campo, "Variedad": variedad, "Año": y, "Fase": "Brotación",
         "Inicio": f"{y}-04-01", "Fin": f"{y}-04-14", "Observaciones": ""},
        {"Campo": campo, "Variedad": variedad, "Año": y, "Fase": "Floración",
         "Inicio": f"{y}-04-15", "Fin": f"{y}-05-10", "Observaciones": ""},
        {"Campo": campo, "Variedad": variedad, "Año": y, "Fase": "Cuajado",
         "Inicio": f"{y}-05-11", "Fin": f"{y}-06-15", "Observaciones": ""},
        {"Campo": campo, "Variedad": variedad, "Año": y, "Fase": "Crecimiento del fruto",
         "Inicio": f"{y}-06-16", "Fin": f"{y}-08-31", "Observaciones": ""},
        {"Campo": campo, "Variedad": variedad, "Año": y, "Fase": "Maduración",
         "Inicio": f"{y}-09-01", "Fin": f"{y}-10-15", "Observaciones": ""},
        {"Campo": campo, "Variedad": variedad, "Año": y, "Fase": "Cosecha",
         "Inicio": f"{y}-10-16", "Fin": f"{y}-11-15", "Observaciones": ""},
        {"Campo": campo, "Variedad": variedad, "Año": y, "Fase": "Caída de hoja",
         "Inicio": f"{y}-11-16", "Fin": f"{y}-12-15", "Observaciones": ""},
    ]


def merge_phenology_template(existing_df, years):
    """
    Añade filas para todas las combinaciones Campo×Variedad de la base de campos.
    Clave de deduplicación: (Campo, Variedad, Año, Fase).
    No borra ni modifica lo ya editado.
    """
    existing = (normalize_phenology_df(existing_df)
                if existing_df is not None and not existing_df.empty
                else pd.DataFrame(
                    columns=["Campo", "Variedad", "Año", "Fase", "Inicio", "Fin", "Observaciones"]
                ))

    existing_keys = set()
    for _, row in existing.iterrows():
        if pd.notna(row.get("Año")):
            existing_keys.add((
                str(row.get("Campo", "")).strip().lower(),
                str(row.get("Variedad", "")).strip().lower(),
                int(row["Año"]),
                str(row["Fase"]).strip().lower(),
            ))

    pairs = get_campo_variedad_pairs()
    new_rows = []
    for y in years:
        for campo, variedad in pairs:
            for row in default_phenology_rows_for_campo_variedad_year(campo, variedad, int(y)):
                key = (
                    row["Campo"].strip().lower(),
                    row["Variedad"].strip().lower(),
                    int(row["Año"]),
                    row["Fase"].strip().lower(),
                )
                if key not in existing_keys:
                    new_rows.append(row)

    merged = (pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)
              if new_rows else existing.copy())

    merged = normalize_phenology_df(merged)
    merged["_fase_orden"] = merged["Fase"].map(PHENOLOGY_PHASE_ORDER).fillna(99)
    merged = (merged
              .sort_values(["Campo", "Variedad", "Año", "_fase_orden"])
              .drop(columns=["_fase_orden"])
              .reset_index(drop=True))
    return merged, len(new_rows)


def phenology_compare_variety_across_fields(phenology_df, variedad, year):
    """
    Para una variedad+año, devuelve un DataFrame Fase × Campo
    con el rango de fechas registrado en cada campo.
    """
    pheno = normalize_phenology_df(phenology_df).dropna(subset=["Año", "Inicio", "Fin"])
    pheno = pheno[
        (pheno["Variedad"].str.strip() == str(variedad).strip()) &
        (pheno["Año"].astype(int) == int(year))
    ].copy()

    if pheno.empty:
        return pd.DataFrame()

    campos = sorted(pheno["Campo"].str.strip().unique())
    rows_out = []
    for fase in PHENOLOGY_PHASES:
        row = {"Fase": fase}
        for campo in campos:
            mask = (pheno["Campo"].str.strip() == campo) & (pheno["Fase"].str.strip() == fase)
            m = pheno[mask]
            if not m.empty:
                ini = pd.to_datetime(m.iloc[0]["Inicio"], errors="coerce")
                fin = pd.to_datetime(m.iloc[0]["Fin"],   errors="coerce")
                row[campo] = (f"{ini.strftime('%d/%m')} → {fin.strftime('%d/%m')}"
                              if pd.notna(ini) and pd.notna(fin) else "Sin fecha")
            else:
                row[campo] = "—"
        rows_out.append(row)

    return pd.DataFrame(rows_out)


def phenology_phase_across_years(phenology_df, campo, variedad, fase,
                                  history, soil_type, hoja_threshold):
    """Para Campo+Variedad+Fase, muestra fechas y clima de cada año."""
    pheno = normalize_phenology_df(phenology_df).dropna(subset=["Año", "Inicio", "Fin"])
    pheno = pheno[
        (pheno["Campo"].str.strip()    == str(campo).strip()) &
        (pheno["Variedad"].str.strip() == str(variedad).strip()) &
        (pheno["Fase"].str.strip()     == str(fase).strip())
    ].copy()

    if pheno.empty:
        return pd.DataFrame()

    rows = []
    for _, phase in pheno.iterrows():
        y        = int(phase["Año"])
        start_ts = pd.Timestamp(phase["Inicio"])
        end_ts   = pd.Timestamp(phase["Fin"]) + pd.Timedelta(hours=23)
        duration = (pd.Timestamp(phase["Fin"]) - start_ts).days + 1

        base = {"Año": y, "Inicio": phase["Inicio"],
                "Fin": phase["Fin"], "Duración días": duration}

        period = history[(history["fecha_hora"] >= start_ts) & (history["fecha_hora"] <= end_ts)].copy()
        if period.empty:
            base["Aviso"] = "Sin datos"
            rows.append(base)
            continue

        period  = add_risk_columns(period, hoja_humeda_threshold=hoja_threshold)
        summary = period_summary(period, soil_type, start_ts, end_ts)
        if not summary.empty:
            for col in summary.columns:
                base[col] = summary.iloc[0][col]
        rows.append(base)

    if not rows:
        return pd.DataFrame()

    df_out = pd.DataFrame(rows).sort_values("Año").reset_index(drop=True)
    leading = ["Año", "Inicio", "Fin", "Duración días"]
    remaining = [c for c in df_out.columns if c not in leading]
    return df_out[leading + remaining]


def phenology_tab(history, soil_type, hoja_threshold):
    st.subheader("Fenología por campo y variedad")
    st.write(
        "Registra las fechas reales de cada fase fenológica para cada combinación "
        "**campo × variedad** de la finca. Permite analizar el clima específico de cada "
        "unidad y comparar cómo evoluciona la misma variedad en distintos campos o en distintos años."
    )

    # ── Sección 1: Carga CSV ───────────────────────────────────────────────────
    uploaded_pheno = st.file_uploader(
        "Cargar calendario fenológico CSV",
        type=["csv"],
        accept_multiple_files=False,
        key="phenology_csv_upload",
    )

    if uploaded_pheno is not None:
        import hashlib, io as _io
        raw_bytes = uploaded_pheno.getvalue()
        file_hash = hashlib.md5(raw_bytes).hexdigest()
        if st.session_state.get("phenology_last_uploaded_hash") != file_hash:
            try:
                pheno_loaded = pd.read_csv(_io.BytesIO(raw_bytes), encoding="utf-8-sig")
                st.session_state.phenology_df = normalize_phenology_df(pheno_loaded)
                st.session_state.phenology_editor_version += 1
                st.session_state["phenology_last_uploaded_hash"] = file_hash
                st.success("Calendario fenológico cargado correctamente.")
                autosave_phenology_to_supabase()   # guardado automático en la nube
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo cargar el calendario fenológico: {e}")

    # ── Sección 2: Generador de plantilla ─────────────────────────────────────
    with st.expander("Generar plantilla para todos los campos y variedades", expanded=True):
        if history.empty:
            st.warning(
                "Primero carga el histórico climático. "
                "Cuando esté cargado, aquí aparecerán los años detectados."
            )
        else:
            detected_years = sorted([int(y) for y in history["fecha_hora"].dt.year.dropna().unique()])
            pairs = get_campo_variedad_pairs()
            n_total = len(pairs) * len(detected_years) * len(PHENOLOGY_PHASES)
            st.info(
                f"**{len(pairs)} combinaciones Campo×Variedad** en la base de campos · "
                f"**{len(detected_years)} años** en el histórico. "
                f"La plantilla completa tendría **{n_total} filas** "
                f"({len(pairs)} combos × {len(detected_years)} años × {len(PHENOLOGY_PHASES)} fases). "
                f"Solo se añaden las que faltan; **no se borra nada ya editado**."
            )
            st.write("Años detectados: " + ", ".join(map(str, detected_years)))

            if st.button(
                "Generar / completar plantilla sin borrar datos existentes",
                type="primary",
                key="generate_pheno_template_v2",
            ):
                merged, added = merge_phenology_template(st.session_state.phenology_df, detected_years)
                st.session_state.phenology_df = merged
                st.session_state.phenology_editor_version += 1
                st.session_state["last_phase_summary"] = pd.DataFrame()
                if added > 0:
                    st.success(f"Plantilla actualizada — {added} filas nuevas añadidas sin modificar las existentes.")
                else:
                    st.info("No había filas nuevas que añadir. La tabla ya estaba completa.")
                autosave_phenology_to_supabase()   # guardado automático en la nube
                st.rerun()

    # ── Sección 3: Editor con filtros ─────────────────────────────────────────
    st.markdown("#### Editar calendario fenológico")
    st.caption(
        "Filtra por campo, variedad y año para ver solo las filas que necesitas editar. "
        "Formato de fecha: **YYYY-MM-DD**."
    )

    # Normalizar siempre al leer: garantiza que "Campo" y "Variedad" existan
    # aunque el session_state venga de una sesión anterior al rediseño.
    pheno_cur = normalize_phenology_df(st.session_state.phenology_df)
    if not pheno_cur.equals(normalize_phenology_df(st.session_state.phenology_df)):
        st.session_state.phenology_df = pheno_cur

    _ph_campos   = sorted([c for c in pheno_cur["Campo"].dropna().unique()    if str(c).strip()])
    _ph_vars     = sorted([v for v in pheno_cur["Variedad"].dropna().unique() if str(v).strip()])
    _ph_years    = sorted([int(y) for y in pheno_cur["Año"].dropna().unique()])

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        filt_campo = st.selectbox("Campo",    ["Todos"] + _ph_campos, key="pheno_filt_campo")
    with fc2:
        filt_var   = st.selectbox("Variedad", ["Todas"] + _ph_vars,   key="pheno_filt_variedad")
    with fc3:
        filt_yr    = st.selectbox("Año",      ["Todos"] + _ph_years,  key="pheno_filt_year")

    # Build filter mask preserving original index for merge-back
    _mask = pd.Series([True] * len(pheno_cur), index=pheno_cur.index)
    if filt_campo != "Todos":
        _mask &= (pheno_cur["Campo"] == filt_campo)
    if filt_var != "Todas":
        _mask &= (pheno_cur["Variedad"] == filt_var)
    if filt_yr != "Todos":
        _mask &= (pheno_cur["Año"].astype(str) == str(filt_yr))

    _edit_slice = pheno_cur[_mask].reset_index(drop=True)
    _untouched  = pheno_cur[~_mask]

    # Changing the filter resets the editor (new key → fresh render)
    _fsig      = f"{filt_campo}_{filt_var}_{filt_yr}".replace(" ", "_")
    editor_key = f"pheno_ed_{st.session_state.phenology_editor_version}_{_fsig}"

    # Editar tablas muy grandes (miles de filas) puede agotar la memoria de
    # Streamlit Cloud y reiniciar la app (perdiendo la sesión). Para editar con
    # fluidez exigimos filtrar a un bloque pequeño.
    _MAX_EDITABLE_ROWS = 200

    if _edit_slice.empty and (_mask.sum() == 0):
        st.info("No hay filas para este filtro. Genera la plantilla primero o ajusta los filtros.")
    elif len(_edit_slice) > _MAX_EDITABLE_ROWS:
        st.warning(
            f"⚠️ La selección actual tiene **{len(_edit_slice)} filas**, demasiadas para editar "
            f"con fluidez (editar tablas tan grandes puede ralentizar o reiniciar la app). "
            f"Usa los filtros de arriba — **Campo + Variedad + Año** — para editar un bloque "
            f"pequeño. Cuando termines un bloque, pulsa **💾 Guardar fenología en Supabase**."
        )
        st.caption("Vista de solo lectura (filtra para poder editar):")
        st.dataframe(_edit_slice, use_container_width=True, hide_index=True)
    else:
        edited = st.data_editor(
            _edit_slice,
            num_rows="dynamic",
            use_container_width=True,
            key=editor_key,
        )
        # Merge edited slice back into full df
        try:
            _en = normalize_phenology_df(edited)
            _un = (normalize_phenology_df(_untouched)
                   if not _untouched.empty
                   else pd.DataFrame(columns=["Campo", "Variedad", "Año", "Fase", "Inicio", "Fin", "Observaciones"]))
            _full_new = normalize_phenology_df(pd.concat([_un, _en], ignore_index=True))
            if not _full_new.equals(normalize_phenology_df(pheno_cur)):
                st.session_state.phenology_df = _full_new
        except Exception:
            pass  # Silent fail — never lose data

    _pc1, _pc2 = st.columns(2)
    with _pc1:
        st.download_button(
            "Descargar calendario fenológico completo",
            data=st.session_state.phenology_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="calendario_fenologico_finca_gallinal.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with _pc2:
        # Guardado manual en Supabase para conservar las ediciones de la tabla.
        # (Las importaciones de CSV/plantilla se guardan solas automáticamente.)
        if st.button("☁️ Guardar fenología en Supabase", use_container_width=True,
                     type="primary", key="save_phenology_supabase"):
            ok, msg = upload_phenology_to_supabase(st.session_state.phenology_df)
            if ok:
                st.success(f"✅ {msg}")
            else:
                st.error(f"❌ {msg}")

    if history.empty:
        st.info("Carga primero el histórico climático para poder analizar por fases.")
        return

    pheno_now = normalize_phenology_df(st.session_state.phenology_df)
    if pheno_now.empty or pheno_now["Inicio"].isna().all():
        st.info("Genera la plantilla o carga un CSV con fechas fenológicas para comenzar el análisis.")
        return

    # ── Sección 4: Análisis ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Análisis fenológico")

    an_campos = sorted([c for c in pheno_now["Campo"].dropna().unique()    if str(c).strip()])
    an_vars   = sorted([v for v in pheno_now["Variedad"].dropna().unique() if str(v).strip()])
    an_years  = sorted([int(y) for y in pheno_now["Año"].dropna().unique()])

    tab_unit, tab_vcf, tab_evo = st.tabs([
        "📍 Por unidad (campo + variedad + año)",
        "🔄 Variedad entre campos",
        "📅 Evolución temporal",
    ])

    # ── Tab 1: Por unidad ─────────────────────────────────────────────────────
    with tab_unit:
        st.markdown(
            "Selecciona un campo, una variedad y un año para ver el análisis climático "
            "de cada fase fenológica de esa combinación concreta."
        )
        col_u1, col_u2, col_u3 = st.columns(3)
        with col_u1:
            sel_campo_u = st.selectbox(
                "Campo", an_campos if an_campos else ["—"], key="pheno_an_campo_unit"
            )
        with col_u2:
            _vars_u = sorted(pheno_now[pheno_now["Campo"] == sel_campo_u]["Variedad"].dropna().unique().tolist())
            sel_var_u = st.selectbox(
                "Variedad", _vars_u if _vars_u else ["—"], key="pheno_an_var_unit"
            )
        with col_u3:
            sel_year_u = st.selectbox(
                "Año", an_years if an_years else [2026],
                index=len(an_years) - 1 if an_years else 0,
                key="pheno_an_year_unit",
            )

        if st.button("Analizar fases", type="primary", key="btn_pheno_unit"):
            if sel_campo_u in ("—", "") or sel_var_u in ("—", ""):
                st.warning("Selecciona un campo y una variedad válidos.")
            else:
                _ps = phenology_phase_summary(
                    history, pheno_now, soil_type, hoja_threshold,
                    campo=sel_campo_u, variedad=sel_var_u, selected_year=sel_year_u,
                )
                st.session_state["last_phase_summary"] = _ps

        phase_df = st.session_state.get("last_phase_summary", pd.DataFrame())
        if not phase_df.empty:
            st.markdown(f"#### Resumen climático · {sel_campo_u} · {sel_var_u} · {sel_year_u}")
            st.dataframe(phase_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar resumen por fases",
                data=phase_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"fenologia_{sel_campo_u}_{sel_var_u}_{sel_year_u}.csv".replace(" ", "_"),
                mime="text/csv",
                key="dl_pheno_unit",
            )
            render_phenology_interpretation(phase_df)

    # ── Tab 2: Variedad entre campos ──────────────────────────────────────────
    with tab_vcf:
        st.markdown(
            "Compara en qué fecha ocurre cada fase para la **misma variedad** "
            "en distintos campos. Útil para detectar diferencias de microclima o exposición."
        )
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            sel_var_vcf = st.selectbox(
                "Variedad", an_vars if an_vars else ["—"], key="pheno_an_var_vcf"
            )
        with col_v2:
            sel_year_vcf = st.selectbox(
                "Año", an_years if an_years else [2026],
                index=len(an_years) - 1 if an_years else 0,
                key="pheno_an_year_vcf",
            )

        if st.button("Comparar campos", type="primary", key="btn_pheno_vcf"):
            if sel_var_vcf in ("—", ""):
                st.warning("Selecciona una variedad válida.")
            else:
                _vcf = phenology_compare_variety_across_fields(pheno_now, sel_var_vcf, sel_year_vcf)
                st.session_state["last_vcf_df"] = _vcf

        vcf_df = st.session_state.get("last_vcf_df", pd.DataFrame())
        if not vcf_df.empty:
            st.markdown(f"#### {sel_var_vcf} · {sel_year_vcf} · Fechas por campo")
            st.caption(
                "Cada columna es un campo. Las celdas muestran inicio → fin de la fase. "
                "Los '—' indican que ese campo no tiene fechas registradas para esa fase."
            )
            # Sticky HTML table
            _vc = list(vcf_df.columns)
            _vth  = "background:#1a2e1e;color:white;padding:8px 12px;white-space:nowrap;font-weight:600;font-size:13px;"
            _vths = "position:sticky;left:0;z-index:2;" + _vth
            _vhdr = "".join(
                f'<th style="{_vths if i == 0 else _vth}">{c}</th>'
                for i, c in enumerate(_vc)
            )
            _vbody = ""
            for _, _r in vcf_df.iterrows():
                _cells = ""
                for _i, _c in enumerate(_vc):
                    _v    = str(_r[_c])
                    _bg   = "#eef2ee" if _i == 0 else ("white" if _v != "—" else "#f9f9f9")
                    _clr  = "#888" if _v == "—" else "inherit"
                    _td   = (f"{'position:sticky;left:0;z-index:1;' if _i == 0 else ''}"
                             f"background:{_bg};color:{_clr};padding:7px 12px;"
                             f"border-bottom:1px solid #e8e8e8;white-space:nowrap;font-size:13px;")
                    _cells += f"<td style='{_td}'>{_v}</td>"
                _vbody += f"<tr>{_cells}</tr>"
            st.markdown(
                f'<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;'
                f'border-radius:8px;border:1px solid #ddd;margin-bottom:1rem;">'
                f'<table style="border-collapse:collapse;width:100%;">'
                f'<thead><tr>{_vhdr}</tr></thead>'
                f'<tbody>{_vbody}</tbody>'
                f'</table></div>',
                unsafe_allow_html=True,
            )
            st.download_button(
                "Descargar comparación entre campos",
                data=vcf_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"comparacion_campos_{sel_var_vcf}_{sel_year_vcf}.csv".replace(" ", "_"),
                mime="text/csv",
                key="dl_vcf",
            )

    # ── Tab 3: Evolución temporal ─────────────────────────────────────────────
    with tab_evo:
        st.markdown(
            "Selecciona un campo, variedad y fase para ver cómo ha cambiado esa fase "
            "a lo largo de los años registrados, junto con el clima de cada período."
        )
        col_e1, col_e2, col_e3 = st.columns(3)
        with col_e1:
            sel_campo_evo = st.selectbox(
                "Campo", an_campos if an_campos else ["—"], key="pheno_an_campo_evo"
            )
        with col_e2:
            _vars_evo = sorted(
                pheno_now[pheno_now["Campo"] == sel_campo_evo]["Variedad"].dropna().unique().tolist()
            ) if sel_campo_evo not in ("—", "") else an_vars
            sel_var_evo = st.selectbox(
                "Variedad", _vars_evo if _vars_evo else ["—"], key="pheno_an_var_evo"
            )
        with col_e3:
            _fi = PHENOLOGY_PHASES.index("Floración") if "Floración" in PHENOLOGY_PHASES else 0
            sel_fase_evo = st.selectbox(
                "Fase", PHENOLOGY_PHASES, index=_fi, key="pheno_an_fase_evo"
            )

        if st.button("Ver evolución temporal", type="primary", key="btn_pheno_evo"):
            if sel_campo_evo in ("—", "") or sel_var_evo in ("—", ""):
                st.warning("Selecciona un campo y una variedad válidos.")
            else:
                _evo = phenology_phase_across_years(
                    pheno_now, sel_campo_evo, sel_var_evo, sel_fase_evo,
                    history, soil_type, hoja_threshold,
                )
                st.session_state["last_evo_df"] = _evo

        evo_df = st.session_state.get("last_evo_df", pd.DataFrame())
        if not evo_df.empty:
            st.markdown(f"#### {sel_fase_evo} · {sel_campo_evo} · {sel_var_evo} — por año")
            st.dataframe(evo_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar evolución temporal",
                data=evo_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"evolucion_{sel_campo_evo}_{sel_var_evo}_{sel_fase_evo}.csv".replace(" ", "_"),
                mime="text/csv",
                key="dl_evo",
            )



def safe_num(series, func="sum"):
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if vals.empty:
        return np.nan
    if func == "sum":
        return float(vals.sum())
    if func == "mean":
        return float(vals.mean())
    if func == "min":
        return float(vals.min())
    if func == "max":
        return float(vals.max())
    return np.nan


def first_available_numeric(df, candidates):
    """Devuelve la primera columna numérica disponible entre varios candidatos."""
    for col in candidates:
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors="coerce")
            if vals.notna().any():
                return vals, col
    return pd.Series(dtype=float), None



def build_weekly_priority_table_all_fields(hist, activities_df, period_df, start_ts, end_ts):
    """
    Construye prioridades semanales partiendo de todos los campos de la finca.

    No usa solo los campos con actuaciones; si un campo no tiene tratamiento registrado,
    también aparece y puede priorizarse más si el periodo climático ha sido desfavorable.
    """
    fields_df = get_fields_base_df()
    if fields_df is None or fields_df.empty or "Campo" not in fields_df.columns:
        return pd.DataFrame()

    # Riesgo climático general del periodo para aplicarlo a todos los campos.
    events = detect_leaf_wetness_events(period_df) if has_sensor(period_df, "Humectación de hoja") else pd.DataFrame()
    max_scab = pd.to_numeric(events.get("Ratio moteado", 0), errors="coerce").fillna(0).max() if not events.empty else 0.0
    max_monilia = pd.to_numeric(events.get("Ratio monilia", 0), errors="coerce").fillna(0).max() if not events.empty else 0.0
    scab_ge1 = int((pd.to_numeric(events.get("Ratio moteado", 0), errors="coerce").fillna(0) >= 1.0).sum()) if not events.empty else 0
    monilia_ge1 = int((pd.to_numeric(events.get("Ratio monilia", 0), errors="coerce").fillna(0) >= 1.0).sum()) if not events.empty else 0
    rain_total = float(pd.to_numeric(period_df.get("lluvia_mm", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    wet_hours = float((pd.to_numeric(period_df.get("humectacion_hoja", pd.Series(dtype=float)), errors="coerce").fillna(0) > 0).sum())

    if scab_ge1 > 0 or monilia_ge1 > 0 or max(max_scab, max_monilia) >= 1.0:
        climate_pressure = "Alta"
        climate_msg = "Periodo con evento(s) compatibles con infección. Priorizar campos sin cobertura registrada."
    elif max(max_scab, max_monilia) >= 0.75 or rain_total >= 10 or wet_hours >= 24:
        climate_pressure = "Media-alta"
        climate_msg = "Periodo húmedo o cercano a umbral. Revisar especialmente campos sin tratamiento registrado."
    elif rain_total >= 5 or wet_hours >= 8:
        climate_pressure = "Media"
        climate_msg = "Periodo con humedad/lluvia moderada. Mantener vigilancia."
    else:
        climate_pressure = "Baja"
        climate_msg = "Sin presión climática clara durante el periodo."

    # Último tratamiento por campo, si existe.
    cross = build_treatment_sanitary_cross(hist, activities_df) if activities_df is not None and not activities_df.empty else pd.DataFrame()
    if cross is not None and not cross.empty:
        # build_treatment_sanitary_cross ya trae último tratamiento por campo.
        treatment_cols = cross.copy()
    else:
        treatment_cols = pd.DataFrame(columns=[
            "Campo", "Último tratamiento", "Días hasta último dato climático", "Producto",
            "Variedades tratadas", "Superficie tratada ha", "Dosis", "Unidad dosis",
            "Lluvia posterior mm", "Eventos hoja mojada posteriores",
            "Eventos moteado ratio >= 1", "Eventos monilia ratio >= 1",
            "Máx ratio moteado posterior", "Máx ratio monilia posterior",
            "Primer evento posterior", "Evento más crítico posterior", "Aviso orientativo", "ID Agroptima"
        ])

    rows = []
    for _, frow in fields_df.iterrows():
        campo = str(frow.get("Campo", "") or "").strip()
        if not campo:
            continue

        tr = pd.DataFrame()
        if not treatment_cols.empty and "Campo" in treatment_cols.columns:
            tr = treatment_cols[treatment_cols["Campo"].astype(str) == campo]

        if not tr.empty:
            base = tr.iloc[0].to_dict()
            treated = True
            last_treatment = base.get("Último tratamiento", "")
            product = base.get("Producto", "")
            varieties_treated = base.get("Variedades tratadas", "") or "Agroptima no especifica variedad; revisar si fue campo completo o parcial."
            aviso = base.get("Aviso orientativo", "")
            if climate_pressure in ["Alta", "Media-alta"] and str(last_treatment).strip():
                aviso = (
                    f"{aviso} Riesgo climático semanal {climate_pressure.lower()}: revisar si el tratamiento cubrió todo el campo "
                    f"y todas las variedades, y si la lluvia posterior pudo reducir persistencia."
                ).strip()
        else:
            treated = False
            last_treatment = "Sin tratamiento registrado"
            product = "Sin tratamiento registrado"
            varieties_treated = "Sin tratamiento registrado"
            if climate_pressure in ["Alta", "Media-alta"]:
                aviso = f"{climate_msg} Este campo no tiene tratamiento registrado en Agroptima."
            elif climate_pressure == "Media":
                aviso = f"{climate_msg} Campo sin tratamiento registrado; revisar si hay síntomas o variedades sensibles."
            else:
                aviso = "Campo sin tratamiento registrado. Seguimiento normal salvo cambio de previsión o síntomas."

            base = {
                "Campo": campo,
                "Último tratamiento": last_treatment,
                "Días hasta último dato climático": np.nan,
                "Producto": product,
                "Variedades tratadas": varieties_treated,
                "Superficie tratada ha": np.nan,
                "Dosis": np.nan,
                "Unidad dosis": "",
                "Lluvia posterior mm": rain_total,
                "Eventos hoja mojada posteriores": int(len(events)),
                "Eventos moteado ratio >= 1": scab_ge1,
                "Eventos monilia ratio >= 1": monilia_ge1,
                "Máx ratio moteado posterior": float(max_scab),
                "Máx ratio monilia posterior": float(max_monilia),
                "Primer evento posterior": "",
                "Evento más crítico posterior": "",
                "Aviso orientativo": aviso,
                "ID Agroptima": "",
            }

        base["Campo"] = campo
        base["Tratado registrado"] = "Sí" if treated else "No"
        base["Último tratamiento"] = last_treatment
        base["Producto"] = product
        base["Variedades tratadas"] = varieties_treated
        base["Variedades actuales"] = frow.get("Variedades actuales", "")
        base["Superficie ha"] = frow.get("Superficie ha", np.nan)
        base["Presión climática semanal"] = climate_pressure
        base["Aviso orientativo"] = aviso

        # Prioridad: los no tratados suben primero cuando hay presión climática.
        if not treated and climate_pressure in ["Alta", "Media-alta"]:
            prioridad = "Alta"
        elif not treated and climate_pressure == "Media":
            prioridad = "Media-alta"
        else:
            prioridad = advisory_priority_label(aviso)

        base["Prioridad"] = prioridad
        rows.append(base)

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    priority_order = {"Alta": 0, "Media-alta": 1, "Media": 2, "Baja": 3}
    out["_orden_prioridad"] = out["Prioridad"].map(priority_order).fillna(9)
    out["_no_tratado"] = (out["Tratado registrado"].astype(str) == "No").astype(int)
    for c in ["Lluvia posterior mm", "Máx ratio moteado posterior", "Máx ratio monilia posterior"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
    out = out.sort_values(
        ["_orden_prioridad", "_no_tratado", "Lluvia posterior mm", "Máx ratio moteado posterior", "Máx ratio monilia posterior", "Campo"],
        ascending=[True, False, False, False, False, True],
    ).drop(columns=["_orden_prioridad", "_no_tratado"], errors="ignore").reset_index(drop=True)

    return out



def build_weekly_executive_report(history_df, activities_df, start_date, end_date):
    """Genera datos y texto para un informe semanal descargable."""
    if history_df is None or history_df.empty:
        return {}, "No hay histórico climático cargado.", pd.DataFrame(), pd.DataFrame()

    hist = history_df.copy()
    hist["fecha_hora"] = pd.to_datetime(hist["fecha_hora"], errors="coerce")
    hist = hist.dropna(subset=["fecha_hora"]).sort_values("fecha_hora")

    start_ts = pd.to_datetime(start_date)
    end_ts = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    period_df = hist[(hist["fecha_hora"] >= start_ts) & (hist["fecha_hora"] <= end_ts)].copy()

    if period_df.empty:
        return {}, "No hay datos climáticos en el periodo seleccionado.", pd.DataFrame(), pd.DataFrame()

    temp_mean = safe_num(period_df.get("temp_media", pd.Series(dtype=float)), "mean")
    temp_min = safe_num(period_df.get("temp_min", period_df.get("temp_media", pd.Series(dtype=float))), "min")
    temp_max = safe_num(period_df.get("temp_max", period_df.get("temp_media", pd.Series(dtype=float))), "max")
    hr_mean = safe_num(period_df.get("hr_media", pd.Series(dtype=float)), "mean")
    rain_total = safe_num(period_df.get("lluvia_mm", pd.Series(dtype=float)), "sum")
    wind_series, wind_col = first_available_numeric(period_df, ["viento_velocidad", "Velocidad del viento"])
    gust_series, gust_col = first_available_numeric(period_df, ["viento_rafaga", "viento_racha", "Ráfaga de viento"])
    radiation_series, radiation_col = first_available_numeric(period_df, ["irradiancia", "radiacion_mj_m2", "radiacion", "Radiación solar"])

    wind_mean = safe_num(wind_series, "mean")
    gust_max = safe_num(gust_series, "max")
    radiation_sum = safe_num(radiation_series, "sum")

    events = detect_leaf_wetness_events(period_df) if has_sensor(period_df, "Humectación de hoja") else pd.DataFrame()
    if not events.empty:
        max_scab = pd.to_numeric(events.get("Ratio moteado", 0), errors="coerce").fillna(0).max()
        max_monilia = pd.to_numeric(events.get("Ratio monilia", 0), errors="coerce").fillna(0).max()
        scab_ge1 = int((pd.to_numeric(events.get("Ratio moteado", 0), errors="coerce").fillna(0) >= 1.0).sum())
        monilia_ge1 = int((pd.to_numeric(events.get("Ratio monilia", 0), errors="coerce").fillna(0) >= 1.0).sum())
    else:
        max_scab = 0.0
        max_monilia = 0.0
        scab_ge1 = 0
        monilia_ge1 = 0

    acts_period = pd.DataFrame()
    if activities_df is not None and not activities_df.empty:
        acts = normalize_activities_df(activities_df).drop(columns=[c for c in ["_clave_fallback", "_clave_importacion"] if c in activities_df.columns], errors="ignore")
        acts["Fecha_dt"] = pd.to_datetime(acts["Fecha"], errors="coerce")
        acts_period = acts[(acts["Fecha_dt"] >= start_ts.normalize()) & (acts["Fecha_dt"] <= end_ts.normalize())].copy()

    priority_table = build_weekly_priority_table_all_fields(hist, activities_df, period_df, start_ts, end_ts)

    metrics = {
        "period_start": start_ts.date().isoformat(),
        "period_end": pd.to_datetime(end_date).date().isoformat(),
        "records": int(len(period_df)),
        "temp_mean": temp_mean,
        "temp_min": temp_min,
        "temp_max": temp_max,
        "hr_mean": hr_mean,
        "rain_total": rain_total,
        "wind_mean": wind_mean,
        "gust_max": gust_max,
        "radiation_sum": radiation_sum,
        "wind_column": wind_col or "",
        "gust_column": gust_col or "",
        "radiation_column": radiation_col or "",
        "leaf_events": int(len(events)),
        "max_scab_ratio": float(max_scab),
        "max_monilia_ratio": float(max_monilia),
        "scab_events_ge1": scab_ge1,
        "monilia_events_ge1": monilia_ge1,
        "activities_count": int(len(acts_period)),
        "fields_treated_count": int(len(set(",".join(acts_period.get("Campos reconocidos", pd.Series(dtype=str)).fillna("").astype(str)).replace("; ", ",").split(",")) - {""})) if not acts_period.empty else 0,
        "priority_high_count": int((priority_table.get("Prioridad", pd.Series(dtype=str)) == "Alta").sum()) if not priority_table.empty else 0,
        "priority_review_count": int(priority_table.get("Prioridad", pd.Series(dtype=str)).isin(["Alta", "Media-alta", "Media"]).sum()) if not priority_table.empty else 0,
    }

    def fmt(value, suffix="", nd=1):
        if value is None or pd.isna(value):
            return "Sin datos"
        return f"{float(value):.{nd}f}{suffix}"

    # Campos prioritarios limitados para informe texto.
    priority_lines = []
    if not priority_table.empty:
        for _, row in priority_table.iterrows():
            priority_lines.append(
                f"- {row['Campo']}: prioridad {row['Prioridad']} · tratado registrado: {row.get('Tratado registrado', '')}. "
                f"Último tratamiento: {row.get('Último tratamiento', '')} · producto: {row.get('Producto', '')}. "
                f"Variedades tratadas: {row.get('Variedades tratadas', '')}. "
                f"Variedades actuales: {row.get('Variedades actuales', '')}. "
                f"Aviso: {row.get('Aviso orientativo', '')}"
            )
    else:
        priority_lines.append("- No hay campos definidos para generar prioridades.")

    act_lines = []
    if not acts_period.empty:
        for _, row in acts_period.head(10).iterrows():
            act_lines.append(
                f"- {row.get('Fecha', '')}: {row.get('Producto', '')} en {row.get('Campos reconocidos', row.get('Campos', ''))}."
            )
    else:
        act_lines.append("- No hay actuaciones registradas en este periodo.")

    report_md = f"""# Informe semanal · Finca Gallinal

**Periodo:** {metrics['period_start']} a {metrics['period_end']}

## 1. Resumen climático

- Registros horarios analizados: **{metrics['records']}**
- Temperatura media: **{fmt(temp_mean, ' ºC')}**
- Temperatura mínima: **{fmt(temp_min, ' ºC')}**
- Temperatura máxima: **{fmt(temp_max, ' ºC')}**
- Humedad relativa media: **{fmt(hr_mean, ' %')}**
- Lluvia acumulada: **{fmt(rain_total, ' mm')}**
- Viento medio: **{fmt(wind_mean, '')}**
- Racha máxima: **{fmt(gust_max, '')}**
- Radiación acumulada: **{fmt(radiation_sum, ' MJ/m²')}**

## 2. Sanidad vegetal

- Eventos de hoja mojada detectados: **{metrics['leaf_events']}**
- Eventos de moteado con ratio ≥ 1: **{metrics['scab_events_ge1']}**
- Eventos de monilia con ratio ≥ 1: **{metrics['monilia_events_ge1']}**
- Máximo ratio moteado: **{metrics['max_scab_ratio']:.2f}**
- Máximo ratio monilia: **{metrics['max_monilia_ratio']:.2f}**

## 3. Actuaciones registradas en el periodo

- Actuaciones registradas: **{metrics['activities_count']}**
- Campos tratados detectados: **{metrics['fields_treated_count']}**

{chr(10).join(act_lines)}

## 4. Campos prioritarios para revisar

El informe incluye todos los campos de la finca, aunque no tengan actuaciones registradas en Agroptima.

- Campos con prioridad alta: **{metrics['priority_high_count']}**
- Campos con aviso de vigilar/revisar/priorizar: **{metrics['priority_review_count']}**

{chr(10).join(priority_lines)}

## 5. Lectura orientativa

Este informe cruza el histórico climático, los tratamientos importados de Agroptima y los eventos de humectación foliar. El clima se usa como referencia general de finca para todos los campos. Se incluyen también campos sin tratamiento registrado, que pueden quedar por delante si hay presión sanitaria. Si Agroptima no especifica variedad, no se debe asumir que todo el campo quedó cubierto.
"""

    return metrics, report_md, acts_period, priority_table





def find_finca_logo_path():
    """Busca el logo de Finca Gallinal en rutas habituales, aceptando assets/asset."""
    from pathlib import Path as _Path
    base = _Path(__file__).parent
    candidates = [
        base / "assets" / "finca_gallinal_logo.png",
        base / "assets" / "finca_gallinal_logo.jpeg",
        base / "assets" / "finca_gallinal_logo.jpg",
        base / "assets" / "logo.png",
        base / "assets" / "logo.jpeg",
        base / "assets" / "logo.jpg",
        base / "asset" / "finca_gallinal_logo.png",
        base / "asset" / "finca_gallinal_logo.jpeg",
        base / "asset" / "finca_gallinal_logo.jpg",
        base / "asset" / "logo.png",
        base / "asset" / "logo.jpeg",
        base / "asset" / "logo.jpg",
        base / "finca_gallinal_logo.png",
        base / "finca_gallinal_logo.jpeg",
        base / "finca_gallinal_logo.jpg",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def render_top_banner():
    """Cabecera elegante tipo banner con el logo de la finca."""
    logo_path = find_finca_logo_path()
    logo_html = ""
    if logo_path is not None:
        try:
            import base64 as _base64
            ext = logo_path.suffix.lower().replace('.', '') or 'png'
            mime = 'image/png' if ext == 'png' else 'image/jpeg'
            encoded = _base64.b64encode(logo_path.read_bytes()).decode('utf-8')
            logo_html = f'<img src="data:{mime};base64,{encoded}" style="width:120px;max-width:120px;height:auto;display:block;"/>'
        except Exception:
            logo_html = ""

    st.markdown(
        f"""
        <style>
        .fg-banner {{
            background: linear-gradient(135deg, #ffffff 0%, #f7faf7 55%, #eef6ef 100%);
            border: 1px solid #dce9dc;
            border-radius: 20px;
            padding: 18px 26px;
            margin: 0.2rem 0 1rem 0;
            box-shadow: 0 6px 18px rgba(45, 72, 45, 0.06);
        }}
        .fg-banner-inner {{
            display: flex;
            align-items: center;
            gap: 20px;
        }}
        .fg-banner-logo {{
            flex: 0 0 auto;
            width: 128px;
            text-align: center;
        }}
        .fg-banner-copy {{
            flex: 1 1 auto;
        }}
        .fg-banner-kicker {{
            color: #648064;
            font-size: 0.9rem;
            font-weight: 600;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            margin-bottom: 0.2rem;
        }}
        .fg-banner-title {{
            color: #1f3f2f;
            font-size: 2rem;
            line-height: 1.15;
            font-weight: 700;
            margin: 0;
        }}
        .fg-banner-subtitle {{
            color: #5d6d5d;
            font-size: 1rem;
            margin-top: 0.45rem;
        }}
        .fg-banner-pill-wrap {{
            margin-top: 0.85rem;
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
        }}
        .fg-banner-pill {{
            background: #ffffff;
            color: #2d5b43;
            border: 1px solid #d5e5d5;
            border-radius: 999px;
            padding: 0.28rem 0.7rem;
            font-size: 0.84rem;
            font-weight: 500;
        }}
        @media (max-width: 820px) {{
            .fg-banner-inner {{
                flex-direction: column;
                align-items: flex-start;
            }}
            .fg-banner-logo {{
                width: 100%;
                text-align: left;
            }}
            .fg-banner-title {{
                font-size: 1.6rem;
            }}
        }}
        </style>
        <div class="fg-banner">
          <div class="fg-banner-inner">
            <div class="fg-banner-logo">{logo_html}</div>
            <div class="fg-banner-copy">
              <div class="fg-banner-kicker">Finca Gallinal</div>
              <div class="fg-banner-title">Plataforma agroclimática</div>
              <div class="fg-banner-subtitle">Clima, sanidad, riego, campos, actuaciones y análisis de campañas.</div>
              <div class="fg-banner-pill-wrap">
                <span class="fg-banner-pill">🌦️ Clima</span>
                <span class="fg-banner-pill">🍄 Sanidad</span>
                <span class="fg-banner-pill">💧 Riego</span>
                <span class="fg-banner-pill">🌱 Fenología</span>
                <span class="fg-banner-pill">📈 Comparador</span>
              </div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Indicador de frescura de los datos climáticos ─────────────────────────
    try:
        _hist = st.session_state.get("history_df", pd.DataFrame())
        if _hist is not None and not _hist.empty and "fecha_hora" in _hist.columns:
            _last = pd.to_datetime(_hist["fecha_hora"], errors="coerce").max()
            if pd.notna(_last):
                _ahora = pd.Timestamp.now()
                _horas = (_ahora - _last).total_seconds() / 3600.0
                _fecha_txt = _last.strftime("%d/%m/%Y · %H:%M")
                if _horas <= 36:
                    st.success(f"🌦️ Datos climáticos actualizados hasta **{_fecha_txt}**.")
                elif _horas <= 24 * 7:
                    _dias = int(_horas // 24)
                    st.warning(
                        f"🌦️ Datos climáticos hasta **{_fecha_txt}** "
                        f"(hace ~{_dias} día/s). Descarga de Sencrop para actualizar."
                    )
                else:
                    st.error(
                        f"🌦️ Datos climáticos desactualizados: último registro **{_fecha_txt}**. "
                        f"Conviene descargar de Sencrop."
                    )
        else:
            st.info("🌦️ Aún no hay datos climáticos cargados. Descarga desde Sencrop.")
    except Exception:
        pass


def build_weekly_pdf_report(metrics, report_md, acts_period, priority_table):
    """Crea un PDF bonito y legible del informe semanal."""
    try:
        from io import BytesIO
        from pathlib import Path as _Path
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
            Image,
            PageBreak,
            KeepTogether,
        )
    except ImportError as exc:
        raise ImportError(
            "Falta la librería reportlab. Añade reportlab>=4.0 a requirements.txt y vuelve a desplegar."
        ) from exc

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=1.1 * cm,
        leftMargin=1.1 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
        title=f"Informe semanal Finca Gallinal {metrics.get('period_start', '')} {metrics.get('period_end', '')}",
        author="Finca Gallinal",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="FGTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=colors.HexColor("#1F2937"),
        alignment=TA_CENTER,
        spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name="FGSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#6B7280"),
        alignment=TA_CENTER,
        spaceAfter=18,
    ))
    styles.add(ParagraphStyle(
        name="FGSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#2F5D50"),
        spaceBefore=12,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="FGNormal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#1F2937"),
    ))
    styles.add(ParagraphStyle(
        name="FGSmall",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.2,
        leading=8.6,
        textColor=colors.HexColor("#6B7280"),
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="FGTableHead",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.4,
        leading=8.6,
        textColor=colors.white,
        alignment=TA_CENTER,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="FGCardTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#374151"),
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="FGCardValue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=15,
        textColor=colors.HexColor("#111827"),
        alignment=TA_CENTER,
    ))

    def fmt(value, suffix="", nd=1):
        if value is None or pd.isna(value):
            return "Sin datos"
        return f"{float(value):.{nd}f}{suffix}"

    story = []

    logo_path = find_finca_logo_path()
    if logo_path:
        try:
            logo = Image(str(logo_path), width=4.0 * cm, height=4.0 * cm)
            logo.hAlign = "CENTER"
            story.append(logo)
            story.append(Spacer(1, 0.15 * cm))
        except Exception:
            pass

    story.append(Paragraph("Informe semanal agroclimático", styles["FGTitle"]))
    story.append(Paragraph("Seguimiento climático, sanitario y de actuaciones", styles["FGSubtitle"]))
    story.append(Paragraph(
        f"Periodo analizado: <b>{metrics.get('period_start', '')}</b> a <b>{metrics.get('period_end', '')}</b>",
        styles["FGNormal"],
    ))
    story.append(Spacer(1, 0.35 * cm))

    # KPI cards
    kpi_data = [
        [
            Paragraph("Lluvia", styles["FGCardTitle"]),
            Paragraph("Eventos hoja mojada", styles["FGCardTitle"]),
            Paragraph("Actuaciones", styles["FGCardTitle"]),
            Paragraph("Campos con aviso", styles["FGCardTitle"]),
        ],
        [
            Paragraph(fmt(metrics.get("rain_total"), " mm"), styles["FGCardValue"]),
            Paragraph(str(metrics.get("leaf_events", 0)), styles["FGCardValue"]),
            Paragraph(str(metrics.get("activities_count", 0)), styles["FGCardValue"]),
            Paragraph(str(metrics.get("priority_review_count", 0)), styles["FGCardValue"]),
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[4.2 * cm] * 4)
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F7F2")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#C8D8C0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DCE8D7")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 0.45 * cm))

    story.append(Paragraph("1. Resumen climático", styles["FGSection"]))
    climate_rows = [
        ["Indicador", "Valor"],
        ["Registros horarios analizados", str(metrics.get("records", 0))],
        ["Temperatura media", fmt(metrics.get("temp_mean"), " ºC")],
        ["Temperatura mínima", fmt(metrics.get("temp_min"), " ºC")],
        ["Temperatura máxima", fmt(metrics.get("temp_max"), " ºC")],
        ["Humedad relativa media", fmt(metrics.get("hr_mean"), " %")],
        ["Lluvia acumulada", fmt(metrics.get("rain_total"), " mm")],
        ["Viento medio", fmt(metrics.get("wind_mean"), "")],
        ["Racha máxima", fmt(metrics.get("gust_max"), "")],
        ["Radiación acumulada", fmt(metrics.get("radiation_sum"), " MJ/m²")],
    ]
    climate_table = Table(climate_rows, colWidths=[8.0 * cm, 8.5 * cm])
    climate_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5D50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#FBFCFA")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAF6")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(climate_table)

    story.append(Paragraph("2. Sanidad vegetal", styles["FGSection"]))
    sanitary_rows = [
        ["Indicador", "Valor"],
        ["Eventos de hoja mojada", str(metrics.get("leaf_events", 0))],
        ["Eventos moteado ratio >= 1", str(metrics.get("scab_events_ge1", 0))],
        ["Eventos monilia ratio >= 1", str(metrics.get("monilia_events_ge1", 0))],
        ["Máximo ratio moteado", f"{float(metrics.get('max_scab_ratio', 0)):.2f}"],
        ["Máximo ratio monilia", f"{float(metrics.get('max_monilia_ratio', 0)):.2f}"],
    ]
    sanitary_table = Table(sanitary_rows, colWidths=[8.0 * cm, 8.5 * cm])
    sanitary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#8A6F3D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FFFFFF"), colors.HexColor("#FBF8EF")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(sanitary_table)

    story.append(Paragraph("3. Actuaciones registradas en el periodo", styles["FGSection"]))
    if acts_period is None or acts_period.empty:
        story.append(Paragraph("No hay actuaciones registradas en este periodo.", styles["FGNormal"]))
    else:
        rows = [["Fecha", "Producto", "Campos reconocidos"]]
        for _, row in acts_period.head(14).iterrows():
            rows.append([
                str(row.get("Fecha", "")),
                Paragraph(str(row.get("Producto", "")), styles["FGSmall"]),
                Paragraph(str(row.get("Campos reconocidos", row.get("Campos", ""))), styles["FGSmall"]),
            ])
        acts_table = Table(rows, colWidths=[2.8 * cm, 5.0 * cm, 8.7 * cm], repeatRows=1)
        acts_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5D50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAF6")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(acts_table)
        if len(acts_period) > 14:
            story.append(Paragraph(f"Se muestran las primeras 14 actuaciones de {len(acts_period)}.", styles["FGSmall"]))

    story.append(PageBreak())
    if logo_path:
        try:
            logo_small = Image(str(logo_path), width=2.0 * cm, height=2.0 * cm)
            logo_small.hAlign = "LEFT"
            story.append(logo_small)
        except Exception:
            pass

    story.append(Paragraph("4. Campos prioritarios para revisar", styles["FGSection"]))
    if priority_table is None or priority_table.empty:
        story.append(Paragraph("No hay campos definidos para generar prioridades.", styles["FGNormal"]))
    else:
        rows = [[
            Paragraph("Campo", styles["FGTableHead"]),
            Paragraph("Prio.", styles["FGTableHead"]),
            Paragraph("Trat.", styles["FGTableHead"]),
            Paragraph("Últ. trat.", styles["FGTableHead"]),
            Paragraph("Producto", styles["FGTableHead"]),
            Paragraph("Aviso", styles["FGTableHead"]),
        ]]
        for _, row in priority_table.iterrows():
            rows.append([
                Paragraph(str(row.get("Campo", "")), styles["FGSmall"]),
                Paragraph(str(row.get("Prioridad", "")), styles["FGSmall"]),
                Paragraph(str(row.get("Tratado registrado", "")), styles["FGSmall"]),
                Paragraph(str(row.get("Último tratamiento", "")), styles["FGSmall"]),
                Paragraph(str(row.get("Producto", "")), styles["FGSmall"]),
                Paragraph(str(row.get("Aviso orientativo", "")), styles["FGSmall"]),
            ])
        priority_pdf_table = Table(rows, colWidths=[3.0 * cm, 1.5 * cm, 1.2 * cm, 2.4 * cm, 4.2 * cm, 14.2 * cm], repeatRows=1)
        priority_pdf_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#A33F2B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FFFFFF"), colors.HexColor("#FFF7F2")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(priority_pdf_table)
        story.append(Paragraph(f"Se muestran todos los campos incluidos en la tabla de prioridades: {len(priority_table)}.", styles["FGSmall"]))

    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("5. Lectura orientativa", styles["FGSection"]))
    story.append(Paragraph(
        "Este informe cruza el histórico climático, los tratamientos importados de Agroptima y los eventos de humectación foliar. "
        "El clima se usa como referencia general de finca para todos los campos. Agroptima no aporta hora exacta de tratamiento, "
        "por lo que los cálculos posteriores se realizan desde la fecha de tratamiento.",
        styles["FGNormal"],
    ))

    def add_page_number(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.drawString(1.1 * cm, 0.6 * cm, "Finca Gallinal · Informe agroclimático")
        canvas.drawRightString(28.3 * cm, 0.6 * cm, f"Página {doc_obj.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf



def weekly_report_tab(history, soil_type, hoja_threshold):
    st.subheader("Informe semanal")

    if history is None or history.empty:
        st.info("Carga primero el histórico climático.")
        return

    st.info(
        "Genera un informe práctico combinando clima, eventos sanitarios, actuaciones Agroptima "
        "y campos prioritarios para revisar. Ahora también puede descargarse en PDF con el logo de Finca Gallinal."
    )

    hist = history.copy()
    hist["fecha_hora"] = pd.to_datetime(hist["fecha_hora"], errors="coerce")
    hist = hist.dropna(subset=["fecha_hora"])
    min_d = hist["fecha_hora"].min().date()
    max_d = hist["fecha_hora"].max().date()

    default_end = max_d
    default_start = max(min_d, default_end - pd.Timedelta(days=6))

    c1, c2 = st.columns(2)
    start_date = c1.date_input("Inicio del informe", value=default_start, min_value=min_d, max_value=max_d)
    end_date = c2.date_input("Fin del informe", value=default_end, min_value=min_d, max_value=max_d)

    if pd.to_datetime(start_date) > pd.to_datetime(end_date):
        st.warning("La fecha de inicio no puede ser posterior a la fecha de fin.")
        return

    activities_df = st.session_state.get("activities_df", pd.DataFrame(columns=ACTIVITY_COLUMNS))
    metrics, report_md, acts_period, priority_table = build_weekly_executive_report(
        history, activities_df, start_date, end_date
    )

    if not metrics:
        st.warning(report_md)
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lluvia semanal", f"{metrics['rain_total']:.1f} mm" if not pd.isna(metrics["rain_total"]) else "Sin datos")
    c2.metric("Eventos hoja mojada", metrics["leaf_events"])
    c3.metric("Actuaciones", metrics["activities_count"])
    c4.metric("Campos con aviso", metrics["priority_review_count"])

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Temp. media", f"{metrics['temp_mean']:.1f} ºC" if not pd.isna(metrics["temp_mean"]) else "Sin datos")
    c6.metric("Máx ratio moteado", f"{metrics['max_scab_ratio']:.2f}")
    c7.metric("Máx ratio monilia", f"{metrics['max_monilia_ratio']:.2f}")
    c8.metric("Prioridad alta", metrics["priority_high_count"])

    with st.expander("Columnas usadas para viento y radiación", expanded=False):
        st.write({
            "Viento medio": metrics.get("wind_column") or "Sin columna detectada",
            "Racha máxima": metrics.get("gust_column") or "Sin columna detectada",
            "Radiación acumulada": metrics.get("radiation_column") or "Sin columna detectada",
        })

    with st.expander("Logo usado en el PDF", expanded=False):
        logo_found = find_finca_logo_path()
        if logo_found:
            st.success(f"Logo detectado: {logo_found}")
            try:
                st.image(str(logo_found), width=180)
            except Exception:
                pass
        else:
            st.warning("No se ha detectado logo. Revisa que exista una carpeta assets o asset con finca_gallinal_logo.jpeg.")

    st.markdown("### Vista previa del informe")
    st.markdown(report_md)

    st.download_button(
        "Descargar informe semanal en Markdown",
        data=report_md.encode("utf-8-sig"),
        file_name=f"informe_semanal_finca_gallinal_{metrics['period_start']}_{metrics['period_end']}.md",
        mime="text/markdown",
        key="download_weekly_report_md",
        use_container_width=True,
    )

    try:
        pdf_bytes = build_weekly_pdf_report(metrics, report_md, acts_period, priority_table)
        st.download_button(
            "Descargar informe semanal en PDF con logo",
            data=pdf_bytes,
            file_name=f"informe_semanal_finca_gallinal_{metrics['period_start']}_{metrics['period_end']}.pdf",
            mime="application/pdf",
            key="download_weekly_report_pdf",
            use_container_width=True,
        )
    except ImportError as exc:
        st.warning(str(exc))
    except Exception as exc:
        st.warning(f"No se pudo generar el PDF: {exc}")

    with st.expander("Actuaciones del periodo", expanded=False):
        if acts_period.empty:
            st.info("No hay actuaciones registradas en el periodo seleccionado.")
        else:
            st.dataframe(acts_period.drop(columns=["Fecha_dt"], errors="ignore"), use_container_width=True)
            st.download_button(
                "Descargar actuaciones del periodo",
                data=acts_period.drop(columns=["Fecha_dt"], errors="ignore").to_csv(index=False).encode("utf-8-sig"),
                file_name=f"actuaciones_periodo_{metrics['period_start']}_{metrics['period_end']}.csv",
                mime="text/csv",
                key="download_weekly_activities_csv",
            )

    with st.expander("Campos prioritarios · todos los campos de la finca", expanded=True):
        if priority_table.empty:
            st.info("No hay campos definidos para generar prioridades.")
        else:
            st.caption(f"Se muestran todos los campos incluidos en la prioridad semanal: {len(priority_table)}.")
            cols = [
                "Campo", "Prioridad", "Tratado registrado", "Último tratamiento", "Producto",
                "Variedades tratadas", "Variedades actuales", "Presión climática semanal",
                "Lluvia posterior mm", "Máx ratio moteado posterior", "Máx ratio monilia posterior", "Aviso orientativo"
            ]
            cols = [c for c in cols if c in priority_table.columns]
            st.dataframe(priority_table[cols], use_container_width=True)
            st.download_button(
                "Descargar campos prioritarios",
                data=priority_table.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"campos_prioritarios_{metrics['period_start']}_{metrics['period_end']}.csv",
                mime="text/csv",
                key="download_weekly_priority_csv",
            )




CARPOCAPSA_DEFAULT_TRAP_COLUMNS = [
    "Fecha",
    "Campo/Zona",
    "Trampa",
    "Tipo trampa",
    "Capturas machos",
    "Días desde lectura anterior",
    "Observaciones",
    "Campaña",
]

CARPOCAPSA_DEFAULT_BIOFIX_COLUMNS = [
    "Campo/Zona",
    "Fecha biofix",
    "Criterio",
    "Activo",
    "Observaciones",
    "Campaña",
]

CARPOCAPSA_DEFAULT_DAMAGE_COLUMNS = [
    "Fecha",
    "Campo/Zona",
    "Frutos revisados",
    "Frutos dañados",
    "Observaciones",
    "Campaña",
]


def carpocapsa_default_traps_df():
    return pd.DataFrame(columns=CARPOCAPSA_DEFAULT_TRAP_COLUMNS)


def carpocapsa_default_biofix_df():
    return pd.DataFrame(columns=CARPOCAPSA_DEFAULT_BIOFIX_COLUMNS)


def carpocapsa_default_damage_df():
    return pd.DataFrame(columns=CARPOCAPSA_DEFAULT_DAMAGE_COLUMNS)


def carpocapsa_prepare_traps_df(df):
    if df is None or df.empty:
        return carpocapsa_default_traps_df()
    out = df.copy()
    for col in CARPOCAPSA_DEFAULT_TRAP_COLUMNS:
        if col not in out.columns:
            out[col] = "" if col not in ["Capturas machos", "Días desde lectura anterior"] else np.nan
    out = out[CARPOCAPSA_DEFAULT_TRAP_COLUMNS].copy()
    out["Fecha"] = pd.to_datetime(out["Fecha"], errors="coerce")
    out["Capturas machos"] = pd.to_numeric(out["Capturas machos"], errors="coerce").fillna(0)
    out["Días desde lectura anterior"] = pd.to_numeric(out["Días desde lectura anterior"], errors="coerce").fillna(7)
    detected_year = carpocapsa_detect_year_from_df(out, "Fecha")
    out["Campaña"] = pd.to_numeric(out.get("Campaña", detected_year), errors="coerce").fillna(detected_year if detected_year is not None else pd.Timestamp.today().year).astype(int)
    out["Capturas/trampa/día"] = out.apply(
        lambda r: round(float(r["Capturas machos"]) / max(float(r["Días desde lectura anterior"]), 1), 2),
        axis=1,
    )
    return out


def carpocapsa_prepare_biofix_df(df):
    if df is None or df.empty:
        return carpocapsa_default_biofix_df()
    out = df.copy()
    for col in CARPOCAPSA_DEFAULT_BIOFIX_COLUMNS:
        if col not in out.columns:
            out[col] = "" if col != "Activo" else True
    out = out[CARPOCAPSA_DEFAULT_BIOFIX_COLUMNS].copy()
    out["Fecha biofix"] = pd.to_datetime(out["Fecha biofix"], errors="coerce")
    detected_year = carpocapsa_detect_year_from_df(out, "Fecha biofix")
    out["Campaña"] = pd.to_numeric(out.get("Campaña", detected_year), errors="coerce").fillna(detected_year if detected_year is not None else pd.Timestamp.today().year).astype(int)
    out["Activo"] = out["Activo"].apply(lambda x: bool(x) if not isinstance(x, str) else x.strip().lower() not in ["false", "0", "no", ""])
    return out


def carpocapsa_prepare_damage_df(df):
    if df is None or df.empty:
        return carpocapsa_default_damage_df()
    out = df.copy()
    for col in CARPOCAPSA_DEFAULT_DAMAGE_COLUMNS:
        if col not in out.columns:
            out[col] = "" if col not in ["Frutos revisados", "Frutos dañados"] else np.nan
    out = out[CARPOCAPSA_DEFAULT_DAMAGE_COLUMNS].copy()
    out["Fecha"] = pd.to_datetime(out["Fecha"], errors="coerce")
    out["Frutos revisados"] = pd.to_numeric(out["Frutos revisados"], errors="coerce").fillna(0)
    out["Frutos dañados"] = pd.to_numeric(out["Frutos dañados"], errors="coerce").fillna(0)
    detected_year = carpocapsa_detect_year_from_df(out, "Fecha")
    out["Campaña"] = pd.to_numeric(out.get("Campaña", detected_year), errors="coerce").fillna(detected_year if detected_year is not None else pd.Timestamp.today().year).astype(int)
    out["% daño"] = out.apply(
        lambda r: round(float(r["Frutos dañados"]) / float(r["Frutos revisados"]) * 100, 2) if float(r["Frutos revisados"]) > 0 else np.nan,
        axis=1,
    )
    return out



def carpocapsa_detect_year_from_df(df, date_col="Fecha"):
    """Detecta el año predominante a partir de una columna de fechas."""
    if df is None or df.empty or date_col not in df.columns:
        return None
    dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
    if dates.empty:
        return None
    counts = dates.dt.year.value_counts()
    if counts.empty:
        return None
    return int(counts.index[0])


def carpocapsa_add_campaign_column(df, campaign_year=None, date_col="Fecha"):
    """Añade o normaliza la columna Campaña."""
    if df is None or df.empty:
        return df
    out = df.copy()
    if "Campaña" not in out.columns:
        detected = campaign_year or carpocapsa_detect_year_from_df(out, date_col=date_col)
        out["Campaña"] = detected if detected is not None else ""
    else:
        out["Campaña"] = pd.to_numeric(out["Campaña"], errors="coerce")
        if campaign_year is not None:
            out["Campaña"] = out["Campaña"].fillna(int(campaign_year))
    return out


def carpocapsa_available_campaigns(*dfs):
    """Devuelve campañas disponibles en capturas/biofix/daños."""
    years = set()
    for df in dfs:
        if df is None or df.empty:
            continue
        if "Campaña" in df.columns:
            vals = pd.to_numeric(df["Campaña"], errors="coerce").dropna().astype(int).tolist()
            years.update(vals)
        elif "Fecha" in df.columns:
            y = carpocapsa_detect_year_from_df(df, "Fecha")
            if y:
                years.add(y)
        elif "Fecha biofix" in df.columns:
            y = carpocapsa_detect_year_from_df(df, "Fecha biofix")
            if y:
                years.add(y)
    if not years:
        years.add(int(pd.Timestamp.today().year))
    return sorted(years)


def carpocapsa_filter_campaign(df, campaign_year):
    """Filtra por campaña de forma tolerante."""
    if df is None or df.empty:
        return df
    out = df.copy()
    if "Campaña" in out.columns:
        return out[pd.to_numeric(out["Campaña"], errors="coerce") == int(campaign_year)].copy()
    if "Fecha" in out.columns:
        dates = pd.to_datetime(out["Fecha"], errors="coerce")
        return out[dates.dt.year == int(campaign_year)].copy()
    if "Fecha biofix" in out.columns:
        dates = pd.to_datetime(out["Fecha biofix"], errors="coerce")
        return out[dates.dt.year == int(campaign_year)].copy()
    return out


def carpocapsa_filter_history_campaign(history, campaign_year):
    """Filtra histórico climático al año de campaña de carpocapsa."""
    if history is None or history.empty or "fecha_hora" not in history.columns:
        return history
    out = history.copy()
    dates = pd.to_datetime(out["fecha_hora"], errors="coerce")
    return out[dates.dt.year == int(campaign_year)].copy()


def carpocapsa_history_campaign_message(history, campaign_year):
    """Genera aviso si no hay clima del año de campaña."""
    if history is None or history.empty or "fecha_hora" not in history.columns:
        return "No hay histórico climático cargado."
    dates = pd.to_datetime(history["fecha_hora"], errors="coerce").dropna()
    if dates.empty:
        return "El histórico climático no tiene fechas válidas."
    years = sorted(dates.dt.year.unique().tolist())
    if int(campaign_year) not in years:
        return f"No hay datos climáticos de {campaign_year}. Años disponibles en clima: {', '.join(map(str, years))}."
    return ""



def carpocapsa_read_excel_sheet(uploaded_file, sheet_name, required_any=None):
    """Lee una hoja Excel de Carpocapsa de forma tolerante."""
    try:
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
    except ValueError:
        return pd.DataFrame(), f"No existe la hoja '{sheet_name}'."
    except Exception as e:
        return pd.DataFrame(), f"No se pudo leer la hoja '{sheet_name}': {e}"

    df = df.dropna(how="all").copy()
    df.columns = [str(c).strip() for c in df.columns]

    # Eliminar columnas completamente vacías o de índice de Excel.
    unnamed = [c for c in df.columns if str(c).lower().startswith("unnamed")]
    if unnamed:
        df = df.drop(columns=unnamed, errors="ignore")

    if required_any:
        present = [c for c in required_any if c in df.columns]
        if not present:
            return pd.DataFrame(), f"La hoja '{sheet_name}' no contiene columnas esperadas: {', '.join(required_any)}."

    return df, ""


def carpocapsa_import_workbook(uploaded_file):
    """Importa un Excel convertido de Carpocapsa con hojas Capturas_App, Biofix_2025 y Danos_2025."""
    messages = []
    imported = {}

    captures_raw, msg = carpocapsa_read_excel_sheet(
        uploaded_file,
        "Capturas_App",
        required_any=["Fecha", "Campo/Zona", "Capturas machos"],
    )
    if msg:
        messages.append(msg)
    if not captures_raw.empty:
        # Adaptar columnas extra del Excel convertido al formato interno de la app.
        captures = captures_raw.copy()
        for col in CARPOCAPSA_DEFAULT_TRAP_COLUMNS:
            if col not in captures.columns:
                captures[col] = "" if col not in ["Capturas machos", "Días desde lectura anterior"] else np.nan
        captures["Tipo trampa"] = captures["Tipo trampa"].replace({"N": "Feromona", "Normal": "Feromona"}).fillna("Feromona")
        captures["Días desde lectura anterior"] = pd.to_numeric(captures["Días desde lectura anterior"], errors="coerce").fillna(7)
        captures["Capturas machos"] = pd.to_numeric(captures["Capturas machos"], errors="coerce").fillna(0)
        captures = captures[CARPOCAPSA_DEFAULT_TRAP_COLUMNS].copy()
        captures_prepared = carpocapsa_prepare_traps_df(captures)
        detected_campaign = carpocapsa_detect_year_from_df(captures_prepared, "Fecha")
        captures_prepared = carpocapsa_add_campaign_column(captures_prepared, detected_campaign, "Fecha")
        imported["traps"] = captures_prepared[CARPOCAPSA_DEFAULT_TRAP_COLUMNS]
        imported["detected_campaign"] = detected_campaign
        messages.append(f"Capturas importadas: {len(imported['traps'])} filas.")
        if detected_campaign:
            messages.append(f"Campaña detectada automáticamente: {detected_campaign}.")

    # Buscar hoja Biofix_2025 o cualquier hoja que empiece por Biofix.
    try:
        xls = pd.ExcelFile(uploaded_file)
        sheet_names = xls.sheet_names
    except Exception:
        sheet_names = []
    biofix_sheet = "Biofix_2025" if "Biofix_2025" in sheet_names else next((s for s in sheet_names if str(s).lower().startswith("biofix")), None)
    if biofix_sheet:
        biofix_raw, msg = carpocapsa_read_excel_sheet(
            uploaded_file,
            biofix_sheet,
            required_any=["Campo/Zona", "Fecha biofix"],
        )
        if msg:
            messages.append(msg)
        if not biofix_raw.empty:
            biofix = biofix_raw.copy()
            for col in CARPOCAPSA_DEFAULT_BIOFIX_COLUMNS:
                if col not in biofix.columns:
                    biofix[col] = "" if col != "Activo" else True
            biofix = biofix[CARPOCAPSA_DEFAULT_BIOFIX_COLUMNS].copy()
            detected_campaign = imported.get("detected_campaign") or carpocapsa_detect_year_from_df(biofix, "Fecha biofix")
            biofix_prepared = carpocapsa_prepare_biofix_df(biofix)
            biofix_prepared = carpocapsa_add_campaign_column(biofix_prepared, detected_campaign, "Fecha biofix")
            imported["biofix"] = biofix_prepared[CARPOCAPSA_DEFAULT_BIOFIX_COLUMNS]
            messages.append(f"Biofix importados: {len(imported['biofix'])} filas.")
    else:
        messages.append("No se encontró hoja Biofix_2025; puedes introducir el biofix manualmente.")

    damage_sheet = "Danos_2025" if "Danos_2025" in sheet_names else next((s for s in sheet_names if str(s).lower().startswith(("danos", "daños"))), None)
    if damage_sheet:
        damage_raw, msg = carpocapsa_read_excel_sheet(
            uploaded_file,
            damage_sheet,
            required_any=["Fecha", "Campo/Zona", "Frutos revisados", "Frutos dañados"],
        )
        if msg and "no contiene" not in msg.lower():
            messages.append(msg)
        if not damage_raw.empty and {"Fecha", "Campo/Zona"}.issubset(set(damage_raw.columns)):
            damage = damage_raw.copy()
            for col in CARPOCAPSA_DEFAULT_DAMAGE_COLUMNS:
                if col not in damage.columns:
                    damage[col] = "" if col not in ["Frutos revisados", "Frutos dañados"] else np.nan
            # Quitar filas vacías de la hoja de plantilla.
            damage = damage[CARPOCAPSA_DEFAULT_DAMAGE_COLUMNS].copy()
            damage = damage.dropna(how="all")
            damage = damage[damage["Campo/Zona"].astype(str).str.strip().replace("nan", "") != ""]
            if not damage.empty:
                detected_campaign = imported.get("detected_campaign") or carpocapsa_detect_year_from_df(damage, "Fecha")
                damage_prepared = carpocapsa_prepare_damage_df(damage)
                damage_prepared = carpocapsa_add_campaign_column(damage_prepared, detected_campaign, "Fecha")
                imported["damage"] = damage_prepared[CARPOCAPSA_DEFAULT_DAMAGE_COLUMNS]
                messages.append(f"Muestreos de daño importados: {len(imported['damage'])} filas.")
            else:
                messages.append("Hoja de daños encontrada, pero sin registros rellenados.")

    return imported, messages


def carpocapsa_export_template_excel():
    """Genera una plantilla Excel vacía en memoria para capturas/biofix/daños."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        carpocapsa_default_traps_df().to_excel(writer, sheet_name="Capturas_App", index=False)
        carpocapsa_default_biofix_df().to_excel(writer, sheet_name="Biofix_2025", index=False)
        carpocapsa_default_damage_df().to_excel(writer, sheet_name="Danos_2025", index=False)
    buffer.seek(0)
    return buffer.getvalue()


# ── Carpocapsa · Supabase Storage (Parquet comprimido, mismo patrón que clima) ──

SUPABASE_CARPOCAPSA_BUCKET = "climate-snapshots"
SUPABASE_CARPOCAPSA_TRAPS_FILE   = "carpocapsa_traps.parquet"
SUPABASE_CARPOCAPSA_BIOFIX_FILE  = "carpocapsa_biofix.parquet"
SUPABASE_CARPOCAPSA_DAMAGE_FILE  = "carpocapsa_damage.parquet"


def _carpocapsa_storage_url(filename):
    url, _ = get_supabase_credentials()
    return f"{url.rstrip('/')}/storage/v1/object/{SUPABASE_CARPOCAPSA_BUCKET}/{filename}"


def _df_to_parquet_bytes(df):
    """Serializa cualquier DataFrame a Parquet comprimido en memoria."""
    if df is None or df.empty:
        return None
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, compression="snappy", engine="pyarrow")
    buf.seek(0)
    return buf.getvalue()


def _parquet_bytes_to_df(content):
    """Deserializa bytes Parquet a DataFrame."""
    return pd.read_parquet(io.BytesIO(content), engine="pyarrow")


def upload_carpocapsa_snapshot_to_supabase(traps_df, biofix_df, damage_df):
    """Guarda los tres DataFrames de carpocapsa como Parquet en Supabase Storage.
    Siempre guarda TODOS los años presentes en sesión (acumulativo)."""
    if not supabase_is_configured():
        return False, "Supabase no está configurado. Revisa SUPABASE_URL y SUPABASE_KEY en Secrets."

    headers = supabase_headers()
    headers["Content-Type"] = "application/octet-stream"
    headers["x-upsert"] = "true"

    files = [
        (traps_df,  SUPABASE_CARPOCAPSA_TRAPS_FILE,  "capturas"),
        (biofix_df, SUPABASE_CARPOCAPSA_BIOFIX_FILE, "biofix"),
        (damage_df, SUPABASE_CARPOCAPSA_DAMAGE_FILE, "daños"),
    ]

    saved = []
    for df, filename, label in files:
        if df is None or df.empty:
            continue
        content = _df_to_parquet_bytes(df)
        if not content:
            continue
        endpoint = _carpocapsa_storage_url(filename)
        try:
            r = requests.post(endpoint, headers=headers, data=content, timeout=60)
        except Exception as exc:
            return False, f"Error subiendo {label}: {exc}"
        if r.status_code not in (200, 201):
            return False, f"Error subiendo {label}: {r.status_code} · {r.text[:300]}"
        n_years = df["Campaña"].nunique() if "Campaña" in df.columns else "?"
        saved.append(f"{label} ({len(df)} filas, {n_years} campaña/s)")

    if not saved:
        return False, "No había datos de carpocapsa para guardar."

    return True, "Snapshot carpocapsa guardado: " + ", ".join(saved) + "."


def autosave_activities_to_supabase():
    """Guarda automáticamente las actuaciones Agroptima en Supabase tras importar.
    Silencioso si Supabase no está configurado; nunca rompe la importación."""
    if not supabase_is_configured():
        return
    try:
        df = st.session_state.get("activities_df", pd.DataFrame())
        if df is None or df.empty:
            return
        ok, msg = upsert_activities_to_supabase(df)
        if ok:
            # toast sobrevive al st.rerun() posterior (la caption se borraría)
            try:
                st.toast("☁️ Actuaciones guardadas en Supabase", icon="✅")
            except Exception:
                pass
            st.caption(f"☁️ Guardado automático en Supabase · {msg}")
        else:
            st.warning(f"⚠️ No se pudo guardar automáticamente en Supabase: {msg}")
    except Exception as e:
        st.warning(f"⚠️ Error en el guardado automático a Supabase: {e}")


def autosave_carpocapsa_to_supabase():
    """Guarda automáticamente el snapshot de carpocapsa (capturas, biofix, daños)
    en Supabase tras importar. Silencioso si Supabase no está configurado."""
    if not supabase_is_configured():
        return
    try:
        ok, msg = upload_carpocapsa_snapshot_to_supabase(
            st.session_state.get("carpocapsa_traps_df",  pd.DataFrame()),
            st.session_state.get("carpocapsa_biofix_df",  pd.DataFrame()),
            st.session_state.get("carpocapsa_damage_df",  pd.DataFrame()),
        )
        if ok:
            # toast sobrevive al st.rerun() posterior (la caption se borraría)
            try:
                st.toast("☁️ Snapshot carpocapsa guardado en Supabase", icon="✅")
            except Exception:
                pass
            st.caption(f"☁️ Snapshot carpocapsa guardado automáticamente en Supabase · {msg}")
        else:
            st.warning(f"⚠️ No se pudo guardar el snapshot de carpocapsa: {msg}")
    except Exception as e:
        st.warning(f"⚠️ Error en el guardado automático de carpocapsa: {e}")


def autosave_climate_snapshot_to_supabase():
    """Crea/actualiza automáticamente el snapshot climático comprimido en Supabase
    tras una descarga de datos. Silencioso si Supabase no está configurado; nunca
    rompe la descarga si el guardado falla."""
    if not supabase_is_configured():
        return
    try:
        df = st.session_state.get("history_df", pd.DataFrame())
        if df is None or df.empty:
            return
        _box = st.empty()
        _box.info("☁️ Actualizando snapshot climático en Supabase…")
        ok, msg = upload_climate_snapshot_to_supabase(df, status_box=_box)
        _box.empty()
        if ok:
            try:
                st.toast("☁️ Snapshot climático actualizado en Supabase", icon="✅")
            except Exception:
                pass
            st.caption(f"☁️ Snapshot climático actualizado automáticamente en Supabase · {msg}")
        else:
            st.warning(f"⚠️ No se pudo actualizar el snapshot climático: {msg}")
    except Exception as e:
        st.warning(f"⚠️ Error en el guardado automático del snapshot climático: {e}")


def load_carpocapsa_snapshot_from_supabase():
    """Descarga los tres archivos Parquet de carpocapsa desde Supabase Storage.
    Devuelve (traps_df, biofix_df, damage_df, mensaje)."""
    if not supabase_is_configured():
        msg = "Supabase no está configurado. Revisa SUPABASE_URL y SUPABASE_KEY en Secrets."
        return None, None, None, msg

    headers = supabase_headers()
    headers.pop("Prefer", None)

    results = {}
    for filename, key in [
        (SUPABASE_CARPOCAPSA_TRAPS_FILE,  "traps"),
        (SUPABASE_CARPOCAPSA_BIOFIX_FILE, "biofix"),
        (SUPABASE_CARPOCAPSA_DAMAGE_FILE, "damage"),
    ]:
        endpoint = _carpocapsa_storage_url(filename)
        try:
            r = requests.get(endpoint, headers=headers, timeout=60)
        except Exception as exc:
            results[key] = None
            continue
        if r.status_code == 200:
            try:
                results[key] = _parquet_bytes_to_df(r.content)
            except Exception:
                results[key] = None
        else:
            results[key] = None

    traps  = results.get("traps")
    biofix = results.get("biofix")
    damage = results.get("damage")

    parts = []
    if traps  is not None and not traps.empty:
        n = traps["Campaña"].nunique() if "Campaña" in traps.columns else "?"
        parts.append(f"{len(traps)} capturas ({n} campaña/s)")
    if biofix is not None and not biofix.empty:
        parts.append(f"{len(biofix)} biofix")
    if damage is not None and not damage.empty:
        parts.append(f"{len(damage)} daños")

    if not parts:
        return None, None, None, "No se encontró snapshot de carpocapsa en Supabase (o está vacío)."

    return traps, biofix, damage, "Snapshot carpocapsa cargado: " + ", ".join(parts) + "."


def carpocapsa_daily_degree_days(history, base_temp=10.0, upper_temp=None, method="horario"):
    """Calcula grados-día diarios para carpocapsa desde histórico climático."""
    columns = ["Fecha", "DD día", "Temp media ºC", "Horas con dato"]
    if history is None or history.empty or "fecha_hora" not in history.columns or "temp_media" not in history.columns:
        return pd.DataFrame(columns=columns)

    df = history[["fecha_hora", "temp_media"]].copy()
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"], errors="coerce")
    df["temp_media"] = pd.to_numeric(df["temp_media"], errors="coerce")
    df = df.dropna(subset=["fecha_hora", "temp_media"])
    if df.empty:
        return pd.DataFrame(columns=columns)

    if upper_temp is not None:
        df["temp_modelo"] = df["temp_media"].clip(upper=float(upper_temp))
    else:
        df["temp_modelo"] = df["temp_media"]

    df["Fecha"] = df["fecha_hora"].dt.date

    if method == "diario":
        daily = df.groupby("Fecha", as_index=False).agg(
            **{
                "Temp media ºC": ("temp_modelo", "mean"),
                "Horas con dato": ("temp_modelo", "count"),
            }
        )
        daily["DD día"] = (daily["Temp media ºC"] - float(base_temp)).clip(lower=0)
    else:
        # Datos horarios: cada hora aporta max(0, T-base)/24.
        df["DD hora"] = (df["temp_modelo"] - float(base_temp)).clip(lower=0) / 24.0
        daily = df.groupby("Fecha", as_index=False).agg(
            **{
                "DD día": ("DD hora", "sum"),
                "Temp media ºC": ("temp_modelo", "mean"),
                "Horas con dato": ("temp_modelo", "count"),
            }
        )

    daily["Fecha"] = pd.to_datetime(daily["Fecha"])
    daily["DD día"] = pd.to_numeric(daily["DD día"], errors="coerce").fillna(0).round(2)
    daily["Temp media ºC"] = pd.to_numeric(daily["Temp media ºC"], errors="coerce").round(2)
    return daily.sort_values("Fecha").reset_index(drop=True)


def carpocapsa_date_for_dd(daily_dd, biofix_date, target_dd):
    if daily_dd is None or daily_dd.empty or pd.isna(biofix_date):
        return pd.NaT, np.nan
    data = daily_dd[daily_dd["Fecha"] >= pd.Timestamp(biofix_date)].copy()
    if data.empty:
        return pd.NaT, np.nan
    data["DD acumulados"] = data["DD día"].cumsum()
    reached = data[data["DD acumulados"] >= float(target_dd)]
    current = float(data["DD acumulados"].iloc[-1]) if not data.empty else np.nan
    if reached.empty:
        return pd.NaT, current
    return pd.Timestamp(reached.iloc[0]["Fecha"]), current


def carpocapsa_estimated_date_for_dd(daily_dd, biofix_date, target_dd):
    date_real, current = carpocapsa_date_for_dd(daily_dd, biofix_date, target_dd)
    if pd.notna(date_real):
        return date_real, "Real"
    if daily_dd is None or daily_dd.empty or pd.isna(current):
        return pd.NaT, "Sin estimación"

    last_days = daily_dd.tail(7)
    avg_dd = float(pd.to_numeric(last_days["DD día"], errors="coerce").mean()) if not last_days.empty else np.nan
    if pd.isna(avg_dd) or avg_dd <= 0:
        return pd.NaT, "Sin estimación"
    remaining = float(target_dd) - float(current)
    if remaining <= 0:
        return daily_dd["Fecha"].max(), "Real"
    estimated = pd.Timestamp(daily_dd["Fecha"].max()) + pd.Timedelta(days=int(np.ceil(remaining / avg_dd)))
    return estimated, "Estimada"


def carpocapsa_status_from_dd(current_dd, recent_captures_per_day=0, rain_since_treatment=np.nan):
    if pd.isna(current_dd):
        return "Sin dato", "Sin grados-día suficientes", "Completar histórico climático o fijar biofix."

    dd = float(current_dd)
    pressure = float(recent_captures_per_day or 0)

    if dd < 70:
        return "Seguimiento", "Antes de ventana", "Revisar trampas semanalmente y confirmar biofix si hay repunte."
    if dd < 90:
        return "Preparar", "90 DD próximo", "Preparar intervención si continúan capturas o existe foco histórico."
    if dd <= 140:
        action = "Ventana activa 90–140 DD: mantener cobertura sobre fruta si hay capturas recientes."
        if pressure >= 2:
            action = "TRATAR/REFORZAR HOY: ventana activa y capturas recientes relevantes."
        return "Ventana activa", "90–140 DD", action
    if dd <= 300:
        if pressure >= 2:
            return "Vigilancia alta", "250–300 DD / vuelo continuo", "Refuerzo si capturas >2 machos/trampa/día o si hubo lavado de tratamiento."
        return "Vigilancia", "Post-ventana inicial", "Seguir capturas y preparar siguiente ola si repunta el vuelo."
    if dd <= 540:
        return "Pico 1ª generación", "460–540 DD", "Revisar daños y cobertura. Considerar tratamiento fuerte si presión alta."
    if dd <= 800:
        return "Verificación", "~500 DD superados", "Verificar eficacia de 1ª generación y muestrear fruto."
    if dd < 1100:
        return "Seguimiento 2ª gen.", "Entre generaciones", "Mantener trampas, bordes y revisión de daños."
    if dd <= 1300:
        return "Pico 2ª generación", "~1200 DD", "Riesgo de 2ª generación: valorar cobertura si hay capturas o daño."
    return "Cierre/seguimiento", ">1200 DD", "Seguimiento final, evaluación de daños y planificación de próxima campaña."



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

def carpocapsa_build_status_table(history, traps_df, biofix_df, base_temp=10.0, upper_temp=31.1, method="horario"):
    daily_dd = carpocapsa_daily_degree_days(history, base_temp=base_temp, upper_temp=upper_temp, method=method)
    traps = carpocapsa_prepare_traps_df(traps_df)
    biofix = carpocapsa_prepare_biofix_df(biofix_df)

    rows = []
    active = biofix[biofix["Activo"] == True].copy() if not biofix.empty else pd.DataFrame()
    if active.empty:
        return pd.DataFrame(), daily_dd

    for _, row in active.iterrows():
        zona = str(row.get("Campo/Zona", "") or "").strip()
        bdate = pd.to_datetime(row.get("Fecha biofix"), errors="coerce")
        if not zona or pd.isna(bdate):
            continue

        if traps.empty:
            recent_pressure = 0.0
            recent_captures = 0
            last_trap_date = pd.NaT
        else:
            t = traps[traps["Campo/Zona"].astype(str).str.strip() == zona].copy()
            if t.empty:
                t = traps[traps["Campo/Zona"].astype(str).str.strip().str.lower().isin(["general", "finca", "toda la finca"])].copy()
            last_trap_date = t["Fecha"].max() if not t.empty and t["Fecha"].notna().any() else pd.NaT
            recent = t[t["Fecha"] >= (pd.Timestamp.today().normalize() - pd.Timedelta(days=14))].copy() if not t.empty else pd.DataFrame()
            if recent.empty and not t.empty:
                recent = t.sort_values("Fecha").tail(2)
            recent_captures = int(pd.to_numeric(recent.get("Capturas machos", pd.Series(dtype=float)), errors="coerce").sum()) if not recent.empty else 0
            recent_pressure = float(pd.to_numeric(recent.get("Capturas/trampa/día", pd.Series(dtype=float)), errors="coerce").max()) if not recent.empty else 0.0

        _, current_dd = carpocapsa_date_for_dd(daily_dd, bdate, 90)
        state, window, action = carpocapsa_status_from_dd(current_dd, recent_pressure)

        target_info = {}
        for target in [90, 110, 140, 250, 300, 460, 500, 540, 1200]:
            d_est, kind = carpocapsa_estimated_date_for_dd(daily_dd, bdate, target)
            target_info[f"{target} DD"] = d_est.strftime("%d/%m/%Y") if pd.notna(d_est) else ""
            target_info[f"{target} DD tipo"] = kind

        rows.append({
            "Campo/Zona": zona,
            "Biofix": bdate.strftime("%d/%m/%Y"),
            "DD acumulados": round(float(current_dd), 1) if pd.notna(current_dd) else np.nan,
            "Estado": state,
            "Ventana": window,
            "Capturas recientes": recent_captures,
            "Máx capturas/trampa/día": round(recent_pressure, 2),
            "Última lectura trampa": last_trap_date.strftime("%d/%m/%Y") if pd.notna(last_trap_date) else "",
            "Acción orientativa": action,
            **target_info,
        })

    return pd.DataFrame(rows), daily_dd


def carpocapsa_dd_at_treatment(traps_df, treatments_df, biofix_df, daily_dd, campaign_year, threshold=5, min_days_gap=5):
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

    # ── Preparar biofix: mapa campo → fecha ───────────────────────────────────
    biofix_map = {}
    if biofix_df is not None and not biofix_df.empty and "Fecha biofix" in biofix_df.columns:
        bf = biofix_df.copy()
        if "Campaña" in bf.columns:
            bf = bf[pd.to_numeric(bf["Campaña"], errors="coerce") == int(campaign_year)]
        if "Activo" in bf.columns:
            bf = bf[bf["Activo"].fillna(True).astype(bool)]
        for _, row in bf.iterrows():
            zona = str(row.get("Campo/Zona", "General") or "General").strip()
            bdate = pd.to_datetime(row["Fecha biofix"], errors="coerce")
            if pd.notna(bdate):
                biofix_map[zona] = bdate

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
            biofix_date = biofix_map.get(campo_str) or biofix_map.get("General") or high_date

            next_treatment_date    = None
            next_treatment_product = "Sin tratamiento registrado"
            dd_lectura_a_trat      = np.nan
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

            rows.append({
                "Campo/Zona":                     campo_str,
                "Campaña":                        int(campaign_year),
                f"Lectura ≥{threshold} capturas": high_date,
                "Capturas":                       high_capts,
                "Biofix":                         biofix_date.strftime("%d/%m/%Y") if hasattr(biofix_date, "strftime") else str(biofix_date),
                "Fecha tratamiento":              next_treatment_date if next_treatment_date else "—",
                "Días hasta trat.":               dias_hasta_trat,
                "DD entre lectura y trat.":       dd_lectura_a_trat,
                "Producto":                       next_treatment_product,
            })

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out = out.sort_values(["Campo/Zona", f"Lectura ≥{threshold} capturas"]).reset_index(drop=True)
    return out

def carpocapsa_tab(history):
    st.subheader("Carpocapsa · Cydia pomonella")

    st.info(
        "Módulo inicial para seguimiento de carpocapsa en manzano: capturas, biofix, grados-día y ventanas de eclosión. "
        "Está pensado para validar el flujo antes de guardar datos en Supabase."
    )

    st.warning(
        "Uso orientativo. Antes de aplicar cualquier producto, verificar registro oficial, etiqueta, dosis, plazo de seguridad, "
        "número máximo de aplicaciones y normativa vigente."
    )

    if "carpocapsa_traps_df" not in st.session_state:  # Ensure traps dataframe is present before processing data
        st.session_state.carpocapsa_traps_df = carpocapsa_default_traps_df()
    if "carpocapsa_biofix_df" not in st.session_state:
        st.session_state.carpocapsa_biofix_df = carpocapsa_default_biofix_df()
    if "carpocapsa_damage_df" not in st.session_state:
        st.session_state.carpocapsa_damage_df = carpocapsa_default_damage_df()

    st.markdown("### 0. Importar / exportar datos de carpocapsa")
    with st.expander("Importar Excel de carpocapsa", expanded=True):
        st.caption(
            "Puedes subir el Excel convertido con hojas **Capturas_App**, **Biofix_2025** y opcionalmente **Danos_2025**. "
            "La app cargará esos datos en la sesión actual."
        )
        import_file = st.file_uploader(
            "Subir Excel Carpocapsa (.xlsx)",
            type=["xlsx", "xlsm"],
            key="carpocapsa_import_excel_v894",
        )
        ic1, ic2 = st.columns(2)
        with ic1:
            if import_file is not None and st.button("Importar Excel en la sesión", type="primary", use_container_width=True):
                imported, messages = carpocapsa_import_workbook(import_file)
                imported_campaign = imported.get("detected_campaign")
                if "traps" in imported:
                    imported_campaign = imported_campaign or carpocapsa_detect_year_from_df(imported["traps"], "Fecha")
                    prev = st.session_state.carpocapsa_traps_df.copy()
                    if imported_campaign and not prev.empty and "Campaña" in prev.columns:
                        prev = prev.dropna(subset=["Campaña"])
                        prev = prev[pd.to_numeric(prev["Campaña"], errors="coerce") != int(imported_campaign)]
                    st.session_state.carpocapsa_traps_df = pd.concat([prev, imported["traps"]], ignore_index=True)
                if "biofix" in imported:
                    prev = st.session_state.carpocapsa_biofix_df.copy()
                    if imported_campaign and not prev.empty and "Campaña" in prev.columns:
                        prev = prev[pd.to_numeric(prev["Campaña"], errors="coerce") != int(imported_campaign)]
                    st.session_state.carpocapsa_biofix_df = pd.concat([prev, imported["biofix"]], ignore_index=True)
                if "damage" in imported:
                    prev = st.session_state.carpocapsa_damage_df.copy()
                    if imported_campaign and not prev.empty and "Campaña" in prev.columns:
                        prev = prev[pd.to_numeric(prev["Campaña"], errors="coerce") != int(imported_campaign)]
                    st.session_state.carpocapsa_damage_df = pd.concat([prev, imported["damage"]], ignore_index=True)
                for m in messages:
                    st.write(f"- {m}")
                if imported:
                    st.success("Datos de carpocapsa importados en la sesión.")
                    # Guardado automático del snapshot en Supabase (sin pasos manuales)
                    autosave_carpocapsa_to_supabase()
                    st.rerun()
                else:
                    st.error("No se importaron datos. Revisa que el Excel tenga la hoja Capturas_App.")

        with ic2:
            st.download_button(
                "Descargar plantilla Excel vacía",
                data=carpocapsa_export_template_excel(),
                file_name="plantilla_carpocapsa_app.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        if not st.session_state.carpocapsa_traps_df.empty:
            st.success(
                f"Sesión actual: {len(st.session_state.carpocapsa_traps_df)} capturas, "
                f"{len(st.session_state.carpocapsa_biofix_df)} biofix y "
                f"{len(st.session_state.carpocapsa_damage_df)} registros de daño."
            )

    with st.expander("☁️ Guardar / Cargar histórico carpocapsa en Supabase", expanded=False):
        st.caption(
            "Guarda todos los años en Supabase para no perderlos entre sesiones. "
            "Puedes importar varios Excels (uno por año) y luego guardar el conjunto completo. "
            "Al cargar, se recuperan todos los años guardados."
        )

        sb1, sb2 = st.columns(2)

        with sb1:
            if st.button("⬆️ Guardar snapshot carpocapsa en Supabase", type="primary", use_container_width=True):
                ok, msg = upload_carpocapsa_snapshot_to_supabase(
                    st.session_state.carpocapsa_traps_df,
                    st.session_state.carpocapsa_biofix_df,
                    st.session_state.carpocapsa_damage_df,
                )
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

        with sb2:
            if st.button("⬇️ Cargar snapshot carpocapsa desde Supabase", use_container_width=True):
                traps, biofix, damage, msg = load_carpocapsa_snapshot_from_supabase()
                if traps is not None:
                    st.session_state.carpocapsa_traps_df = traps
                    st.session_state.carpocapsa_biofix_df = biofix if biofix is not None else carpocapsa_default_biofix_df()
                    st.session_state.carpocapsa_damage_df = damage if damage is not None else carpocapsa_default_damage_df()
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)

        # Resumen de campañas en sesión
        traps_df = st.session_state.carpocapsa_traps_df
        if not traps_df.empty and "Campaña" in traps_df.columns:
            years = sorted(pd.to_numeric(traps_df["Campaña"], errors="coerce").dropna().astype(int).unique())
            st.info(f"Campañas en sesión: {', '.join(str(y) for y in years)}")

    with st.expander("Guía rápida de interpretación", expanded=False):
        st.markdown(
            """
            - **Biofix:** primera captura/repunte claro confirmado por el técnico.
            - **90–110 DD:** inicio operativo de eclosión. Preparar o realizar primer pase si hay presión.
            - **110–140 DD:** cola de eclosión/refuerzo si persisten capturas o hubo lavado.
            - **250–300 DD:** vuelo continuo; vigilar si capturas >2 machos/trampa/día.
            - **460–540 DD:** pico de eclosión de primera generación.
            - **~500 DD:** punto de verificación del control de primera generación.
            - **~1200 DD:** pico orientativo de segunda generación.
            """
        )

    st.markdown("### 1. Configuración de campaña")
    available_campaigns = carpocapsa_available_campaigns(
        st.session_state.carpocapsa_traps_df,
        st.session_state.carpocapsa_biofix_df,
        st.session_state.carpocapsa_damage_df,
    )
    default_year = int(pd.Timestamp.today().year)
    default_index = available_campaigns.index(default_year) if default_year in available_campaigns else len(available_campaigns) - 1
    c0, c1, c2, c3, c4 = st.columns([1.1, 1, 1, 1, 1.2])
    with c0:
        campaign_year = st.selectbox(
            "Campaña a visualizar",
            options=available_campaigns,
            index=default_index,
            key="carpocapsa_campaign_selector_v897",
            help="Filtra capturas, biofix, daños e histórico climático por año de campaña.",
        )
    with c1:
        base_temp = st.number_input("Umbral inferior ºC", min_value=0.0, max_value=20.0, value=10.0, step=0.1)
    with c2:
        use_upper = st.checkbox("Aplicar umbral superior", value=True)
        upper_temp = st.number_input("Umbral superior ºC", min_value=20.0, max_value=40.0, value=31.1, step=0.1, disabled=not use_upper)
    with c3:
        method_label = st.selectbox("Método DD", ["Horario con datos CSV", "Diario simple"], index=0)
    with c4:
        filter_climate = st.checkbox("Usar solo clima de la campaña", value=True, help="Recomendado para comparar capturas 2025 con clima 2025 y capturas 2026 con clima 2026.")
    method = "horario" if method_label.startswith("Horario") else "diario"
    upper_value = float(upper_temp) if use_upper else None

    climate_msg = carpocapsa_history_campaign_message(history, campaign_year)
    if climate_msg:
        st.warning(climate_msg)
    history_campaign = carpocapsa_filter_history_campaign(history, campaign_year) if filter_climate else history

    st.markdown("### 2. Capturas de trampas")
    st.caption(f"Introduce o revisa las lecturas de la campaña {campaign_year}. El campo/zona debe coincidir con el biofix si quieres cálculo por zona.")
    traps_base = carpocapsa_filter_campaign(st.session_state.carpocapsa_traps_df, campaign_year).copy()
    traps_edit = st.data_editor(
        traps_base,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="carpocapsa_traps_editor_v893",
        column_config={
            "Fecha": st.column_config.DateColumn("Fecha"),
            "Capturas machos": st.column_config.NumberColumn("Capturas machos", min_value=0, step=1),
            "Días desde lectura anterior": st.column_config.NumberColumn("Días desde lectura anterior", min_value=1, step=1),
            "Tipo trampa": st.column_config.SelectboxColumn(
                "Tipo trampa",
                options=["Feromona", "Combo CM-DA", "Otra"],
            ),
        },
    )
    if st.button("Guardar capturas en sesión", use_container_width=True):
        prepared = carpocapsa_prepare_traps_df(traps_edit)[CARPOCAPSA_DEFAULT_TRAP_COLUMNS]
        prepared["Campaña"] = int(campaign_year)
        previous = st.session_state.carpocapsa_traps_df.copy()
        previous = previous[pd.to_numeric(previous.get("Campaña", pd.Series(dtype=float)), errors="coerce") != int(campaign_year)] if not previous.empty and "Campaña" in previous.columns else pd.DataFrame(columns=CARPOCAPSA_DEFAULT_TRAP_COLUMNS)
        st.session_state.carpocapsa_traps_df = pd.concat([previous, prepared], ignore_index=True)
        st.success(f"Capturas de {campaign_year} guardadas en sesión.")
        # Guardado automático del snapshot en Supabase (sin pasos manuales)
        autosave_carpocapsa_to_supabase()
        st.rerun()

    traps_prepared = carpocapsa_prepare_traps_df(traps_edit)
    if not traps_prepared.empty:
        with st.expander("Resumen de capturas", expanded=True):
            st.dataframe(traps_prepared, use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar capturas carpocapsa CSV",
                data=traps_prepared.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"carpocapsa_capturas_{campaign_year}.csv",
                mime="text/csv",
            )

    # Biofix ya no se usa manualmente — queda en session_state para compatibilidad
    biofix_edit = st.session_state.carpocapsa_biofix_df.copy()

    st.markdown("### 3. Evolución de capturas totales")
    st.caption("Suma de capturas de todas las trampas por fecha de lectura. Permite identificar picos de vuelo y generaciones.")

    traps_campaign = carpocapsa_filter_campaign(traps_edit, campaign_year).copy() if traps_edit is not None and not traps_edit.empty else pd.DataFrame()

    if traps_campaign.empty:
        st.info("Sube el Excel de carpocapsa para ver la evolución de capturas.")
    else:
        traps_campaign["Fecha"] = pd.to_datetime(traps_campaign.get("Fecha", traps_campaign.get("fecha", pd.Series())), errors="coerce")
        traps_campaign["Capturas machos"] = pd.to_numeric(traps_campaign.get("Capturas machos", traps_campaign.get("capturas_machos", pd.Series())), errors="coerce").fillna(0)
        traps_campaign = traps_campaign.dropna(subset=["Fecha"])

        # Suma total de capturas por fecha
        capturas_total = traps_campaign.groupby("Fecha", as_index=False)["Capturas machos"].sum()
        capturas_total = capturas_total.sort_values("Fecha")
        capturas_total["Fecha_str"] = capturas_total["Fecha"].dt.strftime("%d/%m")

        # Capturas por campo (para gráfica desglosada)
        capturas_campo = traps_campaign.groupby(["Fecha", "Campo/Zona"], as_index=False)["Capturas machos"].sum() if "Campo/Zona" in traps_campaign.columns else pd.DataFrame()

        tab_total, tab_campo = st.tabs(["Total finca", "Por campo"])

        with tab_total:
            import altair as alt
            thresh_val = int(st.session_state.get("carp_capture_threshold", 3))
            n_campos = len(traps_campaign["Campo/Zona"].unique()) if "Campo/Zona" in traps_campaign.columns else 1
            capturas_total["Fecha_dt"] = pd.to_datetime(capturas_total["Fecha"])
            bars = alt.Chart(capturas_total).mark_bar(color="#e05c5c").encode(
                x=alt.X("Fecha_dt:T", title="Fecha lectura", axis=alt.Axis(format="%d/%m", labelAngle=-45)),
                y=alt.Y("Capturas machos:Q", title="Capturas totales"),
                tooltip=[alt.Tooltip("Fecha_dt:T", title="Fecha", format="%d/%m/%Y"),
                         alt.Tooltip("Capturas machos:Q", title="Total capturas")],
            )
            umbral_df = pd.DataFrame({"y": [thresh_val * n_campos]})
            umbral_line = alt.Chart(umbral_df).mark_rule(color="orange", strokeDash=[6,3]).encode(y="y:Q")
            st.altair_chart((bars + umbral_line).properties(height=350, title=f"Capturas totales campaña {campaign_year}"), use_container_width=True)
            st.dataframe(capturas_total[["Fecha_str", "Capturas machos"]].rename(columns={"Fecha_str": "Fecha", "Capturas machos": "Total capturas"}), use_container_width=True, hide_index=True)

        with tab_campo:
            if capturas_campo.empty:
                st.info("No hay datos por campo.")
            else:
                campos_list = sorted(capturas_campo["Campo/Zona"].unique())
                campos_sel = st.multiselect("Campos a mostrar", campos_list, default=campos_list[:min(5, len(campos_list))], key="carp_campos_grafica")
                if campos_sel:
                    import altair as alt
                    df_plot = capturas_campo[capturas_campo["Campo/Zona"].isin(campos_sel)].copy()
                    df_plot["Fecha_dt"] = pd.to_datetime(df_plot["Fecha"])
                    chart2 = alt.Chart(df_plot).mark_line(point=True).encode(
                        x=alt.X("Fecha_dt:T", title="Fecha", axis=alt.Axis(format="%d/%m", labelAngle=-45)),
                        y=alt.Y("Capturas machos:Q", title="Capturas"),
                        color=alt.Color("Campo/Zona:N", title="Campo"),
                        tooltip=[alt.Tooltip("Fecha_dt:T", title="Fecha", format="%d/%m/%Y"),
                                 alt.Tooltip("Campo/Zona:N", title="Campo"),
                                 alt.Tooltip("Capturas machos:Q", title="Capturas")],
                    ).properties(height=400, title=f"Capturas por campo — campaña {campaign_year}")
                    st.altair_chart(chart2, use_container_width=True)

    st.markdown("### 4. Ventanas de tratamiento por campo")
    st.caption(
        "Cada lectura de trampa que supere el umbral configurable abre una ventana de 90 DD. "
        "Pueden coexistir varias ventanas activas por campo a lo largo de la temporada."
    )

    if history_campaign is None or history_campaign.empty:
        st.info("Carga primero el histórico climático de la campaña seleccionada para calcular grados-día.")
    else:
        # Configuración del umbral
        col_thresh1, col_thresh2, col_thresh3 = st.columns(3)
        with col_thresh1:
            capture_threshold = st.number_input(
                "Umbral de capturas (≥ N abre ventana)",
                min_value=1, max_value=50, value=3, step=1,
                key="carp_capture_threshold",
                help="Número mínimo de capturas totales en una lectura para abrir una ventana de tratamiento."
            )
        with col_thresh2:
            dd_active_start = st.number_input(
                "DD inicio ventana activa",
                min_value=50, max_value=150, value=80, step=5,
                key="carp_dd_start",
                help="A 80 DD se abre el aviso de tratar: da margen para repartir los "
                     "tratamientos por campos antes de la eclosión real (~90 DD). El Bt "
                     "aplicado a 80 DD sigue activo en la eclosión.",
            )
        with col_thresh3:
            dd_active_end = st.number_input(
                "DD fin ventana activa",
                min_value=100, max_value=200, value=130, step=5,
                key="carp_dd_end",
            )

        activities_for_cross = st.session_state.get("activities_df", pd.DataFrame(columns=ACTIVITY_COLUMNS))

        multi_df = carpocapsa_build_multi_windows(
            traps_edit,
            history_campaign,
            base_temp=base_temp,
            upper_temp=upper_value,
            capture_threshold=capture_threshold,
            dd_active_start=dd_active_start,
            dd_active_end=dd_active_end,
            activities_df=activities_for_cross,
            campaign_year=campaign_year,
        )

        if multi_df.empty:
            st.warning(
                f"No hay lecturas con capturas ≥ {capture_threshold} en los datos cargados. "
                "Sube el Excel de carpocapsa con las lecturas de esta campaña."
            )
        else:
            # Métricas resumen
            # "reentrada" = ventanas ⚠️ Tratar — reentrada: Xd (tratadas pero bloqueadas)
            n_activas   = len(multi_df[multi_df["Estado"].str.contains("Activa|reentrada|pase", na=False)])
            n_espera    = len(multi_df[multi_df["Estado"].str.contains("espera",   na=False)])
            n_cerradas  = len(multi_df[multi_df["Estado"].str.contains("Cerrada",  na=False)])
            n_tratadas  = len(multi_df[multi_df["Estado"].str.contains("Tratado",  na=False)])

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("🔴 Pendientes de tratar", n_activas)
            mc2.metric("⏳ En espera",             n_espera)
            mc3.metric("✅ Cubiertas / tratadas",  n_tratadas)
            mc4.metric("🔒 Cerradas por DD",       n_cerradas)

            # ── Aviso PARPADEANTE: ventanas a punto de cerrarse sin tratar ─────
            _peligro = multi_df[multi_df["Estado"].astype(str).str.contains("cierra en", na=False)]
            if not _peligro.empty:
                _campos_pel = ", ".join(_peligro["Campo/Zona"].astype(str).unique())
                st.markdown(
                    "<style>@keyframes fgCarpoBlink{0%,100%{opacity:1}50%{opacity:.35}}</style>"
                    f"<div style='background:#c62828;color:#fff;padding:10px 14px;"
                    f"border-radius:8px;font-weight:700;margin:4px 0 12px 0;"
                    f"animation:fgCarpoBlink 1s infinite;'>"
                    f"⚠️ PELIGRO — {len(_peligro)} ventana(s) a punto de pasarse de DD "
                    f"SIN tratar: {_campos_pel}. Última oportunidad de tratar.</div>",
                    unsafe_allow_html=True,
                )

            # Obtener todos los estados reales del DataFrame para el filtro dinámico
            _estados_disponibles = sorted(multi_df["Estado"].dropna().unique().tolist())
            _default_estados = [e for e in _estados_disponibles
                                if "Activa" in e or "espera" in e or "Tratado" in e
                                or "reentrada" in e or "pase" in e]

            # Filtro de estado
            estado_filter = st.multiselect(
                "Filtrar por estado",
                _estados_disponibles,
                default=_default_estados,
                key="carp_estado_filter",
            )
            if estado_filter:
                df_show = multi_df[multi_df["Estado"].isin(estado_filter)]
            else:
                df_show = multi_df

            # Ocultar columnas internas (prefijo _)
            _display_cols = [c for c in df_show.columns if not c.startswith("_")]

            # ── Colores por fila según estado ──────────────────────────────────
            # Verde   : Tratado — cerrada (acción completada)
            # Rojo    : Activa que CIERRA en ≤3d sin tratar (PELIGRO, última opción)
            # Naranja : Activa con margen (precaución, ventana abierta)
            # Gris    : Cerrada por DD sin tratar (se pasó)
            # Blanco  : En espera (aún no activa)
            def _carpo_row_color(row):
                try:
                    e = str(row.get("Estado", ""))
                except Exception:
                    e = ""
                if "Tratado" in e:
                    bg = "#d6f0da"   # verde claro (tratado/cubierto)
                elif "cierra en" in e:
                    bg = "#ffcccc"   # rojo claro (PELIGRO: a punto de pasarse sin tratar)
                elif "Activa" in e:
                    bg = "#ffe0b3"   # naranja claro (precaución: ventana abierta)
                elif "Cerrada" in e:
                    bg = "#e8e8e8"   # gris (cerrada por DD sin tratar)
                else:
                    bg = ""          # blanco (en espera)
                return [f"background-color: {bg}" if bg else "" for _ in row]

            _df_vis = df_show[_display_cols]
            try:
                _styled = _df_vis.style.apply(_carpo_row_color, axis=1)
                st.dataframe(_styled, use_container_width=True, hide_index=True)
            except Exception:
                st.dataframe(_df_vis, use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar ventanas carpocapsa CSV",
                data=multi_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"carpocapsa_ventanas_{campaign_year}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        # Grados-día diarios
        daily_dd = carpocapsa_daily_degree_days(
            history_campaign, base_temp=base_temp, upper_temp=upper_value, method=method
        )
        with st.expander("Grados-día diarios usados por el modelo", expanded=False):
            if not daily_dd.empty:
                st.dataframe(daily_dd, use_container_width=True, hide_index=True)
                st.download_button(
                    "Descargar grados-día diarios",
                    data=daily_dd.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"carpocapsa_grados_dia_{campaign_year}.csv",
                    mime="text/csv",
                )

    st.markdown("### 5. Tratamientos de carpocapsa desde Agroptima")
    st.caption(
        "La app toma estos tratamientos del histórico importado en la pestaña Actuaciones. "
        "Detecta productos o comentarios relacionados con carpocapsa, por ejemplo Bactur."
    )

    rain_days_limit = st.number_input(
        "Días post-tratamiento para acumular lluvia",
        min_value=1, max_value=14, value=3, step=1,
        key="carp_rain_days_limit",
        help="Periodo crítico: la larva tarda ~3 días desde la eclosión del huevo hasta penetrar el fruto. "
             "La lluvia en este periodo puede lavar el producto y reducir su eficacia.",
    )

    carp_treatments = carpocapsa_treatments_from_activities(
        st.session_state.get("activities_df", pd.DataFrame(columns=ACTIVITY_COLUMNS)),
        campaign_year,
        history_campaign,
        rain_days_limit=int(rain_days_limit),
    )
    if carp_treatments.empty:
        st.info(
            "No se han detectado tratamientos de carpocapsa en Actuaciones para esta campaña. "
            "Cuando exportes Agroptima, incluye también Bactur u otros productos anti-carpocapsa."
        )
    else:
        cta1, cta2, cta3 = st.columns(3)
        cta1.metric("Tratamientos carpocapsa", len(carp_treatments))
        cta2.metric("Último tratamiento", str(carp_treatments.iloc[0]["Fecha"]))
        rain_col = f"Lluvia {int(rain_days_limit)}d post-tratamiento mm"
        if rain_col in carp_treatments.columns:
            last_rain = carp_treatments.iloc[0][rain_col]
            cta3.metric(f"Lluvia {int(rain_days_limit)}d tras último trat.", "-" if pd.isna(last_rain) else f"{last_rain:.1f} mm")

        # Ocultar columnas vacías para presentación más limpia
        cols_show = [c for c in carp_treatments.columns
                     if not (carp_treatments[c].astype(str).str.strip().isin(["", "nan", "None"]).all())]
        st.dataframe(carp_treatments[cols_show], use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar tratamientos carpocapsa CSV",
            data=carp_treatments.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"carpocapsa_tratamientos_{campaign_year}.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.caption(
            "Aviso: la detección se basa en palabras clave en Producto/Trabajo/Comentarios. "
            "Revisa siempre que el tratamiento esté correctamente clasificado."
        )

    st.markdown("### 6. DD acumulados en el momento del tratamiento")
    st.caption(
        "Para cada campo, muestra la última lectura de trampa con capturas ≥ al umbral configurado, "
        "el siguiente tratamiento registrado en Agroptima y los grados-día acumulados desde biofix "
        "en ese momento. Útil para evaluar si se trató a tiempo o tarde respecto a la presión real."
    )

    if history_campaign is None or history_campaign.empty:
        st.info("Carga primero el histórico climático para poder calcular grados-día.")
    else:
        s6c1, s6c2, s6c3 = st.columns([1, 1, 2])
        with s6c1:
            threshold_options = [1, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20]
            dd_threshold = st.selectbox(
                "Umbral mínimo de capturas",
                options=threshold_options,
                index=threshold_options.index(5),
                key="dd_treatment_threshold_v2",
                help="Se busca cada lectura con capturas ≥ este valor.",
            )
        with s6c2:
            min_days_gap = st.number_input(
                "Días mínimos de reacción",
                min_value=1, max_value=14, value=5, step=1,
                key="dd_min_days_gap",
                help=(
                    "Tratamientos aplicados dentro de este número de días tras la lectura "
                    "se consideran pre-planificados (parte del ciclo rutinario) y se saltan. "
                    "El primer tratamiento a partir de este umbral es el que se muestra. "
                    "Valor recomendado: 5 días."
                ),
            )
        with s6c3:
            st.caption(
                f"Umbral ≥{dd_threshold} capturas · Saltar tratamientos en los primeros {min_days_gap} días "
                f"(pre-planificados) · Rango esperado de DD: 90–140."
            )

        traps_for_analysis = carpocapsa_filter_campaign(st.session_state.carpocapsa_traps_df, campaign_year)
        biofix_for_analysis = carpocapsa_filter_campaign(st.session_state.carpocapsa_biofix_df, campaign_year)

        daily_dd_for_analysis = carpocapsa_daily_degree_days(
            history_campaign, base_temp=base_temp, upper_temp=upper_value, method=method
        )

        dd_treat_df = carpocapsa_dd_at_treatment(
            traps_for_analysis,
            carp_treatments if not carp_treatments.empty else None,
            biofix_for_analysis,
            daily_dd_for_analysis,
            campaign_year,
            threshold=int(dd_threshold),
            min_days_gap=int(min_days_gap),
        )

        if dd_treat_df.empty:
            st.info(
                f"No se encontraron lecturas con ≥{dd_threshold} capturas en la campaña {campaign_year}. "
                f"Prueba a bajar el umbral o comprueba que tienes capturas guardadas en sesión."
            )
        else:
            st.dataframe(dd_treat_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar análisis DD-tratamiento CSV",
                data=dd_treat_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"carpocapsa_dd_tratamiento_{campaign_year}.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.caption(
                f"💡 'DD entre lectura y trat.' = DD acumulados desde la lectura de presión hasta el tratamiento de carpocapsa. "
                f"Tratamientos dentro de los primeros {min_days_gap} días se consideran pre-planificados y se omiten. "
                f"Rango esperado: 90–140 DD."
            )

    st.caption("Registra muestreos posteriores a tratamiento o revisiones de foco. Objetivo orientativo: daño <1%.")
    damage_edit = st.data_editor(
        carpocapsa_filter_campaign(st.session_state.carpocapsa_damage_df, campaign_year).copy(),
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="carpocapsa_damage_editor_v893",
        column_config={
            "Fecha": st.column_config.DateColumn("Fecha"),
            "Frutos revisados": st.column_config.NumberColumn("Frutos revisados", min_value=0, step=1),
            "Frutos dañados": st.column_config.NumberColumn("Frutos dañados", min_value=0, step=1),
        },
    )
    if st.button("Guardar daños en sesión", use_container_width=True):
        prepared = carpocapsa_prepare_damage_df(damage_edit)[CARPOCAPSA_DEFAULT_DAMAGE_COLUMNS]
        prepared["Campaña"] = int(campaign_year)
        previous = st.session_state.carpocapsa_damage_df.copy()
        previous = previous[pd.to_numeric(previous.get("Campaña", pd.Series(dtype=float)), errors="coerce") != int(campaign_year)] if not previous.empty and "Campaña" in previous.columns else pd.DataFrame(columns=CARPOCAPSA_DEFAULT_DAMAGE_COLUMNS)
        st.session_state.carpocapsa_damage_df = pd.concat([previous, prepared], ignore_index=True)
        st.success(f"Muestreos de daño de {campaign_year} guardados en sesión.")
        st.rerun()

    damage_prepared = carpocapsa_prepare_damage_df(damage_edit)
    if not damage_prepared.empty:
        damage_show = damage_prepared.copy()
        damage_show["Estado objetivo <1%"] = damage_show["% daño"].apply(
            lambda x: "Cumple" if pd.notna(x) and x < 1 else ("Revisar" if pd.notna(x) else "Sin dato")
        )
        st.dataframe(damage_show, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar muestreos de daño CSV",
            data=damage_show.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"carpocapsa_danos_{campaign_year}.csv",
            mime="text/csv",
        )

    with st.expander("Siguiente evolución prevista del módulo", expanded=False):
        st.markdown(
            """
            **v8.9.7 propuesta:**
            - Guardar capturas, biofix y daños en Supabase.
            - Cargar histórico de carpocapsa desde la nube.
            - Cruzar con tratamientos de Agroptima.
            - Calcular lluvia acumulada desde último tratamiento y posible lavado.
            """
        )



def settings_tab():
    st.subheader("Configuración")
    st.write("Configuración general de la sesión.")

    soil_type = st.selectbox(
        "Tipo de suelo",
        options=list(SOIL_PROFILES.keys()),
        index=2,
        key="soil_type_v60",
    )

    with st.expander("Configuración avanzada de hoja mojada", expanded=False):
        hoja_threshold = st.number_input(
            "Umbral heredado para hora húmeda simple",
            min_value=1,
            max_value=100,
            value=30,
            step=1,
            key="hoja_threshold_v60",
            help="Se mantiene por compatibilidad. El módulo sanitario usa minutos reales y eventos continuos.",
        )
        st.caption("El módulo nuevo trabaja con minutos de hoja mojada por hora y eventos continuos.")

    st.divider()
    render_treatment_catalog_manager()

    st.markdown("#### Versión")
    st.write("Finca Gallinal · App agroclimática v8.9.7")
    return soil_type, hoja_threshold



# Safety session-state initialization before main layout.
# This prevents first-load errors if Streamlit reaches the layout before the normal initialization block.
if "history_df" not in st.session_state:
    st.session_state.history_df = pd.DataFrame(columns=CANONICAL_COLUMNS)
if "last_import_errors" not in st.session_state:
    st.session_state.last_import_errors = []
if "last_import_diagnostics" not in st.session_state:
    st.session_state.last_import_diagnostics = []
if "applied_period" not in st.session_state:
    st.session_state.applied_period = None
if "phenology_df" not in st.session_state:
    st.session_state.phenology_df = pd.DataFrame(
        columns=["Campo", "Variedad", "Año", "Fase", "Inicio", "Fin", "Observaciones"]
    )
if "phenology_editor_version" not in st.session_state:
    st.session_state.phenology_editor_version = 0
if "activities_df" not in st.session_state:
    st.session_state.activities_df = pd.DataFrame(columns=ACTIVITY_COLUMNS)
if "last_activities_import_stats" not in st.session_state:
    st.session_state.last_activities_import_stats = {}
if "carpocapsa_traps_df" not in st.session_state:
    st.session_state.carpocapsa_traps_df = carpocapsa_default_traps_df()
if "carpocapsa_biofix_df" not in st.session_state:
    st.session_state.carpocapsa_biofix_df = carpocapsa_default_biofix_df()
if "carpocapsa_damage_df" not in st.session_state:
    st.session_state.carpocapsa_damage_df = carpocapsa_default_damage_df()

# ── Funciones de Supabase para Producción (necesarias antes del auto-load) ───
SUPABASE_PRODUCCION_FILE = "produccion_historica.parquet"


def produccion_storage_url():
    url, _ = get_supabase_credentials()
    return f"{url.rstrip('/')}/storage/v1/object/climate-snapshots/{SUPABASE_PRODUCCION_FILE}"


def load_produccion_from_supabase():
    if not supabase_is_configured():
        return None, "Supabase no configurado."
    headers = supabase_headers()
    headers.pop("Prefer", None)
    try:
        r = requests.get(produccion_storage_url(), headers=headers, timeout=60)
    except Exception as e:
        return None, f"Error de conexión: {e}"
    if r.status_code != 200:
        return None, "No se encontró histórico de producción en Supabase."
    try:
        df = pd.read_parquet(io.BytesIO(r.content), engine="pyarrow")
        años = sorted(df["Año"].unique())
        return df, f"Producción cargada: {len(df)} filas, años {años[0]}–{años[-1]}."
    except Exception as e:
        return None, f"Error leyendo Parquet: {e}"


# ── Funciones de Supabase para Fenología ─────────────────────────────────────
SUPABASE_PHENOLOGY_FILE = "fenologia_historica.parquet"


def phenology_storage_url():
    url, _ = get_supabase_credentials()
    return f"{url.rstrip('/')}/storage/v1/object/climate-snapshots/{SUPABASE_PHENOLOGY_FILE}"


def load_phenology_from_supabase():
    if not supabase_is_configured():
        return None, "Supabase no configurado."
    headers = supabase_headers()
    headers.pop("Prefer", None)
    try:
        r = requests.get(phenology_storage_url(), headers=headers, timeout=60)
    except Exception as e:
        return None, f"Error de conexión: {e}"
    if r.status_code != 200:
        return None, "No se encontró fenología en Supabase."
    try:
        df = pd.read_parquet(io.BytesIO(r.content), engine="pyarrow")
        return df, f"Fenología cargada: {len(df)} filas."
    except Exception as e:
        return None, f"Error leyendo Parquet: {e}"


def upload_phenology_to_supabase(df):
    if not supabase_is_configured():
        return False, "Supabase no configurado."
    if df is None or df.empty:
        return False, "No hay fenología para guardar."
    out = normalize_phenology_df(df)   # tipos estables para Parquet
    buf = io.BytesIO()
    out.to_parquet(buf, index=False, compression="snappy", engine="pyarrow")
    buf.seek(0)
    headers = supabase_headers()
    headers["Content-Type"] = "application/octet-stream"
    headers["x-upsert"] = "true"
    try:
        r = requests.post(phenology_storage_url(), headers=headers, data=buf.getvalue(), timeout=60)
    except Exception as e:
        return False, f"Error de conexión: {e}"
    if r.status_code not in (200, 201):
        return False, f"Error {r.status_code}: {r.text[:200]}"
    return True, f"Fenología guardada: {len(out)} filas."


def autosave_phenology_to_supabase():
    """Guarda automáticamente la fenología en Supabase tras editarla/importarla.
    Silencioso si Supabase no está configurado; nunca rompe la edición."""
    if not supabase_is_configured():
        return
    try:
        df = st.session_state.get("phenology_df", pd.DataFrame())
        if df is None or df.empty:
            return
        ok, msg = upload_phenology_to_supabase(df)
        if ok:
            try:
                st.toast("☁️ Fenología guardada en Supabase", icon="✅")
            except Exception:
                pass
            st.caption(f"☁️ Guardado automático en Supabase · {msg}")
        else:
            st.warning(f"⚠️ No se pudo guardar la fenología en Supabase: {msg}")
    except Exception as e:
        st.warning(f"⚠️ Error en el guardado automático de fenología: {e}")


# ── Auto-carga Supabase al arrancar (una sola vez por sesión) ─────────────────
# Carga Agroptima, Producción y Carpocapsa automáticamente si Supabase está
# configurado y los datos de sesión están vacíos.
if "autoload_supabase_done" not in st.session_state:
    st.session_state.autoload_supabase_done = False

if not st.session_state.autoload_supabase_done and supabase_is_configured():
    st.session_state.autoload_supabase_done = True

    # Histórico climático (snapshot). use_cache=False: al abrir una sesión nueva
    # forzamos la descarga del snapshot MÁS RECIENTE de Supabase (sin caché), para
    # que "abrir la app = ver lo último que guardó el informe de la mañana".
    if st.session_state.history_df.empty:
        _hist_df, _ = load_climate_snapshot_from_supabase(use_cache=False)
        if _hist_df is not None and not _hist_df.empty:
            st.session_state.history_df = _hist_df

    # Agroptima
    if st.session_state.activities_df.empty:
        _act_df, _ = load_activities_from_supabase()
        if not _act_df.empty:
            st.session_state.activities_df = _act_df

    # Producción
    if "produccion_df" not in st.session_state or st.session_state.get("produccion_df", pd.DataFrame()).empty:
        _prod_df, _ = load_produccion_from_supabase()
        if _prod_df is not None and not _prod_df.empty:
            st.session_state.produccion_df = _prod_df

    # Fenología (calendario fenológico por campo × variedad × año)
    if st.session_state.get("phenology_df", pd.DataFrame()).empty:
        _phen_df, _ = load_phenology_from_supabase()
        if _phen_df is not None and not _phen_df.empty:
            st.session_state.phenology_df = normalize_phenology_df(_phen_df)

    # Carpocapsa (capturas, biofix y daños)
    if st.session_state.carpocapsa_traps_df.empty or st.session_state.carpocapsa_biofix_df.empty:
        _t, _b, _d, _ = load_carpocapsa_snapshot_from_supabase()
        if _t is not None and not _t.empty:
            st.session_state.carpocapsa_traps_df = _t
        if _b is not None and not _b.empty:
            st.session_state.carpocapsa_biofix_df = _b
        if _d is not None and not _d.empty:
            st.session_state.carpocapsa_damage_df = _d

# ── Auto-carga predicción Sencrop al arrancar (una sola vez por sesión) ────────
# Descarga la Previsión Sencrop automáticamente si el token está disponible
# y todavía no hay datos de predicción en sesión.
if "autoload_forecast_done" not in st.session_state:
    st.session_state.autoload_forecast_done = False

if not st.session_state.autoload_forecast_done and sencrop_is_configured():
    st.session_state.autoload_forecast_done = True
    _fc_token = sencrop_get_token_from_secrets()
    if _fc_token and not st.session_state.get("forecast_df", pd.DataFrame()).shape[0]:
        _fc_df, _fc_err = sencrop_download_forecast(token=_fc_token, model="sencrop")
        if _fc_df is not None and not _fc_df.empty:
            st.session_state["forecast_df"]    = _fc_df
            st.session_state["forecast_model"] = "⭐ Previsión Sencrop"
            # Guardar token para que render_sencrop_panel lo encuentre ya cacheado
            st.session_state["sencrop_token"]  = _fc_token

# Main layout
if not _HEADLESS:
    render_top_banner()

# Default settings.
# No escribimos manualmente en claves usadas por widgets, porque Streamlit lo bloquea.
soil_type = st.session_state.get("soil_type_v60", "Franco")
hoja_threshold = st.session_state.get("hoja_threshold_v60", 30)

history = st.session_state.history_df.copy()
if not history.empty:
    history = history.sort_values("fecha_hora").reset_index(drop=True)

# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCCIÓN · Datos, Supabase y pestaña
# ═══════════════════════════════════════════════════════════════════════════════
# SUPABASE_PRODUCCION_FILE, produccion_storage_url y load_produccion_from_supabase
# están definidas antes del bloque de auto-carga.

VARIEDAD_NOMBRES = {
    "RX": "Raxao", "DT": "Durona de Tresali", "RE": "Regona",
    "DR": "De la Riega", "V": "Verdialona", "MA": "Madiedo",
    "CA": "Carrió", "CO": "Collaos", "GA": "Gallinal",
    "AMA": "Amariega", "X": "Xuanina", "Exp": "Experimental",
}

PORTAINJERTO_NOMBRES = {
    "M7": "M7", "M9": "M9", "MM109": "MM109", "MM111": "MM111", "F": "Franco",
}

CAMPO_NORMALIZAR = {
    "S 1": "Sector 1", "S 2": "Sector 2", "S 3": "Sector 3",
    "S 4": "Sector 4", "S 5": "Sector 5", "S 6": "Sector 6",
    "S 7": "Sector 7", "S7": "Sector 7", "S 8": "Sector 8",
    "S8": "Sector 8", "S 9": "Sector 9", "S 10": "Sector 10",
    "S 11": "Sector 11", "S 12": "Sector 12",
    "S 1 ": "Sector 1",
    "P. Rincón": "Piedrona Rincón",
}


def produccion_normalizar_campo(nombre):
    if not isinstance(nombre, str):
        return nombre
    nombre = nombre.strip()
    return CAMPO_NORMALIZAR.get(nombre, nombre)


def produccion_parse_excel(uploaded_file):
    """Lee el Excel de producción y devuelve un DataFrame normalizado con todos los años."""
    xls = pd.ExcelFile(uploaded_file)
    frames = []
    for sheet in xls.sheet_names:
        try:
            year = int(sheet)
        except ValueError:
            continue
        df = pd.read_excel(xls, sheet_name=sheet, header=2)
        if df.shape[1] < 8:
            continue
        df.columns = ["Campo", "Variedad", "Ha", "Portainjerto",
                      "Num_arboles", "Arboles_prod", "Pct_prod", "Kg"]
        df = df[df["Campo"] != "TOTAL"].copy()
        df = df[~df["Campo"].isin(["Sec.", "Porta injerto", None])].copy()
        df["Año"] = year
        for col in ["Ha", "Num_arboles", "Arboles_prod", "Pct_prod", "Kg"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["Kg"]).copy()
        df = df[df["Kg"] > 0].copy()
        df["Campo"] = df["Campo"].apply(produccion_normalizar_campo)
        df["Variedad"] = df["Variedad"].astype(str).str.strip()
        df["Portainjerto"] = df["Portainjerto"].astype(str).str.strip().replace("nan", "")
        df["Variedad_nombre"] = df["Variedad"].map(VARIEDAD_NOMBRES).fillna(df["Variedad"])
        df["Portainjerto_nombre"] = df["Portainjerto"].map(PORTAINJERTO_NOMBRES).fillna(df["Portainjerto"])
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def upload_produccion_to_supabase(df):
    if not supabase_is_configured():
        return False, "Supabase no configurado."
    if df is None or df.empty:
        return False, "No hay datos de producción para guardar."
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, compression="snappy", engine="pyarrow")
    buf.seek(0)
    headers = supabase_headers()
    headers["Content-Type"] = "application/octet-stream"
    headers["x-upsert"] = "true"
    try:
        r = requests.post(produccion_storage_url(), headers=headers, data=buf.getvalue(), timeout=60)
    except Exception as e:
        return False, f"Error de conexión: {e}"
    if r.status_code not in (200, 201):
        return False, f"Error {r.status_code}: {r.text[:200]}"
    años = sorted(df["Año"].unique())
    return True, f"Producción guardada: {len(df)} filas, años {años[0]}–{años[-1]}."


def autosave_produccion_to_supabase():
    """Guarda automáticamente los datos de producción en Supabase tras importar.
    Silencioso si Supabase no está configurado; nunca rompe la importación."""
    if not supabase_is_configured():
        return
    try:
        df = st.session_state.get("produccion_df", pd.DataFrame())
        if df is None or df.empty:
            return
        ok, msg = upload_produccion_to_supabase(df)
        if ok:
            try:
                st.toast("☁️ Producción guardada en Supabase", icon="✅")
            except Exception:
                pass
            st.caption(f"☁️ Guardado automático en Supabase · {msg}")
        else:
            st.warning(f"⚠️ No se pudo guardar la producción en Supabase: {msg}")
    except Exception as e:
        st.warning(f"⚠️ Error en el guardado automático de producción: {e}")


def _fmt_es_number(value, decimals):
    """Formato español: separador de miles '.', decimales ','. NaN/None → '—'.
    Las cadenas (p.ej. '—', 'Buena polinización') se devuelven tal cual."""
    if value is None:
        return "—"
    try:
        if pd.isna(value):
            return "—"
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value
    try:
        s = f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)
    # Intercambiar separadores al estilo español (, ↔ .)
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _auto_decimals(series):
    """0 decimales si todos los valores son enteros; 1 si hay parte decimal."""
    nums = pd.to_numeric(series, errors="coerce").dropna()
    if nums.empty:
        return 0
    if ((nums - nums.round(0)).abs() > 1e-9).any():
        return 1
    return 0


def render_year_table(df, index_label="Año", max_height=430):
    """Renderiza un DataFrame como tabla HTML con el mismo estilo que el resto de
    la app: 1ª columna (el índice) FIJA, encabezados de color y números con
    separador de miles español. Robusto en móvil (clases fg-fixedcol/fg-th)."""
    _TH = ("background:#1a2e1e;color:white;padding:8px 12px;font-weight:600;"
           "font-size:13px;white-space:nowrap;position:sticky;top:0;z-index:2;"
           "text-align:right;")
    _TH_CORNER = ("background:#1a2e1e;color:white;padding:8px 12px;font-weight:600;"
                  "font-size:13px;white-space:nowrap;position:sticky;top:0;left:0;"
                  "z-index:4;text-align:left;")
    _TD0 = ("position:sticky;left:0;z-index:1;padding:7px 12px;"
            "border-bottom:1px solid #ddd;font-weight:600;font-size:13px;"
            "white-space:nowrap;border-right:2px solid #1a2e1e;"
            "background:#f4f8f5;text-align:left;")
    _TD = ("padding:7px 12px;border-bottom:1px solid #ddd;white-space:nowrap;"
           "font-size:13px;text-align:right;")

    _decs = {c: _auto_decimals(df[c]) for c in df.columns}
    _hdr = f'<th class="fg-th-corner" style="{_TH_CORNER}">{index_label}</th>'
    for _c in df.columns:
        _hdr += f'<th class="fg-th" style="{_TH}">{_c}</th>'
    _body = ""
    for _idx, _row in df.iterrows():
        _cells = f'<td style="{_TD0}">{_idx}</td>'
        for _c in df.columns:
            _cells += f'<td style="{_TD}">{_fmt_es_number(_row[_c], _decs[_c])}</td>'
        _body += f"<tr>{_cells}</tr>"
    st.markdown(
        f'<div style="overflow-x:auto;overflow-y:auto;max-height:{max_height}px;'
        f'border-radius:8px;border:1px solid #ccc;margin-bottom:1rem;">'
        f'<table class="fg-fixedcol" style="border-collapse:separate;border-spacing:0;min-width:100%;">'
        f'<thead><tr>{_hdr}</tr></thead><tbody>{_body}</tbody></table></div>',
        unsafe_allow_html=True,
    )


def produccion_tab(history):
    st.subheader("🍎 Producción · Histórico y análisis")

    # ── Inicializar session_state ─────────────────────────────────────────────
    if "produccion_df" not in st.session_state:
        st.session_state.produccion_df = pd.DataFrame()

    # ── 1. Importación y Supabase ─────────────────────────────────────────────
    with st.expander("📥 Importar Excel de producción / Supabase", expanded=st.session_state.produccion_df.empty):
        col1, col2 = st.columns(2)
        with col1:
            uploaded = st.file_uploader(
                "Excel de producción (una hoja por año)",
                type=["xlsx"],
                key="produccion_uploader",
            )
            if uploaded:
                df_nuevo = produccion_parse_excel(uploaded)
                if df_nuevo.empty:
                    st.error("No se pudieron leer datos del Excel.")
                else:
                    # Fusionar con datos existentes (acumulativo por año)
                    if not st.session_state.produccion_df.empty:
                        años_nuevos = df_nuevo["Año"].unique()
                        base = st.session_state.produccion_df[
                            ~st.session_state.produccion_df["Año"].isin(años_nuevos)
                        ]
                        df_nuevo = pd.concat([base, df_nuevo], ignore_index=True)
                    st.session_state.produccion_df = df_nuevo
                    años = sorted(df_nuevo["Año"].unique())
                    st.success(f"Importado: {len(df_nuevo)} filas, años {años}.")
                    # Guardado automático en Supabase (sin pasos manuales)
                    autosave_produccion_to_supabase()

        with col2:
            st.markdown("**Supabase**")
            sb1, sb2 = st.columns(2)
            with sb1:
                if st.button("⬆️ Guardar en Supabase", use_container_width=True, type="primary"):
                    ok, msg = upload_produccion_to_supabase(st.session_state.produccion_df)
                    st.success(msg) if ok else st.error(msg)
            with sb2:
                if st.button("⬇️ Cargar desde Supabase", use_container_width=True):
                    df, msg = load_produccion_from_supabase()
                    if df is not None:
                        st.session_state.produccion_df = df
                        st.success(msg)
                        st.rerun()
                    else:
                        st.warning(msg)

    df = st.session_state.produccion_df
    if df.empty:
        st.info("Importa el Excel de producción o carga el histórico desde Supabase para comenzar.")
        return

    años_disponibles = sorted(df["Año"].unique())

    # ── 2. Resumen anual ──────────────────────────────────────────────────────
    st.markdown("### 1. Resumen anual")

    resumen = df.groupby("Año").agg(
        Kg_total=("Kg", "sum"),
        Ha_total=("Ha", "sum"),
        Num_arboles=("Num_arboles", "sum"),
        Arboles_prod=("Arboles_prod", "sum"),
    ).reset_index()
    resumen["Kg_por_Ha"] = (resumen["Kg_total"] / resumen["Ha_total"]).round(0)
    resumen["Kg_por_arbol"] = (resumen["Kg_total"] / resumen["Arboles_prod"]).round(1)
    resumen["Pct_prod"] = ((resumen["Arboles_prod"] / resumen["Num_arboles"]) * 100).round(1)
    resumen.columns = ["Año", "Kg totales", "Ha", "Nº árboles", "Árboles prod.",
                       "Kg/Ha", "Kg/árbol prod.", "% árb. productores"]

    render_year_table(resumen.set_index("Año"))

    # Gráfico kg totales por año
    fig_resumen = {
        "data": [{"x": list(resumen["Año"].astype(str)),
                  "y": list(resumen["Kg totales"]),
                  "type": "bar",
                  "marker": {"color": "#4caf7d"},
                  "name": "Kg totales"}],
        "layout": {"title": "Producción total por año (Kg)",
                   "xaxis": {"title": "Año"},
                   "yaxis": {"title": "Kg"},
                   "plot_bgcolor": "rgba(0,0,0,0)",
                   "paper_bgcolor": "rgba(0,0,0,0)"}
    }
    st.plotly_chart_from_dict = None  # usamos st.bar_chart como fallback

    # Usar pandas chart via streamlit
    resumen_chart = resumen.set_index("Año")[["Kg totales", "Kg/Ha"]]
    c1, c2 = st.columns(2)
    with c1:
        # .rename(index=str): año como categoría (texto) → eje "2020", no "2,020"
        st.bar_chart(resumen.set_index("Año")["Kg totales"].rename(index=str), color="#4caf7d")
        st.caption("Kg totales por año")
    with c2:
        st.bar_chart(resumen.set_index("Año")["Kg/Ha"].rename(index=str), color="#2196f3")
        st.caption("Kg por hectárea por año")

    # ── 3. Por campo ──────────────────────────────────────────────────────────
    st.markdown("### 2. Producción por campo")

    por_campo = df.groupby(["Año", "Campo"]).agg(Kg=("Kg", "sum"), Ha=("Ha", "sum")).reset_index()
    por_campo["Kg/Ha"] = (por_campo["Kg"] / por_campo["Ha"]).round(0)

    campos_sel = st.multiselect(
        "Campos a comparar",
        options=sorted(por_campo["Campo"].unique()),
        default=sorted(por_campo["Campo"].unique())[:6],
        key="prod_campos_sel",
    )
    metrica_campo = st.radio("Métrica", ["Kg", "Kg/Ha"], horizontal=True, key="prod_metrica_campo")

    if campos_sel:
        pivot_campo = por_campo[por_campo["Campo"].isin(campos_sel)].pivot(
            index="Año", columns="Campo", values=metrica_campo
        )
        st.line_chart(pivot_campo.rename(index=str))
        render_year_table(pivot_campo.round(0))

    # ── 4. Por variedad ───────────────────────────────────────────────────────
    st.markdown("### 3. Producción por variedad")

    por_var = df.groupby(["Año", "Variedad_nombre"]).agg(
        Kg=("Kg", "sum"), Ha=("Ha", "sum"), Arboles_prod=("Arboles_prod", "sum")
    ).reset_index()
    por_var["Kg/Ha"] = (por_var["Kg"] / por_var["Ha"]).round(0)

    vars_sel = st.multiselect(
        "Variedades a comparar",
        options=sorted(por_var["Variedad_nombre"].unique()),
        default=sorted(por_var["Variedad_nombre"].unique()),
        key="prod_vars_sel",
    )
    metrica_var = st.radio("Métrica", ["Kg", "Kg/Ha"], horizontal=True, key="prod_metrica_var")

    if vars_sel:
        pivot_var = por_var[por_var["Variedad_nombre"].isin(vars_sel)].pivot(
            index="Año", columns="Variedad_nombre", values=metrica_var
        )
        st.line_chart(pivot_var.rename(index=str))
        render_year_table(pivot_var.round(0))

    # ── 5. Por portainjerto ───────────────────────────────────────────────────
    st.markdown("### 4. Producción por portainjerto")
    st.caption("Comparativa de Kg/Ha y Kg/árbol productor según portainjerto, agregado por año.")

    por_porta = df.groupby(["Año", "Portainjerto_nombre"]).agg(
        Kg=("Kg", "sum"),
        Ha=("Ha", "sum"),
        Arboles_prod=("Arboles_prod", "sum"),
    ).reset_index()
    por_porta["Kg/Ha"] = (por_porta["Kg"] / por_porta["Ha"]).round(0)
    por_porta["Kg/árbol"] = (por_porta["Kg"] / por_porta["Arboles_prod"]).round(1)

    metrica_porta = st.radio("Métrica", ["Kg/Ha", "Kg/árbol"], horizontal=True, key="prod_metrica_porta")
    pivot_porta = por_porta.pivot(index="Año", columns="Portainjerto_nombre", values=metrica_porta)
    st.line_chart(pivot_porta.rename(index=str))
    render_year_table(pivot_porta.round(1))

    # ── 6. Correlación clima-producción ──────────────────────────────────────
    st.markdown("### 5. Correlación clima–producción")
    st.caption(
        "Cruza los datos de producción con el histórico climático. "
        "Esta sección irá creciendo con nuevas correlaciones (horas frío, floración, carpocapsa...)."
    )

    if history is None or history.empty:
        st.info("Carga el histórico climático para activar las correlaciones.")
    else:
        temp_col = None
        for c in ["temp_media", "temp", "temperatura", "Temperatura", "temp_avg"]:
            if c in history.columns:
                temp_col = c
                break

        if temp_col:
            hist_risk = history.copy()
            if "polinizacion_score" not in hist_risk.columns:
                try:
                    hist_risk = add_risk_columns(hist_risk)
                except Exception:
                    hist_risk = history.copy()

            correlacion_rows = []
            for año in años_disponibles:
                # ── Frío invernal: Nov(año-1) → Mar(año) ──────────────────
                inicio_frio, fin_frio = winter_period_from_analysis_year(año)
                mask_frio = (hist_risk["fecha_hora"] >= inicio_frio) & (hist_risk["fecha_hora"] <= fin_frio)
                frio_data = hist_risk[mask_frio]
                temps = pd.to_numeric(frio_data[temp_col], errors="coerce")

                horas_menor7 = int((temps < 7).sum())
                horas_0_72 = int(((temps >= 0) & (temps <= 7.2)).sum())
                utah_total = round(float(
                    pd.to_numeric(frio_data.get("utah_cu_hora", pd.Series(dtype=float)), errors="coerce").sum()
                ), 0) if "utah_cu_hora" in frio_data.columns else np.nan

                # ── Chill Portions (modelo Dynamic) sobre el periodo de frío ──
                chill_portions = np.nan
                if not frio_data.empty:
                    try:
                        _frio_ord = frio_data.sort_values("fecha_hora")
                        chill_portions = round(
                            float(np.sum(dynamic_chill_portions(_frio_ord[temp_col]))), 1
                        )
                    except Exception:
                        chill_portions = np.nan

                # ── Floración Abr–May: polinización y lluvia ──────────────
                inicio_flor = pd.Timestamp(año, 4, 1)
                fin_flor = pd.Timestamp(año, 5, 31)
                mask_flor = (hist_risk["fecha_hora"] >= inicio_flor) & (hist_risk["fecha_hora"] <= fin_flor)
                flor_data = hist_risk[mask_flor]

                score_medio = np.nan
                horas_fav = 0
                horas_ventana = 0
                calidad_polinizacion = "Sin datos"
                lluvia_abr_may = np.nan

                if not flor_data.empty:
                    if "lluvia_mm" in flor_data.columns:
                        lluvia_abr_may = round(float(
                            pd.to_numeric(flor_data["lluvia_mm"], errors="coerce").fillna(0).sum()
                        ), 1)
                    if "polinizacion_score" in flor_data.columns:
                        scores = pd.to_numeric(flor_data["polinizacion_score"], errors="coerce")
                        score_medio = round(float(scores[scores > 0].mean()), 1) if (scores > 0).any() else 0.0
                        if "polinizacion_hora_favorable" in flor_data.columns:
                            horas_fav = int(flor_data["polinizacion_hora_favorable"].sum())
                        if "en_ventana_polinizacion" in flor_data.columns:
                            horas_ventana = int(flor_data["en_ventana_polinizacion"].sum())
                        calidad_polinizacion = pollination_quality_from_score(score_medio, horas_fav, horas_ventana)

                kg_año = df[df["Año"] == año]["Kg"].sum()
                ha_año = df[df["Año"] == año]["Ha"].sum()
                kg_ha = round(kg_año / ha_año, 0) if ha_año > 0 else np.nan

                correlacion_rows.append({
                    "Año": año,
                    "Kg/Ha": int(kg_ha) if pd.notna(kg_ha) else "—",
                    "Kg totales": int(kg_año),
                    "H. frío <7°C": horas_menor7,
                    "H. frío 0–7,2°C": horas_0_72,
                    "Utah CU": int(utah_total) if pd.notna(utah_total) else "—",
                    "Chill Portions": chill_portions if pd.notna(chill_portions) else "—",
                    "Lluvia Abr–May (mm)": lluvia_abr_may if pd.notna(lluvia_abr_may) else "—",
                    "Score polinización": score_medio if pd.notna(score_medio) else "—",
                    "H. favorables poliniz.": horas_fav,
                    "Calidad polinización": calidad_polinizacion,
                })

            corr_df = pd.DataFrame(correlacion_rows).set_index("Año")
            render_year_table(corr_df, max_height=500)
            st.caption(
                "Frío: H. frío <7°C, 0–7,2°C, Utah CU y Chill Portions (modelo Dynamic) "
                "corresponden a Nov(año-1)–Mar(año). "
                "Polinización y lluvia: Abr–May del año de producción."
            )

            # ── Resumen narrativo ─────────────────────────────────────────
            st.markdown("#### Resumen por campaña")

            # Mejor y peor año
            mejor_año = corr_df["Kg/Ha"].replace("—", np.nan)
            mejor_año = pd.to_numeric(mejor_año, errors="coerce")
            año_mejor = mejor_año.idxmax()
            año_peor = mejor_año.idxmin()

            # Por campo
            por_campo_total = df.groupby("Campo")["Kg"].sum()
            campo_mejor = por_campo_total.idxmax()
            campo_peor = por_campo_total.idxmin()

            # Kg/Ha por campo
            por_campo_kgha = df.groupby("Campo").apply(
                lambda x: x["Kg"].sum() / x["Ha"].sum() if x["Ha"].sum() > 0 else np.nan
            )
            campo_mejor_kgha = por_campo_kgha.idxmax()

            # Por variedad
            por_var_kgha = df.groupby("Variedad_nombre").apply(
                lambda x: x["Kg"].sum() / x["Ha"].sum() if x["Ha"].sum() > 0 else np.nan
            )
            var_mejor = por_var_kgha.idxmax()
            var_peor = por_var_kgha.idxmin()

            # Por portainjerto
            por_porta_kgha = df.groupby("Portainjerto_nombre").apply(
                lambda x: x["Kg"].sum() / x["Ha"].sum() if x["Ha"].sum() > 0 else np.nan
            ).dropna()
            porta_mejor = por_porta_kgha.idxmax() if not por_porta_kgha.empty else "—"

            # Año con mejor/peor polinización
            poliniz_scores = pd.to_numeric(
                corr_df["Score polinización"].replace("—", np.nan), errors="coerce"
            ).dropna()
            año_mejor_poliniz = poliniz_scores.idxmax() if not poliniz_scores.empty else "—"
            año_peor_poliniz = poliniz_scores.idxmin() if not poliniz_scores.empty else "—"

            # Frío
            horas_frio_series = pd.to_numeric(corr_df["H. frío <7°C"], errors="coerce")
            año_mas_frio = horas_frio_series.idxmax() if not horas_frio_series.empty else "—"
            año_menos_frio = horas_frio_series.idxmin() if not horas_frio_series.empty else "—"

            # Chill Portions (modelo Dynamic)
            chill_series = pd.to_numeric(
                corr_df["Chill Portions"].replace("—", np.nan), errors="coerce"
            )
            tiene_cp = chill_series.notna().any()
            año_mas_cp = chill_series.idxmax() if tiene_cp else "—"
            año_menos_cp = chill_series.idxmin() if tiene_cp else "—"
            cp_mejor = chill_series.get(año_mejor, np.nan)

            resumen_años = []
            for año in años_disponibles:
                row = corr_df.loc[año]
                kg_ha_val = pd.to_numeric(row["Kg/Ha"], errors="coerce")
                score_val = pd.to_numeric(row["Score polinización"], errors="coerce")
                frio_val = pd.to_numeric(row["H. frío <7°C"], errors="coerce")
                lluvia_val = pd.to_numeric(row["Lluvia Abr–May (mm)"], errors="coerce")

                nivel_prod = (
                    "excepcional" if pd.notna(kg_ha_val) and kg_ha_val == mejor_año.max() else
                    "muy buena" if pd.notna(kg_ha_val) and kg_ha_val >= mejor_año.quantile(0.75) else
                    "buena" if pd.notna(kg_ha_val) and kg_ha_val >= mejor_año.median() else
                    "baja" if pd.notna(kg_ha_val) and kg_ha_val >= mejor_año.quantile(0.25) else
                    "muy baja"
                )
                frio_txt = (
                    f"{int(frio_val)} horas de frío (<7°C)" if pd.notna(frio_val) else "frío sin datos"
                )
                poliniz_txt = (
                    f"polinización {str(row['Calidad polinización']).lower()} "
                    f"(score {score_val:.0f}, {int(row['H. favorables poliniz.'])} h favorables)"
                    if pd.notna(score_val) else "polinización sin datos"
                )
                lluvia_txt = (
                    f"{lluvia_val:.0f} mm de lluvia en Abr–May" if pd.notna(lluvia_val) else ""
                )
                resumen_años.append(
                    f"**{año}** — Producción {nivel_prod} "
                    f"({int(kg_ha_val) if pd.notna(kg_ha_val) else '—'} Kg/Ha, {int(row['Kg totales']):,} Kg totales). "
                    f"{frio_txt.capitalize()}, {poliniz_txt}"
                    + (f", {lluvia_txt}." if lluvia_txt else ".")
                )

            for linea in resumen_años:
                st.markdown(linea)

            # Línea narrativa de Chill Portions (modelo Dynamic)
            if tiene_cp:
                cp_mejor_txt = (
                    f"acumuló **{cp_mejor:.1f} Chill Portions**"
                    if pd.notna(cp_mejor) else "no tiene Chill Portions calculados"
                )
                chill_line = (
                    f"**❄️ Frío Dynamic (Chill Portions):** más acumulación en "
                    f"{año_mas_cp} ({chill_series[año_mas_cp]:.1f} CP), menos en "
                    f"{año_menos_cp} ({chill_series[año_menos_cp]:.1f} CP). "
                    f"La mejor campaña ({año_mejor}) {cp_mejor_txt}."
                )
            else:
                chill_line = (
                    "**❄️ Frío Dynamic (Chill Portions):** sin datos suficientes "
                    "para calcular el modelo."
                )
            st.markdown(chill_line)

            st.markdown("---")
            st.markdown(
                f"**🏆 Mejor campaña:** {año_mejor} · "
                f"**Peor campaña:** {año_peor}  \n"
                f"**Año más frío:** {año_mas_frio} ({int(horas_frio_series[año_mas_frio])} h <7°C) · "
                f"**Año menos frío:** {año_menos_frio} ({int(horas_frio_series[año_menos_frio])} h <7°C)  \n"
                f"**Más Chill Portions:** {año_mas_cp}"
                + (f" ({chill_series[año_mas_cp]:.1f} CP)" if tiene_cp else "")
                + f" · **Menos Chill Portions:** {año_menos_cp}"
                + (f" ({chill_series[año_menos_cp]:.1f} CP)" if tiene_cp else "")
                + "  \n"
                f"**Mejor polinización:** {año_mejor_poliniz} · "
                f"**Peor polinización:** {año_peor_poliniz}  \n"
                f"**Campo con más Kg/Ha (histórico):** {campo_mejor_kgha} · "
                f"**Variedad más productiva (Kg/Ha):** {var_mejor}  \n"
                f"**Variedad menos productiva (Kg/Ha):** {var_peor} · "
                f"**Portainjerto más productivo (Kg/Ha):** {porta_mejor}"
            )
        else:
            st.info("No se encontró columna de temperatura en el histórico climático.")

    # ── Descarga ──────────────────────────────────────────────────────────────
    st.markdown("---")
    st.download_button(
        "⬇️ Descargar histórico de producción CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="produccion_historica.csv",
        mime="text/csv",
        use_container_width=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ANÁLISIS GALLINAL · Fenología × Clima × Producción × Vecería
# Se construye por fases. Fase 1 (actual): consulta de producción y % productores
# por año(s) / campo / variedad, con desglose por portainjerto y variedad.
# ═══════════════════════════════════════════════════════════════════════════════
def _gallinal_breakdown(sel, group_col, index_label):
    """Agrega la selección por una columna (portainjerto o variedad) y la
    renderiza como tabla estilizada con números en español."""
    g = sel.groupby(group_col).agg(
        Kg=("Kg", "sum"),
        Ha=("Ha", "sum"),
        Arboles_tot=("Num_arboles", "sum"),
        Arboles_prod=("Arboles_prod", "sum"),
    )
    g["% productores"] = (g["Arboles_prod"] / g["Arboles_tot"].replace(0, np.nan) * 100).round(1)
    g["Kg/árbol prod."] = (g["Kg"] / g["Arboles_prod"].replace(0, np.nan)).round(1)
    g["Kg/Ha"] = (g["Kg"] / g["Ha"].replace(0, np.nan)).round(0)
    g = g.rename(columns={"Arboles_tot": "Árboles totales", "Arboles_prod": "Árboles prod."})
    g = g[["Kg", "Árboles totales", "Árboles prod.", "% productores", "Kg/árbol prod.", "Kg/Ha"]]
    g = g.sort_values("Kg", ascending=False)
    render_year_table(g, index_label=index_label)


# ── FASE 3 · Índice Climático por fases fenológicas (finca, por año) ──────────
# (id, etiqueta, mes_ini, día_ini, mes_fin, día_fin, peso_por_defecto)
# El frío usa el CRITERIO ÚNICO de la app (CHILL_PERIOD_*_MD = 1 nov → 31 mar,
# fuente SERIDA/Delgado 2021), igual que el item Frío. Brotación arranca el 1 abr
# para no solaparse (en Asturias la brotación es de finales de marzo/principios de abril).
# Ventanas por defecto ajustadas por el productor (Finca Gallinal, Asturias).
# El frío usa el CRITERIO ÚNICO de la app (CHILL_PERIOD_*_MD = 1 nov → 31 mar).
# El resto son las fechas que el usuario fijó (persisten al reabrir la app).
# En el futuro, la fenología real por campo/variedad/año vendrá de un CSV.
_GALLINAL_PHASES = [
    ("frio",       "🥶 Frío",       CHILL_PERIOD_START_MD[0], CHILL_PERIOD_START_MD[1],
                                    CHILL_PERIOD_END_MD[0],   CHILL_PERIOD_END_MD[1], 20),
    ("brotacion",  "🌱 Brotación",   4,  1,  4, 20, 10),
    ("floracion",  "🌸 Floración",   4, 21,  5, 21, 30),
    ("cuajado",    "🍏 Cuajado",     5, 22,  6, 15, 15),
    ("engorde",    "☀️ Engorde",     6, 16,  8, 31, 15),
    ("maduracion", "🍎 Maduración",  9,  1, 10, 20, 10),
]


def _phase_window(sm, sd, em, ed, year):
    """Ventana (inicio, fin) de una fase para un año. Si el inicio (mes,día) es
    posterior al fin, la ventana cruza el cambio de año (caso del frío invernal).
    El día se ajusta al máximo del mes (evita fechas inválidas como 31 de sep.)."""
    import calendar as _cal

    def _md(yr, mo, d):
        return pd.Timestamp(yr, mo, min(int(d), _cal.monthrange(yr, mo)[1]))

    if (sm, sd) <= (em, ed):
        start = _md(year, sm, sd)
    else:
        start = _md(year - 1, sm, sd)
    end = _md(year, em, ed) + pd.Timedelta(hours=23, minutes=59)
    return start, end


def _phase_metrics(hist, start, end, temp_col, frost_thr=0.0, heat_thr=32.0,
                   base_temp=10.0, pollin_lo=12.0, pollin_hi=25.0):
    """Métricas climáticas de una ventana fenológica. None si no hay datos."""
    sl = hist[(hist["fecha_hora"] >= start) & (hist["fecha_hora"] <= end)].copy()
    if sl.empty:
        return None
    sl = sl.sort_values("fecha_hora")
    t = pd.to_numeric(sl[temp_col], errors="coerce")
    n_hours = int(t.notna().sum())
    if n_hours == 0:
        return None
    daily = sl.set_index("fecha_hora")[temp_col]
    dmin = pd.to_numeric(daily.resample("D").min(), errors="coerce")
    dmax = pd.to_numeric(daily.resample("D").max(), errors="coerce")
    dmean = pd.to_numeric(daily.resample("D").mean(), errors="coerce")
    expected_days = max(1, (end - start).days + 1)
    rain = (float(pd.to_numeric(sl["lluvia_mm"], errors="coerce").fillna(0).sum())
            if "lluvia_mm" in sl.columns else np.nan)
    fav = int(((t >= pollin_lo) & (t <= pollin_hi)).sum())
    return {
        "n_hours": n_hours,
        "n_days": int(dmean.notna().sum()),
        "coverage": dmean.notna().sum() / expected_days,
        "mean_temp": float(t.mean()),
        "frost_nights": int((dmin <= frost_thr).sum()),
        "heat_days": int((dmax > heat_thr).sum()),
        "gdd": float(np.clip(dmean - base_temp, 0, None).sum()),
        "rain_mm": rain,
        "pollin_frac": float(fav / n_hours) if n_hours > 0 else np.nan,
        # Tres modelos de frío (solo relevantes en la fase de frío):
        "horas_frio": int((t <= 7.2).sum()),                 # horas de frío (Dapena/sector)
        "utah_cu": float(t.apply(utah_weight).sum()),         # unidades Utah
        "chill_cp": float(np.sum(dynamic_chill_portions(t))), # Chill Portions (Dynamic)
    }


def _tri_adequacy(x, lo, peak_lo, peak_hi, hi):
    """Idoneidad 0–100: 100 en [peak_lo, peak_hi], baja lineal hasta 0 en lo/hi."""
    if pd.isna(x):
        return np.nan
    if peak_lo <= x <= peak_hi:
        return 100.0
    if x < peak_lo:
        return 0.0 if x <= lo else (x - lo) / (peak_lo - lo) * 100.0
    return 0.0 if x >= hi else (hi - x) / (hi - peak_hi) * 100.0


def _score_phase(pid, m, p):
    """Puntuación climática 0–100 de una fase, según sus métricas y parámetros."""
    if m is None:
        return np.nan
    if pid == "frio":
        _req = p.get("frio_req", 0)
        if not _req or _req <= 0:
            return np.nan
        _fm = p.get("frio_metric", "horas")
        _val = (m["chill_cp"] if _fm == "cp"
                else m["utah_cu"] if _fm == "utah"
                else m["horas_frio"])
        return float(np.clip(_val / _req * 100, 0, 100))
    if pid == "brotacion":
        return float(np.clip(m["gdd"] / p["gdd_ref"] * 100, 0, 100)) if p["gdd_ref"] > 0 else np.nan
    if pid == "floracion":
        if pd.isna(m["pollin_frac"]):
            return np.nan
        temp_score = float(np.clip(m["pollin_frac"] / 0.5 * 100, 0, 100))
        rain_pen = (float(np.clip((m["rain_mm"] - 40) / (150 - 40), 0, 1) * 0.4)
                    if pd.notna(m["rain_mm"]) else 0.0)
        frost_factor = max(0.0, 1 - 0.25 * m["frost_nights"])
        return float(temp_score * (1 - rain_pen) * frost_factor)
    if pid == "cuajado":
        adq = _tri_adequacy(m["mean_temp"], 10, 16, 22, 28)
        if pd.isna(adq):
            return np.nan
        frost_factor = max(0.0, 1 - 0.30 * m["frost_nights"])
        return float(adq * frost_factor)
    if pid == "engorde":
        heat_pen = float(np.clip(m["heat_days"] / 20.0, 0, 1) * 0.5)
        drought_pen = (float(np.clip((p["rain_min_engorde"] - m["rain_mm"]) / p["rain_min_engorde"], 0, 1) * 0.4)
                       if pd.notna(m["rain_mm"]) else 0.0)
        return float(100 * (1 - heat_pen) * (1 - drought_pen))
    if pid == "maduracion":
        return _tri_adequacy(m["mean_temp"], 8, 14, 20, 26)
    return np.nan


def _score_color(s):
    """Color de una puntuación 0–100 (verde alto, rojo bajo)."""
    if pd.isna(s):
        return "#9e9e9e"
    if s >= 80:
        return "#2e7d32"
    if s >= 60:
        return "#558b2f"
    if s >= 40:
        return "#e65100"
    return "#c62828"


def _phase_clima_text(pid, m):
    """Resumen legible del clima de una fase (las métricas que más pesan)."""
    if m is None:
        return "—"
    pre = "⚠️ datos parciales · " if m.get("coverage", 1) < 0.5 else ""
    _r = (_fmt_es_number(round(m["rain_mm"]), 0) if pd.notna(m.get("rain_mm")) else "—")
    if pid == "frio":
        return pre + (f"{_fmt_es_number(round(m['horas_frio']), 0)} h frío · "
                      f"{_fmt_es_number(round(m['utah_cu']), 0)} Utah · "
                      f"{_fmt_es_number(round(m['chill_cp']), 0)} CP")
    if pid == "brotacion":
        return pre + f"{_fmt_es_number(round(m['gdd']), 0)} GDD"
    if pid == "floracion":
        return (pre + f"{m['frost_nights']} heladas · {_r} mm · "
                f"{_fmt_es_number(round(m['pollin_frac'] * 100), 0)} % horas favorables")
    if pid == "cuajado":
        return pre + f"{m['frost_nights']} heladas · {_fmt_es_number(round(m['mean_temp'], 1), 1)} °C media"
    if pid == "engorde":
        return pre + f"{m['heat_days']} días calor · {_r} mm"
    if pid == "maduracion":
        return pre + f"{_fmt_es_number(round(m['mean_temp'], 1), 1)} °C media"
    return pre + "—"


def _render_html_table(headers, rows, max_height=480):
    """Renderiza una tabla HTML genérica con 1ª columna fija y encabezados de
    color (clases fg-fixedcol/fg-th, robustas en móvil).
    headers: lista de (texto, alineación). rows: lista de listas con el HTML ya
    formateado de cada celda."""
    _THb = ("background:#1a2e1e;color:white;padding:8px 12px;font-weight:600;"
            "font-size:13px;white-space:nowrap;position:sticky;top:0;z-index:2;")
    _THc = _THb + "left:0;z-index:4;"
    _TD0 = ("position:sticky;left:0;z-index:1;padding:7px 12px;"
            "border-bottom:1px solid #ddd;font-weight:600;font-size:13px;"
            "white-space:nowrap;border-right:2px solid #1a2e1e;background:#f4f8f5;")
    _TD = "padding:7px 12px;border-bottom:1px solid #ddd;white-space:nowrap;font-size:13px;"
    _hdr = ""
    for _i, (_label, _align) in enumerate(headers):
        _s = (_THc if _i == 0 else _THb) + f"text-align:{_align};"
        _cls = "fg-th-corner" if _i == 0 else "fg-th"
        _hdr += f'<th class="{_cls}" style="{_s}">{_label}</th>'
    _body = ""
    for _row in rows:
        _cells = ""
        for _i, (_label, _align) in enumerate(headers):
            _base = _TD0 if _i == 0 else _TD
            _cells += f'<td style="{_base}text-align:{_align};">{_row[_i]}</td>'
        _body += f"<tr>{_cells}</tr>"
    st.markdown(
        f'<div style="overflow-x:auto;overflow-y:auto;max-height:{max_height}px;'
        f'border-radius:8px;border:1px solid #ccc;margin-bottom:1rem;">'
        f'<table class="fg-fixedcol" style="border-collapse:separate;border-spacing:0;min-width:100%;">'
        f'<thead><tr>{_hdr}</tr></thead><tbody>{_body}</tbody></table></div>',
        unsafe_allow_html=True,
    )


def _veceria_level(bbi):
    """Devuelve (etiqueta, color_texto, color_fondo) según el BBI (0–1)."""
    if pd.isna(bbi):
        return ("Sin datos", "#9e9e9e", "#f5f5f5")
    if bbi < 0.20:
        return ("Regular", "#2e7d32", "#e8f5e9")
    if bbi < 0.40:
        return ("Vecería leve", "#f9a825", "#fff8e1")
    if bbi < 0.60:
        return ("Vecería moderada", "#e65100", "#fff3e0")
    return ("Vecería acentuada", "#c62828", "#ffebee")


def _compute_bbi(years, vals):
    """Índice de vecería (Hoblyn 1936) sobre años CONSECUTIVOS.
    BBI = media de |Vₙ−Vₙ₋₁| / (Vₙ+Vₙ₋₁). Devuelve (bbi, nº_transiciones)."""
    num = 0.0
    trans = 0
    for i in range(1, len(years)):
        if years[i] - years[i - 1] == 1:          # solo pares de años consecutivos
            a, b = vals[i - 1], vals[i]
            if (a + b) > 0:
                num += abs(b - a) / (a + b)
                trans += 1
    return (num / trans if trans > 0 else np.nan), trans


def _veceria_pattern_html(years, vals):
    """Puntos coloreados por año: verde = año de carga (≥ mediana), gris = año
    de descarga (< mediana). Visualiza la alternancia de un vistazo."""
    if not vals:
        return ""
    med = float(np.median(vals))
    dots = ""
    for y, v in zip(years, vals):
        col = "#2e7d32" if v >= med else "#cfd8dc"
        dots += (
            f'<span title="{y}: {_fmt_es_number(round(v), 0)}" '
            f'style="display:inline-block;width:11px;height:11px;border-radius:50%;'
            f'background:{col};margin:0 1px;"></span>'
        )
    return dots


def _veceria_yearly_values(prod, metric):
    """Una fila por (Campo, Variedad, Portainjerto, Año) con: 'kg_ha', 'pct_prod'
    (% de árboles que produjeron) y 'valor' (la métrica base del BBI)."""
    g = prod.groupby(
        ["Campo", "Variedad_nombre", "Portainjerto_nombre", "Año"]
    ).agg(
        Kg=("Kg", "sum"),
        Ha=("Ha", "sum"),
        Num_arboles=("Num_arboles", "sum"),
        Arboles_prod=("Arboles_prod", "sum"),
    ).reset_index()
    g["kg_ha"] = g["Kg"] / g["Ha"].replace(0, np.nan)
    g["pct_prod"] = g["Arboles_prod"] / g["Num_arboles"].replace(0, np.nan) * 100
    if metric == "Kg por árbol productor":
        g["valor"] = g["Kg"] / g["Arboles_prod"].replace(0, np.nan)
    else:  # "Kg/Ha (cosecha)" — la unidad del objetivo
        g["valor"] = g["kg_ha"]
    return g


def _drill_pattern_message(bbi, pct_std):
    """Diagnóstico del patrón combinando vecería de cosecha (BBI) y estabilidad de
    la participación (desv. del % productores), usando las MISMAS bandas que las
    tablas (sin cajones de sastre que suavicen). Devuelve (tipo, mensaje)."""
    if pd.isna(bbi) or pd.isna(pct_std):
        return ("info", "ℹ️ Pocos años consecutivos para diagnosticar el patrón con fiabilidad.")
    vec_lbl, _, _ = _veceria_level(bbi)          # Regular / Vecería leve / moderada / acentuada
    con_lbl, _, _ = _constancia_label(pct_std)   # Muy constante / Constante / Variable / Muy variable
    bbi_txt = _fmt_es_number(round(bbi, 2), 2)
    vec_phrase = "cosecha regular" if bbi < 0.20 else vec_lbl.lower()
    cabecera = (f"**{vec_phrase.capitalize()}** (BBI {bbi_txt}) · participación "
                f"**{con_lbl.lower()}**.")

    # Caso ideal: poca vecería y participación estable
    if bbi < 0.20 and pct_std < 10:
        return ("success", f"✅ {cabecera} Cosecha y participación estables: es el "
                           f"comportamiento que buscamos.")

    consejos = []
    if bbi >= 0.40:
        consejos.append("**aclareo de fruto en los años de carga alta** para regularizar "
                        "la floración del año siguiente")
    elif bbi >= 0.20:
        consejos.append("un **aclareo ligero** en los años de más carga ayuda a regularizar")
    if pct_std >= 20:
        consejos.append("revisar por qué algunos años cargan bastantes **menos árboles** "
                        "(heladas en floración, fallos de cuajado, vigor desigual)")
    elif pct_std >= 10:
        consejos.append("vigilar la **uniformidad de floración** entre árboles")

    consejo_txt = "; ".join(consejos) if consejos else "seguimiento normal"
    kind = "warning" if (bbi >= 0.60 or pct_std >= 20) else "info"
    return (kind, f"🔎 {cabecera} Conviene: {consejo_txt}.")


def _constancia_label(std):
    """Constancia del % de árboles productores entre años (a menor desviación,
    más árboles repiten producción año tras año → mejor)."""
    if pd.isna(std):
        return ("—", "#9e9e9e", "#f5f5f5")
    if std < 5:
        return ("Muy constante", "#2e7d32", "#e8f5e9")
    if std < 10:
        return ("Constante", "#558b2f", "#f1f8e9")
    if std < 20:
        return ("Variable", "#e65100", "#fff3e0")
    return ("Muy variable", "#c62828", "#ffebee")


def _kgha_target_html(value, target):
    """Kg/Ha medio coloreado según cercanía al objetivo (verde ≥ objetivo)."""
    if pd.isna(value):
        return '<span style="color:#9e9e9e;">—</span>'
    if target and target > 0:
        ratio = value / target
        color = ("#2e7d32" if ratio >= 1.0 else
                 "#558b2f" if ratio >= 0.85 else
                 "#f9a825" if ratio >= 0.6 else
                 "#e65100" if ratio >= 0.4 else "#c62828")
    else:
        color = "#333"
    return f'<span style="color:{color};font-weight:600;">{_fmt_es_number(round(value), 0)}</span>'


def _nivel_cosecha(kg_ha, objetivo):
    """Nivel ABSOLUTO de la cosecha de un año, respecto al objetivo (no on/off).
    Responde a '¿fue buena cosecha?', no a '¿subió o bajó en el ciclo?'."""
    if pd.isna(kg_ha) or not objetivo or objetivo <= 0:
        return ("—", "#9e9e9e")
    r = kg_ha / objetivo
    if r >= 0.90:
        return ("Alta", "#2e7d32")
    if r >= 0.65:
        return ("Media-alta", "#558b2f")
    if r >= 0.40:
        return ("Media-baja", "#e65100")
    return ("Baja", "#c62828")


def _ig_diagnosis(ig, kgha, objetivo):
    """Cruza el clima (IG) con la cosecha real para diagnosticar el año.
    El gran objetivo: distinguir años limitados por CLIMA de años donde el clima
    fue bueno pero la cosecha no (→ vecería/manejo). Devuelve (texto, color)."""
    if pd.isna(ig) or pd.isna(kgha) or not objetivo or objetivo <= 0:
        return ("—", "#9e9e9e")
    clima_bueno = ig >= 65
    clima_malo = ig < 50
    cosecha_buena = kgha >= 0.65 * objetivo
    cosecha_mala = kgha < 0.40 * objetivo
    if clima_malo and cosecha_mala:
        return ("Limitado por clima", "#c62828")
    if clima_bueno and cosecha_mala:
        return ("No fue el clima → vecería/manejo", "#e65100")
    if clima_bueno and cosecha_buena:
        return ("Clima y cosecha buenos", "#2e7d32")
    if clima_malo and cosecha_buena:
        return ("Buena cosecha pese al clima", "#558b2f")
    return ("Intermedio", "#9e9e9e")


def _iep_score(kg_ha_medio, pct_medio, objetivo, w_kgha=0.65, w_part=0.35):
    """Índice de Excelencia Productiva (0–100). El Kg/Ha es el criterio dominante
    (logro respecto al objetivo, tope 100) y la participación de árboles modula.
    Refleja: 75% árboles · 19.000 Kg/Ha (IEP alto) es mejor que 90% · 12.000."""
    if pd.isna(kg_ha_medio) or pd.isna(pct_medio) or not objetivo or objetivo <= 0:
        return np.nan
    logro = min(1.0, kg_ha_medio / objetivo) * 100.0
    return w_kgha * logro + w_part * pct_medio


def _iep_level(iep):
    """(etiqueta, color) según el IEP (0–100)."""
    if pd.isna(iep):
        return ("—", "#9e9e9e")
    if iep >= 85:
        return ("Excelente", "#2e7d32")
    if iep >= 70:
        return ("Bueno", "#558b2f")
    if iep >= 50:
        return ("Mejorable", "#e65100")
    return ("Bajo", "#c62828")


def _pct_prod_color(p):
    """Color del % de árboles productores (verde = cerca del 100%)."""
    if pd.isna(p):
        return "#9e9e9e"
    if p >= 85:
        return "#2e7d32"
    if p >= 70:
        return "#558b2f"
    if p >= 50:
        return "#e65100"
    return "#c62828"


def _colored_num(value, color, decimals=0, suffix=""):
    """Número coloreado en negrita (o '—' si NaN), con formato español."""
    if pd.isna(value):
        return '<span style="color:#9e9e9e;">—</span>'
    return (f'<span style="color:{color};font-weight:600;">'
            f'{_fmt_es_number(round(value, decimals), decimals)}{suffix}</span>')


def gallinal_tab(history):
    st.subheader("🍏 Análisis Gallinal · Fenología · Clima · Producción")
    st.caption(
        "Cruce de la producción con la fenología, el clima y la vecería, por campo, "
        "variedad y portainjerto, para entender qué mueve la cosecha."
    )

    with st.expander("📖 Guía: qué es esto, qué mide cada fase y cómo leer los números"):
        st.markdown(
            "**¿Para qué sirve?** Cruza tu **producción** con el **clima**, el "
            "**portainjerto** y la **variedad** para entender qué mueve la cosecha y "
            "**separar lo que es clima de lo que es vecería o manejo**. Tiene 4 bloques:\n\n"
            "1. **Consulta** — eliges año/campo/variedad → Kg y % de árboles que produjeron.\n"
            "2. **Regularidad y vecería** — si la cosecha es estable o alterna.\n"
            "3. **Índice Climático** — puntúa el clima de cada fase del año.\n"
            "4. **Índice Gallinal** — cruza ese clima con tu producción.\n\n"
            "---\n"
            "**Abreviaturas (glosario):**\n"
            "- **DD / GDD** = grados-día (calor acumulado; cada día suma los grados por "
            "encima de 10 °C). El primo \"calor\" del frío.\n"
            "- **CP (Chill Portions)** = porciones de frío del modelo *Dynamic* (el más "
            "preciso). **Utah (CU)** = unidades del modelo Utah. **Horas de frío** = horas "
            "por debajo de 7,2 °C (la métrica de Dapena/el sector).\n"
            "- **Kg/Ha** = kilos por hectárea (objetivo ≈ 20.000). **% prod.** = % de "
            "árboles que dieron fruta.\n"
            "- **BBI** = Índice de Vecería (0 regular … 1 alternancia total).\n"
            "- **IEP** = Índice de Excelencia Productiva (nota 0-100: Kg/Ha 65 % + "
            "participación 35 %).\n"
            "- **IC** = Índice Climático (nota 0-100 del clima del año). "
            "**IG** = Índice Gallinal (el IC calibrado con tu producción).\n\n"
            "---\n"
            "**Las 6 fases del año y qué mira el clima** (cada una se puntúa 0-100, "
            "🟢 alto = favorable):\n\n"
            "| Fase | Ventana | Qué mide el clima | Umbral (base científica) |\n"
            "|---|---|---|---|\n"
            "| 🥶 Frío | 1 Nov–31 Mar | Frío acumulado para romper el reposo invernal | "
            "Regona ≈ 90 CP (SERIDA) |\n"
            "| 🌱 Brotación | 1–20 Abr | Calor (GDD) para brotar con vigor | calibrable "
            "(la fase menos crítica) |\n"
            "| 🌸 Floración | 21 Abr–21 May | Heladas + clima de polinización + lluvia | "
            "helada daña desde **−2 °C** (10 % de pérdida a −2,2 °C); abejas vuelan ≥10–15 °C |\n"
            "| 🍏 Cuajado | 22 May–15 Jun | Heladas tardías + temperatura | helada desde "
            "**−2 °C**; templado mejor |\n"
            "| ☀️ Engorde | 16 Jun–31 Ago | Golpe de calor + sequía | daño de calor a "
            "**35 °C** (golpe de sol) |\n"
            "| 🍎 Maduración | 1 Sep–20 Oct | Temperatura para acumular azúcares | templado "
            "favorece azúcar/color |\n\n"
            "El **IC** del año es la **media ponderada** de las 6 notas (los *pesos* dicen "
            "cuánto cuenta cada fase). No tienes que saber los pesos: la Fase 4 los "
            "**aprende de tu producción**.\n\n"
            "---\n"
            "**Ejemplo (datos inventados) — año «X»:**\n"
            "- 🥶 Frío: 92 CP → **100** (cumple el requerimiento de 90).\n"
            "- 🌱 Brotación: poco calor en abril → **55**.\n"
            "- 🌸 Floración: 0 heladas, 60 % de horas en rango de abeja, poca lluvia → **88**.\n"
            "- 🍏 Cuajado: temperatura ideal, sin heladas → **100**.\n"
            "- ☀️ Engorde: ningún día >35 °C, lluvia suficiente → **98**.\n"
            "- 🍎 Maduración: otoño templado → **100**.\n\n"
            "Con los pesos (Floración 30, Frío 20, Cuajado/Engorde 15, Brotación/Maduración 10):\n\n"
            "**IC = (20×100 + 10×55 + 30×88 + 15×100 + 15×98 + 10×100) ÷ 100 = 91/100** "
            "→ un año climáticamente muy bueno. Si la cosecha hubiera sido baja, el "
            "**diagnóstico** diría *«no fue el clima → vecería/manejo»*.\n\n"
            "---\n"
            "*Fuentes de los umbrales: frío — SERIDA/Delgado 2021; heladas — MSU/USU "
            "(temperaturas críticas); polinización — AHDB; golpe de sol — UC Davis/WSU.*"
        )

    prod = st.session_state.get("produccion_df", pd.DataFrame())
    if prod is None or prod.empty:
        st.info(
            "Aún no hay datos de producción cargados. Ve al item **🍎 Producción**, "
            "importa el Excel o carga el histórico desde Supabase, y vuelve aquí."
        )
        return

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 1 · Consulta: año(s) · campo · variedad → Kg y % árboles productores
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("### 🔎 Consulta de producción por campo y variedad")

    años_disp = sorted(prod["Año"].unique())
    campos_disp = sorted(prod["Campo"].unique())

    c1, c2, c3 = st.columns([1.3, 1, 1])
    with c1:
        años_sel = st.multiselect(
            "Año(s)", años_disp,
            default=[años_disp[-1]] if años_disp else [],
            key="gallinal_años",
        )
    with c2:
        campo_sel = st.selectbox("Campo", campos_disp, key="gallinal_campo")
    with c3:
        vars_campo = sorted(prod[prod["Campo"] == campo_sel]["Variedad_nombre"].unique())
        variedad_sel = st.selectbox("Variedad", ["(Todas)"] + vars_campo, key="gallinal_variedad")

    if not años_sel:
        st.warning("Selecciona al menos un año.")
        return

    sel = prod[(prod["Campo"] == campo_sel) & (prod["Año"].isin(años_sel))].copy()
    if variedad_sel != "(Todas)":
        sel = sel[sel["Variedad_nombre"] == variedad_sel]

    if sel.empty:
        st.warning("No hay datos de producción para esa combinación.")
        return

    # ── Totales de la selección ───────────────────────────────────────────────
    kg_tot = float(sel["Kg"].sum())
    arb_tot = float(sel["Num_arboles"].sum())
    arb_prod = float(sel["Arboles_prod"].sum())
    pct_prod = (arb_prod / arb_tot * 100) if arb_tot > 0 else np.nan
    kg_arbol_prod = (kg_tot / arb_prod) if arb_prod > 0 else np.nan

    _var_txt = variedad_sel if variedad_sel != "(Todas)" else "todas las variedades"
    _año_txt = f"año {años_sel[0]}" if len(años_sel) == 1 else f"{len(años_sel)} años ({min(años_sel)}–{max(años_sel)})"
    st.markdown(f"**{campo_sel} · {_var_txt} · {_año_txt}**")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Kg producidos", _fmt_es_number(round(kg_tot), 0))
    m2.metric("% árboles productores",
              f"{_fmt_es_number(round(pct_prod, 1), 1)} %" if pd.notna(pct_prod) else "—")
    m3.metric("Árboles productores",
              f"{_fmt_es_number(int(arb_prod), 0)} / {_fmt_es_number(int(arb_tot), 0)}")
    m4.metric("Kg/árbol productor",
              _fmt_es_number(round(kg_arbol_prod, 1), 1) if pd.notna(kg_arbol_prod) else "—")

    st.caption(
        "El % de árboles productores es el agregado de la selección (árboles que "
        "produjeron ÷ árboles totales). Con varios años o variedades es la media "
        "ponderada por número de árboles."
    )

    # ── Tabla por año (agregando portainjertos / variedades) ──────────────────
    if len(años_sel) > 1:
        st.markdown("#### Por año")
        por_año = sel.groupby("Año").agg(
            Kg=("Kg", "sum"),
            Ha=("Ha", "sum"),
            Arboles_tot=("Num_arboles", "sum"),
            Arboles_prod=("Arboles_prod", "sum"),
        )
        por_año["% productores"] = (por_año["Arboles_prod"] / por_año["Arboles_tot"].replace(0, np.nan) * 100).round(1)
        por_año["Kg/árbol prod."] = (por_año["Kg"] / por_año["Arboles_prod"].replace(0, np.nan)).round(1)
        por_año["Kg/Ha"] = (por_año["Kg"] / por_año["Ha"].replace(0, np.nan)).round(0)
        por_año = por_año.rename(columns={"Arboles_tot": "Árboles totales", "Arboles_prod": "Árboles prod."})
        render_year_table(
            por_año[["Kg", "Árboles totales", "Árboles prod.", "% productores", "Kg/árbol prod.", "Kg/Ha"]],
            index_label="Año",
        )
        st.bar_chart(por_año["Kg"].rename(index=str), color="#4caf7d")
        st.caption(
            "Kg por año. Los dientes de sierra (un año alto seguido de uno bajo) "
            "anticipan la vecería, que cuantificaremos en la siguiente fase."
        )

    # ── Desglose por portainjerto ─────────────────────────────────────────────
    st.markdown("#### Desglose por portainjerto")
    _gallinal_breakdown(sel, "Portainjerto_nombre", "Portainjerto")
    st.caption(
        "Agregado de los años seleccionados. Los portainjertos más vigorosos suelen "
        "mostrar más vecería (mayor variación de cosecha entre años)."
    )

    # ── Desglose por variedad (solo si se eligió '(Todas)') ───────────────────
    if variedad_sel == "(Todas)" and sel["Variedad_nombre"].nunique() > 1:
        st.markdown("#### Desglose por variedad")
        _gallinal_breakdown(sel, "Variedad_nombre", "Variedad")

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 2 · Regularidad productiva: cosecha sostenida (Kg/Ha) + participación
    #          estable de los árboles (los dos pilares del objetivo)
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("### 📈 Regularidad productiva y vecería")

    with st.expander("ℹ️ Los dos pilares del objetivo y cómo se miden"):
        st.markdown(
            "El objetivo de cada campo y variedad es producir **~20.000 Kg/Ha cada "
            "año, de forma sostenida**. Eso depende de **dos pilares** que medimos "
            "juntos (no basta uno):\n\n"
            "**1️⃣ Cosecha alta y regular (Kg/Ha) — el criterio que MÁS pesa.** Lo "
            "importante son los Kg/Ha, no los Kg por árbol. *Ejemplo:* 90% de árboles "
            "a 5 kg → 12.000 Kg/Ha es **peor** que 75% de árboles a 10 kg → 19.000 "
            "Kg/Ha. Y aquí influye mucho el portainjerto: **a menor vigor, más árboles "
            "por Ha**, y más fácil acercarse a los 20.000 aunque cada árbol dé menos "
            "(lo ganas en número de árboles). La regularidad entre años se mide con el "
            "**Índice de Vecería (BBI)** de Hoblyn (1936) sobre años consecutivos:\n\n"
            "$$BBI = \\frac{1}{n-1}\\sum \\frac{|V_n - V_{n-1}|}{V_n + V_{n-1}}$$\n\n"
            "**0 = cosecha regular**, **1 = alternancia total**.\n\n"
            "**2️⃣ Participación de los árboles (% productores) alta y constante.** "
            "Que muchos árboles produzcan **y repitan año tras año**. Cuanto más cerca "
            "del 100% y más constante, mejor.\n\n"
            "**🏅 Índice de Excelencia Productiva (IEP, 0–100):** combina los dos "
            "pilares dando **más peso al Kg/Ha (65%)** que a la participación (35%). "
            "Resume cómo de cerca está cada combinación de la excelencia (≈20.000 "
            "Kg/Ha con casi todos los árboles produciendo). Bandas: ≥85 excelente · "
            "70–85 bueno · 50–70 mejorable · <50 bajo.\n\n"
            "Los **puntos** del patrón muestran cada año: 🟢 año de carga (≥ mediana), "
            "⚪ año de descarga (< mediana).\n\n"
            "⚠️ **No confundir BBI y Constancia:** el **BBI** mide si la *cosecha* "
            "(Kg/Ha) sube y baja entre años; la **Constancia** mide si el *% de "
            "árboles que producen* se mantiene estable. Son ejes distintos: un campo "
            "puede dar muchos Kg/Ha pero con participación variable, o pocos Kg/Ha "
            "pero con casi todos los árboles cargando cada año."
        )

    cobj, cmet, csort = st.columns([1, 1.3, 1.1])
    with cobj:
        objetivo_kgha = st.number_input(
            "Objetivo Kg/Ha", min_value=0, value=20000, step=1000,
            key="gallinal_objetivo_kgha",
        )
    with cmet:
        metric_vec = st.radio(
            "Métrica base de la vecería",
            ["Kg/Ha (cosecha)", "Kg por árbol productor"],
            horizontal=True,
            key="gallinal_veceria_metric",
            help="'Kg/Ha (cosecha)' es la métrica del objetivo y refleja la vecería "
                 "real. 'Kg por árbol productor' aísla la intensidad por árbol, pero "
                 "OJO: oculta el problema de que pocos árboles carguen mucho.",
        )
    with csort:
        orden_vec = st.radio(
            "Ordenar por",
            ["Excelencia (IEP)", "Vecería (BBI)"],
            horizontal=True,
            key="gallinal_veceria_orden",
        )

    # ── Filtros de la tabla (campo / variedad / años) ─────────────────────────
    # Útil para excluir, p.ej., los primeros años de un campo joven que aún no
    # produce y falsearían la vecería. Por defecto: todo incluido.
    st.markdown("**Filtrar** (por defecto: todos los campos, variedades y años):")
    fc1, fc2, fc3 = st.columns([1, 1, 1.7])
    with fc1:
        _campos_v = ["(Todos)"] + sorted(prod["Campo"].unique())
        campo_v = st.selectbox("Campo", _campos_v, key="gallinal_vec_campo")
    with fc2:
        if campo_v != "(Todos)":
            _vars_v = sorted(prod[prod["Campo"] == campo_v]["Variedad_nombre"].unique())
        else:
            _vars_v = sorted(prod["Variedad_nombre"].unique())
        variedad_v = st.selectbox("Variedad", ["(Todas)"] + _vars_v, key="gallinal_vec_var")
    with fc3:
        _años_all = sorted(int(a) for a in prod["Año"].unique())
        años_v = st.multiselect("Años (deselecciona los que no quieras contar)",
                                _años_all, default=_años_all, key="gallinal_vec_años")

    prod_vec = prod.copy()
    if campo_v != "(Todos)":
        prod_vec = prod_vec[prod_vec["Campo"] == campo_v]
    if variedad_v != "(Todas)":
        prod_vec = prod_vec[prod_vec["Variedad_nombre"] == variedad_v]
    if años_v:
        prod_vec = prod_vec[prod_vec["Año"].isin(años_v)]
    else:
        st.caption("⚠️ No has seleccionado años: se muestran todos.")

    gvals = _veceria_yearly_values(prod_vec, metric_vec)

    # ── Métricas por cada Campo × Variedad × Portainjerto ─────────────────────
    records = []
    excluidos = 0
    for (g_campo, g_var, g_porta), subg in gvals.groupby(
        ["Campo", "Variedad_nombre", "Portainjerto_nombre"]
    ):
        subg = subg.dropna(subset=["valor"]).sort_values("Año")
        years = subg["Año"].astype(int).tolist()
        vals = subg["valor"].astype(float).tolist()
        bbi, trans = _compute_bbi(years, vals)
        if trans < 1:
            excluidos += 1
            continue
        kg_ha_medio = float(subg["kg_ha"].mean())
        pct_serie = subg["pct_prod"].dropna()
        pct_medio = float(pct_serie.mean()) if not pct_serie.empty else np.nan
        pct_std = float(pct_serie.std(ddof=0)) if len(pct_serie) > 1 else np.nan
        pct_min = float(pct_serie.min()) if not pct_serie.empty else np.nan
        pct_max = float(pct_serie.max()) if not pct_serie.empty else np.nan
        densidad = float((subg["Num_arboles"] / subg["Ha"].replace(0, np.nan)).mean())
        iep = _iep_score(kg_ha_medio, pct_medio, objetivo_kgha)
        records.append({
            "label": f"{g_campo} · {g_var} · {g_porta}",
            "porta": g_porta,
            "n_years": len(years),
            "n_trans": trans,
            "bbi": bbi,
            "kg_ha_medio": kg_ha_medio,
            "pct_medio": pct_medio,
            "pct_std": pct_std,
            "pct_min": pct_min,
            "pct_max": pct_max,
            "densidad": densidad,
            "iep": iep,
            "pattern": _veceria_pattern_html(years, vals),
        })

    # Orden según elección del usuario
    if orden_vec == "Excelencia (IEP)":
        # mejores primero (IEP alto); NaN al final
        records.sort(key=lambda r: (-1e9 if pd.isna(r["iep"]) else r["iep"]), reverse=True)
    else:
        # más veceros primero (BBI alto)
        records.sort(key=lambda r: (-1 if pd.isna(r["bbi"]) else r["bbi"]), reverse=True)

    if not records:
        st.info(
            "Aún no hay suficientes años CONSECUTIVOS por combinación para el análisis "
            "(hace falta al menos 2 años seguidos)."
        )
    else:
        st.markdown("#### Por campo · variedad · portainjerto")
        _headers = [
            ("Campo · Variedad · Portainjerto", "left"),
            ("IEP", "right"), ("Kg/Ha medio", "right"), ("% prod. medio", "right"),
            ("BBI", "right"), ("Constancia % prod.", "center"),
            ("Patrón (años →)", "left"),
        ]
        _rows = []
        for r in records:
            _, bbi_fg, _ = _veceria_level(r["bbi"])
            cons_lbl, cfg, cbg = _constancia_label(r["pct_std"])
            _rango_txt = (
                f' <span style="color:#777;font-size:11px;white-space:nowrap;">'
                f'{_fmt_es_number(round(r["pct_min"]), 0)}–'
                f'{_fmt_es_number(round(r["pct_max"]), 0)} %</span>'
                if pd.notna(r["pct_std"]) and pd.notna(r.get("pct_min")) else ""
            )
            cons_badge = (f'<span style="background:{cbg};color:{cfg};'
                          f'border-radius:4px;padding:2px 8px;font-size:12px;'
                          f'font-weight:600;">{cons_lbl}</span>{_rango_txt}')
            iep_lbl, iep_col = _iep_level(r["iep"])
            iep_html = (
                f'<span title="{iep_lbl}" style="color:{iep_col};font-weight:700;'
                f'font-size:14px;">{_fmt_es_number(round(r["iep"]),0)}</span>'
                if pd.notna(r["iep"]) else '<span style="color:#9e9e9e;">—</span>'
            )
            _rows.append([
                r["label"],
                iep_html,
                _kgha_target_html(r["kg_ha_medio"], objetivo_kgha),
                _colored_num(r["pct_medio"], _pct_prod_color(r["pct_medio"]), 1, " %"),
                _colored_num(r["bbi"], bbi_fg, 2),
                cons_badge, r["pattern"],
            ])
        _render_html_table(_headers, _rows)
        _orden_txt = "mejor IEP primero" if orden_vec == "Excelencia (IEP)" else "más vecero primero"
        _cap = (
            f"Columnas: **IEP** = nota global de excelencia 0–100 (Kg/Ha pesa 65 %, "
            f"participación 35 %): ≥85 excelente · 70–85 bueno · 50–70 mejorable · <50 bajo. · "
            f"**Kg/Ha medio**: cosecha media, en verde si llega al objetivo "
            f"({_fmt_es_number(objetivo_kgha,0)}). · **% prod. medio**: cuántos árboles "
            f"producen de media. · **BBI**: vecería de la cosecha (0 regular … 1 alternancia). · "
            f"**Constancia % prod.**: si ese % se repite cada año (al lado, el rango entre años). · "
            f"**Patrón**: 🟢 año de carga / ⚪ año de descarga. Ordenado: {_orden_txt}.")
        if excluidos:
            _cap += f" {excluidos} combinación(es) sin años consecutivos suficientes no se muestran."
        st.caption(_cap)

        # ── Resumen por portainjerto (los dos pilares + densidad + vigor) ──────
        df_rec = pd.DataFrame(records)
        porta_rows = []
        for g_porta, subp in df_rec.groupby("porta"):
            valid = subp.dropna(subset=["bbi"])
            if valid.empty:
                continue
            w = valid["n_trans"].astype(float)
            bbi_mean = (np.average(valid["bbi"], weights=w) if w.sum() > 0
                        else float(valid["bbi"].mean()))
            kg_ha_mean = float(valid["kg_ha_medio"].mean())
            pct_mean = float(valid["pct_medio"].mean())
            porta_rows.append({
                "porta": g_porta,
                "n": len(valid),
                "bbi": bbi_mean,
                "kg_ha": kg_ha_mean,
                "pct": pct_mean,
                "densidad": float(valid["densidad"].mean()),
                "iep": _iep_score(kg_ha_mean, pct_mean, objetivo_kgha),
            })
        # mejor IEP primero (la excelencia productiva)
        porta_rows.sort(key=lambda r: (-1e9 if pd.isna(r["iep"]) else r["iep"]), reverse=True)

        if porta_rows:
            st.markdown("#### Resumen por portainjerto")
            _h2 = [("Portainjerto", "left"), ("Comb.", "right"), ("IEP", "right"),
                   ("Kg/Ha medio", "right"), ("% prod. medio", "right"),
                   ("Árboles/Ha", "right"), ("BBI medio", "right")]
            _r2 = []
            for pr in porta_rows:
                _, bbi_fg, _ = _veceria_level(pr["bbi"])
                iep_lbl, iep_col = _iep_level(pr["iep"])
                iep_html = (f'<span title="{iep_lbl}" style="color:{iep_col};font-weight:700;'
                            f'font-size:14px;">{_fmt_es_number(round(pr["iep"]),0)}</span>'
                            if pd.notna(pr["iep"]) else '<span style="color:#9e9e9e;">—</span>')
                _r2.append([
                    pr["porta"], str(pr["n"]), iep_html,
                    _kgha_target_html(pr["kg_ha"], objetivo_kgha),
                    _colored_num(pr["pct"], _pct_prod_color(pr["pct"]), 1, " %"),
                    _fmt_es_number(round(pr["densidad"]), 0),
                    _colored_num(pr["bbi"], bbi_fg, 2),
                ])
            _render_html_table(_h2, _r2, max_height=340)
            st.caption("Ordenado por IEP (excelencia). **Árboles/Ha** = densidad: a menor "
                       "vigor del portainjerto, más densidad y más fácil llegar al objetivo "
                       "con menos kg por árbol.")

            # ── Narrativa ──────────────────────────────────────────────────────
            best_porta = porta_rows[0]
            most_vecero = max(porta_rows, key=lambda r: (-1 if pd.isna(r["bbi"]) else r["bbi"]))
            _bp_lbl, _ = _iep_level(best_porta["iep"])
            _mv_n, _, _ = _veceria_level(most_vecero["bbi"])
            st.markdown(
                f"**Portainjerto más cerca de la excelencia:** {best_porta['porta']} "
                f"(IEP {_fmt_es_number(round(best_porta['iep']),0)} → {_bp_lbl.lower()}, "
                f"{_fmt_es_number(round(best_porta['kg_ha']),0)} Kg/Ha, "
                f"{_fmt_es_number(round(best_porta['pct'],1),1)} % productores, "
                f"{_fmt_es_number(round(best_porta['densidad']),0)} árb/Ha). "
                f"**Más vecero:** {most_vecero['porta']} "
                f"(BBI {_fmt_es_number(round(most_vecero['bbi'],2),2)} → {_mv_n.lower()})."
            )

    # ── Drill-down: detalle año por año de una combinación ────────────────────
    if not gvals.empty:
        st.markdown("#### 🔬 Detalle año por año de una combinación")
        combo_map = {}
        for _c, _v, _p in (gvals[["Campo", "Variedad_nombre", "Portainjerto_nombre"]]
                           .drop_duplicates().itertuples(index=False, name=None)):
            combo_map[f"{_c} · {_v} · {_p}"] = (_c, _v, _p)
        combo_labels = sorted(combo_map.keys())
        _default_idx = 0
        if records:
            try:
                _default_idx = combo_labels.index(records[0]["label"])
            except ValueError:
                _default_idx = 0
        combo_sel = st.selectbox("Combinación", combo_labels, index=_default_idx,
                                 key="gallinal_drill")
        _dc, _dv, _dp = combo_map[combo_sel]
        det = gvals[(gvals["Campo"] == _dc) &
                    (gvals["Variedad_nombre"] == _dv) &
                    (gvals["Portainjerto_nombre"] == _dp)].sort_values("Año").copy()

        if det.empty:
            st.info("Sin datos para esa combinación.")
        else:
            rec = next((r for r in records if r["label"] == combo_sel), None)
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Kg/Ha medio", _fmt_es_number(round(det["kg_ha"].mean()), 0))
            _pm = det["pct_prod"].mean()
            d2.metric("% prod. medio",
                      f"{_fmt_es_number(round(_pm, 1), 1)} %" if pd.notna(_pm) else "—")
            d3.metric("BBI (vecería)",
                      _fmt_es_number(round(rec["bbi"], 2), 2)
                      if rec and pd.notna(rec.get("bbi")) else "—")
            if rec and pd.notna(rec.get("iep")):
                _il, _ = _iep_level(rec["iep"])
                d4.metric("IEP", _fmt_es_number(round(rec["iep"]), 0), help=_il)
            else:
                d4.metric("IEP", "—")

            # Diagnóstico accionable del patrón (prominente, bajo las métricas)
            if rec is not None:
                _kind, _msg = _drill_pattern_message(rec.get("bbi"), rec.get("pct_std"))
                if _kind == "success":
                    st.success(_msg)
                elif _kind == "warning":
                    st.warning(_msg)
                else:
                    st.info(_msg)

            # Tabla año por año — Nivel cosecha = nivel ABSOLUTO vs objetivo
            def _nivel_html(k):
                lbl, col = _nivel_cosecha(k, objetivo_kgha)
                return f'<span style="color:{col};font-weight:600;">{lbl}</span>'
            det["Nivel cosecha"] = det["kg_ha"].apply(_nivel_html)
            det["Kg/árbol prod."] = (det["Kg"] / det["Arboles_prod"].replace(0, np.nan)).round(1)
            det["% prod."] = det["pct_prod"].round(1)
            det["Kg/Ha"] = det["kg_ha"].round(0)
            detail_df = det.set_index("Año")[
                ["Kg", "Kg/Ha", "Num_arboles", "Arboles_prod", "% prod.",
                 "Kg/árbol prod.", "Nivel cosecha"]
            ].rename(columns={"Num_arboles": "Árboles tot.", "Arboles_prod": "Árboles prod."})
            render_year_table(detail_df, index_label="Año", max_height=400)
            st.caption(
                f"**Nivel cosecha** = nivel absoluto del año vs el objetivo "
                f"({_fmt_es_number(objetivo_kgha,0)} Kg/Ha): Alta ≥90% · Media-alta 65–90% · "
                f"Media-baja 40–65% · Baja <40%. (Es distinto del 🟢/⚪ del patrón, que marca "
                f"subida/bajada respecto a la mediana de la propia combinación.)"
            )

            # Gráficas: Kg/Ha y % productores por año
            det_idx = det.assign(_a=det["Año"].astype(str)).set_index("_a")
            gc1, gc2 = st.columns(2)
            with gc1:
                st.bar_chart(det_idx["kg_ha"], color="#4caf7d")
                st.caption("Kg/Ha por año")
            with gc2:
                st.line_chart(det_idx["pct_prod"], color="#2196f3")
                st.caption("% árboles productores por año")

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 5 · Campo vs Campo (H2H)
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("### ⚔️ Campo vs Campo (H2H)")
    st.caption("Enfrenta dos campos en los mismos años. Puedes filtrar variedades y "
               "elegir los años que quieras, aunque no sean consecutivos.")

    _campos_all = sorted(prod["Campo"].unique())
    if len(_campos_all) < 2:
        st.info("Hacen falta al menos 2 campos con datos para comparar.")
    else:
        hc1, hc2, hc3 = st.columns(3)
        with hc1:
            campo_a = st.selectbox("🔵 Campo A", _campos_all, index=0, key="h2h_a")
        with hc2:
            campo_b = st.selectbox("🔴 Campo B", _campos_all,
                                   index=min(1, len(_campos_all) - 1), key="h2h_b")
        with hc3:
            _años_h_all = sorted(int(a) for a in prod["Año"].unique())
            años_h = st.multiselect("Años (no hace falta que sean seguidos)",
                                    _años_h_all, default=_años_h_all, key="h2h_años")
        _vars_ab = sorted(set(prod[prod["Campo"].isin([campo_a, campo_b])]["Variedad_nombre"]))
        vars_h = st.multiselect("Variedades (vacío = todas)", _vars_ab, default=[], key="h2h_var")

        def _h2h_stats(campo):
            d = prod[(prod["Campo"] == campo) & (prod["Año"].isin(años_h))]
            if vars_h:
                d = d[d["Variedad_nombre"].isin(vars_h)]
            if d.empty:
                return None
            g = d.groupby("Año").agg(Kg=("Kg", "sum"), Ha=("Ha", "sum"),
                                     Nt=("Num_arboles", "sum"), Np=("Arboles_prod", "sum"))
            g["kg_ha"] = g["Kg"] / g["Ha"].replace(0, np.nan)
            g["pct"] = g["Np"] / g["Nt"].replace(0, np.nan) * 100
            kg_ha = float(g["kg_ha"].mean()); pct = float(g["pct"].mean())
            bbi, trans = _compute_bbi([int(y) for y in g.index], g["kg_ha"].tolist())
            return {"kg_ha": kg_ha, "pct": pct, "iep": _iep_score(kg_ha, pct, objetivo_kgha),
                    "kg_tot": float(d["Kg"].sum()), "bbi": bbi, "trans": trans, "g": g}

        if campo_a == campo_b:
            st.warning("Elige dos campos distintos.")
        elif not años_h:
            st.warning("Selecciona al menos un año.")
        else:
            sa, sb = _h2h_stats(campo_a), _h2h_stats(campo_b)
            if sa is None or sb is None:
                st.warning("Algún campo no tiene datos para esa combinación de variedades/años.")
            else:
                _wins = {"a": 0, "b": 0}

                def _cmp_row(label, va, vb, better, fmt, suf=""):
                    if pd.isna(va) or pd.isna(vb):
                        gan, ca, cb = "—", "#333", "#333"
                    elif abs(va - vb) < 1e-9:
                        gan, ca, cb = "Empate", "#333", "#333"
                    elif (va > vb) if better == "high" else (va < vb):
                        gan, ca, cb = f"🔵 {campo_a}", "#1565c0", "#999"; _wins.__setitem__("a", _wins["a"] + 1)
                    else:
                        gan, ca, cb = f"🔴 {campo_b}", "#999", "#c62828"; _wins.__setitem__("b", _wins["b"] + 1)
                    _va = (f'<span style="color:{ca};font-weight:600;">{fmt(va)}{suf}</span>'
                           if pd.notna(va) else "—")
                    _vb = (f'<span style="color:{cb};font-weight:600;">{fmt(vb)}{suf}</span>'
                           if pd.notna(vb) else "—")
                    return [label, _va, _vb, gan]

                _f0 = lambda x: _fmt_es_number(round(x), 0) if pd.notna(x) else "—"
                _f1 = lambda x: _fmt_es_number(round(x, 1), 1) if pd.notna(x) else "—"
                _f2 = lambda x: _fmt_es_number(round(x, 2), 2) if pd.notna(x) else "—"
                _rows_h = [
                    _cmp_row("Kg/Ha medio", sa["kg_ha"], sb["kg_ha"], "high", _f0),
                    _cmp_row("% prod. medio", sa["pct"], sb["pct"], "high", _f1, " %"),
                    _cmp_row("IEP (excelencia)", sa["iep"], sb["iep"], "high", _f0),
                    _cmp_row("Kg totales", sa["kg_tot"], sb["kg_tot"], "high", _f0),
                ]
                _bbi_ok = sa["trans"] >= 1 and sb["trans"] >= 1
                if _bbi_ok:
                    _rows_h.append(_cmp_row("Vecería (BBI · menos = mejor)",
                                            sa["bbi"], sb["bbi"], "low", _f2))
                _render_html_table(
                    [("Métrica", "left"), (f"🔵 {campo_a}", "right"),
                     (f"🔴 {campo_b}", "right"), ("Ganador", "center")],
                    _rows_h, max_height=320)
                if not _bbi_ok:
                    st.caption("La **vecería (BBI)** no se muestra: necesita ≥2 años "
                               "consecutivos en la selección. El resto de métricas sí valen "
                               "con años sueltos (p. ej. 2020, 2022, 2024).")
                if _wins["a"] > _wins["b"]:
                    st.success(f"🏆 **{campo_a}** gana el H2H ({_wins['a']}–{_wins['b']}).")
                elif _wins["b"] > _wins["a"]:
                    st.success(f"🏆 **{campo_b}** gana el H2H ({_wins['b']}–{_wins['a']}).")
                else:
                    st.info(f"🤝 Empate técnico ({_wins['a']}–{_wins['b']}).")
                _cmp = pd.DataFrame({campo_a: sa["g"]["kg_ha"], campo_b: sb["g"]["kg_ha"]})
                _cmp.index = _cmp.index.astype(str)
                st.line_chart(_cmp)
                st.caption("Kg/Ha por año de cada campo (mismos años).")

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 3 · Índice Climático por fases fenológicas (finca, por año)
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("### 🌡️ Índice Climático por fases (por año)")

    temp_col_g = next((c for c in ["temp_media", "temp", "temperatura", "Temperatura", "temp_avg"]
                       if history is not None and not history.empty and c in history.columns), None)
    if history is None or history.empty or temp_col_g is None or "fecha_hora" not in history.columns:
        st.info("Carga el histórico climático (con temperatura) para calcular el índice climático por año.")
    else:
        with st.expander("ℹ️ Cómo se calcula el Índice Climático"):
            st.markdown(
                "Para cada año puntúo (0–100) el clima de cada fase fenológica y las "
                "combino en un **Índice Climático (IC)** ponderado. Es **idoneidad "
                "climática pura** (no producción): mide si el año fue favorable. En la "
                "Fase 4 se cruzará con tu producción/IEP/vecería para separar clima de "
                "portainjerto/vecería/prácticas.\n\n"
                "- 🥶 **Frío:** acumulación de frío (1 Nov–31 Mar) vs requerimiento. Eliges "
                "la métrica: **horas de frío** (la de Dapena/el sector), Utah o Chill "
                "Portions. La app calcula las tres y muestra las tres en el detalle.\n"
                "- 🌱 **Brotación:** calor acumulado (GDD).\n"
                "- 🌸 **Floración:** heladas (penaliza fuerte) + clima de polinización "
                "(horas en 12–25 °C, lluvia).\n"
                "- 🍏 **Cuajado:** heladas tardías + temperatura moderada.\n"
                "- ☀️ **Engorde:** estrés por calor (días > umbral) + déficit hídrico.\n"
                "- 🍎 **Maduración:** temperatura para azúcares.\n\n"
                "Ventanas, pesos y umbrales son **editables** abajo."
            )

        _MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                  "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        with st.expander("📅 Ventanas fenológicas (editar — mes y día, sin año)"):
            st.caption(
                "El **Frío** va de **1 Nov (año anterior) → 31 Mar** — el mismo criterio que "
                "el item Frío y la correlación (fuente: SERIDA/Delgado 2021, sidra asturiana). "
                "Es normal que el mes de inicio (Nov) sea posterior al de fin (Mar): la ventana "
                "cruza el cambio de año. El resto de fases son del mismo año."
            )
            _hc = st.columns([2.2, 1.5, 1, 1.5, 1])
            _hc[1].caption("Mes inicio"); _hc[2].caption("Día")
            _hc[3].caption("Mes fin"); _hc[4].caption("Día")
            edited_phases = []
            for (pid, label, sm, sd, em, ed, w) in _GALLINAL_PHASES:
                c0, c1, c2, c3, c4 = st.columns([2.2, 1.5, 1, 1.5, 1])
                c0.markdown(f"**{label}**")
                _mi = c1.selectbox("mi", _MESES, index=sm - 1,
                                   key=f"gph_mi_{pid}", label_visibility="collapsed")
                _ddi = c2.number_input("di", 1, 31, sd,
                                       key=f"gph_di_{pid}", label_visibility="collapsed")
                _mf = c3.selectbox("mf", _MESES, index=em - 1,
                                   key=f"gph_mf_{pid}", label_visibility="collapsed")
                _ddf = c4.number_input("df", 1, 31, ed,
                                       key=f"gph_df_{pid}", label_visibility="collapsed")
                edited_phases.append((pid, label, _MESES.index(_mi) + 1, int(_ddi),
                                      _MESES.index(_mf) + 1, int(_ddf), w))

        with st.expander("⚙️ Ajustes del modelo (pesos y umbrales)"):
            st.markdown("**Pesos de cada fase** (se normalizan al sumar):")
            weights = {}
            wcols = st.columns(len(edited_phases))
            for _i, (pid, label, _a, _b, _c, _d, w) in enumerate(edited_phases):
                weights[pid] = wcols[_i].slider(label, 0, 50, int(w), key=f"gw_{pid}")
            st.markdown("**Frío** — elige la métrica (la app calcula las tres):")
            fm1, fm2 = st.columns([1.3, 1])
            _frio_lbl = fm1.selectbox(
                "Métrica de frío",
                ["Horas de frío (<7,2 °C)", "Utah (CU)", "Chill Portions"],
                index=0, key="g_frio_metric",
                help="Horas de frío = la métrica que usa el SERIDA/Dapena con el sector "
                     "(la que oyes en las charlas). Utah y Chill Portions son modelos más "
                     "elaborados. OJO: el requerimiento por variedad solo está publicado "
                     "en Chill Portions (Regona ≈ 90 CP); en horas/Utah lo calibras tú.",
            )
            _frio_metric = {"Horas de frío (<7,2 °C)": "horas", "Utah (CU)": "utah",
                            "Chill Portions": "cp"}[_frio_lbl]
            if _frio_metric == "cp":
                frio_req = fm2.slider("Requerim. (CP)", 30, 110, 90, key="g_req_cp",
                                      help="Regona ≈ 90 CP (SERIDA/Delgado 2021; rango 59–90).")
            elif _frio_metric == "utah":
                frio_req = fm2.slider("Requerim. (Utah CU)", 400, 2000, 1300, step=50,
                                      key="g_req_utah",
                                      help="Asturias acumula ~1.300–1.430 Utah CU por invierno "
                                           "(SERIDA). Sin requerimiento por variedad publicado: calíbralo.")
            else:
                frio_req = fm2.slider("Requerim. (horas <7,2 °C)", 300, 1500, 900, step=25,
                                      key="g_req_horas",
                                      help="Asturias acumula ~800–1.100 h/invierno (SERIDA). "
                                           "Sin requerimiento por variedad publicado: calíbralo "
                                           "(o pregunta a Dapena por tu variedad).")
            st.markdown("**Otros umbrales:**")
            u2c, u3c = st.columns(2)
            frost_thr = u2c.slider(
                "Umbral helada (°C)", -5, 2, -2, key="g_frost",
                help="El daño por helada en flor/cuajado empieza a −2 °C: 10 % de pérdida "
                     "a −2,2 °C y 90 % a −4,4 °C (MSU/USU, temperaturas críticas del manzano). "
                     "Por eso el defecto es −2 °C, no 0.")
            heat_thr = u3c.slider(
                "Umbral calor (°C)", 28, 38, 32, key="g_heat",
                help="Estrés de calor en el fruto: daño claro de firmeza/fotosíntesis a "
                     "35 °C; golpe de sol cuando la piel supera ~46 °C, lo que pasa con aire "
                     "≥35 °C y sol (UC Davis/WSU). 32 °C es una precaución conservadora.")

        params = {"frio_metric": _frio_metric, "frio_req": float(frio_req),
                  "gdd_ref": 120.0, "rain_min_engorde": 120.0}

        # Cálculo por año (años de producción)
        ic_rows = []
        detail = {}
        for y in años_disp:
            pscores, pmetrics = {}, {}
            for (pid, label, sm, sd, em, ed, w) in edited_phases:
                _start, _end = _phase_window(sm, sd, em, ed, int(y))
                m = _phase_metrics(history, _start, _end, temp_col_g,
                                   frost_thr=float(frost_thr), heat_thr=float(heat_thr))
                pscores[pid] = _score_phase(pid, m, params)
                pmetrics[pid] = (m, _start, _end)
            _num = _den = 0.0
            for (pid, *_r) in edited_phases:
                s = pscores[pid]
                if pd.notna(s):
                    _num += weights[pid] * s
                    _den += weights[pid]
            ic = (_num / _den) if _den > 0 else np.nan
            ic_rows.append((y, pscores, ic))
            detail[y] = (pmetrics, pscores, ic)

        # Tabla año × fases + IC
        _hh = ([("Año", "left")]
               + [(label, "right") for (pid, label, *_r) in edited_phases]
               + [("IC", "right")])
        _rr = []
        for (y, pscores, ic) in ic_rows:
            _cells = [str(int(y))]
            for (pid, label, *_r) in edited_phases:
                s = pscores[pid]
                _cells.append(_colored_num(s, _score_color(s), 0))
            _cells.append(
                f'<span style="color:{_score_color(ic)};font-weight:700;font-size:14px;">'
                f'{_fmt_es_number(round(ic), 0)}</span>'
                if pd.notna(ic) else '<span style="color:#9e9e9e;">—</span>'
            )
            _rr.append(_cells)
        _render_html_table(_hh, _rr, max_height=420)
        st.caption("Puntuación 0–100 por fase (verde alto, rojo bajo). **IC** = Índice "
                   "Climático del año (media ponderada de las fases con datos).")

        # Detalle climático de un año
        st.markdown("#### Detalle climático de un año")
        ysel = st.selectbox("Año", años_disp, index=len(años_disp) - 1, key="g_ic_year")
        pmetrics, pscores, ic = detail[ysel]
        _dh = [("Fase", "left"), ("Ventana", "left"), ("Clima", "left"), ("Score", "right")]
        _dr = []
        for (pid, label, sm, sd, em, ed, w) in edited_phases:
            m, _start, _end = pmetrics[pid]
            ventana = f"{_start.strftime('%d/%m/%Y')} – {_end.strftime('%d/%m/%Y')}"
            s = pscores[pid]
            _dr.append([label, ventana, _phase_clima_text(pid, m),
                        _colored_num(s, _score_color(s), 0)])
        _render_html_table(_dh, _dr, max_height=320)
        if pd.notna(ic):
            st.markdown(f"**Índice Climático {ysel}: "
                        f"<span style='color:{_score_color(ic)};font-weight:700;'>"
                        f"{_fmt_es_number(round(ic),0)}/100</span>**", unsafe_allow_html=True)

        # ══════════════════════════════════════════════════════════════════════
        # FASE 4 · Índice Gallinal (IG) — clima calibrado con la producción
        # ══════════════════════════════════════════════════════════════════════
        st.markdown("---")
        st.markdown("### 🏅 Índice Gallinal (IG) · clima calibrado con tu producción")

        with st.expander("ℹ️ Qué es el Índice Gallinal y cómo se calibra"):
            st.markdown(
                "El **IG** es el Índice Climático pero con los **pesos de cada fase "
                "aprendidos de TU producción**: mide la correlación de cada fase con "
                "tus Kg/Ha de finca y da más peso a las que de verdad explican la "
                "cosecha. Una fase que no discrimina (como el frío, que casi siempre se "
                "cumple) recibe peso ≈0 sola.\n\n"
                "El **deslizador de confianza** mezcla esos pesos calibrados con tus "
                "pesos manuales (0 % = solo tu criterio, 100 % = solo los datos).\n\n"
                "Y el **diagnóstico** cruza clima ↔ cosecha para responder lo que "
                "buscábamos desde el principio: *¿un año flojo fue por el clima o por "
                "la vecería/manejo?*\n\n"
                "⚠️ Con pocos años, las correlaciones son **indicios**, no certezas. "
                "La vecería mete ruido; cuantos más años, más fiable."
            )

        # Producción de finca (Kg/Ha) por año
        kgha_year = {}
        for y in años_disp:
            _d = prod[prod["Año"] == y]
            _ha = _d["Ha"].sum()
            kgha_year[y] = (_d["Kg"].sum() / _ha) if _ha > 0 else np.nan

        phase_ids = [pid for (pid, *_r) in edited_phases]
        # Correlación de cada fase con Kg/Ha de finca
        corr = {}
        for pid in phase_ids:
            xs, ys = [], []
            for y in años_disp:
                s = detail[y][1].get(pid, np.nan)
                k = kgha_year[y]
                if pd.notna(s) and pd.notna(k):
                    xs.append(s); ys.append(k)
            if len(xs) >= 4 and np.std(xs) > 0 and np.std(ys) > 0:
                corr[pid] = float(np.corrcoef(xs, ys)[0, 1])
            else:
                corr[pid] = np.nan
        n_pairs = sum(1 for y in años_disp
                      if pd.notna(kgha_year[y]) and pd.notna(detail[y][2]))

        # Pesos manuales (de la Fase 3) y calibrados (∝ correlación positiva)
        _msum = sum(weights[pid] for pid in phase_ids) or 1
        manual_norm = {pid: weights[pid] / _msum for pid in phase_ids}
        cal_raw = {pid: (max(0.0, corr[pid]) if pd.notna(corr[pid]) else 0.0) for pid in phase_ids}
        _csum = sum(cal_raw.values())
        cal_norm = ({pid: cal_raw[pid] / _csum for pid in phase_ids} if _csum > 0
                    else dict(manual_norm))

        conf = st.slider(
            "Confianza en la calibración (%)  ·  0 = solo pesos manuales · 100 = solo datos",
            0, 100, 70, key="g_ig_conf") / 100.0
        final_w = {pid: conf * cal_norm[pid] + (1 - conf) * manual_norm[pid] for pid in phase_ids}

        # Tabla de calibración
        _ch = [("Fase", "left"), ("r con Kg/Ha", "right"), ("Peso calibrado", "right"),
               ("Peso manual", "right"), ("Peso final", "right")]
        _cr = []
        for (pid, label, *_r) in edited_phases:
            _rv = corr[pid]
            _rhtml = (_colored_num(_rv, "#2e7d32" if (pd.notna(_rv) and _rv > 0) else "#c62828", 2)
                      if pd.notna(_rv) else '<span style="color:#9e9e9e;">—</span>')
            _cr.append([label, _rhtml,
                        f'{_fmt_es_number(round(cal_norm[pid]*100),0)} %',
                        f'{_fmt_es_number(round(manual_norm[pid]*100),0)} %',
                        f'<b>{_fmt_es_number(round(final_w[pid]*100),0)} %</b>'])
        _render_html_table(_ch, _cr, max_height=320)
        if n_pairs < 4:
            st.warning(f"⚠️ Solo {n_pairs} año(s) con clima y producción a la vez. La "
                       f"calibración aún no es fiable; baja la confianza y manda tu criterio.")
        else:
            st.caption(f"Correlación (r) de cada fase con los Kg/Ha de finca sobre {n_pairs} años. "
                       f"Peso calibrado ∝ correlación positiva. Con pocos años, tómalo como indicio.")

        # IG por año + cruce clima/cosecha
        ig_rows = []
        for y in años_disp:
            ps = detail[y][1]
            _num = _den = 0.0
            for pid in phase_ids:
                s = ps.get(pid, np.nan)
                if pd.notna(s):
                    _num += final_w[pid] * s
                    _den += final_w[pid]
            ig = (_num / _den) if _den > 0 else np.nan
            ig_rows.append((y, ig, kgha_year[y]))

        st.markdown("#### IG y producción por año")
        _ih = [("Año", "left"), ("IG clima", "right"), ("Kg/Ha finca", "right"),
               ("Nivel cosecha", "center"), ("Diagnóstico", "left")]
        _ir = []
        for (y, ig, k) in ig_rows:
            _nivel, _ncol = _nivel_cosecha(k, objetivo_kgha)
            _diag, _dcol = _ig_diagnosis(ig, k, objetivo_kgha)
            _ir.append([
                str(int(y)),
                _colored_num(ig, _score_color(ig), 0),
                _kgha_target_html(k, objetivo_kgha),
                f'<span style="color:{_ncol};font-weight:600;">{_nivel}</span>',
                f'<span style="color:{_dcol};font-weight:600;">{_diag}</span>',
            ])
        _render_html_table(_ih, _ir, max_height=420)
        st.caption("**IG clima** = índice climático con pesos calibrados. **Diagnóstico** "
                   "cruza clima vs cosecha: separa los años limitados por CLIMA de los que "
                   "el clima fue bueno pero la cosecha no (→ vecería/manejo).")

        # Narrativa: qué fase manda en tu finca
        if n_pairs >= 4 and _csum > 0:
            _top = max(phase_ids, key=lambda p: cal_norm[p])
            _topl = next(l for (pid, l, *_r) in edited_phases if pid == _top)
            st.markdown(
                f"**En tu finca, la fase cuyo clima más se relaciona con la cosecha es "
                f"{_topl}** (r = {_fmt_es_number(round(corr[_top],2),2)}). "
                "El frío, al cumplirse casi siempre, apenas explica diferencias entre años."
            )

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 6 · Resumen histórico e interpretación (todo el histórico)
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("### 🏆 Resumen histórico e interpretación")

    def _rank_by(col):
        g = prod.groupby(col).agg(Kg=("Kg", "sum"), Ha=("Ha", "sum"),
                                  Nt=("Num_arboles", "sum"), Np=("Arboles_prod", "sum"))
        g["kg_ha"] = g["Kg"] / g["Ha"].replace(0, np.nan)
        g["pct"] = g["Np"] / g["Nt"].replace(0, np.nan) * 100
        return g.sort_values("kg_ha", ascending=False)

    _rc, _rv, _rp = _rank_by("Campo"), _rank_by("Variedad_nombre"), _rank_by("Portainjerto_nombre")

    # Regularidad por campo: BBI medio de sus combinaciones (de la Fase 2)
    _bbi_campo = {}
    if records:
        _dfrec = pd.DataFrame(records)
        _dfrec["_campo"] = _dfrec["label"].str.split(" · ").str[0]
        for _c, _sub in _dfrec.groupby("_campo"):
            _v = _sub.dropna(subset=["bbi"])
            if not _v.empty:
                _w = _v["n_trans"].astype(float)
                _bbi_campo[_c] = float(np.average(_v["bbi"], weights=_w) if _w.sum() > 0
                                       else _v["bbi"].mean())

    _cr = st.columns(2)
    with _cr[0]:
        st.markdown("**🥇 Más productivos** (Kg/Ha medio, todo el histórico):")
        st.markdown(
            f"- **Campo:** {_rc.index[0]} ({_fmt_es_number(round(_rc['kg_ha'].iloc[0]),0)} Kg/Ha)\n"
            f"- **Variedad:** {_rv.index[0]} ({_fmt_es_number(round(_rv['kg_ha'].iloc[0]),0)} Kg/Ha)\n"
            f"- **Portainjerto:** {_rp.index[0]} ({_fmt_es_number(round(_rp['kg_ha'].iloc[0]),0)} Kg/Ha)"
        )
    with _cr[1]:
        if _bbi_campo:
            _mreg = min(_bbi_campo, key=_bbi_campo.get)
            _mvec = max(_bbi_campo, key=_bbi_campo.get)
            _rl, _, _ = _veceria_level(_bbi_campo[_mreg])
            _vl, _, _ = _veceria_level(_bbi_campo[_mvec])
            st.markdown("**📊 Regularidad** (vecería por campo):")
            st.markdown(
                f"- **Más regular:** {_mreg} (BBI {_fmt_es_number(round(_bbi_campo[_mreg],2),2)} → {_rl.lower()})\n"
                f"- **Más vecero:** {_mvec} (BBI {_fmt_es_number(round(_bbi_campo[_mvec],2),2)} → {_vl.lower()})"
            )
        else:
            st.caption("Vecería por campo: hacen falta años consecutivos.")

    st.markdown("#### Ranking por variedad")
    _hv = [("Variedad", "left"), ("Kg/Ha medio", "right"),
           ("% prod. medio", "right"), ("Kg totales", "right")]
    _rvrows = [[_vn,
                _kgha_target_html(_row["kg_ha"], objetivo_kgha),
                _colored_num(_row["pct"], _pct_prod_color(_row["pct"]), 1, " %"),
                _fmt_es_number(round(_row["Kg"]), 0)]
               for _vn, _row in _rv.iterrows()]
    _render_html_table(_hv, _rvrows, max_height=360)

    # ── Interpretación: respuesta al frío por variedad ────────────────────────
    st.markdown("#### ❄️ ¿Qué variedades responden al frío?")
    _tcol_r = next((c for c in ["temp_media", "temp", "temperatura", "Temperatura"]
                    if history is not None and not history.empty and c in history.columns), None)
    if _tcol_r is None or history is None or history.empty:
        st.info("Carga el histórico climático para analizar la respuesta al frío por variedad.")
    else:
        chill_by_year = {}
        for _y in sorted(int(a) for a in prod["Año"].unique()):
            _s, _e = _phase_window(CHILL_PERIOD_START_MD[0], CHILL_PERIOD_START_MD[1],
                                   CHILL_PERIOD_END_MD[0], CHILL_PERIOD_END_MD[1], _y)
            _m = _phase_metrics(history, _s, _e, _tcol_r)
            chill_by_year[_y] = (_m["chill_cp"], _m["horas_frio"]) if _m else (np.nan, np.nan)

        _hr = [("Variedad", "left"), ("Años", "right"), ("r(frío,Kg/Ha)", "right"),
               ("CP mejores años", "right"), ("Horas mejores años", "right"),
               ("Interpretación", "left")]
        _rrows = []
        for _vn in sorted(prod["Variedad_nombre"].unique()):
            _dv = prod[prod["Variedad_nombre"] == _vn].groupby("Año").agg(Kg=("Kg", "sum"), Ha=("Ha", "sum"))
            _dv["kg_ha"] = _dv["Kg"] / _dv["Ha"].replace(0, np.nan)
            _xs, _ys, _pairs = [], [], []
            for _y in _dv.index:
                _cp, _hf = chill_by_year.get(int(_y), (np.nan, np.nan))
                _kh = _dv.loc[_y, "kg_ha"]
                if pd.notna(_cp) and pd.notna(_kh):
                    _xs.append(_cp); _ys.append(_kh); _pairs.append((_cp, _hf, _kh))
            if len(_xs) < 3:
                continue
            _r = (float(np.corrcoef(_xs, _ys)[0, 1])
                  if np.std(_xs) > 0 and np.std(_ys) > 0 else np.nan)
            _ps = sorted(_pairs, key=lambda p: p[2], reverse=True)
            _ntop = max(1, len(_ps) // 3)
            _cp_best = float(np.mean([p[0] for p in _ps[:_ntop]]))
            _h_best = float(np.nanmean([p[1] for p in _ps[:_ntop]]))
            if pd.isna(_r):
                _interp, _icol = "Sin variación suficiente", "#9e9e9e"
            elif _r >= 0.4:
                _interp, _icol = "Mejor con inviernos fríos → exigente en frío", "#1565c0"
            elif _r <= -0.4:
                _interp, _icol = "Mejor con inviernos suaves → poco exigente", "#e65100"
            else:
                _interp, _icol = "El frío no parece limitarla", "#558b2f"
            _rrows.append([
                _vn, str(len(_xs)),
                (_colored_num(_r, "#1565c0" if _r > 0 else "#c62828", 2) if pd.notna(_r) else "—"),
                _fmt_es_number(round(_cp_best), 0),
                _fmt_es_number(round(_h_best), 0) if pd.notna(_h_best) else "—",
                f'<span style="color:{_icol};font-weight:600;">{_interp}</span>',
            ])
        if _rrows:
            _render_html_table(_hr, _rrows, max_height=400)
            st.caption(
                "Correlación, por variedad, entre el **frío del invierno** y sus **Kg/Ha** "
                "a lo largo de los años. **r>0** = produce más cuando hay más frío (exigente); "
                "**r≈0** = el frío no la limita. **CP/Horas mejores años** = cuánto frío hubo "
                "en sus cosechas altas → tu **requerimiento empírico** por variedad. "
                "⚠️ Pocos años + vecería = indicios, no certezas; el frío es de finca (igual "
                "para todas las variedades cada año)."
            )
        else:
            st.info("Aún no hay suficientes años con frío + producción por variedad (mín. 3).")

    st.markdown("---")
    st.success(
        "✅ **Modelo Gallinal completo (Fases 1–4):** producción y participación → "
        "vecería (BBI) e IEP → índice climático por fases → **Índice Gallinal** que "
        "separa clima de vecería/manejo. Próximos pasos posibles: requerimientos de "
        "frío/calor por variedad (datos SERIDA), fenología real por año, y recomendaciones "
        "de aclareo automáticas."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DECISIONES · Panel de evolución de enfermedades y plagas (estilo RIMpro)
# ═══════════════════════════════════════════════════════════════════════════════

def _dec_mills_value(temp_c, horas_mojadura):
    """Valor numérico 0-150 para moteado (Mills). 100 = umbral de infección moderada."""
    if pd.isna(temp_c) or horas_mojadura == 0:
        return 0.0
    t = float(temp_c)
    h = int(horas_mojadura)
    if t < 6 or t > 28:
        return 0.0
    mills = [
        (6,28,18),(7,21,14),(8,18,12),(9,15,11),(10,12,9),
        (11,11,8),(12,10,7),(13,9,6),(14,8,6),(15,8,5),
        (16,7,5),(17,7,5),(18,6,5),(19,6,4),(20,6,4),
        (21,6,4),(22,7,4),(23,8,5),(24,9,6),(25,10,7),
        (26,12,8),(27,15,10),
    ]
    row = next((r for r in mills if int(r[0]) == int(round(t))), None)
    if row is None:
        return 0.0
    _, h_ligera, h_grave = row
    if h >= h_grave:
        return min(h / h_grave * 100.0, 150.0)
    if h >= max(h_grave - 2, 1):
        return h / h_ligera * 50.0
    return 0.0


def _dec_monilia_value(temp_c, hr, lluvia_mm, horas_mojadura):
    """Valor numérico 0-100 para monilia."""
    if pd.isna(temp_c):
        return 0.0
    t = float(temp_c)
    h = float(hr) if pd.notna(hr) else 0.0
    ll = float(lluvia_mm) if pd.notna(lluvia_mm) else 0.0
    hm = int(horas_mojadura)
    if t < 15 or t > 30:
        return 0.0
    t_factor = 1.0 if 18 <= t <= 28 else ((t-15)/3 if t < 18 else max(0.0,(30-t)/2))
    if hm >= 6 and h > 90:
        hm_factor = 1.0
    elif hm >= 3 or h > 85:
        hm_factor = 0.6
    elif ll > 1 or h > 80:
        hm_factor = 0.3
    else:
        return 0.0
    return min(t_factor * hm_factor * 100.0, 100.0)


def _dec_oidio_value(temp_c, hr, lluvia_mm):
    """Valor numérico 0-100 para oídio (condiciones favorables secas y cálidas)."""
    if pd.isna(temp_c):
        return 0.0
    t = float(temp_c)
    h = float(hr) if pd.notna(hr) else 0.0
    ll = float(lluvia_mm) if pd.notna(lluvia_mm) else 0.0
    if t < 10 or t > 35 or ll > 8:
        return 0.0
    t_factor = (1.0 if 17 <= t <= 25
                else ((t-10)/7 if t < 17 else max(0.0,(35-t)/10)))
    h_factor = (1.0 if 50 <= h <= 80
                else (max(0.0,(h-30)/20) if h < 50 else max(0.0,1.0-(h-80)/20)))
    rain_penalty = max(0.0, 1.0 - ll/8)
    return min(t_factor * h_factor * rain_penalty * 100.0, 100.0)


def _dec_bar_color(value):
    """Color del bar según valor de riesgo."""
    if value >= 100: return "#d62728"
    if value >= 60:  return "#ff7f0e"
    if value >= 25:  return "#f5c518"
    return "#2ca02c"


# ── Catálogo de fungicidas — campaña 2026 ─────────────────────────────────────
# Solo los productos disponibles en almacén. Columna "FRAC" para gestión de resistencias.
DEFAULT_FUNGICIDE_CATALOG = [
    {
        "Producto": "FOLICUR 25 WG",
        "Objetivos": "Moteado, Oídio",
        "Tipo": "Sistémico curativo",
        "Plazo seguridad días": 7,
        "FRAC": "G1",
        "Familia": "Triazol (DMI)",
        "Notas": (
            "Tebuconazol 25%. Inhibe la biosíntesis de ergosterol (FRAC G1). "
            "Acción curativa eficaz hasta 72h post-infección en moteado (Venturia). "
            "Redistribución sistémica acrópeta. Máx 3 aplicaciones/campaña para evitar resistencias. "
            "Efecto secundario sobre raleo de fruto si se aplica en floración."
        ),
    },
    {
        "Producto": "SIGNUM",
        "Objetivos": "Monilia, Moteado",
        "Tipo": "Sistémico preventivo",
        "Plazo seguridad días": 7,
        "FRAC": "C2+C3",
        "Familia": "SDHI + Estrobilurina",
        "Notas": (
            "Boscalid 26,7% + Piraclostrobina 6,7%. Doble modo de acción: inhibe la cadena "
            "respiratoria mitocondrial en el complejo II (SDHI) y III (QoI). Alta actividad "
            "preventiva y larga persistencia (~14-21 días). Especialmente eficaz contra "
            "Monilia laxa en floración y Monilia fructigena en precosecha. "
            "No mezclar ni alternar de forma consecutiva con Flint (ambos contienen FRAC C3)."
        ),
    },
    {
        "Producto": "FLINT 50 WG",
        "Objetivos": "Moteado, Oídio",
        "Tipo": "Sistémico preventivo/curativo",
        "Plazo seguridad días": 14,
        "FRAC": "C3",
        "Familia": "Estrobilurina (QoI)",
        "Notas": (
            "Trifloxistrobina 50%. Inhibe el complejo III de la cadena respiratoria (FRAC C3). "
            "Excelente actividad preventiva y vapor-fase; penetración traslaminar. "
            "Eficaz contra Venturia (moteado) y Podosphaera (oídio). "
            "Máx 2 aplicaciones consecutivas; alternar con G1 o C2+G1. "
            "No aplicar junto a Signum (acumulación de presión selectiva sobre FRAC C3)."
        ),
    },
    {
        "Producto": "LUNA EXPERIENCE",
        "Objetivos": "Monilia, Moteado, Oídio",
        "Tipo": "Sistémico curativo + preventivo",
        "Plazo seguridad días": 7,
        "FRAC": "C2+G1",
        "Familia": "SDHI + Triazol",
        "Notas": (
            "Fluopyram 200 g/L + Tebuconazol 200 g/L. SDHI (FRAC C2) + DMI triazol (FRAC G1). "
            "Doble modo de acción sistémico con excelente actividad contra Monilia spp. "
            "(M. laxa y M. fructigena), moteado y oídio. Acción curativa y de parada del "
            "desarrollo miceliar hasta 96-120h post-infección. "
            "Alta eficacia en condiciones de alta presión. Máx 2 aplicaciones/campaña; "
            "no repetir consecutivamente con Folicur (ambos FRAC G1)."
        ),
    },
]

# Biblioteca de alternativas para rotación (productos no en almacén pero relevantes)
ROTATION_ALTERNATIVES = [
    {
        "Producto": "SWITCH 62.5 WG",
        "Objetivos": "Monilia",
        "FRAC": "D1+E2",
        "Familia": "Anilinopirimidina + Fenilpirrole",
        "Motivo rotación": "Grupo D1+E2 totalmente distinto a los usados en 2026. Ideal para romper ciclo de resistencia en Monilia.",
    },
    {
        "Producto": "CAPTAN 80 WG",
        "Objetivos": "Moteado",
        "FRAC": "M4",
        "Familia": "Multi-sitio (contacto)",
        "Motivo rotación": "Grupo M (multi-sitio). Sin riesgo de resistencia. Alterna con sistémicos para reducir presión de selección.",
    },
    {
        "Producto": "TELDOR 500 SC",
        "Objetivos": "Monilia",
        "FRAC": "E2",
        "Familia": "Fenilpirrole",
        "Motivo rotación": "Fenhexamid. Específico de Monilia. Grupo E2 no usado en 2026; muy recomendable para rotación.",
    },
    {
        "Producto": "THIRAM (Pomarsol)",
        "Objetivos": "Moteado",
        "FRAC": "M3",
        "Familia": "Multi-sitio (contacto)",
        "Motivo rotación": "Multi-sitio, sin riesgo de resistencia. Complemento de contacto para reducir dependencia de sistémicos.",
    },
    {
        "Producto": "KUMULUS DF",
        "Objetivos": "Oídio",
        "FRAC": "M2",
        "Familia": "Inorgánico (Azufre)",
        "Motivo rotación": "Azufre. Grupo M2 sin resistencias conocidas. Solo preventivo. No usar con T>30°C.",
    },
]

# Inicialización session_state del catálogo — versión 2 (fuerza reseteo si hay productos obsoletos)
_CATALOG_VERSION = "v2_2026"
_VALID_PRODUCTS_2026 = {"FOLICUR 25 WG", "SIGNUM", "FLINT 50 WG", "LUNA EXPERIENCE"}
_needs_reset = (
    "fungicide_catalog_df" not in st.session_state
    or st.session_state.get("fungicide_catalog_version") != _CATALOG_VERSION
)
if _needs_reset:
    st.session_state.fungicide_catalog_df = pd.DataFrame(DEFAULT_FUNGICIDE_CATALOG)
    st.session_state.fungicide_catalog_version = _CATALOG_VERSION


# ── Ranking de eficacia por patógeno (fuente: FRAC guidelines + ensayos en frutales) ──────────
# Puntuación 1-4: 4 = primera elección científica, 1 = elección secundaria
# Basado en: modo de acción, eficacia documentada en Venturia inaequalis / Monilia spp. /
# Podosphaera leucotricha, velocidad de acción curativa y persistencia residual.
PRODUCT_EFFICACY_RANKING = {
    "Monilia": {
        # Luna Experience: SDHI (C2) + DMI (G1) — doble modo de acción sistémico.
        # Eficacia >90% contra M. laxa y M. fructigena (ensayos BASF 2018-2022).
        "LUNA EXPERIENCE": 4,
        # Signum: SDHI (C2) + QoI (C3) — alta persistencia, excelente en floración.
        "SIGNUM":          3,
        # Folicur: DMI (G1) — actividad curativa aceptable sobre Monilia, menor que SDHI.
        "FOLICUR 25 WG":   2,
        # Flint: QoI (C3) — actividad limitada sobre Monilia spp.
        "FLINT 50 WG":     1,
    },
    "Moteado": {
        # Flint: QoI (C3) — primera elección preventiva contra Venturia inaequalis.
        # Excelente actividad de vapor-fase y traslaminar (Bayer CropScience).
        "FLINT 50 WG":     4,
        # Folicur: DMI (G1) — acción curativa hasta 72h post-infección Mills.
        "FOLICUR 25 WG":   3,
        # Luna Experience: SDHI + DMI — amplio espectro, buen curativo.
        "LUNA EXPERIENCE": 2,
        # Signum: SDHI + QoI — buena actividad preventiva sobre Venturia.
        "SIGNUM":          2,
    },
    "Oídio": {
        # Flint: QoI — primera elección contra Podosphaera leucotricha.
        "FLINT 50 WG":     4,
        # Folicur: DMI — buena eficacia sistémica sobre oídio.
        "FOLICUR 25 WG":   3,
        # Luna Experience: SDHI + DMI — eficaz sobre oídio por componente triazol.
        "LUNA EXPERIENCE": 2,
        # Signum: actividad inferior sobre Podosphaera vs QoI puros.
        "SIGNUM":          1,
    },
}

# FRAC de cada producto del catálogo 2026 (para filtro de rotación)
PRODUCT_FRAC_MAP = {
    "FOLICUR 25 WG":  ["G1"],
    "SIGNUM":         ["C2", "C3"],
    "FLINT 50 WG":    ["C3"],
    "LUNA EXPERIENCE":["C2", "G1"],
}

# Límites de aplicación por campaña según registro MAPA + guías FRAC
# Fuente: ficha registro MAPA, FRAC Code List 2024, fichas técnicas fabricante
PRODUCT_MAX_APPLICATIONS = {
    "FOLICUR 25 WG":  3,   # FRAC G1 (DMI): máx 3 en frutales. MAPA: 3 app/campaña.
    "SIGNUM":         2,   # FRAC C2 (SDHI): máx 2 estricto. FRAC recomienda ≤2 SDHI/campaña.
    "FLINT 50 WG":    2,   # FRAC C3 (QoI): máx 2 en manzano/peral. MAPA: 2 app/campaña.
    "LUNA EXPERIENCE":2,   # FRAC C2+G1: componente SDHI marca límite en 2. BASF ficha técnica.
}

# Límite combinado del grupo SDHI (C2): Signum + Luna Experience juntos ≤ 3 por campaña
# para no agotar el grupo SDHI completo. (FRAC SDHI resistance risk guidelines, 2022)
SDHI_GROUP_MAX_COMBINED = 3


def _campo_exact_in_list(campos_str, campo_name):
    """
    True si campo_name aparece como elemento exacto (no como subcadena)
    en la lista de campos separados por coma.
    "Huertona" NO coincide con "La Huertona" ni con "Huertona Nueva".
    """
    campos_list = [c.strip().lower() for c in str(campos_str).split(",")]
    return campo_name.strip().lower() in campos_list


def _normalize_product_to_catalog(prod_raw):
    """
    Normaliza el nombre de un producto de Agroptima a las claves del catálogo.
    Devuelve LISTA de claves coincidentes (puede haber varias si la celda contiene
    varios productos: "FLINT 50 WG + SIGNUM" → ["FLINT 50 WG", "SIGNUM"]).

    Agroptima puede registrar en UNA celda varios productos mezclados en el mismo
    caldo (p.ej. "FLINT 50 WG + BACTUR WG"). En ese caso se detectan TODOS los
    fungicidas del catálogo presentes y se ignoran los no-fungicidas.
    """
    prod_up = str(prod_raw).strip().upper()
    matches = []
    for catalog_key in PRODUCT_MAX_APPLICATIONS:
        first_word = catalog_key.split()[0].upper()   # "FOLICUR", "SIGNUM", "FLINT", "LUNA"
        cat_up     = catalog_key.upper()
        if (first_word in prod_up
                or cat_up in prod_up
                or prod_up in cat_up
                or prod_up == first_word):
            matches.append(catalog_key)
    return matches  # lista vacía si no hay coincidencias


def count_field_applications(activities_df, campo, year=None):
    """
    Cuenta cuántas veces se ha aplicado cada fungicida del catálogo a un campo
    en la campaña (año actual o `year`).

    Maneja correctamente:
    - Pasadas mixtas: fungicida + insecticida en la misma fila ("FLINT + BACTUR")
      o en filas separadas el mismo día. Solo cuentan los fungicidas del catálogo.
    - Pasadas con varios fungicidas: "FLINT + SIGNUM" → cuenta 1 pase de cada uno.
    - Filas duplicadas de importación: (fecha, campo, producto) idénticos → 1 pase.
    - Matching exacto de campo: "Huertona" no coincide con "La Huertona".

    Lógica de agrupación:
    - Todas las filas fungicidas del mismo campo y la misma fecha = misma pasada.
    - Cada producto del catálogo detectado en esa pasada suma 1 pase a su contador.

    Devuelve (dict {producto_catálogo: n_pases}, sdhi_total).
    """
    if year is None:
        year = pd.Timestamp.now().year

    counts     = {}
    sdhi_total = 0

    if activities_df.empty or "Campos reconocidos" not in activities_df.columns:
        return counts, sdhi_total

    _acts = activities_df.copy()
    _acts["Fecha_dt"] = pd.to_datetime(_acts["Fecha"], errors="coerce")
    _acts = _acts.dropna(subset=["Fecha_dt"])
    _acts = _acts[_acts["Fecha_dt"].dt.year == int(year)]

    if _acts.empty:
        return counts, sdhi_total

    # 1. Solo filas con al menos un fungicida confirmado
    _mask_fung = _acts.apply(
        lambda r: is_fungicide_activity(r.get("Producto", ""), r.get("Trabajo", "")),
        axis=1,
    )
    _acts = _acts[_mask_fung]

    if _acts.empty:
        return counts, sdhi_total

    # 2. Matching EXACTO del campo
    _mask_campo = _acts["Campos reconocidos"].fillna("").apply(
        lambda x: _campo_exact_in_list(x, campo)
    )
    campo_acts = _acts[_mask_campo].copy()

    if campo_acts.empty:
        return counts, sdhi_total

    campo_acts["_fecha_dia"] = campo_acts["Fecha_dt"].dt.date

    # 3. Agrupar por fecha (= misma pasada).
    #    Recopilar todos los productos fungicidas del catálogo aplicados ese día.
    #    Deduplica automáticamente filas repetidas del mismo producto en la misma fecha.
    seen = set()   # (fecha, producto_catálogo) ya contados → evita doble conteo

    for _, row in campo_acts.iterrows():
        prod_raw  = str(row.get("Producto", ""))
        fecha_dia = row["_fecha_dia"]
        matched   = _normalize_product_to_catalog(prod_raw)   # lista de claves

        for catalog_key in matched:
            dedup_key = (fecha_dia, catalog_key)
            if dedup_key in seen:
                continue   # misma fecha + mismo producto ya contado (fila duplicada)
            seen.add(dedup_key)
            counts[catalog_key] = counts.get(catalog_key, 0) + 1
            if "C2" in PRODUCT_FRAC_MAP.get(catalog_key, []):
                sdhi_total += 1

    return counts, sdhi_total


def get_smart_recommendation(dominant_risk_list, catalog_df, last_product=None,
                              app_counts=None, sdhi_total=0):
    """
    Devuelve (producto_recomendado, alternativa, motivo) con lógica científica:
      1. Eficacia por patógeno (PRODUCT_EFFICACY_RANKING).
      2. Penalización por rotación FRAC (no repetir mismo grupo).
      3. Penalización por límite de aplicaciones alcanzado (PRODUCT_MAX_APPLICATIONS).
      4. Penalización por límite SDHI combinado (Signum + Luna ≤ 3/campaña).

    app_counts: dict {producto: n_aplicaciones_campaña} para el campo en cuestión.
    sdhi_total: total de aplicaciones de cualquier SDHI (C2) en la campaña para ese campo.
    """
    if catalog_df is None or catalog_df.empty:
        return "—", "—", "Sin catálogo"

    risks = [r.strip() for r in dominant_risk_list if r.strip() not in ("—", "")]
    if not risks:
        return "—", "—", "Sin riesgo activo"

    if app_counts is None:
        app_counts = {}

    # ── Grupos FRAC de TODOS los productos de la última pasada → penalizar repetición ──
    # last_product puede ser "FLINT 50 WG + SIGNUM" si se mezclaron en el mismo caldo.
    # Recogemos los grupos FRAC de todos ellos para no repetir ninguno en la recomendación.
    last_fracs = set()
    _last_names = []
    _invalid = ("Sin registro", "Sin especificar", "nan", "", "⚠️ Sin fungicida registrado")
    if last_product and last_product not in _invalid:
        # Separar productos por " + " o "," para manejar mezclas de caldo
        _lp_parts = [p.strip() for p in str(last_product).replace(",", "+").split("+") if p.strip()]
        for _lp in _lp_parts:
            _lp_norm  = _lp.upper()
            for prod_key, fracs in PRODUCT_FRAC_MAP.items():
                _pk_norm  = prod_key.upper()
                _pk_first = _pk_norm.split()[0]
                _lp_first = _lp_norm.split()[0]
                if (_pk_norm in _lp_norm or _lp_norm in _pk_norm
                        or _pk_first in _lp_norm or _lp_first in _pk_norm):
                    last_fracs.update(fracs)
                    if prod_key not in _last_names:
                        _last_names.append(prod_key)
                    break
    _last_name = " + ".join([p.split()[0] for p in _last_names]) if _last_names else ""

    scores = {}
    limit_notes = {}   # avisos de límite para incluir en el motivo

    for _, row in catalog_df.iterrows():
        prod = str(row.get("Producto", "")).strip()
        if not prod:
            continue

        # 1. Eficacia base
        score = sum(PRODUCT_EFFICACY_RANKING.get(risk, {}).get(prod, 0) for risk in risks)

        # 2. Penalización rotación FRAC (-5): desplaza al siguiente grupo sin bloquearlo
        prod_fracs = set(PRODUCT_FRAC_MAP.get(prod, []))
        if last_fracs and prod_fracs & last_fracs:
            score -= 5

        # 3. Penalización límite de aplicaciones (-10 si se ha alcanzado el límite):
        #    restamos más fuerte para sacarlo de la primera elección pero mantenerlo
        #    como alternativa informativa si no hay nada más
        n_used = app_counts.get(prod, 0)
        max_app = PRODUCT_MAX_APPLICATIONS.get(prod, 99)
        if n_used >= max_app:
            score -= 10
            limit_notes[prod] = f"límite {max_app} pases alcanzado"
        elif n_used == max_app - 1:
            limit_notes[prod] = f"{n_used}/{max_app} pases"

        # 4. Penalización SDHI combinado: si Signum+Luna ya suman ≥ límite
        if "C2" in prod_fracs and sdhi_total >= SDHI_GROUP_MAX_COMBINED:
            score -= 10
            limit_notes[prod] = limit_notes.get(prod, "") + " (grupo SDHI agotado)"

        if score > -10:   # mantener incluso penalizados para usarlos como alternativa informativa
            scores[prod] = score

    if not scores:
        return "Revisar catálogo", "—", "Sin productos disponibles en catálogo"

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    primary   = ranked[0][0]
    alternate = ranked[1][0] if len(ranked) > 1 else "—"

    # ── Motivo legible ─────────────────────────────────────────────────────────
    parts = [f"Eficacia en {' + '.join(risks)}"]

    if _last_name and last_fracs:
        same_group = [p for p in scores if set(PRODUCT_FRAC_MAP.get(p, [])) & last_fracs and p != primary]
        if same_group:
            parts.append(f"rota vs {_last_name.split()[0]} (FRAC {'+'.join(sorted(last_fracs))})")

    p_apps = app_counts.get(primary, 0)
    p_max  = PRODUCT_MAX_APPLICATIONS.get(primary, 99)
    parts.append(f"{p_apps}/{p_max} pases usados")

    if primary in limit_notes:
        parts.append(limit_notes[primary])

    return primary, alternate, " · ".join(parts)


def build_treatment_narrative(days_since, rain_since, mills_events_since,
                              monilia_events_since, fc_mills_max, fc_monilia_max,
                              fc_rain, last_product, persistence_days, priority,
                              last_date=None):
    """
    Genera una narrativa en lenguaje claro explicando POR QUÉ se recomienda
    (o no) un tratamiento fungicida hoy para un campo concreto.

    Clasifica el tipo de tratamiento (preventivo / curativo / no necesario)
    y lista los factores activos con su base científica resumida.

    Referencias:
    - Umbral Mills: Mills & Laplante 1951 (temperatura + horas de mojadura foliar).
    - Ventana curativa DMI/SDHI: 48-96h post-infección (Köller 2001; BASF Luna ficha).
    - Umbral lavado sistémicos: ~35 mm acumulados (EPPO PP 1/5; fichas técnicas FRAC).
    - Persistencia: 14-21 días según producto (etiqueta registro MAPA).
    - Monilia: T óptima infección 20-25°C + humedad alta (Villarino et al. 2012; EPPO PM7/18).
    """
    reasons   = []   # frases de razón, en orden de importancia
    tipo      = ""   # "Preventivo" / "Curativo" / "No necesario"
    urgencia  = ""   # adjetivo de urgencia para el encabezado

    last_prod_short = (str(last_product).split()[0].capitalize()
                       if last_product not in ("Sin registro", "Sin especificar", "nan", "")
                       else "último fungicida")
    last_date_str = (last_date.strftime("%d/%m") if last_date is not None else "fecha desconocida")

    # ── 1. Previsión de infección (razón más urgente) ──────────────────────────
    if fc_mills_max >= 100:
        reasons.append(
            f"Evento Mills previsto (índice {int(fc_mills_max)}): "
            f"temperatura + mojadura foliar superan umbral de infección de Venturia inaequalis "
            f"(Mills & Laplante 1951). Aplicar ANTES de la lluvia para acción preventiva."
        )
        tipo = "Preventivo urgente"

    if fc_monilia_max >= 100:
        reasons.append(
            f"Condiciones óptimas para Monilia spp. previstas (índice {int(fc_monilia_max)}): "
            f"temperatura y humedad en rango de máxima infección (20-25°C, HR >90%). "
            f"Especialmente crítico en fruto en desarrollo (Villarino et al. 2012)."
        )
        if not tipo:
            tipo = "Preventivo urgente"

    if fc_rain >= 15 and not fc_mills_max >= 100:
        reasons.append(
            f"Lluvia prevista de {fc_rain:.0f} mm en los próximos 3 días: "
            f"favorece mojadura foliar y puede coincidir con el fin de la cobertura actual."
        )

    # ── 2. Estado de la cobertura actual ──────────────────────────────────────
    if days_since >= persistence_days:
        reasons.append(
            f"Cobertura caducada: {days_since} días desde {last_prod_short} ({last_date_str}). "
            f"La persistencia estimada de los sistémicos es de {persistence_days} días en campo "
            f"(etiqueta MAPA; FRAC persistence data). El campo está sin protección activa."
        )
        if not tipo:
            tipo = "Preventivo"
    elif days_since >= 12 and rain_since >= 35:
        reasons.append(
            f"Lavado por lluvia: {rain_since:.0f} mm acumulados desde {last_prod_short} ({last_date_str}). "
            f"Los fungicidas sistémicos pierden eficacia preventiva a partir de ~35 mm acumulados "
            f"(EPPO PP 1/5; fichas FRAC grupo C2-C3). La cobertura está comprometida."
        )
        if not tipo:
            tipo = "Preventivo"

    # ── 3. Exposición acumulada sin cobertura ─────────────────────────────────
    total_events = mills_events_since + monilia_events_since
    if total_events >= 3:
        reasons.append(
            f"{total_events} eventos de infección registrados sin cobertura activa "
            f"desde {last_prod_short} ({last_date_str}) "
            f"({mills_events_since} Mills + {monilia_events_since} Monilia). "
            f"Cada evento representa un período de infección completado; "
            f"la latencia hasta síntomas visibles es de 9-21 días según temperatura "
            f"(Rühmer 1998; modelo Mills). El daño de esas infecciones está en curso."
        )
    elif total_events > 0 and days_since >= 10:
        reasons.append(
            f"{total_events} evento(s) de infección desde el último fungicida. "
            f"Vigilar próxima semana: la latencia puede mostrar síntomas en 10-21 días."
        )

    # ── 4. Ventana curativa ───────────────────────────────────────────────────
    # Si el último evento real fue reciente (aproximado: hay eventos y cobertura caducada
    # pero todavía dentro del umbral de 96h para SDHI/triazoles)
    if total_events >= 1 and days_since >= persistence_days and days_since <= persistence_days + 4:
        reasons.append(
            "Posible ventana curativa activa: los fungicidas DMI (triazoles) y SDHI "
            "pueden detener infecciones incipientes hasta 48-96h post-eventos "
            "(Köller 2001; BASF ficha Luna Experience). "
            "Preferir productos con acción curativa (Folicur, Luna Experience)."
        )
        tipo = "Curativo + preventivo"

    # ── 5. Sin razón para tratar ──────────────────────────────────────────────
    if priority == 4:
        tipo = "No necesario hoy"
        dias_resto = max(0, persistence_days - days_since)
        reasons.append(
            f"Cobertura activa: {days_since} días desde {last_prod_short} ({last_date_str}), "
            f"~{dias_resto} días de margen estimados. "
            f"Sin previsión de eventos de infección en los próximos 3 días. "
            f"Tratar sin justificación añade presión de resistencia innecesaria (FRAC 2024)."
        )

    if not reasons:
        if priority == 3:
            reasons.append(
                f"Cobertura próxima a caducar ({days_since} días desde {last_prod_short}). "
                f"Sin previsión de infección inmediata. Planificar tratamiento preventivo "
                f"en los próximos 3-5 días antes de que la ventana de riesgo se abra."
            )
            tipo = "Planificar preventivo"
        else:
            reasons.append("Revisar manualmente: situación no clasificada.")
            tipo = "Revisar"

    if not tipo:
        tipo = "Preventivo"

    # ── Encabezado de tipo ────────────────────────────────────────────────────
    tipo_emoji = {
        "Preventivo urgente":    "🛡️ Preventivo urgente",
        "Preventivo":            "🛡️ Preventivo",
        "Planificar preventivo": "📅 Planificar preventivo",
        "Curativo + preventivo": "⚕️ Curativo + preventivo",
        "No necesario hoy":      "✅ Sin tratamiento",
        "Revisar":               "🔍 Revisar",
    }.get(tipo, f"🛡️ {tipo}")

    narrative = f"[{tipo_emoji}] " + " | ".join(reasons)
    return narrative


def build_rotation_advice(activities_df, catalog_df=None):
    """
    Analiza los productos usados en la campaña actual y propone rotaciones
    para la próxima campaña basándose en grupos FRAC.
    Devuelve dict con:
      - 'used_products': {producto: n_aplicaciones}
      - 'used_fracs': set de grupos FRAC usados
      - 'advice': lista de dicts con alternativas recomendadas
      - 'warnings': lista de alertas (ej. mismo grupo repetido)
    """
    used_products = {}
    used_fracs    = set()
    warnings      = []

    if not activities_df.empty and "Producto" in activities_df.columns:
        current_year = pd.Timestamp.now().year
        acts = activities_df.copy()
        acts["Fecha_dt"] = pd.to_datetime(acts.get("Fecha", pd.Series(dtype=str)), errors="coerce")
        acts = acts[acts["Fecha_dt"].dt.year == current_year]
        for _, r in acts.iterrows():
            prod = str(r.get("Producto", "")).strip()
            if prod and prod != "nan":
                used_products[prod] = used_products.get(prod, 0) + 1

    # Mapear productos usados a sus grupos FRAC mediante el catálogo
    if catalog_df is not None and not catalog_df.empty:
        for _, r in catalog_df.iterrows():
            prod = str(r.get("Producto", "")).strip()
            frac = str(r.get("FRAC", "")).strip()
            if prod in used_products and frac:
                for f in frac.split("+"):
                    used_fracs.add(f.strip())

    # Advertencias de rotación dentro del catálogo actual
    if catalog_df is not None and not catalog_df.empty:
        # Estrobilurina usada más de 2 veces
        qoi_count = sum(v for k, v in used_products.items()
                        if any(k.upper() in r.get("Producto","").upper() and "C3" in str(r.get("FRAC",""))
                               for _, r in catalog_df.iterrows()))
        if qoi_count > 2:
            warnings.append("⚠️ Estrobilurinas (FRAC C3) usadas más de 2 veces en la campaña. Riesgo de resistencia en Moteado.")
        # Triazol acumulado
        g1_count = sum(v for k, v in used_products.items()
                       if any(k.upper() in r.get("Producto","").upper() and "G1" in str(r.get("FRAC",""))
                              for _, r in catalog_df.iterrows()))
        if g1_count > 3:
            warnings.append("⚠️ Triazoles (FRAC G1) usados >3 veces. Considera alternar con grupos D1 o E para Monilia.")

    # Alternativas recomendadas: productos de ROTATION_ALTERNATIVES cuyo FRAC no está en los usados
    advice = []
    for alt in ROTATION_ALTERNATIVES:
        alt_fracs = {f.strip() for f in str(alt.get("FRAC","")).split("+")}
        # Recomendar si al menos uno de sus grupos FRAC no está ya en el arsenal 2026
        new_groups = alt_fracs - used_fracs - {"C2", "C3", "G1"}  # excluir grupos ya en almacén
        if new_groups or alt_fracs.isdisjoint(used_fracs):
            advice.append({
                "Producto":       alt["Producto"],
                "Para":           alt["Objetivos"],
                "FRAC":           alt["FRAC"],
                "Familia":        alt["Familia"],
                "Por qué rotar":  alt["Motivo rotación"],
            })

    return {
        "used_products": used_products,
        "used_fracs":    used_fracs,
        "advice":        advice,
        "warnings":      warnings,
    }


# ── Clasificador de tratamientos fungicidas ────────────────────────────────────
# Palabras clave de materias activas y nombres comerciales de FUNGICIDAS.
# Fuente: FRAC, Registro de productos fitosanitarios MAPA (España).
_FUNGICIDE_KEYWORDS = {
    # ── Materias activas ──────────────────────────────────────────────────────
    "tebuconazol", "boscalid", "piraclostrobin", "trifloxistrobin", "fluopyram",
    "captan", "thiram", "tiram", "mancozeb", "mancoceb", "maneb", "zineb", "folpet",
    "azufre", "sulfur", "cobre", "copper", "oxicloruro", "hidroxido calcico",
    "bordeaux", "bordeauxs", "bordelesa",
    "fenhexamid", "ciprodinil", "fludioxonil", "dodina",
    "myclobutanil", "miclobutanil", "penconazol", "difenoconazol", "propiconazol",
    "iprodiona", "iprodione", "pyrimethanil", "pirimatanil", "kresoxim",
    "dithianon", "ditianon", "captafol", "tolylfluanid", "metiram",
    "metrafenona", "quinoxifen", "spiroxamina", "espiroxamina",
    "cyflufenamid", "ciflufenamid", "proquinazid",
    # ── Nombres comerciales (catálogo propio + habituales en frutales) ────────
    "folicur", "signum", "flint", "luna experience", "luna",
    "switch", "teldor", "kumulus", "pomarsol", "merpan",
    "chorus", "scala", "bellis", "cantus", "headline",
    "score", "sico", "bumper", "tilt",
    "delan", "syllit", "ventu",
    # ── Términos genéricos de tipo de trabajo ─────────────────────────────────
    "fungicida", "fungicide", "antifúngico", "fitosanitario fungicida",
    "tratamiento fungicida", "aplicacion fungicida",
}

# Palabras clave de NO-fungicidas: si el producto o trabajo contiene alguna de estas
# Y no contiene ninguna keyword fungicida, se descarta como tratamiento fúngico.
_NON_FUNGICIDE_KEYWORDS = {
    # ── Insecticidas ──────────────────────────────────────────────────────────
    "bactur", "bacillus", "thuringiensis", "xentari", "dipel",
    "spinosad", "spintor", "tracer", "success",
    "karate", "lambda", "lambdacialotrina", "cipermetrin", "deltametrin",
    "chlorpyrifos", "clorpirifos", "dimethoate", "dimetoato",
    "imidacloprid", "imidacloprid", "acetamiprid", "tiamethoxam",
    "confidor", "mospilan", "actara", "chess", "movento",
    "pirimicarb", "pirimor", "calypso", "thiacloprid",
    "insecticida", "insecticide",
    # ── Acaricidas ────────────────────────────────────────────────────────────
    "aracan", "abamectin", "abamectina", "vertimec", "kraft",
    "envidor", "oberon", "spirodiclofen", "hexitiazox",
    "bifenazato", "floramite", "nexter", "pyridaben",
    "acaricida", "acaricide",
    # ── Herbicidas ────────────────────────────────────────────────────────────
    "herbicida", "herbicide", "glifosato", "roundup", "glyphosate",
    "simazina", "terbutilazina", "pendimetalina",
    # ── Abonos y fertilizantes ─────────────────────────────────────────────────
    "abono", "fertilizante", "fertirrigacion", "npk", "nitrogeno",
    "fosforo", "potasio", "calcio foliar", "boro foliar", "magnesio",
    "aminoacido", "alga", "humus", "humico", "fulvico",
    # ── Confusión sexual / feromonas ──────────────────────────────────────────
    "feromona", "confusion sexual", "isomate", "disrupt", "checkmate",
    "trampa", "diffuser",
    # ── Otros ─────────────────────────────────────────────────────────────────
    "nematicida", "bactericida", "caolinita", "kaolin", "surround",
    "aceite mineral", "aceite parafina",
}


def is_fungicide_activity(producto_str, trabajo_str=""):
    """
    Devuelve True si una actuación de Agroptima es un tratamiento fungicida.

    Lógica de decisión (conservadora: si hay duda, NO es fungicida):
    1. Construye un texto combinado con producto + tipo de trabajo.
    2. Si contiene alguna keyword NON_FUNGICIDE y ninguna FUNGICIDE → False.
    3. Si contiene alguna keyword FUNGICIDE → True.
    4. Si el campo 'Trabajo' menciona explícitamente "fungicida" → True.
    5. En caso de duda (texto vacío o no clasificable) → False (conservador).
    """
    texto = (str(producto_str) + " " + str(trabajo_str)).lower()

    tiene_fungicida    = any(kw in texto for kw in _FUNGICIDE_KEYWORDS)
    tiene_no_fungicida = any(kw in texto for kw in _NON_FUNGICIDE_KEYWORDS)

    if tiene_no_fungicida and not tiene_fungicida:
        return False   # claramente no es fungicida
    if tiene_fungicida:
        return True    # confirmado fungicida
    # texto ambiguo o vacío → conservador: no contamos como cobertura fungicida
    return False


def daily_treatment_decision(history_df, activities_df, risk_df, persistence_days=16):
    """
    Para cada campo de la finca, calcula el estado de protección FUNGICIDA y
    la acción recomendada para hoy.
    Solo tiene en cuenta aplicaciones de fungicidas (filtradas con is_fungicide_activity).
    """
    today = pd.Timestamp.now().normalize()
    rows  = []

    # Pre-process activities: solo fungicidas, con fecha válida
    acts_clean = pd.DataFrame()
    if not activities_df.empty and "Campos reconocidos" in activities_df.columns:
        _acts = activities_df.copy()
        _acts["Fecha_dt"] = pd.to_datetime(_acts["Fecha"], errors="coerce")
        _acts = _acts.dropna(subset=["Fecha_dt"])
        # Filtrar SOLO fungicidas
        _mask_fung = _acts.apply(
            lambda r: is_fungicide_activity(
                r.get("Producto", ""),
                r.get("Trabajo", ""),
            ),
            axis=1,
        )
        acts_clean = _acts[_mask_fung].copy()

    for field_row in FIELDS_BASE_ROWS:
        campo      = field_row["Campo"]
        variedades = field_row.get("Variedades actuales", "")

        # ── Última pasada fungicida ───────────────────────────────────────────
        # Matching EXACTO de campo. Agrupa por fecha para recoger TODOS los
        # fungicidas aplicados ese día (e.g. FLINT + SIGNUM en el mismo caldo).
        # Los productos no-fungicidas (Bactur, Aracan…) se ignoraron al filtrar acts_clean.
        last_date       = None
        last_products   = []   # lista de todos los fungicidas de la última pasada
        last_product    = "Sin registro"   # representación legible para display
        if not acts_clean.empty:
            mask = acts_clean["Campos reconocidos"].fillna("").apply(
                lambda x: _campo_exact_in_list(x, campo)
            )
            campo_acts_all = acts_clean[mask].sort_values("Fecha_dt", ascending=False)
            if not campo_acts_all.empty:
                last_date = campo_acts_all.iloc[0]["Fecha_dt"].normalize()
                # Todos los productos fungicidas del mismo día = misma pasada
                same_day = campo_acts_all[
                    campo_acts_all["Fecha_dt"].dt.normalize() == last_date
                ]
                # Normalizar cada fila al catálogo y recoger todos los productos únicos
                _prods_set = []
                _seen_keys = set()
                for _, _row in same_day.iterrows():
                    for _ck in _normalize_product_to_catalog(_row.get("Producto", "")):
                        if _ck not in _seen_keys:
                            _prods_set.append(_ck)
                            _seen_keys.add(_ck)
                    # También guardar nombre original para display cuando no está en catálogo
                    _raw = str(_row.get("Producto", "")).strip()
                    if _raw and not _normalize_product_to_catalog(_raw):
                        pass  # producto no catalogado → no se muestra en last_products
                last_products = _prods_set if _prods_set else [
                    str(same_day.iloc[0].get("Producto", "Sin especificar")).strip()
                ]
                last_product = " + ".join(last_products) if last_products else "Sin especificar"

        days_since = (today - last_date).days if last_date is not None else 999

        # ── Lluvia y eventos desde el último tratamiento ──────────────────────
        rain_since          = 0.0
        mills_events_since  = 0
        monilia_events_since = 0
        max_mills_since     = 0.0
        max_monilia_since   = 0.0

        ref_date = last_date if last_date is not None else today - pd.Timedelta(days=persistence_days)

        if not history_df.empty:
            h = history_df.copy()
            h["fecha_hora"] = pd.to_datetime(h["fecha_hora"])
            h_since = h[h["fecha_hora"] >= ref_date]
            rain_since = round(float(pd.to_numeric(h_since["lluvia_mm"], errors="coerce").sum()), 1)

        if not risk_df.empty:
            hist_risk = risk_df[(risk_df["Fecha"] >= ref_date) & (~risk_df["Es_prediccion"])]
            mills_events_since   = int((hist_risk["Mills_valor"].fillna(0)   >= 100).sum())
            monilia_events_since = int((hist_risk["Monilia_valor"].fillna(0) >= 100).sum())
            max_mills_since      = float(hist_risk["Mills_valor"].fillna(0).max())
            max_monilia_since    = float(hist_risk["Monilia_valor"].fillna(0).max())

        # ── Previsión 3 días ──────────────────────────────────────────────────
        fc_mills_max   = 0.0
        fc_monilia_max = 0.0
        fc_rain        = 0.0
        if not risk_df.empty:
            fc = risk_df[
                risk_df["Es_prediccion"] &
                (risk_df["Fecha"] >= today) &
                (risk_df["Fecha"] <= today + pd.Timedelta(days=3))
            ]
            if not fc.empty:
                fc_mills_max   = float(fc["Mills_valor"].fillna(0).max())
                fc_monilia_max = float(fc["Monilia_valor"].fillna(0).max())
                fc_rain        = float(fc["Lluvia"].fillna(0).sum())

        # ── Lógica de decisión ────────────────────────────────────────────────
        # Basada en EPPO PP1/5 (Venturia), CABI compendium y guías RIMpro:
        #
        # COBERTURA CADUCADA: criterio temporal + efecto lluvia acumulada
        #   - Más de `persistence_days` días sin fungicida, O
        #   - Más de 12 días Y lluvia acumulada ≥ 35 mm (lixivia el contacto preventivo)
        unprotected = (days_since >= persistence_days) or (days_since >= 12 and rain_since >= 35)

        # PREVISIÓN DE INFECCIÓN (próximos 3 días) — el factor más urgente.
        # Si hay cobertura caducada + previsión → tratar ANTES de que llegue la lluvia.
        fc_mills_event   = fc_mills_max >= 100    # evento Mills confirmado en previsión
        fc_monilia_event = fc_monilia_max >= 100   # evento Monilia en previsión
        fc_rain_alert    = fc_rain >= 15           # ≥15 mm previstos (umbral lavado + infección)
        fc_alert = fc_mills_event or fc_monilia_event or fc_rain_alert

        # EXPOSICIÓN ACUMULADA SIN COBERTURA: eventos Mills/Monilia desde el último fungicida.
        # Cada evento = período de infección completado (latencia 9-21 días, Rühmer 1998).
        # NO dispara "tratar hoy" por sí solo, pero aumenta la urgencia de planificar.
        # Umbral: ≥3 eventos sin cobertura = exposición seria (no hay número en la bibliografía
        # pero es conservador para frutales de pepita en fase sensible).
        accumulated_exposure = (mills_events_since + monilia_events_since) >= 3

        # ── Prioridades ───────────────────────────────────────────────────────
        if unprotected and fc_alert:
            # Sin cobertura + infección inminente: actuar antes de la lluvia
            priority = 1
            action   = "🔴 TRATAR HOY — infección prevista"
            row_bg   = "#ffcdd2"

        elif unprotected and accumulated_exposure:
            # Sin cobertura + exposición acumulada seria + sin previsión inmediata:
            # planificar en ≤2 días, no es una emergencia de hoy pero no puede esperar
            priority = 2
            action   = "🟠 Tratar pronto — cobertura caducada"
            row_bg   = "#ffe0b2"

        elif unprotected:
            # Sin cobertura pero sin previsión ni exposición seria:
            # ventana segura corta, planificar en 3-5 días
            priority = 3
            action   = "🟡 Planificar — sin cobertura activa"
            row_bg   = "#fff9c4"

        elif fc_alert and days_since >= 10:
            # Cobertura aún activa pero próxima a caducar + previsión de infección:
            # la lluvia puede lavar o coincidir con fin de cobertura
            priority = 3
            action   = "🟡 Vigilar — infección prevista"
            row_bg   = "#fff9c4"

        else:
            # Cobertura activa y sin previsión de infección
            priority = 4
            action   = "🟢 OK — protegido"
            row_bg   = "#f1f8f1"

        # Riesgo dominante (para seleccionar producto)
        # Solo incluye patógenos con previsión activa o exposición acumulada relevante
        dominant = []
        if fc_mills_event or (mills_events_since >= 2 and unprotected):
            dominant.append("Moteado")
        if fc_monilia_event or (monilia_events_since >= 1 and unprotected):
            dominant.append("Monilia")
        if not dominant and unprotected:
            # Sin riesgo específico confirmado pero sin cobertura → espectro amplio
            dominant = ["Moteado", "Monilia"]
        if not dominant:
            dominant = ["—"]

        # Conteo de aplicaciones en la campaña actual para este campo
        _app_counts, _sdhi_total = count_field_applications(
            activities_df, campo, year=today.year
        )
        # Resumen legible de pases: "Flint 1/2 · Folicur 0/3"
        _pases_parts = []
        for _pk, _pmax in PRODUCT_MAX_APPLICATIONS.items():
            _n = _app_counts.get(_pk, 0)
            _short = _pk.split()[0]   # "FOLICUR", "SIGNUM", "FLINT", "LUNA"
            _pases_parts.append(f"{_short} {_n}/{_pmax}")
        _pases_label = " · ".join(_pases_parts)

        # Texto descriptivo del último fungicida aplicado
        if last_date:
            _last_label = f"{last_date.strftime('%d/%m/%Y')} · {last_product}"
        else:
            _last_label = "⚠️ Sin fungicida registrado"

        # Narrativa explicativa del motivo de tratamiento
        _narrative = build_treatment_narrative(
            days_since         = days_since,
            rain_since         = rain_since,
            mills_events_since = mills_events_since,
            monilia_events_since = monilia_events_since,
            fc_mills_max       = fc_mills_max,
            fc_monilia_max     = fc_monilia_max,
            fc_rain            = fc_rain,
            last_product       = last_product,
            persistence_days   = persistence_days,
            priority           = priority,
            last_date          = last_date,
        )

        rows.append({
            "Campo":              campo,
            "Variedades":         variedades,
            "Último fungicida":  _last_label,
            "Días sin trat.":    (days_since if days_since < 999 else "—"),
            "Lluvia desde mm":   rain_since,
            "Eventos infección":  mills_events_since + monilia_events_since,
            "Previsión Mills":   int(fc_mills_max),
            "Lluvia prevista mm": round(fc_rain, 1),
            "Pases campaña":     _pases_label,
            "Riesgo principal":  ", ".join(dominant),
            "🎯 Acción":         action,
            "📋 Motivo":         _narrative,
            "_priority":         priority,
            "_bg":               row_bg,
            "_days_sort":        days_since,
            "_last_product":     last_product,
            "_dominant_list":    dominant,
            "_app_counts":       _app_counts,
            "_sdhi_total":       _sdhi_total,
        })

    df = (pd.DataFrame(rows)
          .sort_values(["_priority", "_days_sort"], ascending=[True, False])
          .drop(columns=["_days_sort"])
          .reset_index(drop=True))
    return df


def build_risk_timeline(history_df, forecast_df, days_back=45, base_temp=10.0, upper_temp=31.1):
    """
    DataFrame diario con valores de riesgo para Moteado, Monilia, Oídio y DD Carpocapsa.
    Cubre los últimos `days_back` días reales + todos los días de predicción.

    MODELO POR EVENTOS (coherente con el item Sanidad): el moteado y la monilia se
    calculan a partir de EVENTOS CONTINUOS de hoja mojada (detect_leaf_wetness_events)
    y su ratio frente al umbral de Mills, NO de la suma diaria de horas húmedas (que
    sobreestimaba y pintaba casi todos los días como "grave"). Cada evento se asigna
    al día en que TERMINA (cuando se completa la infección).
    """
    today = pd.Timestamp.now().normalize()
    start = today - pd.Timedelta(days=int(days_back))

    # 1. Combinar histórico (real) + previsión (futuro) en un único horario.
    frames = []
    if history_df is not None and not history_df.empty:
        h = history_df.copy()
        h["fecha_hora"] = pd.to_datetime(h["fecha_hora"])
        h = h[(h["fecha_hora"] >= start) & (h["fecha_hora"] < today)].copy()
        if not h.empty:
            h["_es_pred"] = False
            frames.append(h)
    if forecast_df is not None and not forecast_df.empty:
        f = forecast_df.copy()
        f["fecha_hora"] = pd.to_datetime(f["fecha_hora"])
        f = f[f["fecha_hora"] >= today].copy()
        if not f.empty:
            # La previsión no tiene sensor de hoja: estimamos hoja mojada horaria de
            # forma conservadora (lluvia o HR≥92, como antes), para no inflar el futuro.
            if "humectacion_hoja" not in f.columns:
                f["humectacion_hoja"] = np.nan
            _hr = pd.to_numeric(f.get("hr_media"), errors="coerce")
            _ll = pd.to_numeric(f.get("lluvia_mm"), errors="coerce").fillna(0)
            _wet_est = ((_hr >= 92) | (_ll > 0.1))
            _sin_sensor = pd.to_numeric(f["humectacion_hoja"], errors="coerce").isna()
            f.loc[_sin_sensor, "humectacion_hoja"] = np.where(_wet_est[_sin_sensor], 60.0, 0.0)
            f["_es_pred"] = True
            frames.append(f)

    if not frames:
        return pd.DataFrame()

    allh = pd.concat(frames, ignore_index=True).sort_values("fecha_hora")
    for _col in ("temp_media", "temp_min", "temp_max", "hr_media", "lluvia_mm", "humectacion_hoja"):
        if _col not in allh.columns:
            allh[_col] = np.nan

    # 2. Detectar eventos de hoja mojada sobre TODO el horario (igual que Sanidad)
    #    y mapear cada evento al día en que termina → máximo ratio de ese día.
    mills_by_day, monilia_by_day = {}, {}
    try:
        events = detect_leaf_wetness_events(allh)
    except Exception:
        events = pd.DataFrame()
    if events is not None and not events.empty:
        for _, ev in events.iterrows():
            fin = pd.to_datetime(ev.get("Fin"), errors="coerce")
            if pd.isna(fin):
                continue
            d = fin.normalize()
            rm = ev.get("Ratio moteado", np.nan)
            ro = ev.get("Ratio monilia", np.nan)
            if pd.notna(rm):
                mills_by_day[d] = max(mills_by_day.get(d, 0.0), float(rm) * 100.0)
            if pd.notna(ro):
                monilia_by_day[d] = max(monilia_by_day.get(d, 0.0), float(ro) * 100.0)

    # 3. Construir filas diarias con agregados meteo + valores de enfermedad por evento.
    allh["_fecha"] = allh["fecha_hora"].dt.date
    rows = []
    for fecha, g in allh.groupby("_fecha"):
        d = pd.Timestamp(fecha)
        es_pred  = bool(g["_es_pred"].any()) if "_es_pred" in g.columns else False
        temp_med = pd.to_numeric(g["temp_media"], errors="coerce").mean()
        temp_min = pd.to_numeric(g["temp_min"],   errors="coerce").min()
        temp_max = pd.to_numeric(g["temp_max"],   errors="coerce").max()
        hr_med   = pd.to_numeric(g["hr_media"],   errors="coerce").mean()
        lluvia   = pd.to_numeric(g["lluvia_mm"],  errors="coerce").sum()
        horas_hum = int((pd.to_numeric(g["humectacion_hoja"], errors="coerce").fillna(0) > 0).sum())
        dd_dia = max(0.0, min(float(temp_med) if pd.notna(temp_med) else 0.0, float(upper_temp)) - base_temp) if pd.notna(temp_med) else 0.0
        rows.append({
            "Fecha":          d,
            "T_min":          round(float(temp_min), 1) if pd.notna(temp_min) else None,
            "T_max":          round(float(temp_max), 1) if pd.notna(temp_max) else None,
            "T_med":          round(float(temp_med), 1) if pd.notna(temp_med) else None,
            "HR_med":         round(float(hr_med), 1)   if pd.notna(hr_med)   else None,
            "Lluvia":         round(float(lluvia), 1)   if pd.notna(lluvia)   else 0.0,
            "Horas_mojadura": horas_hum,
            "Es_prediccion":  es_pred,
            "Mills_valor":    round(min(mills_by_day.get(d, 0.0), 150.0), 1),
            "Monilia_valor":  round(min(monilia_by_day.get(d, 0.0), 100.0), 1),
            "Oidio_valor":    _dec_oidio_value(temp_med, hr_med, lluvia),
            "DD_dia":         round(dd_dia, 1),
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df = df.drop_duplicates("Fecha", keep="last").sort_values("Fecha").reset_index(drop=True)
    df["DD_acumulado"] = df["DD_dia"].cumsum().round(1)
    return df


def _dec_disease_chart(risk_df, value_col, disease_name, today, treats_df, height=300):
    """
    Crea gráfico Plotly estilo RIMpro para una enfermedad.
    Barras coloreadas por nivel de riesgo + lluvia como fondo + zona predicción.
    """
    import plotly.graph_objects as go

    dates  = risk_df["Fecha"].tolist()
    values = risk_df[value_col].fillna(0).tolist()
    lluvia = risk_df["Lluvia"].fillna(0).tolist()
    es_pred = risk_df["Es_prediccion"].tolist()

    fig = go.Figure()

    # Precipitación (fondo, eje secundario)
    fig.add_trace(go.Bar(
        x=dates, y=lluvia,
        name="Lluvia (mm)",
        marker_color="rgba(100,160,255,0.35)",
        yaxis="y2",
        hovertemplate="%{x|%d/%m}<br>Lluvia: %{y:.1f} mm<extra></extra>",
    ))

    # Zonas de gravedad de fondo (verde / amarillo / naranja / rojo)
    _zones = [
        (0,   25,  "rgba(44,160,44,0.10)"),    # verde   — sin/ligero
        (25,  50,  "rgba(245,197,24,0.14)"),   # amarillo — ligero
        (50,  100, "rgba(255,127,14,0.14)"),   # naranja  — moderado
        (100, 160, "rgba(214,39,40,0.14)"),    # rojo     — grave
    ]
    for _lo, _hi, _col in _zones:
        fig.add_hrect(y0=_lo, y1=_hi, fillcolor=_col, line_width=0, layer="below")

    # Curva de infección: línea suavizada (spline) rellena hasta cero. El relleno
    # deja ver las zonas de color del fondo → el área se "colorea" según la gravedad
    # que alcanza la curva. La línea se colorea según el pico del periodo.
    _peak_col = _dec_bar_color(max(values) if values else 0)
    fig.add_trace(go.Scatter(
        x=dates, y=values,
        name=disease_name,
        mode="lines",
        line=dict(shape="spline", smoothing=0.9, color=_peak_col, width=2.6),
        fill="tozeroy", fillcolor="rgba(120,120,120,0.10)",
        customdata=list(zip(
            risk_df["T_med"].fillna("?").tolist(),
            risk_df["HR_med"].fillna("?").tolist(),
            risk_df["Horas_mojadura"].tolist(),
        )),
        hovertemplate=(
            "<b>%{x|%d/%m/%Y}</b><br>"
            f"Valor infección: %{{y:.0f}}<br>"
            "T media: %{customdata[0]}°C<br>"
            "HR media: %{customdata[1]}%<br>"
            "Horas mojadura: %{customdata[2]}<extra></extra>"
        ),
    ))

    # Etiquetas de umbral a la derecha
    fig.add_hline(y=100, line_dash="dash", line_color="rgba(214,39,40,0.5)", line_width=1,
                  annotation_text="Grave", annotation_position="right")
    fig.add_hline(y=50,  line_dash="dash", line_color="rgba(255,127,14,0.5)", line_width=1,
                  annotation_text="Moderado", annotation_position="right")
    fig.add_hline(y=25,  line_dash="dot",  line_color="rgba(204,187,0,0.5)", line_width=1,
                  annotation_text="Ligero", annotation_position="right")

    # Zona predicción
    pred_dates = risk_df[risk_df["Es_prediccion"]]["Fecha"]
    if not pred_dates.empty:
        x0_pred = pred_dates.min() - pd.Timedelta(hours=12)
        fig.add_vrect(
            x0=x0_pred,
            x1=risk_df["Fecha"].max() + pd.Timedelta(hours=12),
            fillcolor="rgba(180,210,255,0.12)", line_width=0,
        )
        fig.add_annotation(
            x=x0_pred, y=1, yref="paper",
            text="◀ real │ predicción ▶",
            showarrow=False, xanchor="left",
            font=dict(size=10, color="rgba(80,80,180,0.8)"),
            bgcolor="rgba(255,255,255,0.6)",
        )

    # Línea de hoy
    fig.add_vline(
        x=today,
        line_color="rgba(255,140,0,0.9)", line_width=2, line_dash="solid",
    )

    # Tratamientos
    if treats_df is not None and not treats_df.empty and "Fecha_dt" in treats_df.columns:
        t_dates = pd.to_datetime(treats_df["Fecha_dt"], errors="coerce").dropna()
        t_dates = t_dates[(t_dates >= risk_df["Fecha"].min()) & (t_dates <= risk_df["Fecha"].max())]
        for td in t_dates:
            fig.add_vline(
                x=td,
                line_color="rgba(150,0,200,0.7)", line_width=1.5, line_dash="dash",
            )
        # Leyenda de tratamiento
        if not t_dates.empty:
            fig.add_trace(go.Scatter(
                x=[None], y=[None], mode="lines",
                name="Tratamiento",
                line=dict(color="rgba(150,0,200,0.7)", width=1.5, dash="dash"),
            ))

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=60, t=10, b=30),
        barmode="overlay",
        showlegend=True,
        # Sin arrastre: que deslizar/clic-arrastrar sobre la gráfica NO la mueva
        # (en el móvil deja pasar el scroll de la página; en PC no la desplaza).
        dragmode=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font_size=11),
        yaxis=dict(title="Valor de infección", range=[0, max(160, max(values)*1.1) if values else 160],
                   gridcolor="rgba(200,200,200,0.3)", fixedrange=True),
        yaxis2=dict(title="Lluvia (mm)", overlaying="y", side="right",
                    range=[0, max(max(lluvia)*4, 10) if lluvia else 10],
                    showgrid=False, tickfont_color="rgba(100,160,255,0.8)", fixedrange=True),
        xaxis=dict(tickformat="%d/%m", gridcolor="rgba(200,200,200,0.2)", fixedrange=True),
        plot_bgcolor="rgba(255,255,255,1)",
        paper_bgcolor="rgba(0,0,0,0)",
        bargap=0.1,
    )
    return fig


def _dec_carpocapsa_chart(risk_df, today, biofix_df, traps_df, treats_carpo_df, base_temp, upper_temp, height=320, days_back=45, history_df=None):
    """Gráfico de DD acumulados desde biofix + capturas + tratamientos."""
    import plotly.graph_objects as go

    # Determinar biofix del año en curso
    biofix_date = None
    current_year = today.year
    if biofix_df is not None and not biofix_df.empty and "Fecha biofix" in biofix_df.columns:
        bf_all_dates = pd.to_datetime(biofix_df["Fecha biofix"], errors="coerce").dropna()
        if not bf_all_dates.empty:
            # 1. Preferir fechas cuyo año coincide con el año actual
            bf_current = bf_all_dates[bf_all_dates.dt.year == current_year]
            if not bf_current.empty:
                biofix_date = bf_current.min()
            else:
                # 2. Sin biofix del año actual → proyectar la fecha más reciente al año en curso
                last_bf = bf_all_dates.max()
                candidate = last_bf.replace(year=current_year)
                # Usar sólo si ya ha pasado; si es futura (raro), usar año anterior
                biofix_date = candidate if candidate <= pd.Timestamp(today) else last_bf.replace(year=current_year - 1)

    # Construir DD desde biofix usando todo el histórico si está disponible
    # (así DD acumulado es correcto aunque sólo mostremos la ventana reciente)
    if biofix_date is not None and history_df is not None and not history_df.empty:
        _h = history_df.copy()
        _h["fecha_hora"] = pd.to_datetime(_h["fecha_hora"])
        _h["_fecha"] = _h["fecha_hora"].dt.date
        _h["temp_media"] = pd.to_numeric(_h["temp_media"], errors="coerce")
        _h_daily = (
            _h[_h["fecha_hora"] >= pd.Timestamp(biofix_date)]
            .groupby("_fecha")["temp_media"].mean()
            .reset_index()
        )
        _h_daily["DD_dia_full"] = (_h_daily["temp_media"].clip(upper=float(upper_temp)) - base_temp).clip(lower=0)
        _h_daily["Fecha"] = pd.to_datetime(_h_daily["_fecha"])
        _h_daily["DD_acum_full"] = _h_daily["DD_dia_full"].cumsum().round(1)
        # Merge the full cumulative DD back into risk_df by date
        _merge = risk_df.merge(
            _h_daily[["Fecha", "DD_acum_full"]],
            on="Fecha", how="left"
        )
        # For forecast dates (not in history), extend cumulation
        last_dd = _merge["DD_acum_full"].dropna().iloc[-1] if not _merge["DD_acum_full"].dropna().empty else 0.0
        for i in _merge.index:
            if pd.isna(_merge.at[i, "DD_acum_full"]):
                last_dd = last_dd + _merge.at[i, "DD_dia"]
                _merge.at[i, "DD_acum_full"] = round(last_dd, 1)
        plot_df = _merge.copy()
        plot_df["DD_acumulado"] = plot_df["DD_acum_full"]
    else:
        plot_df = risk_df.copy()
        if biofix_date is not None:
            plot_df = plot_df[plot_df["Fecha"] >= biofix_date].copy()
            if not plot_df.empty:
                plot_df["DD_acumulado"] = plot_df["DD_dia"].cumsum().round(1)

    if plot_df.empty:
        plot_df = risk_df.copy()

    # Ventana de visualización: sólo mostrar los últimos days_back días + predicción
    display_start = today - pd.Timedelta(days=int(days_back))
    plot_df_display = plot_df[plot_df["Fecha"] >= display_start].copy()
    if plot_df_display.empty:
        plot_df_display = plot_df.copy()

    dates     = plot_df_display["Fecha"].tolist()
    dd_acum   = plot_df_display["DD_acumulado"].tolist()
    dd_dia    = plot_df_display["DD_dia"].tolist()
    es_pred   = plot_df_display["Es_prediccion"].tolist()
    lluvia    = plot_df_display["Lluvia"].fillna(0).tolist()

    fig = go.Figure()

    # DD diarios (fondo)
    dd_colors = ["rgba(255,100,50,0.55)" if p else "rgba(255,100,50,0.80)" for p in es_pred]
    fig.add_trace(go.Bar(
        x=dates, y=dd_dia,
        name="DD diarios",
        marker_color=dd_colors,
        yaxis="y2",
        hovertemplate="%{x|%d/%m}<br>DD día: %{y:.1f}<extra></extra>",
    ))

    # DD acumulados — histórico
    hist_idx = [i for i, p in enumerate(es_pred) if not p]
    pred_idx = [i for i, p in enumerate(es_pred) if p]

    if hist_idx:
        fig.add_trace(go.Scatter(
            x=[dates[i] for i in hist_idx],
            y=[dd_acum[i] for i in hist_idx],
            mode="lines",
            name="DD acumulados (real)",
            line=dict(color="#d62728", width=2.5),
            fill="tozeroy",
            fillcolor="rgba(214,39,40,0.12)",
            hovertemplate="%{x|%d/%m}<br>DD acum: %{y:.0f}<extra></extra>",
        ))

    if pred_idx:
        # Conectar con el último punto del histórico
        connect_i = hist_idx[-1] if hist_idx else pred_idx[0]
        x_pred = [dates[connect_i]] + [dates[i] for i in pred_idx]
        y_pred = [dd_acum[connect_i]] + [dd_acum[i] for i in pred_idx]
        fig.add_trace(go.Scatter(
            x=x_pred, y=y_pred,
            mode="lines",
            name="DD acumulados (predicción)",
            line=dict(color="#d62728", width=2, dash="dot"),
            fill="tozeroy",
            fillcolor="rgba(214,39,40,0.05)",
            hovertemplate="%{x|%d/%m}<br>DD acum (prev): %{y:.0f}<extra></extra>",
        ))

    # Umbrales de tratamiento
    max_dd = max(dd_acum) if dd_acum else 400
    ymax   = max(max_dd * 1.15, 400)
    for umbral, color, label in [(80, "#2ca02c", "1ª gen. inicio (80 DD)"),
                                  (150, "#ff7f0e", "1ª gen. pico (150 DD)"),
                                  (300, "#d62728", "2ª gen. inicio (300 DD)"),
                                  (500, "#9467bd", "2ª gen. pico (500 DD)")]:
        if umbral <= ymax * 1.2:
            fig.add_hline(y=umbral, line_dash="dash", line_color=color, line_width=1, opacity=0.7,
                          annotation_text=label, annotation_position="right",
                          annotation_font_size=10)

    # Capturas de trampas
    if traps_df is not None and not traps_df.empty:
        tf = traps_df.copy()
        if "Fecha_dt" in tf.columns and "Capturas" in tf.columns:
            tf["Fecha_dt"] = pd.to_datetime(tf["Fecha_dt"], errors="coerce")
            tf = tf.dropna(subset=["Fecha_dt"])
            if not plot_df_display.empty:
                tf = tf[(tf["Fecha_dt"] >= plot_df_display["Fecha"].min()) &
                        (tf["Fecha_dt"] <= plot_df_display["Fecha"].max())]
            if not tf.empty:
                # Interpolar DD en fecha de captura
                dd_interp = np.interp(
                    tf["Fecha_dt"].astype(np.int64),
                    pd.to_datetime(dates).astype(np.int64),
                    dd_acum,
                )
                fig.add_trace(go.Scatter(
                    x=tf["Fecha_dt"].tolist(),
                    y=dd_interp.tolist(),
                    mode="markers+text",
                    name="Capturas trampa",
                    marker=dict(
                        size=[max(8, min(c*3, 28)) for c in tf["Capturas"].fillna(0)],
                        color="rgba(0,120,200,0.8)",
                        symbol="circle",
                        line=dict(color="white", width=1),
                    ),
                    text=tf["Capturas"].astype(int).astype(str),
                    textposition="top center",
                    textfont=dict(size=9, color="rgba(0,80,160,1)"),
                    customdata=tf["Capturas"].tolist(),
                    hovertemplate="%{x|%d/%m}<br>Capturas: %{customdata}<br>DD: %{y:.0f}<extra></extra>",
                ))

    # Zona predicción
    pred_dates_df = plot_df_display[plot_df_display["Es_prediccion"]]["Fecha"]
    if not pred_dates_df.empty:
        fig.add_vrect(
            x0=pred_dates_df.min() - pd.Timedelta(hours=12),
            x1=plot_df_display["Fecha"].max() + pd.Timedelta(hours=12),
            fillcolor="rgba(180,210,255,0.12)", line_width=0,
        )

    # Línea de hoy
    fig.add_vline(x=today, line_color="rgba(255,140,0,0.9)", line_width=2)

    # Biofix marker — sólo si cae dentro de la ventana visible
    # (si está fuera, add_vline forzaría el eje X a extenderse hasta esa fecha)
    if biofix_date is not None:
        if biofix_date >= display_start:
            fig.add_vline(x=biofix_date, line_color="rgba(0,160,0,0.8)", line_width=2, line_dash="dash")
            fig.add_annotation(
                x=biofix_date, y=1, yref="paper",
                text=f"Biofix {biofix_date.strftime('%d/%m')}",
                showarrow=False, xanchor="left",
                font=dict(color="green", size=11),
                bgcolor="rgba(255,255,255,0.7)",
            )
        else:
            # Biofix fuera de la ventana: mostrar DD totales en subtítulo
            total_dd = dd_acum[-1] if dd_acum else 0
            fig.add_annotation(
                x=0, y=1.06, xref="paper", yref="paper",
                text=f"Biofix: {biofix_date.strftime('%d/%m/%Y')} · DD acumulados desde biofix: {total_dd:.0f}",
                showarrow=False, xanchor="left",
                font=dict(color="green", size=11),
                bgcolor="rgba(255,255,255,0.75)",
            )

    # Tratamientos carpocapsa
    if treats_carpo_df is not None and not treats_carpo_df.empty and "Fecha_dt" in treats_carpo_df.columns:
        t_dates = pd.to_datetime(treats_carpo_df["Fecha_dt"], errors="coerce").dropna()
        if not plot_df_display.empty:
            t_dates = t_dates[(t_dates >= plot_df_display["Fecha"].min()) &
                              (t_dates <= plot_df_display["Fecha"].max())]
        for td in t_dates:
            fig.add_vline(x=td, line_color="rgba(150,0,200,0.7)", line_width=1.5, line_dash="dash")
        if not t_dates.empty:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines",
                                     name="Tratamiento carpo.",
                                     line=dict(color="rgba(150,0,200,0.7)", width=1.5, dash="dash")))

    # Calcular límites explícitos del eje X para que Plotly no los amplíe
    # aunque algún add_vline/add_annotation caiga fuera de los datos
    if not plot_df_display.empty:
        _x_end = plot_df_display["Fecha"].max() + pd.Timedelta(hours=12)
    else:
        _x_end = today + pd.Timedelta(days=7)
    _x_start = display_start - pd.Timedelta(hours=12)

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=110, t=30, b=30),
        barmode="overlay",
        showlegend=True,
        dragmode=False,   # sin arrastre: deslizar sobre la gráfica no la mueve
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font_size=11),
        yaxis=dict(title="DD acumulados", range=[0, ymax], gridcolor="rgba(200,200,200,0.3)", fixedrange=True),
        yaxis2=dict(title="DD/día", overlaying="y", side="right",
                    range=[0, max(max(dd_dia)*5, 15) if dd_dia else 15],
                    showgrid=False, tickfont_color="rgba(255,100,50,0.8)", fixedrange=True),
        xaxis=dict(
            tickformat="%d/%m",
            gridcolor="rgba(200,200,200,0.2)",
            range=[_x_start, _x_end],   # ← fija el rango; evita expansión por biofix lejano
            fixedrange=True,
        ),
        plot_bgcolor="rgba(250,250,255,1)",
        paper_bgcolor="rgba(0,0,0,0)",
        bargap=0.1,
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# SEGUIMIENTO DE TODOS LOS FITOSANITARIOS
# ══════════════════════════════════════════════════════════════════════════════

# Catálogo de productos conocidos con su tipo y plazo de seguridad.
# Se usa para clasificar actuaciones de Agroptima y calcular días de franquicia.
# Fuente: Registro de productos fitosanitarios MAPA, fichas técnicas fabricante.
PHYTOSANITARY_CATALOG = [
    # ── Fungicidas (catálogo propio 2026) ─────────────────────────────────────
    {"Producto": "FOLICUR 25 WG",    "Tipo": "Fungicida",     "Plazo días": 7,  "Objetivo": "Moteado, Oídio"},
    {"Producto": "SIGNUM",           "Tipo": "Fungicida",     "Plazo días": 7,  "Objetivo": "Monilia, Moteado"},
    {"Producto": "FLINT 50 WG",      "Tipo": "Fungicida",     "Plazo días": 14, "Objetivo": "Moteado, Oídio"},
    {"Producto": "LUNA EXPERIENCE",  "Tipo": "Fungicida",     "Plazo días": 7,  "Objetivo": "Monilia, Moteado, Oídio"},
    # ── Insecticidas biológicos ────────────────────────────────────────────────
    {"Producto": "BACTUR",           "Tipo": "Insecticida biológico", "Plazo días": 0,  "Objetivo": "Carpocapsa, Tortrix, Orugas"},
    {"Producto": "XENTARI",          "Tipo": "Insecticida biológico", "Plazo días": 0,  "Objetivo": "Carpocapsa, Orugas"},
    {"Producto": "DIPEL",            "Tipo": "Insecticida biológico", "Plazo días": 0,  "Objetivo": "Carpocapsa, Orugas"},
    {"Producto": "SPINTOR",          "Tipo": "Insecticida biológico", "Plazo días": 7,  "Objetivo": "Carpocapsa, Trips"},
    # ── Insecticidas químicos ──────────────────────────────────────────────────
    {"Producto": "KARATE ZEON",      "Tipo": "Insecticida",   "Plazo días": 7,  "Objetivo": "Pulgón, Trips, Orugas"},
    {"Producto": "MOSPILAN",         "Tipo": "Insecticida",   "Plazo días": 14, "Objetivo": "Pulgón, Psila"},
    {"Producto": "CONFIDOR",         "Tipo": "Insecticida",   "Plazo días": 21, "Objetivo": "Pulgón, Psila"},
    {"Producto": "MOVENTO",          "Tipo": "Insecticida",   "Plazo días": 14, "Objetivo": "Pulgón, Psila, Ácaros"},
    # ── Acaricidas ────────────────────────────────────────────────────────────
    {"Producto": "ARACAN",           "Tipo": "Acaricida",     "Plazo días": 14, "Objetivo": "Ácaros"},
    {"Producto": "VERTIMEC",         "Tipo": "Acaricida",     "Plazo días": 14, "Objetivo": "Ácaros"},
    {"Producto": "ENVIDOR",          "Tipo": "Acaricida",     "Plazo días": 14, "Objetivo": "Ácaros"},
    {"Producto": "OBERON",           "Tipo": "Acaricida",     "Plazo días": 28, "Objetivo": "Ácaros"},
    # ── Confusión sexual ──────────────────────────────────────────────────────
    {"Producto": "ISOMATE",          "Tipo": "Confusión sexual", "Plazo días": 0, "Objetivo": "Carpocapsa"},
    {"Producto": "CHECKMATE",        "Tipo": "Confusión sexual", "Plazo días": 0, "Objetivo": "Carpocapsa"},
    {"Producto": "DISRUPT",          "Tipo": "Confusión sexual", "Plazo días": 0, "Objetivo": "Carpocapsa"},
]

# Mapa rápido: primera palabra en mayúsculas → entrada del catálogo
_PHYTO_CATALOG_INDEX = {}
for _entry in PHYTOSANITARY_CATALOG:
    _first = _entry["Producto"].split()[0].upper()
    if _first not in _PHYTO_CATALOG_INDEX:
        _PHYTO_CATALOG_INDEX[_first] = _entry
    # También indexar por nombre completo en mayúsculas
    _PHYTO_CATALOG_INDEX[_entry["Producto"].upper()] = _entry


def _classify_phyto_product(producto_str):
    """
    Clasifica un producto de Agroptima según el catálogo fitosanitario completo.
    Devuelve dict con Tipo, Plazo días, Objetivo (o valores por defecto si no reconocido).
    Diferente de classify_product() (que clasifica para Carpocapsa/fungicida/abono).
    """
    prod_up = str(producto_str).strip().upper()
    # Búsqueda exacta primero
    if prod_up in _PHYTO_CATALOG_INDEX:
        return _PHYTO_CATALOG_INDEX[prod_up]
    # Búsqueda por primera palabra
    first_word = prod_up.split()[0] if prod_up else ""
    if first_word in _PHYTO_CATALOG_INDEX:
        return _PHYTO_CATALOG_INDEX[first_word]
    # Búsqueda parcial: ¿alguna clave del índice está contenida en el nombre del producto?
    for key, entry in _PHYTO_CATALOG_INDEX.items():
        if len(key) >= 4 and key in prod_up:
            return entry
    # No reconocido → clasificar por keywords genéricas
    if is_fungicide_activity(producto_str):
        return {"Producto": producto_str, "Tipo": "Fungicida",    "Plazo días": 7,  "Objetivo": "Ver etiqueta"}
    _prod_low = prod_up.lower()
    for kw in _NON_FUNGICIDE_KEYWORDS:
        if kw in _prod_low:
            if kw in ("bactur", "bacillus", "thuringiensis", "spinosad", "dipel", "xentari"):
                return {"Producto": producto_str, "Tipo": "Insecticida biológico", "Plazo días": 0, "Objetivo": "Lepidópteros"}
            if kw in ("aracan", "abamectin", "abamectina", "envidor", "oberon"):
                return {"Producto": producto_str, "Tipo": "Acaricida", "Plazo días": 14, "Objetivo": "Ácaros"}
            if kw in ("karate", "lambda", "cipermetrin", "deltametrin", "imidacloprid", "acetamiprid"):
                return {"Producto": producto_str, "Tipo": "Insecticida", "Plazo días": 14, "Objetivo": "Ver etiqueta"}
    return {"Producto": producto_str, "Tipo": "No clasificado", "Plazo días": None, "Objetivo": "—"}


def _split_multi_product(prod_str):
    """
    Divide una cadena de productos que puede contener varios mezclados en la misma
    cuba, tal como los exporta Agroptima tras clean_agroptima_bullet_text:
      "FLINT 50 WG, BACTUR WG"  →  ["FLINT 50 WG", "BACTUR WG"]
      "LUNA EXPERIENCE"          →  ["LUNA EXPERIENCE"]

    Heurística: el separador es una COMA seguida de espacio donde la parte
    siguiente empieza por un token reconocido en el catálogo fitosanitario O
    tiene al menos 3 caracteres en mayúsculas.  Esto evita partir nombres como
    "BACTUR 2X, WG" mal si alguien escribiera eso, aunque en la práctica
    Agroptima ya da el nombre comercial limpio.
    """
    if not prod_str or str(prod_str).lower() == "nan":
        return []

    # Primero intentar con punto y coma (separador más inequívoco)
    parts = [p.strip() for p in str(prod_str).replace(";", ",").split(",") if p.strip()]

    if len(parts) <= 1:
        return parts

    # Filtrar fragmentos vacíos o que sean claramente continuación del nombre
    # (menos de 2 caracteres, o solo números/unidades como "25", "WG", "50")
    _UNIT_TOKENS = {"WG", "WP", "SC", "EC", "SL", "CS", "GR", "DP", "EW",
                    "25", "50", "75", "80", "100", "2X", "L", "KG", "G"}
    cleaned = []
    pending = ""
    for part in parts:
        tok = part.strip().upper()
        if tok in _UNIT_TOKENS or (len(tok) <= 2 and not tok.isalpha()):
            # Es una unidad o código, pegar al anterior
            if cleaned:
                cleaned[-1] = cleaned[-1] + " " + part.strip()
            elif pending:
                pending = pending + " " + part.strip()
        else:
            if pending:
                cleaned.append(pending)
            pending = part.strip()
    if pending:
        cleaned.append(pending)

    return cleaned if cleaned else [prod_str]


def build_phytosanitary_tracking(activities_df, year=None):
    """
    Genera un DataFrame con el seguimiento de TODOS los productos fitosanitarios
    aplicados en la campaña, por campo.

    Columnas: Campo | Producto | Tipo | Objetivo | Último uso | Días desde uso |
              Pases campaña | Plazo seguridad días | Estado plazo

    Excluye abonos, fertirrigación y herbicidas (no son fitosanitarios de cultivo).
    """
    if year is None:
        year = pd.Timestamp.now().year
    today = pd.Timestamp.now().normalize()

    if activities_df.empty or "Campos reconocidos" not in activities_df.columns:
        return pd.DataFrame()

    _acts = activities_df.copy()
    _acts["Fecha_dt"] = pd.to_datetime(_acts["Fecha"], errors="coerce")
    _acts = _acts.dropna(subset=["Fecha_dt"])
    _acts = _acts[_acts["Fecha_dt"].dt.year == int(year)]

    if _acts.empty:
        return pd.DataFrame()

    # Excluir abonos, herbicidas y no-fitosanitarios
    _EXCLUDE_KW = {
        "abono", "fertilizante", "fertirrigacion", "npk", "nitrogeno",
        "fosforo", "potasio", "aminoacido", "alga", "humico", "fulvico",
        "herbicida", "glifosato", "roundup", "simazina",
        "aceite mineral", "aceite parafina",
    }

    def _is_excluded(prod):
        t = str(prod).lower()
        return any(kw in t for kw in _EXCLUDE_KW)

    _acts = _acts[~_acts["Producto"].apply(_is_excluded)]
    if _acts.empty:
        return pd.DataFrame()

    # Expandir: una fila por campo × producto individual × fecha
    # IMPORTANTE: Agroptima puede exportar varios productos en una misma celda
    # separados por coma (p.ej. "FLINT 50 WG, BACTUR WG" cuando se mezclan en
    # la misma cuba). Hay que desglosarlos para que cada producto se contabilice
    # por separado.
    records = []
    for _, row in _acts.iterrows():
        campos_str = str(row.get("Campos reconocidos", "") or row.get("Campos", ""))
        campos = [c.strip() for c in campos_str.split(",") if c.strip()]
        prod_raw = str(row.get("Producto", "")).strip()
        if not prod_raw or prod_raw.lower() == "nan":
            continue
        fecha_dt = row["Fecha_dt"].normalize()

        # Separar productos individuales (pueden venir como "PROD A, PROD B")
        # Usamos heurística: si una parte coincide con catálogo o tiene ≥4 chars
        # la tratamos como producto separado; si no, puede ser continuación del nombre.
        productos_individuales = _split_multi_product(prod_raw)

        for prod_individual in productos_individuales:
            info = _classify_phyto_product(prod_individual)
            for campo in campos:
                records.append({
                    "Campo":       campo,
                    "Producto":    prod_individual,
                    "Tipo":        info["Tipo"],
                    "Objetivo":    info["Objetivo"],
                    "Plazo días":  info["Plazo días"],
                    "Fecha_dt":    fecha_dt,
                })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["Fecha_dt"] = pd.to_datetime(df["Fecha_dt"])

    # Agrupar: por campo × producto → último uso + conteo de pases
    rows_out = []
    for (campo, prod), grp in df.groupby(["Campo", "Producto"], sort=False):
        info       = _classify_phyto_product(prod)
        last_fecha = grp["Fecha_dt"].max()
        dias       = int((today - last_fecha).days)
        n_pases    = grp["Fecha_dt"].dt.date.nunique()  # pasadas únicas por fecha
        plazo      = info["Plazo días"]

        if plazo is None:
            estado = "—"
        elif plazo == 0:
            estado = "✅ Sin plazo"
        elif dias <= plazo:
            restantes = plazo - dias
            estado = f"⚠️ En plazo ({restantes}d restantes)" if restantes <= 7 else f"🔒 En plazo ({restantes}d restantes)"
        else:
            estado = "✅ Plazo superado"

        rows_out.append({
            "Campo":           campo,
            "Producto":        prod,
            "Tipo":            info["Tipo"],
            "Objetivo":        info["Objetivo"],
            "Último uso":      last_fecha.strftime("%d/%m/%Y"),
            "Días desde uso":  dias,
            "Pases campaña":   n_pases,
            "Plazo seg. días": plazo if plazo is not None else "—",
            "Estado plazo":    estado,
        })

    if not rows_out:
        return pd.DataFrame()

    result = (pd.DataFrame(rows_out)
              .sort_values(["Campo", "Tipo", "Días desde uso"])
              .reset_index(drop=True))
    return result


def carpocapsa_sync_annotation(campo_name, windows_df):
    """
    Dado un campo del panel de fungicidas, busca si hay una ventana de carpocapsa
    activa, próxima o ya tratada para ese campo.

    Devuelve (texto_anotacion, nivel_urgencia):
      nivel_urgencia: "now" | "soon" | "later" | "done" | "none"

    Lógica de prioridad:
      1. Ventana activa sin tratamiento → combinar HOY (fungicida + carpocapsa)
      2. Ventana en ≤3 días             → esperar y combinar
      3. Ventana en 4-7 días            → valorar esperar
      4. Ventana ya tratada             → sin urgencia, ya cubierta
      5. Sin ventana relevante          → sin anotación
    """
    if windows_df is None or windows_df.empty:
        return "", "none"

    campo_low = str(campo_name).strip().lower()

    def _carpo_campo_match(zona_str):
        z      = str(zona_str).strip().lower()
        z_base = z.split(" - ")[0].strip()
        c_base = campo_low.split(" - ")[0].strip()
        if z == campo_low or z_base == c_base:
            return True

        def _substr_whole(needle, haystack):
            """
            True si needle aparece en haystack como palabra completa:
            el carácter siguiente a la coincidencia debe ser fin de cadena,
            espacio o un separador no alfanumérico/no guión.
            Esto evita que 'sector 10' coincida con 'sector 10-b'.
            """
            idx = haystack.find(needle)
            if idx == -1:
                return False
            end = idx + len(needle)
            if end >= len(haystack):
                return True            # coincidencia exacta al final
            next_ch = haystack[end]
            return not (next_ch.isalnum() or next_ch == "-")

        # Substring bidireccional (mínimo 4 caracteres para evitar falsos)
        if len(c_base) >= 4 and _substr_whole(c_base, z):
            return True
        if len(z_base) >= 4 and _substr_whole(z_base, campo_low):
            return True
        return False

    matched = windows_df[windows_df["Campo/Zona"].apply(_carpo_campo_match)]
    if matched.empty:
        return "", "none"

    # "Activa" sin tratar o "2º pase" (residuo agotado) → acción pendiente.
    activas    = matched[matched["Estado"].str.contains("Activa|pase", na=False)]
    tratadas   = matched[matched["Estado"].str.contains("Tratado", na=False)]
    # "espera" pero NO "esperar" de un 2º pase (ya cubierto por activas)
    en_espera  = matched[matched["Estado"].str.contains("En espera|hasta ventana", na=False)]

    # ── 1. Ventana activa sin tratar / 2º pase ────────────────────────────────
    if not activas.empty:
        # Comprobar si hay restricción de reentrada Bactur
        if "_reentry_wait" in activas.columns:
            max_wait = int(activas["_reentry_wait"].fillna(0).max())
            if max_wait > 0:
                return f"⏳ Esperar {max_wait}d — reentrada Bactur", "soon"
        return "🐛 Combinar HOY — ventana activa", "now"

    # ── 2. En espera — extraer días más próximos ──────────────────────────────
    if not en_espera.empty:
        min_days = None
        for _, _r in en_espera.iterrows():
            _info = str(_r.get("Info", ""))
            _m = re.match(r"(\d+)d hasta ventana", _info)
            if _m:
                _d = int(_m.group(1))
                if min_days is None or _d < min_days:
                    min_days = _d
        if min_days is not None:
            if min_days <= 3:
                return f"🐛 Ventana en ~{min_days}d — esperar y combinar", "soon"
            elif min_days <= 7:
                return f"🐛 Ventana en ~{min_days}d — valorar esperar", "later"
            else:
                return f"⏳ Carpocapsa en {min_days}d", "none"
        return "⏳ En espera carpocapsa", "none"

    # ── 3. Ya tratado (o tratado pero en espera de reentrada) ────────────────
    if not tratadas.empty:
        if "_reentry_wait" in tratadas.columns:
            max_wait = int(tratadas["_reentry_wait"].fillna(0).max())
            if max_wait > 0:
                return f"⚠️ Tratar hoy — esperar {max_wait}d (reentrada)", "soon"
        return "✅ Carpocapsa cubierta", "done"

    return "", "none"


# ═══════════════════════════════════════════════════════════════════════════════
# Integración con Telegram — informe diario
# ═══════════════════════════════════════════════════════════════════════════════

def telegram_is_configured():
    """True si hay token y chat_id de Telegram en Secrets."""
    try:
        token = str(st.secrets.get("TELEGRAM_BOT_TOKEN", "")).strip()
        chat  = str(st.secrets.get("TELEGRAM_CHAT_ID", "")).strip()
        return bool(token and chat)
    except Exception:
        return False


def telegram_send_message(text, parse_mode="HTML"):
    """Envía un mensaje al chat configurado. Devuelve (ok, detalle)."""
    try:
        token = str(st.secrets.get("TELEGRAM_BOT_TOKEN", "")).strip()
        chat  = str(st.secrets.get("TELEGRAM_CHAT_ID", "")).strip()
    except Exception:
        return False, "No se pudieron leer las credenciales de Telegram."
    if not token or not chat:
        return False, "Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en Secrets."
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        if r.status_code == 200:
            return True, "Mensaje enviado correctamente."
        return False, f"Error {r.status_code}: {r.text[:300]}"
    except Exception as e:
        return False, f"Error de conexión: {e}"


def telegram_discover_chats():
    """Consulta getUpdates para listar los chats que han escrito al bot.
    Útil para descubrir el chat_id. Devuelve dict {chat_id: nombre} o None."""
    try:
        token = str(st.secrets.get("TELEGRAM_BOT_TOKEN", "")).strip()
    except Exception:
        return None
    if not token:
        return None
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        chats = {}
        for upd in data.get("result", []):
            msg  = upd.get("message") or upd.get("channel_post") or {}
            chat = msg.get("chat", {})
            cid  = chat.get("id")
            if cid is not None:
                nombre = (chat.get("title") or chat.get("username")
                          or chat.get("first_name") or "—")
                chats[str(cid)] = nombre
        return chats
    except Exception:
        return None


def build_daily_report_text(history_df, traps_df, activities_df,
                            forecast_df=None, persistence_days=16):
    """Construye el texto del informe diario centrado en lo urgente:
    carpocapsa (ventanas activas; aviso si cierran en ≤3 días sin tratar) +
    fungicidas (tratar hoy / sin cobertura). Formato HTML para Telegram."""
    import html as _html

    def _esc(v):
        return _html.escape(str(v))

    today_str = pd.Timestamp.today().strftime("%d/%m/%Y")
    lines = ["🌳 <b>Finca Gallinal — Informe diario</b>", f"📅 {today_str}", ""]

    # ── 1. Carpocapsa: ventanas urgentes ──────────────────────────────────────
    carpo_red, carpo_orange = [], []
    try:
        cw = carpocapsa_build_multi_windows(
            traps_df, history_df, activities_df=activities_df,
            campaign_year=pd.Timestamp.now().year,
        )
    except Exception:
        cw = pd.DataFrame()

    _CIERRE_AVISO_DIAS = 3   # avisar si una ventana activa cierra en ≤ N días sin tratar
    if not cw.empty:
        # Columna de fecha estimada de cierre (DD fin = la del número mayor)
        _est_cols = [c for c in cw.columns
                     if c.startswith("Fecha estimada") and c.strip().endswith("DD")]
        def _dd_of(c):
            _d = "".join(ch for ch in c if ch.isdigit())
            return int(_d) if _d else 0
        _end_col = max(_est_cols, key=_dd_of) if _est_cols else None
        _today_n = pd.Timestamp.today().normalize()

        for _, r in cw.iterrows():
            e     = str(r.get("Estado", ""))
            campo = _esc(r.get("Campo/Zona", ""))
            dd    = r.get("DD actual", "")
            info  = _esc(r.get("Info", ""))
            if "Activa" not in e:        # solo ventanas activas SIN tratar
                continue
            # Días hasta el cierre (cuando los DD llegan a DD fin)
            dias_cierre = None
            if _end_col:
                _de = pd.to_datetime(r.get(_end_col, ""), format="%d/%m/%Y", errors="coerce")
                if pd.notna(_de):
                    dias_cierre = int((_de.normalize() - _today_n).days)
            if dias_cierre is not None and dias_cierre <= _CIERRE_AVISO_DIAS:
                carpo_orange.append(
                    f"  🟠 <b>{campo}</b> — CIERRA EN {max(0, dias_cierre)}d sin tratar · {dd} DD")
            else:
                _cola = f" · cierra en {dias_cierre}d" if dias_cierre is not None else ""
                carpo_red.append(f"  🔴 <b>{campo}</b> — {dd} DD{_cola}")

    lines.append("🐛 <b>CARPOCAPSA</b>")
    if carpo_orange:
        lines.append(f"<b>⚠️ Cierran en ≤{_CIERRE_AVISO_DIAS}d SIN tratar (última oportunidad):</b>")
        lines.extend(carpo_orange)
    if carpo_red:
        lines.append("<b>Ventana activa — tratar:</b>")
        lines.extend(carpo_red)
    if not carpo_red and not carpo_orange:
        lines.append("  ✅ Sin ventanas activas hoy.")
    lines.append("")

    # ── 2. Fungicidas: campos que requieren acción ────────────────────────────
    try:
        _risk = build_risk_timeline(
            history_df,
            forecast_df if forecast_df is not None else pd.DataFrame(),
            days_back=60,
        )
        dec = daily_treatment_decision(
            history_df, activities_df, _risk, persistence_days=persistence_days
        )
    except Exception:
        dec = pd.DataFrame()

    lines.append("🍎 <b>FUNGICIDAS</b>")
    if not dec.empty and "_priority" in dec.columns:
        red    = dec[dec["_priority"] == 1]   # tratar hoy (infección prevista)
        orange = dec[dec["_priority"] == 2]   # tratar pronto (cobertura caducada + exposición)
        yellow = dec[dec["_priority"] == 3]   # planificar (sin cobertura activa)
        if not red.empty:
            lines.append("<b>🔴 Tratar HOY (infección prevista):</b>")
            for _, r in red.iterrows():
                campo  = _esc(r.get("Campo", ""))
                dias   = r.get("Días sin trat.", "")
                lines.append(f"  • <b>{campo}</b> — {dias} días sin tratar")
        if not orange.empty:
            lines.append("<b>🟠 Tratar pronto (cobertura caducada):</b>")
            for _, r in orange.iterrows():
                campo = _esc(r.get("Campo", ""))
                dias  = r.get("Días sin trat.", "")
                lines.append(f"  • <b>{campo}</b> — {dias} días sin tratar")
        if not yellow.empty:
            lines.append("<b>🟡 Planificar (sin cobertura activa):</b>")
            for _, r in yellow.iterrows():
                campo = _esc(r.get("Campo", ""))
                dias  = r.get("Días sin trat.", "")
                lines.append(f"  • <b>{campo}</b> — {dias} días sin tratar")
        if red.empty and orange.empty and yellow.empty:
            lines.append("  ✅ Todos los campos con cobertura vigente.")
    else:
        lines.append("  ℹ️ Sin datos suficientes para el panel de decisión.")

    # ── 3. Resumen climático de los últimos 7 días ────────────────────────────
    try:
        _hoy = pd.Timestamp.today().normalize()
        _ini = (_hoy - pd.Timedelta(days=6)).date()
        _fin = _hoy.date()
        _m, _txt, _acts7, _prio = build_weekly_executive_report(
            history_df, activities_df, _ini, _fin
        )
        if _m:
            def _n(v, dec=1, suf=""):
                try:
                    return f"{float(v):.{dec}f}{suf}"
                except Exception:
                    return "—"
            lines.append("")
            lines.append(f"📊 <b>RESUMEN 7 DÍAS</b> ({_ini.strftime('%d/%m')}–{_fin.strftime('%d/%m')})")
            lines.append(
                f"  🌡️ Temp: media {_n(_m.get('temp_mean'))}°C "
                f"(mín {_n(_m.get('temp_min'))} / máx {_n(_m.get('temp_max'))})"
            )
            lines.append(
                f"  💧 HR media: {_n(_m.get('hr_mean'))}% · "
                f"hoja húmeda: {int(_m.get('leaf_events', 0))} eventos"
            )
            lines.append(f"  🌧️ Lluvia: {_n(_m.get('rain_total'))} mm")
            lines.append(
                f"  💨 Viento medio: {_n(_m.get('wind_mean'))} · "
                f"ráfaga máx: {_n(_m.get('gust_max'))}"
            )
            lines.append(f"  ☀️ Radiación acum.: {_n(_m.get('radiation_sum'))} MJ/m²")
            _sc = int(_m.get('scab_events_ge1', 0))
            _mo = int(_m.get('monilia_events_ge1', 0))
            _max_scab = float(_m.get('max_scab_ratio', 0) or 0)
            _max_mon  = float(_m.get('max_monilia_ratio', 0) or 0)
            lines.append(
                f"  🍄 Moteado: ratio máx {_n(_max_scab, 2)} "
                f"· {_sc} evento(s) de infección"
            )
            lines.append(
                f"  🍑 Monilia: ratio máx {_n(_max_mon, 2)} "
                f"· {_mo} evento(s)"
            )

            # Oídio: se calcula aparte (favorece cálido y seco, no hoja mojada).
            _oidio_vals = []
            try:
                _ho = history_df.copy()
                _ho["fecha_hora"] = pd.to_datetime(_ho["fecha_hora"], errors="coerce")
                _ho = _ho.dropna(subset=["fecha_hora"])
                _ho = _ho[(_ho["fecha_hora"].dt.date >= _ini) & (_ho["fecha_hora"].dt.date <= _fin)]
                for _dd, _gg in _ho.groupby(_ho["fecha_hora"].dt.date):
                    _tm = pd.to_numeric(_gg["temp_media"], errors="coerce").mean()
                    _hm = pd.to_numeric(_gg["hr_media"],   errors="coerce").mean()
                    _ll = pd.to_numeric(_gg["lluvia_mm"],  errors="coerce").sum()
                    _oidio_vals.append(_dec_oidio_value(_tm, _hm, _ll))
            except Exception:
                _oidio_vals = []
            _oidio_max  = max(_oidio_vals) if _oidio_vals else 0.0
            _oidio_days = sum(1 for v in _oidio_vals if v >= 50)
            lines.append(
                f"  🌬️ Oídio: favorabilidad máx {_n(_oidio_max, 0)}/100 "
                f"· {_oidio_days} día(s) favorable(s)"
            )

            # ── Interpretación global del riesgo sanitario de la semana ───────
            if _sc > 0 or _mo > 0:
                _interp = "🔴 Semana con evento(s) de infección — revisar cobertura fungicida."
            elif _max_scab >= 0.75 or _max_mon >= 0.75 or _oidio_max >= 60:
                _interp = "🟡 Riesgo sanitario moderado — conviene vigilar la evolución."
            else:
                _interp = "🟢 Semana de bajo riesgo sanitario."
            lines.append(f"  <b>{_interp}</b>")
    except Exception:
        pass  # el resumen semanal nunca debe romper el informe diario

    lines.append("")
    lines.append("<i>Generado automáticamente desde la app Finca Gallinal.</i>")
    return "\n".join(lines)


def render_decisiones_panel():
    """Panel de decisiones agronómicas con 4 gráficas estilo RIMpro."""
    try:
        import plotly.graph_objects as _go_test  # noqa: F401
    except ImportError:
        st.error(
            "📦 **Plotly no está instalado.** Haz clic en **Manage app → Reboot app** "
            "para que Streamlit Cloud instale las nuevas dependencias."
        )
        return

    history_df  = st.session_state.get("history_df",  pd.DataFrame())
    forecast_df = st.session_state.get("forecast_df", pd.DataFrame())
    activities_df = st.session_state.get("activities_df", pd.DataFrame())
    biofix_df   = st.session_state.get("carpocapsa_biofix_df", pd.DataFrame())
    traps_df    = st.session_state.get("carpocapsa_traps_df",  pd.DataFrame())

    if history_df.empty and forecast_df.empty:
        st.warning("⚠️ Sin datos climáticos. Carga el histórico desde Supabase o Sencrop y la predicción desde la pestaña 🌦️ Sencrop.")
        return

    st.markdown(
        "Evolución del riesgo sanitario y grado-día carpocapsa combinando datos reales con la "
        "**predicción Sencrop** — para tomar decisiones de tratamiento con días de antelación."
    )

    # ══════════════════════════════════════════════════════════════════════════
    # INFORME A TELEGRAM
    # ══════════════════════════════════════════════════════════════════════════
    with st.expander("📲 Enviar informe a Telegram", expanded=False):
        if not telegram_is_configured():
            st.info(
                "Para activar el envío a Telegram, añade en **Secrets** de Streamlit:\n\n"
                "```toml\n"
                "TELEGRAM_BOT_TOKEN = \"tu_token_del_bot\"\n"
                "TELEGRAM_CHAT_ID = \"tu_chat_id\"\n"
                "```\n\n"
                "El **token** te lo da @BotFather al crear el bot. "
                "El **chat_id** lo descubres escribiendo un mensaje a tu bot y pulsando el botón de abajo."
            )
            try:
                _tok = str(st.secrets.get("TELEGRAM_BOT_TOKEN", "")).strip()
            except Exception:
                _tok = ""
            if _tok:
                if st.button("🔍 Descubrir mi chat_id", key="tg_discover"):
                    _chats = telegram_discover_chats()
                    if _chats:
                        st.success("Chats que han escrito al bot:")
                        for _cid, _nom in _chats.items():
                            st.code(f'TELEGRAM_CHAT_ID = "{_cid}"   # {_nom}')
                    else:
                        st.warning(
                            "No se detectó ningún chat. Escribe primero un mensaje a tu bot "
                            "en Telegram (por ejemplo «hola») y vuelve a pulsar."
                        )
        else:
            st.success("✅ Telegram configurado. La app puede enviar informes.")
            _vista = st.checkbox("Ver el informe antes de enviar", value=True, key="tg_preview")
            if _vista:
                _preview = build_daily_report_text(
                    history_df, traps_df, activities_df,
                    forecast_df=forecast_df,
                    persistence_days=st.session_state.get("dec_persist_days", 16),
                )
                # Mostrar como texto plano (quitar etiquetas HTML para la vista previa)
                import re as _re_tg
                _plain = _re_tg.sub(r"</?[^>]+>", "", _preview)
                st.text(_plain)
            if st.button("📤 Enviar informe ahora", type="primary", key="tg_send"):
                _msg = build_daily_report_text(
                    history_df, traps_df, activities_df,
                    forecast_df=forecast_df,
                    persistence_days=st.session_state.get("dec_persist_days", 16),
                )
                _ok, _detalle = telegram_send_message(_msg)
                if _ok:
                    st.success(f"✅ {_detalle}")
                else:
                    st.error(f"❌ {_detalle}")

    # ══════════════════════════════════════════════════════════════════════════
    # PANEL DE DECISIÓN DIARIA
    # ══════════════════════════════════════════════════════════════════════════
    with st.expander("⚙️ Catálogo de fungicidas (campaña activa)", expanded=False):
        st.caption(
            "Productos disponibles en almacén esta campaña. "
            "La columna **Objetivos** guía las recomendaciones del panel diario. "
            "La columna **FRAC** se usa para el asesor de rotación de la próxima campaña."
        )
        _catalog_key = "fungicide_catalog_editor_v2"
        _catalog_edited = st.data_editor(
            st.session_state.get("fungicide_catalog_df", pd.DataFrame(DEFAULT_FUNGICIDE_CATALOG)),
            num_rows="dynamic",
            use_container_width=True,
            key=_catalog_key,
        )
        try:
            if not _catalog_edited.equals(st.session_state.get("fungicide_catalog_df", pd.DataFrame())):
                st.session_state["fungicide_catalog_df"] = _catalog_edited
        except Exception:
            st.session_state["fungicide_catalog_df"] = _catalog_edited

    with st.expander("🔄 Planificación de rotación — próxima campaña", expanded=False):
        st.markdown(
            "Análisis de los grupos FRAC usados en la campaña actual y propuesta de alternativas "
            "para **reducir el riesgo de resistencias** en la próxima temporada."
        )
        _rot_catalog = st.session_state.get("fungicide_catalog_df", pd.DataFrame(DEFAULT_FUNGICIDE_CATALOG))
        _rot = build_rotation_advice(activities_df, _rot_catalog)

        # ── Productos usados esta campaña ──────────────────────────────────────
        if _rot["used_products"]:
            _col_u, _col_f = st.columns([2, 1])
            with _col_u:
                st.markdown("**Productos aplicados esta campaña:**")
                _up_rows = [{"Producto": k, "Aplicaciones": v} for k, v in sorted(_rot["used_products"].items(), key=lambda x: -x[1])]
                _up_df   = pd.DataFrame(_up_rows)
                st.dataframe(_up_df, hide_index=True, use_container_width=True)
            with _col_f:
                st.markdown("**Grupos FRAC activos:**")
                for _f in sorted(_rot["used_fracs"]):
                    st.markdown(f"- **{_f}**")
        else:
            st.info("Carga las actuaciones de Agroptima para ver el análisis de uso.")

        # ── Advertencias ───────────────────────────────────────────────────────
        if _rot["warnings"]:
            for _w in _rot["warnings"]:
                st.warning(_w)

        # ── Alternativas recomendadas ──────────────────────────────────────────
        if _rot["advice"]:
            st.markdown("---")
            st.markdown("#### 💡 Alternativas recomendadas para la próxima campaña")
            st.caption(
                "Productos de grupos FRAC distintos a los usados en 2026. "
                "Incorporarlos rompe el ciclo de selección de resistencias."
            )
            _adv_df = pd.DataFrame(_rot["advice"])
            # Tabla HTML con encabezados verdes
            _th = "background:#1a2e1e;color:white;padding:8px 12px;white-space:nowrap;font-weight:600;font-size:13px;"
            _td_s = "padding:7px 12px;border-bottom:1px solid #e8e8e8;font-size:13px;white-space:nowrap;"
            _hdr_rot = "".join(f'<th style="{_th}">{c}</th>' for c in _adv_df.columns)
            _body_rot = ""
            for _, _r in _adv_df.iterrows():
                _cells = "".join(f'<td style="{_td_s}">{_r[c]}</td>' for c in _adv_df.columns)
                _body_rot += f"<tr>{_cells}</tr>"
            st.markdown(
                f'<div style="overflow-x:auto;border-radius:8px;border:1px solid #ddd;margin-top:0.5rem;">'
                f'<table style="border-collapse:collapse;width:100%;">'
                f'<thead><tr>{_hdr_rot}</tr></thead>'
                f'<tbody>{_body_rot}</tbody>'
                f'</table></div>',
                unsafe_allow_html=True,
            )
        else:
            st.success("✅ El catálogo actual ya cubre una buena diversidad de grupos FRAC. Sin alternativas urgentes.")

    st.markdown("### 📋 Panel de decisión diaria")

    _persist_days = st.slider(
        "Días de persistencia del tratamiento (umbral de protección caducada)",
        min_value=10, max_value=25, value=16, step=1,
        help="Por encima de este umbral de días sin tratar, el campo se considera sin cobertura.",
        key="dec_persist_days",
    )

    # Construir risk_df rápido (solo los últimos 60 días + forecast) para el panel
    _risk_quick = build_risk_timeline(history_df, forecast_df, days_back=60)

    _catalog_df = st.session_state.get("fungicide_catalog_df", pd.DataFrame(DEFAULT_FUNGICIDE_CATALOG))
    _dec_df = daily_treatment_decision(history_df, activities_df, _risk_quick, persistence_days=_persist_days)

    if _dec_df.empty:
        st.info("Carga el histórico y las actuaciones de Agroptima para generar el panel de decisión.")
    else:
        # ── Resumen ejecutivo ────────────────────────────────────────────────
        _n_red    = (_dec_df["_priority"] == 1).sum()
        _n_orange = (_dec_df["_priority"] == 2).sum()
        _n_yellow = (_dec_df["_priority"] == 3).sum()
        _n_green  = (_dec_df["_priority"] == 4).sum()

        _s1, _s2, _s3, _s4 = st.columns(4)
        _s1.metric("🔴 Tratar hoy",         _n_red)
        _s2.metric("🟠 Sin cobertura",       _n_orange)
        _s3.metric("🟡 Revisar",             _n_yellow)
        _s4.metric("🟢 OK",                  _n_green)

        # ── Ventanas de carpocapsa para sincronizar tratamientos ──────────────
        # Calcula una única vez las ventanas activas/en espera de carpocapsa
        # para todos los campos, y luego anota cada fila del panel de fungicidas.
        _carpo_sync_map = {}   # campo → (texto, nivel)
        _carpo_windows  = pd.DataFrame()
        if not traps_df.empty and not history_df.empty:
            try:
                _carpo_windows = carpocapsa_build_multi_windows(
                    traps_df,
                    history_df,
                    activities_df=activities_df,
                    campaign_year=pd.Timestamp.now().year,
                )
            except Exception:
                _carpo_windows = pd.DataFrame()

        # ── Calcular recomendaciones por campo usando ranking científico ────────
        _dec_display = _dec_df.copy()
        _rec_primary  = []
        _rec_alt      = []
        _rec_motivo   = []
        _rec_combo    = []   # anotación de sync carpocapsa
        for _, _r in _dec_display.iterrows():
            _campo = str(_r.get("Campo", ""))
            _dom  = _r.get("_dominant_list", [])
            _lp   = str(_r.get("_last_product", ""))
            _ac   = _r.get("_app_counts", {})
            _sdhi = int(_r.get("_sdhi_total", 0))
            _p, _a, _m = get_smart_recommendation(
                _dom, _catalog_df, last_product=_lp,
                app_counts=_ac, sdhi_total=_sdhi,
            )
            _rec_primary.append(_p)
            _rec_alt.append(_a)
            _rec_motivo.append(_m)
            # Sync carpocapsa
            _ann, _lvl = carpocapsa_sync_annotation(_campo, _carpo_windows)
            _carpo_sync_map[_campo] = (_ann, _lvl)
            _rec_combo.append((_ann, _lvl))

        _dec_display["1ª elección"]  = _rec_primary
        _dec_display["Alternativa"]  = _rec_alt
        _dec_display["Por qué"]      = _rec_motivo
        _dec_display["_combo_ann"]   = [t for t, _ in _rec_combo]
        _dec_display["_combo_lvl"]   = [l for _, l in _rec_combo]

        # ── Tabla HTML: scroll vertical + horizontal, columna Campo fija ─────
        # Orden: columnas de acción inmediata primero (visible sin scroll),
        # recomendaciones en bloque central, combo cuba junto a la elección.
        _display_cols = [
            "Campo", "🎯 Acción",
            "Último fungicida", "Días sin trat.",
            "Lluvia desde mm", "Eventos infección", "Previsión Mills",
            "Pases campaña", "Riesgo principal",
            "1ª elección", "Alternativa", "🐛 Combo cuba",
            "Por qué", "📋 Motivo",
        ]

        # Estilos base
        _TH_BASE   = ("background:#1a2e1e;color:white;padding:8px 12px;"
                      "font-weight:600;font-size:13px;white-space:nowrap;"
                      "position:sticky;top:0;z-index:2;")
        _TH_CORNER = _TH_BASE + "left:0;z-index:4;"   # esquina superior izquierda
        _TD_STICKY = ("position:sticky;left:0;z-index:1;"
                      "padding:7px 12px;border-bottom:1px solid #ddd;"
                      "font-weight:600;font-size:13px;white-space:nowrap;"
                      "border-right:2px solid #1a2e1e;")

        # Cabecera — clases fg-th / fg-th-corner para fijado robusto en móvil
        _hdr_cells = ""
        for _i, _c in enumerate(_display_cols):
            if _i == 0:
                _hdr_cells += f'<th class="fg-th-corner" style="{_TH_CORNER}">{_c}</th>'
            else:
                _hdr_cells += f'<th class="fg-th" style="{_TH_BASE}">{_c}</th>'

        # Colores para la columna de sincronización carpocapsa
        _COMBO_STYLES = {
            "now":  {"bg": "#ff8f00", "color": "white",   "fw": "700"},   # naranja oscuro — combinar HOY
            "soon": {"bg": "#ffe082", "color": "#4a2c00", "fw": "700"},   # amarillo — próxima ventana
            "later":{"bg": "#fff9c4", "color": "#555",    "fw": "400"},   # amarillo claro
            "done": {"bg": "#c8e6c9", "color": "#1b5e20", "fw": "400"},   # verde claro — cubierta
            "none": {"bg": "transparent", "color": "#aaa","fw": "400"},
        }

        # Filas — la columna "📋 Motivo" muestra solo el tipo en la tabla compacta
        # (el texto completo está en el expander de análisis detallado de abajo)
        _tbody = ""
        for _, _r in _dec_display.iterrows():
            _bg   = _r["_bg"]
            _cells = ""
            for _i, _c in enumerate(_display_cols):
                if _c == "🐛 Combo cuba":
                    _ann = str(_r.get("_combo_ann", ""))
                    _lvl = str(_r.get("_combo_lvl", "none"))
                    _cs  = _COMBO_STYLES.get(_lvl, _COMBO_STYLES["none"])
                    if _ann:
                        _v = (
                            f'<span style="background:{_cs["bg"]};color:{_cs["color"]};'
                            f'font-weight:{_cs["fw"]};border-radius:4px;'
                            f'padding:2px 7px;font-size:12px;white-space:nowrap;">'
                            f'{_ann}</span>'
                        )
                    else:
                        _v = '<span style="color:#ccc;font-size:12px;">—</span>'
                    _style = (f"background:{_bg};padding:6px 10px;"
                              f"border-bottom:1px solid #ddd;white-space:nowrap;")
                elif _c == "📋 Motivo":
                    # Extraer solo el tipo entre corchetes: "[🛡️ Preventivo urgente]"
                    _full = str(_r.get(_c, ""))
                    import re as _re
                    _match = _re.match(r"\[([^\]]+)\]", _full)
                    _v = _match.group(1) if _match else _full[:40]
                    _style = (f"background:{_bg};padding:7px 12px;"
                              f"border-bottom:1px solid #ddd;"
                              f"white-space:nowrap;font-size:13px;")
                else:
                    _v = _r.get(_c, "")
                    if _i == 0:
                        _style = _TD_STICKY + f"background:{_bg};"
                    else:
                        _wrap  = "normal" if _c in ("Por qué", "Último fungicida", "Pases campaña") else "nowrap"
                        _mw    = "min-width:160px;" if _c == "Por qué" else ""
                        _style = (f"background:{_bg};padding:7px 12px;"
                                  f"border-bottom:1px solid #ddd;"
                                  f"white-space:{_wrap};font-size:13px;{_mw}")
                _cells += f'<td style="{_style}">{_v}</td>'
            _tbody += f"<tr>{_cells}</tr>"

        # Contenedor con doble scroll y altura máxima
        st.markdown(
            f'<div style="overflow-x:auto;overflow-y:auto;max-height:420px;'
            f'border-radius:8px;border:1px solid #ccc;margin-bottom:1.5rem;">'
            f'<table class="fg-fixedcol" style="border-collapse:separate;border-spacing:0;min-width:100%;">'
            f'<thead><tr>{_hdr_cells}</tr></thead>'
            f'<tbody>{_tbody}</tbody>'
            f'</table></div>',
            unsafe_allow_html=True,
        )

        # ── Análisis detallado por campo (expander) ───────────────────────────
        with st.expander("📋 Ver análisis detallado por campo", expanded=False):
            st.markdown(
                "Explicación completa del motivo de cada recomendación, "
                "con los factores activos y su base científica."
            )
            for _, _r in _dec_display.iterrows():
                _bg_hex = _r["_bg"]
                _campo  = _r["Campo"]
                _accion = _r["🎯 Acción"]
                _motivo = str(_r.get("📋 Motivo", ""))
                _prod1  = _r.get("1ª elección", "—")
                _prod2  = _r.get("Alternativa", "—")

                # Separar tipo y razones del string narrativo
                import re as _re2
                _match2 = _re2.match(r"\[([^\]]+)\]\s*(.*)", _motivo, _re2.DOTALL)
                if _match2:
                    _tipo_str   = _match2.group(1)
                    _razones_str = _match2.group(2)
                else:
                    _tipo_str   = ""
                    _razones_str = _motivo

                # Dividir razones por " | "
                _razones = [r.strip() for r in _razones_str.split(" | ") if r.strip()]

                _combo_ann = str(_r.get("_combo_ann", ""))
                _combo_lvl = str(_r.get("_combo_lvl", "none"))
                _cs_det = _COMBO_STYLES.get(_combo_lvl, _COMBO_STYLES["none"])
                _combo_html = ""
                if _combo_ann:
                    _combo_html = (
                        f'<br><span style="background:{_cs_det["bg"]};color:{_cs_det["color"]};'
                        f'font-weight:{_cs_det["fw"]};border-radius:4px;'
                        f'padding:2px 8px;font-size:12px;">{_combo_ann}</span>'
                    )

                st.markdown(
                    f'<div style="background:{_bg_hex};border-radius:8px;'
                    f'padding:12px 16px;margin-bottom:10px;border-left:4px solid #1a2e1e;">'
                    f'<b style="font-size:15px;">{_campo}</b> &nbsp;·&nbsp; '
                    f'<span style="font-size:13px;">{_accion}</span>'
                    f'{_combo_html}<br>'
                    f'<span style="font-size:12px;color:#555;">1ª elección: <b>{_prod1}</b> · Alternativa: <b>{_prod2}</b></span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                for _idx, _razon in enumerate(_razones, 1):
                    st.markdown(f"**{_idx}.** {_razon}")

        st.caption(
            "🔴 **Tratar hoy** — infección prevista + sin cobertura. "
            "🟠 **Tratar pronto** — exposición acumulada + sin cobertura. "
            "🟡 **Planificar** — sin cobertura activa pero sin urgencia inmediata. "
            "🟢 **OK** — protegido y sin previsión de infección. "
            "· *Pases campaña*: aplicaciones registradas / máximo por registro MAPA. "
            "· **🐛 Combo cuba**: oportunidad de combinar fungicida + insecticida carpocapsa en la misma cuba — "
            "🟠 ventana activa (tratar hoy), 🟡 ventana próxima (valorar esperar), ✅ ya cubierta."
        )

        with st.expander("Descargar tabla de decisión", expanded=False):
            _dl_export_cols = ["Campo", "🎯 Acción", "🐛 Combo cuba", "Último fungicida",
                               "Días sin trat.", "Lluvia desde mm", "Eventos infección",
                               "Previsión Mills", "Pases campaña", "Riesgo principal",
                               "1ª elección", "Alternativa", "Por qué"]
            # Para el CSV la columna combo usa texto plano (sin HTML)
            _dec_dl = _dec_display.copy()
            _dec_dl["🐛 Combo cuba"] = _dec_dl["_combo_ann"]
            _dec_dl = _dec_dl[[c for c in _dl_export_cols if c in _dec_dl.columns]]
            st.download_button(
                "⬇️ Descargar panel de decisión (CSV)",
                data=_dec_dl.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"decision_tratamiento_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                key="dl_decision_panel",
            )

    # ══════════════════════════════════════════════════════════════════════════
    # SEGUIMIENTO COMPLETO DE FITOSANITARIOS POR CAMPO
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("### 📦 Seguimiento de fitosanitarios por campo")
    st.caption(
        "Todos los productos fitosanitarios aplicados esta campaña, agrupados por campo. "
        "Incluye fungicidas, insecticidas, acaricidas y confusión sexual. "
        "Permite controlar los pases por producto y verificar los plazos de seguridad antes de la recolección."
    )

    _phyto_df = build_phytosanitary_tracking(activities_df)

    if _phyto_df.empty:
        st.info("Carga las actuaciones de Agroptima para ver el seguimiento de fitosanitarios.")
    else:
        # ── Colores por tipo de producto ──────────────────────────────────────
        _TYPE_COLORS = {
            "Fungicida":             "#e8f5e9",  # verde claro
            "Insecticida biológico": "#e3f2fd",  # azul claro
            "Insecticida":           "#fff3e0",  # naranja claro
            "Acaricida":             "#fce4ec",  # rosa claro
            "Confusión sexual":      "#f3e5f5",  # lila claro
            "No clasificado":        "#f5f5f5",  # gris claro
        }
        _TYPE_BADGES = {
            "Fungicida":             "#2e7d32",
            "Insecticida biológico": "#1565c0",
            "Insecticida":           "#e65100",
            "Acaricida":             "#880e4f",
            "Confusión sexual":      "#6a1b9a",
            "No clasificado":        "#616161",
        }

        # ── Tabla HTML con scroll y columna Campo fija ─────────────────────────
        _PT_TH_BASE   = ("background:#1a2e1e;color:white;padding:8px 12px;"
                         "font-weight:600;font-size:13px;white-space:nowrap;"
                         "position:sticky;top:0;z-index:2;")
        _PT_TH_CORNER = _PT_TH_BASE + "left:0;z-index:4;"
        _PT_TD_STICKY = ("position:sticky;left:0;z-index:1;"
                         "padding:7px 12px;border-bottom:1px solid #ddd;"
                         "font-weight:600;font-size:13px;white-space:nowrap;"
                         "border-right:2px solid #1a2e1e;")

        _pt_display_cols = [
            "Campo", "Producto", "Tipo", "Objetivo",
            "Último uso", "Días desde uso", "Pases campaña",
            "Plazo seg. días", "Estado plazo",
        ]

        # Cabecera — clases fg-th / fg-th-corner para que el CSS móvil pueda
        # fijarlas por clase (robusto ante el reformateo de inline-styles)
        _pt_hdr = ""
        for _i, _c in enumerate(_pt_display_cols):
            if _i == 0:
                _pt_hdr += f'<th class="fg-th-corner" style="{_PT_TH_CORNER}">{_c}</th>'
            else:
                _pt_hdr += f'<th class="fg-th" style="{_PT_TH_BASE}">{_c}</th>'

        # Filas
        _pt_tbody = ""
        _prev_campo = None
        for _, _r in _phyto_df.iterrows():
            _campo  = _r["Campo"]
            _tipo   = _r["Tipo"]
            _estado = _r["Estado plazo"]
            _row_bg = _TYPE_COLORS.get(_tipo, "#f5f5f5")

            # Badge de tipo con color
            _badge_color = _TYPE_BADGES.get(_tipo, "#616161")
            _tipo_badge  = (
                f'<span style="background:{_badge_color};color:white;'
                f'border-radius:4px;padding:2px 7px;font-size:11px;font-weight:600;">'
                f'{_tipo}</span>'
            )

            # Estado plazo con color semáforo
            if "⚠️" in str(_estado):
                _estado_bg = "#fff3e0"; _estado_color = "#e65100"
            elif "🔒" in str(_estado):
                _estado_bg = "#e8f5e9"; _estado_color = "#2e7d32"
            elif "✅" in str(_estado):
                _estado_bg = "#f5f5f5"; _estado_color = "#616161"
            else:
                _estado_bg = "#f5f5f5"; _estado_color = "#616161"
            _estado_styled = (
                f'<span style="background:{_estado_bg};color:{_estado_color};'
                f'border-radius:4px;padding:2px 7px;font-size:12px;">{_estado}</span>'
            )

            # Separador visual entre campos
            _campo_display = _campo if _campo != _prev_campo else ""
            _prev_campo = _campo

            _pt_cells = ""
            for _i, _c in enumerate(_pt_display_cols):
                if _i == 0:
                    _style = _PT_TD_STICKY + f"background:{_row_bg};"
                    _val   = _campo_display
                elif _c == "Tipo":
                    _style = f"background:{_row_bg};padding:7px 12px;border-bottom:1px solid #ddd;white-space:nowrap;"
                    _val   = _tipo_badge
                elif _c == "Estado plazo":
                    _style = f"background:{_row_bg};padding:7px 12px;border-bottom:1px solid #ddd;white-space:nowrap;"
                    _val   = _estado_styled
                else:
                    _style = f"background:{_row_bg};padding:7px 12px;border-bottom:1px solid #ddd;white-space:nowrap;font-size:13px;"
                    _val   = _r.get(_c, "—")
                _pt_cells += f'<td style="{_style}">{_val}</td>'
            _pt_tbody += f"<tr>{_pt_cells}</tr>"

        st.markdown(
            f'<div style="overflow-x:auto;overflow-y:auto;max-height:450px;'
            f'border-radius:8px;border:1px solid #ccc;margin-bottom:1rem;">'
            f'<table class="fg-fixedcol" style="border-collapse:separate;border-spacing:0;min-width:100%;">'
            f'<thead><tr>{_pt_hdr}</tr></thead>'
            f'<tbody>{_pt_tbody}</tbody>'
            f'</table></div>',
            unsafe_allow_html=True,
        )

        # ── Leyenda de colores ─────────────────────────────────────────────────
        _leg_parts = []
        for _t, _bg in _TYPE_COLORS.items():
            _bc = _TYPE_BADGES.get(_t, "#616161")
            _leg_parts.append(
                f'<span style="display:inline-flex;align-items:center;margin-right:14px;">'
                f'<span style="width:12px;height:12px;background:{_bg};border:1px solid {_bc};'
                f'border-radius:2px;display:inline-block;margin-right:5px;"></span>'
                f'<span style="font-size:12px;color:#555;">{_t}</span></span>'
            )
        st.markdown(
            f'<div style="margin-top:4px;margin-bottom:0.5rem;">{"".join(_leg_parts)}</div>',
            unsafe_allow_html=True,
        )

        # ── Botón de descarga ──────────────────────────────────────────────────
        with st.expander("⬇️ Descargar seguimiento fitosanitarios", expanded=False):
            st.download_button(
                "⬇️ Descargar (CSV)",
                data=_phyto_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"fitosanitarios_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                key="dl_phyto_tracking",
            )

    st.markdown("---")
    st.markdown("### 📈 Gráficas de riesgo detalladas")

    # ── Parámetros ────────────────────────────────────────────────────────────
    p1, p2, p3 = st.columns([1, 1, 2])
    with p1:
        days_back = st.number_input(
            "Días de histórico", min_value=15, max_value=90, value=30, step=5, key="dec_days_back",
            help="Cuántos días pasados incluir en las gráficas",
        )
    with p2:
        base_temp_d  = st.number_input("Base DD carpocapsa (°C)", 0.0, 15.0, 10.0, 0.5, key="dec_base_temp")
        upper_temp_d = st.number_input("Umbral sup. DD (°C)", 20.0, 40.0, 31.1, 0.5, key="dec_upper_temp")
    with p3:
        if forecast_df.empty:
            st.info("💡 No hay predicción cargada. Las gráficas sólo mostrarán datos reales.")
        else:
            fc_dates = pd.to_datetime(forecast_df["fecha_hora"])
            st.success(
                f"✅ Predicción activa hasta **{fc_dates.max().strftime('%d/%m %Hh')}** · "
                f"{int((fc_dates.max() - pd.Timestamp.now()).total_seconds()/3600/24)+1} días por delante"
            )

    today = pd.Timestamp.now().normalize()

    # ── Construir timeline ────────────────────────────────────────────────────
    risk_df = build_risk_timeline(
        history_df, forecast_df,
        days_back=int(days_back),
        base_temp=float(base_temp_d),
        upper_temp=float(upper_temp_d),
    )

    if risk_df.empty:
        st.warning("No hay suficientes datos para construir el análisis de riesgo.")
        return

    # ── Tratamientos del período ──────────────────────────────────────────────
    treats_all   = pd.DataFrame()
    treats_carpo = pd.DataFrame()
    if not activities_df.empty and "Fecha" in activities_df.columns:
        acts = activities_df.copy()
        acts["Fecha_dt"] = pd.to_datetime(acts["Fecha"], errors="coerce")
        acts = acts.dropna(subset=["Fecha_dt"])
        t_mask = acts["Fecha_dt"] >= risk_df["Fecha"].min()
        if t_mask.any():
            treats_all = acts[t_mask].copy()
            # Carpocapsa: buscar en columna Producto (nombre del producto aplicado)
            for _col in ["Producto", "Descripcion", "Comentarios", "Trabajo"]:
                if _col in treats_all.columns:
                    carpo_mask = treats_all[_col].fillna("").str.lower().apply(
                        lambda x: any(kw.lower() in x for kw in CARPOCAPSA_TREATMENT_KEYWORDS)
                    )
                    if carpo_mask.any():
                        treats_carpo = treats_all[carpo_mask]
                        break

    chart_h = 290

    # ── Info de tratamientos detectados ──────────────────────────────────────
    n_treats = len(treats_all) if not treats_all.empty else 0
    if n_treats > 0:
        _t_dates_str = ", ".join(
            pd.to_datetime(treats_all["Fecha_dt"]).dt.strftime("%d/%m").unique()[:8].tolist()
        )
        _treats_info = f"🟣 **{n_treats} tratamientos** en el período: {_t_dates_str}"
    else:
        _treats_info = "ℹ️ Sin tratamientos registrados en Agroptima para este período (comprueba que están cargados)."

    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("#### 🍄 Moteado · *Venturia inaequalis* (Modelo de Mills)")
    st.caption(f"Umbral 25 = riesgo ligero · 50 = moderado · **100 = infección confirmada**. Zona azul = predicción Sencrop. {_treats_info}")
    fig_m = _dec_disease_chart(risk_df, "Mills_valor", "Moteado", today, treats_all, chart_h)
    st.plotly_chart(fig_m, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})

    st.divider()

    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("#### 🍑 Monilia · *Monilinia* spp.")
    st.caption("Umbral 50 = riesgo moderado · **100 = riesgo alto**. Requiere T>15°C + hoja mojada ≥3h o HR>85%.")
    fig_mo = _dec_disease_chart(risk_df, "Monilia_valor", "Monilia", today, treats_all, chart_h)
    st.plotly_chart(fig_mo, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})

    st.divider()

    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("#### 🐛 Carpocapsa · *Cydia pomonella* — Grados-día desde biofix")
    st.caption("Línea roja = DD acumulados. Círculos azules = capturas en trampa (tamaño proporcional). Umbrales de generación marcados.")
    fig_c = _dec_carpocapsa_chart(
        risk_df, today, biofix_df, traps_df, treats_carpo,
        float(base_temp_d), float(upper_temp_d), chart_h + 30,
        days_back=int(days_back),
        history_df=history_df,
    )
    st.plotly_chart(fig_c, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})

    st.divider()

    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("#### 🌫️ Oídio · *Podosphaera leucotricha*")
    st.caption("Favorece condiciones cálidas y secas (T 17-25°C, HR 50-80%). La lluvia intensa frena el riesgo.")
    fig_o = _dec_disease_chart(risk_df, "Oidio_valor", "Oídio", today, treats_all, chart_h)
    st.plotly_chart(fig_o, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})

    # ── Leyenda explicativa ───────────────────────────────────────────────────
    with st.expander("📖 Cómo interpretar estas gráficas", expanded=False):
        st.markdown("""
### Cómo leer los gráficos

#### 🎨 Colores de las barras (Moteado, Monilia, Oídio)
| Color | Valor | Qué significa | Qué hacer |
|---|---|---|---|
| 🟢 Verde | 0–25 | Sin riesgo. Condiciones no favorables para la infección | Nada, estás cubierto |
| 🟡 Amarillo | 25–50 | Riesgo ligero. Condiciones en el límite | Vigilar, evaluar si hay tratamiento vigente |
| 🟠 Naranja | 50–100 | Riesgo moderado. Umbral de infección próximo | Considerar tratamiento preventivo |
| 🔴 Rojo | >100 | **Período de infección.** El umbral se ha superado | **Tratar antes de que llegue (preventivo) o cuanto antes (curativo)** |

#### 📅 Zonas del gráfico
- **Parte izquierda (hasta la línea naranja)** = datos reales del pasado. Muestra qué ocurrió.
- **Línea naranja vertical** = hoy.
- **Zona azul claro (a la derecha)** = predicción Sencrop. Muestra qué puede ocurrir.
- **Líneas moradas verticales** = tratamientos registrados en Agroptima.

#### 💡 Cómo tomar la decisión de tratar
1. Mira la **zona azul** (predicción): ¿hay barras naranjas o rojas próximas?
2. ¿Tienes un tratamiento reciente (línea morada) que aún proteja? Los fungicidas curativos suelen cubrir 5–10 días, los preventivos 7–14 días.
3. Si se acerca un período rojo y no tienes protección vigente → **trata antes de la lluvia**, no durante ni después.
4. Si el período rojo ya pasó y no hubo tratamiento → evalúa un curativo en las próximas 48–72h.

#### 🐛 Gráfica de Carpocapsa (DD acumulados)
- **Línea roja** = grados-día acumulados desde el biofix (inicio de vuelo).
- **Barras naranjas** = DD de cada día (cuánto calor útil acumuló ese día).
- **Círculos azules** = capturas en trampa (el tamaño es proporcional al número de capturas).
- **Líneas de umbral horizontales**:
  - 80 DD = inicio 1ª generación → **primer tratamiento**
  - 150 DD = pico 1ª generación → reforzar si capturas altas
  - 300 DD = inicio 2ª generación → **segundo ciclo de tratamientos**
  - 500 DD = pico 2ª generación

#### 📊 Lluvia (barras azul claro, eje derecho)
Aparece en todos los gráficos como referencia. La lluvia genera hoja mojada (riesgo moteado/monilia) pero en cambio puede frenar el oídio.
        """)


# ── Render de la interfaz: solo cuando NO estamos en modo headless ───────────
if not _HEADLESS:
    # ── Navegación lateral ────────────────────────────────────────────────────────
    if "nav_page" not in st.session_state:
        st.session_state.nav_page = "dashboard"

    # CSS: estilo del sidebar
    st.markdown("""
    <style>
    /* ── Scrollbar fino y verde en el sidebar ── */
    section[data-testid="stSidebar"] ::-webkit-scrollbar { width: 4px; }
    section[data-testid="stSidebar"] ::-webkit-scrollbar-track { background: transparent; }
    section[data-testid="stSidebar"] ::-webkit-scrollbar-thumb {
        background: rgba(27,107,53,0.35);
        border-radius: 4px;
    }
    section[data-testid="stSidebar"] ::-webkit-scrollbar-thumb:hover {
        background: rgba(27,107,53,0.65);
    }
    /* Botones de navegación: alineados a la izquierda, sin borde */
    section[data-testid="stSidebar"] button {
        text-align: left !important;
        justify-content: flex-start !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 6px !important;
        padding: 4px 10px !important;
        font-size: 0.9rem !important;
        color: inherit !important;
        width: 100% !important;
    }
    section[data-testid="stSidebar"] button:hover {
        background: rgba(27,107,53,0.10) !important;
    }
    /* Título del grupo */
    section[data-testid="stSidebar"] .nav-group {
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #888;
        margin: 12px 0 2px 10px;
    }
    /* Página activa: fondo verde suave + borde izquierdo */
    .nav-active-item {
        background: rgba(27,107,53,0.13) !important;
        color: #1b6b35 !important;
        font-weight: 600;
        padding: 6px 10px 6px 8px;
        border-radius: 6px;
        border-left: 3px solid #1b6b35;
        font-size: 0.9rem;
        display: block;
        margin: 1px 0;
        cursor: default;
        line-height: 1.5;
    }
    /* ── Cabecera de página ── */
    .page-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 0 0 18px 0;
        padding-bottom: 10px;
        border-bottom: 2px solid rgba(27,107,53,0.15);
    }
    .page-header-icon {
        font-size: 2rem;
        line-height: 1;
    }
    .page-header-text { display: flex; flex-direction: column; gap: 1px; }
    .page-header-title {
        font-size: 1.45rem;
        font-weight: 700;
        color: #1a1a1a;
        line-height: 1.2;
        margin: 0;
    }
    .page-header-crumb {
        font-size: 0.74rem;
        color: #aaa;
        letter-spacing: 0.03em;
        margin: 0;
    }
    /* Breadcrumb encima del contenido (legacy, por si se usa en algún sitio) */
    .page-breadcrumb {
        color: #aaa;
        font-size: 0.78rem;
        margin: 0 0 6px 0;
        letter-spacing: 0.02em;
    }
    /* ── Animación fade-in al cambiar de página ── */
    @keyframes fg-fadein {
        from { opacity: 0; transform: translateY(6px); }
        to   { opacity: 1; transform: translateY(0);   }
    }
    section[data-testid="stMain"] > div:first-child {
        animation: fg-fadein 0.25s ease-out;
    }
    /* ── Ítem activo: borde animado que se desliza ── */
    @keyframes fg-activeslide {
        from { border-left-width: 0px; padding-left: 11px; }
        to   { border-left-width: 3px; padding-left: 8px;  }
    }
    .nav-active-item {
        animation: fg-activeslide 0.18s ease-out;
    }
    /* ── Footer del sidebar ── */
    .sidebar-footer {
        font-size: 0.68rem;
        color: #bbb;
        text-align: center;
        padding: 6px 0 2px 0;
        letter-spacing: 0.02em;
        line-height: 1.5;
    }
    /* ── Grupos colapsables en sidebar ── */
    section[data-testid="stSidebar"] [data-testid="stExpander"] {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
    }
    section[data-testid="stSidebar"] [data-testid="stExpander"] details {
        border: none !important;
        background: transparent !important;
    }
    section[data-testid="stSidebar"] [data-testid="stExpander"] summary {
        font-size: 0.73rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
        color: #888 !important;
        padding: 5px 4px 3px 8px !important;
        margin-top: 6px !important;
    }
    section[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
        color: #555 !important;
        background: rgba(0,0,0,0.03) !important;
        border-radius: 4px !important;
    }
    section[data-testid="stSidebar"] [data-testid="stExpander"] details > div {
        padding-top: 0 !important;
        padding-bottom: 2px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # Metadatos de cada página: (icono, grupo, nombre)
    _PAGE_META: dict = {
        "dashboard":     ("📊", "Clima",   "Dashboard"),
        "sencrop":       ("🌦️", "Clima",   "Sencrop"),
        "analisis":      ("🔎", "Clima",   "Análisis"),
        "comparador":    ("📈", "Clima",   "Comparador"),
        "frio":          ("❄️", "Clima",   "Frío"),
        "fenologia":     ("🌱", "Cultivo", "Fenología"),
        "sanidad":       ("🍄", "Cultivo", "Sanidad"),
        "decisiones":    ("🎯", "Cultivo", "Decisiones"),
        "carpocapsa":    ("🐛", "Cultivo", "Carpocapsa"),
        "riego":         ("💧", "Cultivo", "Riego"),
        "campos":        ("🌳", "Gestión", "Campos"),
        "agroptima":     ("🧾", "Gestión", "Agroptima"),
        "produccion":    ("🍎", "Gestión", "Producción"),
        "gallinal":      ("🍏", "Gestión", "Análisis Gallinal"),
        "informe":       ("📝", "Gestión", "Informe semanal"),
        "instrucciones": ("📘", "",        "Instrucciones"),
        "configuracion": ("⚙️", "",        "Configuración"),
    }

    def _nav_btn(label: str, page_key: str) -> None:
        """Botón de navegación. Página activa → div resaltado; inactiva → botón normal."""
        current = st.session_state.get("nav_page", "dashboard")
        if current == page_key:
            st.markdown(f'<div class="nav-active-item">{label}</div>', unsafe_allow_html=True)
        else:
            if st.button(label, key=f"nav_{page_key}", use_container_width=True):
                st.session_state.nav_page = page_key

    def _render_page_header(page_key: str) -> None:
        """Cabecera visual con icono grande, título y breadcrumb de grupo."""
        meta = _PAGE_META.get(page_key)
        if meta:
            icon, group, name = meta
            crumb = f"{group}  ›  {name}" if group else ""
            st.markdown(
                f'<div class="page-header">'
                f'  <span class="page-header-icon">{icon}</span>'
                f'  <div class="page-header-text">'
                f'    <p class="page-header-title">{name}</p>'
                f'    {"<p class=\"page-header-crumb\">" + crumb + "</p>" if crumb else ""}'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # Páginas por grupo (para auto-expandir el grupo activo)
    _CLIMA_PAGES   = {"dashboard","sencrop","analisis","comparador","frio"}
    _CULTIVO_PAGES = {"fenologia","sanidad","decisiones","carpocapsa","riego"}
    _GESTION_PAGES = {"campos","agroptima","produccion","gallinal","informe"}

    _active_page = st.session_state.get("nav_page","dashboard")
    if _active_page in _CLIMA_PAGES:   st.session_state["grp_clima"]   = True
    if _active_page in _CULTIVO_PAGES: st.session_state["grp_cultivo"] = True
    if _active_page in _GESTION_PAGES: st.session_state["grp_gestion"] = True

    with st.sidebar:
        # Título con logo inline (base64) en lugar del emoji 🌿
        try:
            import base64 as _b64, os as _os
            if _os.path.exists("finca_gallinal_logo.jpeg"):
                with open("finca_gallinal_logo.jpeg", "rb") as _lf:
                    _logo_b64 = _b64.b64encode(_lf.read()).decode()
                # Imagen 379x379px: manzana en top ~60%, texto FINCA/GALLINAL en bottom ~40%.
                # Contenedor 70×42px recorta el texto inferior (overflow:hidden).
                # mix-blend-mode:multiply elimina el fondo blanco fundiéndolo con el sidebar.
                st.markdown(
                    f'<p style="display:flex;align-items:center;gap:8px;'
                    f'font-size:1.22rem;font-weight:700;margin:4px 0 2px 0;line-height:1;">'
                    f'<span style="display:inline-block;width:70px;height:42px;'
                    f'overflow:hidden;flex-shrink:0;">'
                    f'<img src="data:image/jpeg;base64,{_logo_b64}" '
                    f'style="width:70px;height:70px;display:block;mix-blend-mode:multiply;">'
                    f'</span>'
                    f'Finca Gallinal</p>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown("## 🌿 Finca Gallinal")
        except Exception:
            st.markdown("## 🌿 Finca Gallinal")
        st.caption("Plataforma agroclimática")
        st.divider()

        with st.expander("🌤️  Clima", expanded=True, key="grp_clima"):
            _nav_btn("📊 Dashboard",   "dashboard")
            _nav_btn("🌦️ Sencrop",    "sencrop")
            _nav_btn("🔎 Análisis",    "analisis")
            _nav_btn("📈 Comparador",  "comparador")
            _nav_btn("❄️ Frío",        "frio")

        with st.expander("🌿  Cultivo", expanded=True, key="grp_cultivo"):
            _nav_btn("🌱 Fenología",   "fenologia")
            _nav_btn("🍄 Sanidad",     "sanidad")
            _nav_btn("🎯 Decisiones",  "decisiones")
            _nav_btn("🐛 Carpocapsa",  "carpocapsa")
            _nav_btn("💧 Riego",       "riego")

        with st.expander("📋  Gestión", expanded=True, key="grp_gestion"):
            _nav_btn("🌳 Campos",          "campos")
            _nav_btn("🧾 Agroptima",        "agroptima")
            _nav_btn("🍎 Producción",       "produccion")
            _nav_btn("🍏 Análisis Gallinal", "gallinal")
            _nav_btn("📝 Informe semanal",  "informe")

        st.divider()
        _nav_btn("📘 Instrucciones",  "instrucciones")
        _nav_btn("⚙️ Configuración",  "configuracion")
        st.divider()
        st.markdown(
            '<p class="sidebar-footer">🌿 Finca Gallinal<br>Plataforma agroclimática v2</p>',
            unsafe_allow_html=True,
        )

    # ── Contenido principal según página seleccionada ─────────────────────────────
    _page = st.session_state.get("nav_page", "dashboard")
    _render_page_header(_page)

    if _page == "dashboard":
        dashboard_tab(history, soil_type, hoja_threshold)
    elif _page == "sencrop":
        import_panel()
    elif _page == "analisis":
        analysis_tab(history, soil_type, hoja_threshold)
    elif _page == "comparador":
        comparator_tab(history, soil_type, hoja_threshold)
    elif _page == "frio":
        cold_tab(history)
    elif _page == "fenologia":
        phenology_tab(history, soil_type, hoja_threshold)
    elif _page == "sanidad":
        health_tab(history, soil_type, hoja_threshold)
    elif _page == "decisiones":
        render_decisiones_panel()
    elif _page == "carpocapsa":
        carpocapsa_tab(history)
    elif _page == "riego":
        irrigation_tab(history, soil_type, hoja_threshold)
    elif _page == "campos":
        fields_tab()
    elif _page == "agroptima":
        activities_tab()
    elif _page == "produccion":
        produccion_tab(history)
    elif _page == "gallinal":
        gallinal_tab(history)
    elif _page == "informe":
        weekly_report_tab(history, soil_type, hoja_threshold)
    elif _page == "instrucciones":
        instructions_tab()
    elif _page == "configuracion":
        settings_tab()
