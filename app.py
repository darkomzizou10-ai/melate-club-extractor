import io
import re
import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

BASE_URL = "https://melate.club/sorteo-{concurso}"
PRODUCTS = ("Melate", "Revancha", "Revanchita")

MONTHS = {
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"septiembre":9,"setiembre":9,"octubre":10,
    "noviembre":11,"diciembre":12
}

PRIZE_RE = re.compile(
    r"^(.*?)\s*\|\s*([\d,]+)\s+ganador(?:es)?\s*\|\s*premio\s*\$\s*([\d,]+\.\d{2})$",
    re.I
)

st.set_page_config(
    page_title="Melate Club Extractor v4",
    page_icon="🎟️",
    layout="centered"
)

st.title("🎟️ Melate Club Extractor v4")
st.caption("Extractor basado en la estructura HTML real de Melate Club.")

def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0"," ")).strip()

def parse_date(text):
    m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+del?\s+(\d{4})", text, re.I)
    if not m:
        return None
    d = int(m.group(1))
    mon = m.group(2).lower().translate(str.maketrans("áéíóú","aeiou"))
    y = int(m.group(3))
    mo = MONTHS.get(mon)
    return datetime(y, mo, d).strftime("%Y-%m-%d") if mo else None

def parse_product(soup, product):
    h3 = None
    for h in soup.find_all("h3"):
        if norm(h.get_text(" ", strip=True)) == product:
            h3 = h
            break

    if h3 is None:
        return {"numeros": [], "adicional": None, "premios": []}

    # Números: los div.resultado inmediatamente posteriores al h3,
    # antes del siguiente ol.detalle_resultado
    nums = []
    node = h3.find_next_sibling()
    while node:
        if getattr(node, "name", None) == "ol":
            break
        if getattr(node, "name", None) == "h3":
            break
        if getattr(node, "name", None) == "div" and "resultado" in (node.get("class") or []):
            t = norm(node.get_text(" ", strip=True))
            if t.isdigit():
                nums.append(int(t))
        node = node.find_next_sibling()

    # Premios: primer ol.detalle_resultado que sigue al h3
    ol = h3.find_next_sibling("ol", class_="detalle_resultado")
    premios = []
    if ol:
        for idx, li in enumerate(ol.find_all("li", class_="res", recursive=False), start=1):
            text = norm(li.get_text(" ", strip=True))
            m = PRIZE_RE.match(text)
            if not m:
                continue
            premios.append({
                "lugar": idx,
                "descripcion_acierto": norm(m.group(1)),
                "ganadores": int(m.group(2).replace(",","")),
                "premio_individual": float(m.group(3).replace(",",""))
            })

    if product == "Melate":
        naturales = nums[:6]
        adicional = nums[6] if len(nums) >= 7 else None
    else:
        naturales = nums[:6]
        adicional = None

    return {
        "numeros": naturales,
        "adicional": adicional,
        "premios": premios
    }

def parse_page(requested, html, url):
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    p = h1.find_next_sibling("p") if h1 else None

    concurso = None
    if h1:
        m = re.search(r"(\d{4})", h1.get_text(" ", strip=True))
        if m:
            concurso = int(m.group(1))

    fecha = parse_date(p.get_text(" ", strip=True)) if p else None

    data = {
        "concurso": concurso,
        "fecha": fecha,
        "url": url
    }

    for product in PRODUCTS:
        data[product] = parse_product(soup, product)

    mel = data["Melate"]["premios"]
    rev = data["Revancha"]["premios"]
    rvt = data["Revanchita"]["premios"]

    econ = mel + rev
    if len(mel) == 9 and len(rev) == 5 and econ and all(
        x["ganadores"] == 0 and x["premio_individual"] == 0 for x in econ
    ):
        estado = "SIN_DATOS_ECONOMICOS"
    elif len(mel) == 9 and len(rev) == 5 and len(rvt) >= 1:
        estado = "COMPLETO"
    else:
        estado = "INCOMPLETO"

    data["estado_economico"] = estado
    return data

def validate(d, requested):
    errors = []

    if d["concurso"] != requested:
        errors.append(f"Concurso página={d['concurso']} solicitado={requested}")

    if len(d["Melate"]["numeros"]) != 6 or d["Melate"]["adicional"] is None:
        errors.append(f"Melate números inválidos: {d['Melate']['numeros']} + {d['Melate']['adicional']}")

    if len(d["Revancha"]["numeros"]) != 6:
        errors.append(f"Revancha números inválidos: {d['Revancha']['numeros']}")

    if len(d["Revanchita"]["numeros"]) != 6:
        errors.append(f"Revanchita números inválidos: {d['Revanchita']['numeros']}")

    if len(d["Melate"]["premios"]) != 9:
        errors.append(f"Melate categorías={len(d['Melate']['premios'])}; esperado=9")

    if len(d["Revancha"]["premios"]) != 5:
        errors.append(f"Revancha categorías={len(d['Revancha']['premios'])}; esperado=5")

    if len(d["Revanchita"]["premios"]) < 1:
        errors.append("Revanchita sin premio")

    return errors

def flatten(d):
    rows = []

    for product in PRODUCTS:
        b = d[product]
        nums = b["numeros"]

        for pr in b["premios"]:
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
                "lugar": pr["lugar"],
                "descripcion_acierto": pr["descripcion_acierto"],
                "ganadores": pr["ganadores"],
                "premio_individual": pr["premio_individual"],
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

            if r.status_code in (403, 429):
                return None, f"HTTP {r.status_code}", url

            r.raise_for_status()
            d = parse_page(concurso, r.text, url)
            time.sleep(pause)
            return d, None, url

        except Exception as e:
            last = str(e)
            if attempt < retries:
                time.sleep(max(1, pause * 2))

    return None, last, url

with st.expander("⚙️ Configuración", expanded=True):
    c1, c2 = st.columns(2)
    inicio = c1.number_input("Concurso inicial", min_value=1, value=3192, step=1)
    fin = c2.number_input("Concurso final", min_value=1, value=3192, step=1)

    c3, c4 = st.columns(2)
    pausa = c3.slider("Pausa entre páginas (seg)", 0.5, 5.0, 2.0, 0.5)
    retries = c4.slider("Reintentos", 0, 5, 2, 1)

if "rows" not in st.session_state:
    st.session_state.rows = []
if "errors" not in st.session_state:
    st.session_state.errors = []

if st.button("🔎 Extraer datos", type="primary", use_container_width=True):
    if fin < inicio:
        st.error("Rango inválido.")
        st.stop()

    total = int(fin - inicio + 1)

    if total > 100:
        st.warning("Máximo 100 concursos por corrida (aprox. 1,500 filas).")
        st.stop()

    st.session_state.rows = []
    st.session_state.errors = []

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; MelateDataResearch/4.0)"
    })

    progress = st.progress(0)
    status = st.empty()

    for k, concurso in enumerate(range(int(inicio), int(fin)+1), start=1):
        status.write(f"Procesando **{concurso}** ({k}/{total})…")

        d, err, url = fetch(s, concurso, float(pausa), int(retries))

        if err:
            st.session_state.errors.append({
                "concurso": concurso,
                "url": url,
                "detalle": err
            })
            if "HTTP 403" in err or "HTTP 429" in err:
                st.error(err)
                break

        else:
            issues = validate(d, concurso)

            with st.expander(f"Diagnóstico {concurso}", expanded=False):
                st.write("Melate:", d["Melate"]["numeros"], "Adicional:", d["Melate"]["adicional"])
                st.write("Melate categorías:", len(d["Melate"]["premios"]))
                st.write("Revancha:", d["Revancha"]["numeros"])
                st.write("Revancha categorías:", len(d["Revancha"]["premios"]))
                st.write("Revanchita:", d["Revanchita"]["numeros"])
                st.write("Revanchita categorías:", len(d["Revanchita"]["premios"]))

            if issues:
                st.session_state.errors.append({
                    "concurso": concurso,
                    "url": url,
                    "detalle": " | ".join(issues)
                })
            else:
                st.session_state.rows.extend(flatten(d))

        progress.progress(k / total)

    status.write("Extracción terminada.")

if st.session_state.rows or st.session_state.errors:

    df = pd.DataFrame(st.session_state.rows)
    edf = pd.DataFrame(st.session_state.errors)

    if not df.empty:
        st.subheader("Premios extraídos")

        st.dataframe(
            df[[
                "concurso","producto","lugar","descripcion_acierto",
                "ganadores","premio_individual",
                "n1","n2","n3","n4","n5","n6","adicional"
            ]],
            use_container_width=True,
            hide_index=True
        )

        st.metric("Filas extraídas", len(df))

        st.download_button(
            "⬇️ Descargar CSV",
            df.to_csv(index=False).encode("utf-8-sig"),
            f"premios_{int(inicio)}_{int(fin)}.csv",
            "text/csv",
            use_container_width=True
        )

        xbuf = io.BytesIO()
        with pd.ExcelWriter(xbuf, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Premios", index=False)
            edf.to_excel(writer, sheet_name="Errores", index=False)

        st.download_button(
            "⬇️ Descargar Excel",
            xbuf.getvalue(),
            f"premios_{int(inicio)}_{int(fin)}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    if not edf.empty:
        st.subheader("Errores")
        st.dataframe(edf, use_container_width=True, hide_index=True)

st.caption("v4 — parser basado en la estructura HTML real: h3 + div.resultado + ol.detalle_resultado + li.res.")
    
