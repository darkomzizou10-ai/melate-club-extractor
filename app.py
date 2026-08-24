import io
import time
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="Melate Club Diagnóstico", page_icon="🧪", layout="centered")
st.title("🧪 Melate Club — Diagnóstico HTML")
st.caption("Esta versión descarga SIEMPRE el HTML crudo aunque falle el parser.")

concurso = st.number_input("Concurso", min_value=1, value=3192, step=1)
pausa = st.slider("Pausa (seg)", 0.0, 5.0, 1.0, 0.5)

if st.button("Descargar página y diagnosticar", type="primary", use_container_width=True):
    url = f"https://melate.club/sorteo-{int(concurso)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MelateDataResearch-Diagnostic/1.0)"
    }

    try:
        r = requests.get(url, headers=headers, timeout=25)
        st.write("HTTP:", r.status_code)
        st.write("URL final:", r.url)
        st.write("Content-Type:", r.headers.get("content-type"))

        if r.status_code in (403, 429):
            st.error(f"HTTP {r.status_code}: el sitio rechazó o limitó la solicitud.")
        else:
            r.raise_for_status()
            html = r.text

            # SIEMPRE habilitar descarga del HTML
            st.download_button(
                "⬇️ Descargar HTML crudo",
                data=html.encode("utf-8", errors="replace"),
                file_name=f"sorteo-{int(concurso)}.html",
                mime="text/html",
                use_container_width=True
            )

            soup = BeautifulSoup(html, "html.parser")

            st.subheader("Diagnóstico básico")
            st.write("Tamaño HTML:", len(html), "caracteres")
            st.write("Título:", soup.title.get_text(" ", strip=True) if soup.title else "(sin title)")
            st.write("Cantidad de <li>:", len(soup.find_all("li")))
            st.write("Cantidad de <h2>:", len(soup.find_all("h2")))
            st.write("Cantidad de <h3>:", len(soup.find_all("h3")))
            st.write("Cantidad de <h4>:", len(soup.find_all("h4")))

            # Mostrar líneas que contengan términos clave
            texts = [x.strip() for x in soup.stripped_strings if x.strip()]
            claves = []
            for t in texts:
                low = t.lower()
                if (
                    "ganador" in low
                    or "premio" in low
                    or t in ("Melate", "Revancha", "Revanchita")
                    or "números" in low
                    or "numeros" in low
                ):
                    claves.append(t)

            st.subheader("Texto clave recibido")
            if claves:
                st.code("\n".join(claves[:200]))
            else:
                st.warning("No se encontraron textos clave de premios en el HTML recibido.")

            # También descargar el texto clave
            key_text = "\n".join(claves)
            st.download_button(
                "⬇️ Descargar texto clave (.txt)",
                data=key_text.encode("utf-8"),
                file_name=f"sorteo-{int(concurso)}_texto_clave.txt",
                mime="text/plain",
                use_container_width=True
            )

    except Exception as e:
        st.exception(e)

st.caption("Esta app no extrae la base final: sólo nos permite ver exactamente qué recibe Streamlit desde Melate Club.")
