
import io
import re
import time
import zipfile
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://melate.club/sorteo-{concurso}"
PRODUCTS = ("Melate", "Revancha", "Revanchita")

MONTHS = {
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"septiembre":9,"setiembre":9,"octubre":10,
    "noviembre":11,"diciembre":12
}

# Ejemplos reales:
# "1. 6 números | 0 ganador | premio $ 0.00"
# "3. 5 números | 6 ganadores | premio $ 109,800.55"
PRIZE_RE = re.compile(
    r"^\s*(\d+)\.\s*(.*?)\s*\|\s*"
    r"([\d,]+)\s+ganador(?:es)?\s*\|\s*"
    r"premio\s*\$\s*([\d,]+\.\d{2})\s*$",
    re.I
)

st.set_page_config(
    page_title="Melate Club Extractor v3",
    page_icon="🎟️",
    layout="centered"
)

st.title("🎟️ Melate Club Extractor v3")
st.caption("Extrae cada categoría directamente desde los elementos de la página de Melate Club.")

def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0"," ")).strip()

def parse_date(text):
    m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+del?\s+(\d{4})", text, re.I)
    if not m:
        return None
    day = int(m.group(1))
    mon = m.group(2).lower().translate(str.maketrans("áéíóú","aeiou"))
    year = int(m.group(3))
    month = MONTHS.get(mon)
    if not month:
        return None
    return datetime(year, month, day).strftime("%Y-%m-%d")

def find_product_heading(soup, product):
    # Busca h3 exacto: Melate / Revancha / Revanchita
    for h in soup.find_all(["h2","h3","h4"]):
        if norm(h.get_text(" ", strip=True)) == product:
            return h
    return None

def elements_until_next_heading(heading):
    """Devuelve nodos posteriores hasta el siguiente h2/h3/h4."""
    out = []
    for el in heading.next_elements:
        if el is heading:
            continue
        if isinstance(el, Tag) and el.name in ("h2","h3","h4"):
            break
        out.append(el)
    return out

def parse_product(soup, product):
    heading = find_product_heading(soup, product)
    if not heading:
        return {"numeros": [], "adicional": None, "premios": [], "debug": "Encabezado no encontrado"}

    elems = elements_until_next_heading(heading)

    # -------- Premios: leer <li> individualmente --------
    prizes = []
    seen_li = set()
    first_li_pos = None

    for pos, el in enumerate(elems):
        if isinstance(el, Tag) and el.name == "li":
            # evitar procesar li anidados/repetidos
            marker = id(el)
            if marker in seen_li:
                continue
            seen_li.add(marker)

            text = norm(el.get_text(" ", strip=True))
            m = PRIZE_RE.match(text)
            if m:
                if first_li_pos is None:
                    first_li_pos = pos
                prizes.append({
                    "lugar": int(m.group(1)),
                    "descripcion_acierto": norm(m.group(2)),
                    "ganadores": int(m.group(3).replace(",","")),
                    "premio_individual": float(m.group(4).replace(",",""))
                })

    # -------- Números: sólo texto anterior a la primera categoría --------
    # Recoger strings numéricos aislados antes del primer <li> válido.
    nums = []
    limit = first_li_pos if first_li_pos is not None else len(elems)

    for el in elems[:limit]:
        if isinstance(el, str):
            t = norm(el)
            if re.fullmatch(r"\d{1,2}", t):
                n = int(t)
                if 1 <= n <= 56:
                    nums.append(n)

    need = 7 if product == "Melate" else 6

    # Quitar duplicados consecutivos que a veces produce next_elements
    clean = []
    for n in nums:
        if not clean or n != clean[-1]:
            clean.append(n)
        if len(clean) >= need:
            break

    naturals = clean[:6]
    adicional = clean[6] if product == "Melate" and len(clean) >= 7 else None

    return {
        "numeros": naturals,
        "adicional": adicional,
        "premios": prizes,
        "debug": None
    }

def parse_page(requested, html, url):
    soup = BeautifulSoup(html, "html.parser")
    page_text = norm(soup.get_text(" ", strip=True))

    m = re.search(r"Sorteo\s+Melate,\s*Revancha\s+y\s+Revanchita\s+(\d+)", page_text, re.I)
    if not m:
        m = re.search(r"\bSorteo\s+(\d{4})\b", page_text, re.I)

    concurso = int(m.group(1)) if m else None

    data = {
        "solicitado": requested,
        "concurso": concurso,
        "fecha": parse_date(page_text[:1500]),
        "url": url
    }

    for product in PRODUCTS:
        data[product] = parse_product(soup, product)

    mel = data["Melate"]["premios"]
    rev = data["Revancha"]["premios"]
    rvt = data["Revanchita"]["premios"]

    economic = mel + rev
    if len(mel) == 9 and len(rev) == 5 and economic and all(
        x["ganadores"] == 0 and x["premio_individual"] == 0
        for x in economic
    ):
        estado = "SIN_DATOS_ECONOMICOS"
    elif len(mel) == 9 and len(rev) == 5 and len(rvt) >= 1:
        estado = "COMPLETO"
    else:
        estado = "INCOMPLETO"

    data["estado_economico"] = estado
    return data

def validate(d, requested):
    issues = []

    if d["concurso"] != requested:
        issues.append(f"concurso página={d['concurso']} solicitado={requested}")

    if len(d["Melate"]["numeros"]) != 6 or d["Melate"]["adicional"] is None:
        issues.append(f"Melate números={d['Melate']['numeros']} adicional={d['Melate']['adicional']}")

    if len(d["Revancha"]["numeros"]) != 6:
        issues.append(f"Revancha números={d['Revancha']['numeros']}")

    if len(d["Revanchita"]["numeros"]) != 6:
        issues.append(f"Revanchita números={d['Revanchita']['numeros']}")

    mel_places = [x["lugar"] for x in d["Melate"]["premios"]]
    rev_places = [x["lugar"] for x in d["Revancha"]["premios"]]
    rvt_places = [x["lugar"] for x in d["Revanchita"]["premios"]]

    if mel_places != list(range(1,10)):
        issues.append(f"Melate categorías={mel_places}, esperado 1..9")

    if rev_places != list(range(1,6)):
        issues.append(f"Revancha categorías={rev_places}, esperado 1..5")

    if len(rvt_places) < 1:
        issues.append("Revanchita sin premio")

    return issues

def flatten(d):
    rows = []
    for product in PRODUCTS:
        b = d[product]
        nums = b["numeros"]

        for p in b["premios"]:
            rows.append({
                "concurso": d["concurso"],
                "fecha": d["fecha"],
                "producto": product.upper(),
                "n1": nums[0] if len(nums)>0 else None,
                "n2": nums[1] if len(nums)>1 else None,
                "n3": nums[2] if len(nums)>2 else None,
                "n4": nums[3] if len(nums)>3 else None,
                "n5": nums[4] if len(nums)>4 else None,
                "n6": nums[5] if len(nums)>5 else None,
                "adicional": b["adicional"],
                "lugar": p["lugar"],
                "descripcion_acierto": p["descripcion_acierto"],
                "ganadores": p["ganadores"],
                "premio_individual": p["premio_individual"],
                "estado_economico": d["estado_economico"],
                "url": d["url"]
            })
    return rows

def fetch(session, concurso, pause, retries):
    url = BASE_URL.format(concurso=concurso)
    last = None

    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=25)
            if r.status_code in (403,429):
                return None, f"HTTP {r.status_code}", url, None
            r.raise_for_status()

            d = parse_page(concurso, r.text, url)
            time.sleep(pause)
            return d, None, url, r.text

        except Exception as e:
            last = str(e)
            if attempt < retries:
                time.sleep(max(1, pause*2))

    return None, last, url, None

with st.expander("⚙️ Configuración", expanded=True):
    c1,c2 = st.columns(2)
    inicio = c1.number_input("Concurso inicial", min_value=1, value=3192, step=1)
    fin = c2.number_input("Concurso final", min_value=1, value=3192, step=1)

    c3,c4 = st.columns(2)
    pausa = c3.slider("Pausa entre páginas (seg)", 0.5,5.0,2.0,0.5)
    retries = c4.slider("Reintentos",0,5,2,1)

    guardar_html = st.checkbox("Conservar HTML crudo", value=False)
    mostrar_debug = st.checkbox("Mostrar diagnóstico de extracción", value=True)

if "rows" not in st.session_state:
    st.session_state.rows=[]
if "errors" not in st.session_state:
    st.session_state.errors=[]
if "raw" not in st.session_state:
    st.session_state.raw={}

if st.button("🔎 Extraer datos", type="primary", use_container_width=True):
    if fin < inicio:
        st.error("Rango inválido")
        st.stop()

    total = int(fin-inicio+1)
    if total > 250:
        st.warning("Máximo 250 concursos por corrida")
        st.stop()

    st.session_state.rows=[]
    st.session_state.errors=[]
    st.session_state.raw={}

    session = requests.Session()
    session.headers.update({
        "User-Agent":"Mozilla/5.0 (compatible; MelateDataResearch/3.0)"
    })

    progress = st.progress(0)
    status = st.empty()

    for k,c in enumerate(range(int(inicio),int(fin)+1), start=1):
        status.write(f"Procesando **{c}** ({k}/{total})…")

        d,err,url,raw = fetch(session,c,float(pausa),int(retries))

        if err:
            st.session_state.errors.append({
                "concurso":c,
                "url":url,
                "tipo_error":"FETCH",
                "detalle":err
            })
            if "HTTP 403" in err or "HTTP 429" in err:
                st.error(f"{err}. Proceso detenido.")
                break
        else:
            issues = validate(d,c)

            if mostrar_debug:
                with st.expander(f"Diagnóstico sorteo {c}", expanded=False):
                    st.write("Melate números:", d["Melate"]["numeros"], "Adicional:", d["Melate"]["adicional"])
                    st.write("Melate categorías:", len(d["Melate"]["premios"]))
                    st.write("Revancha números:", d["Revancha"]["numeros"])
                    st.write("Revancha categorías:", len(d["Revancha"]["premios"]))
                    st.write("Revanchita números:", d["Revanchita"]["numeros"])
                    st.write("Revanchita categorías:", len(d["Revanchita"]["premios"]))
                    if issues:
                        st.warning(" | ".join(issues))

            if issues:
                st.session_state.errors.append({
                    "concurso":c,
                    "url":url,
                    "tipo_error":"INTEGRIDAD",
                    "detalle":" | ".join(issues)
                })
            else:
                st.session_state.rows.extend(flatten(d))
                if guardar_html:
                    st.session_state.raw[c]=raw

        progress.progress(k/total)

    status.write("Extracción terminada.")

if st.session_state.rows or st.session_state.errors:

    df = pd.DataFrame(st.session_state.rows)
    edf = pd.DataFrame(
        st.session_state.errors,
        columns=["concurso","url","tipo_error","detalle"]
    )

    if not df.empty:
        resumen = (
            df.groupby(["concurso","fecha","estado_economico"],dropna=False)
              .agg(
                  filas=("producto","size"),
                  productos=("producto","nunique")
              )
              .reset_index()
              .sort_values("concurso")
        )

        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Concursos OK",df["concurso"].nunique())
        c2.metric("Filas",len(df))
        c3.metric("Completos",df[df["estado_economico"]=="COMPLETO"]["concurso"].nunique())
        c4.metric("Errores",len(edf))

        st.subheader("Premios extraídos")
        st.dataframe(
            df[[
                "concurso","producto","lugar","descripcion_acierto",
                "ganadores","premio_individual"
            ]],
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "⬇️ Descargar CSV completo",
            df.to_csv(index=False).encode("utf-8-sig"),
            f"premios_{int(inicio)}_{int(fin)}.csv",
            "text/csv",
            use_container_width=True
        )

        out=io.BytesIO()
        with pd.ExcelWriter(out,engine="openpyxl") as writer:
            df.to_excel(writer,sheet_name="Premios",index=False)
            resumen.to_excel(writer,sheet_name="Resumen",index=False)
            edf.to_excel(writer,sheet_name="Errores",index=False)

        st.download_button(
            "⬇️ Descargar Excel completo",
            out.getvalue(),
            f"premios_{int(inicio)}_{int(fin)}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    if not edf.empty:
        st.subheader("Errores")
        st.dataframe(edf,use_container_width=True,hide_index=True)

    if guardar_html and st.session_state.raw:
        z=io.BytesIO()
        with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as zz:
            for c,h in st.session_state.raw.items():
                zz.writestr(f"sorteo-{c}.html",h)

        st.download_button(
            "⬇️ Descargar HTML crudo",
            z.getvalue(),
            f"html_{int(inicio)}_{int(fin)}.zip",
            "application/zip",
            use_container_width=True
        )

st.caption(
    "v3: premios extraídos directamente de cada <li>. "
    "Un concurso sólo se acepta con 9 categorías Melate + 5 Revancha + Revanchita."
        )
        
