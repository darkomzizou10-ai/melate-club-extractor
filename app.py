
import io, re, time, zipfile
from datetime import datetime
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

BASE_URL="https://melate.club/sorteo-{concurso}"
PRODUCTS=("Melate","Revancha","Revanchita")
MONTHS={"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,"julio":7,"agosto":8,"septiembre":9,"setiembre":9,"octubre":10,"noviembre":11,"diciembre":12}
PRIZE_RE=re.compile(r"^\s*(\d+)\.\s*(.*?)\s*\|\s*([\d,]+)\s+ganador(?:es)?\s*\|\s*premio\s*\$\s*([\d,]+\.\d{2})\s*$",re.I)

st.set_page_config(page_title="Melate Club Extractor",page_icon="🎟️",layout="centered")
st.title("🎟️ Melate Club Extractor")
st.caption("Extrae Melate, Revancha y Revanchita desde melate.club y descarga CSV/Excel.")

def norm(s): return re.sub(r"\s+"," ",(s or "").replace("\xa0"," ")).strip()

def parse_date(text):
    m=re.search(r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+del?\s+(\d{4})",text,re.I)
    if not m: return None
    d=int(m.group(1)); mon=m.group(2).lower()
    mon=mon.translate(str.maketrans("áéíóú","aeiou"))
    mo=MONTHS.get(mon)
    return datetime(int(m.group(3)),mo,d).strftime("%Y-%m-%d") if mo else None

def tokens(html):
    soup=BeautifulSoup(html,"html.parser")
    return [norm(x) for x in soup.stripped_strings if norm(x)]

def sections(toks):
    idx={}
    for i,t in enumerate(toks):
        if t in PRODUCTS and t not in idx: idx[t]=i
    out={}
    for p in PRODUCTS:
        if p not in idx: out[p]=[]; continue
        start=idx[p]+1
        later=[idx[q] for q in PRODUCTS if q in idx and idx[q]>idx[p]]
        end=min(later) if later else len(toks)
        for j in range(start,end):
            l=toks[j].lower()
            if l.startswith("despues de") or l.startswith("después de") or l.startswith("información sobre"):
                end=j; break
        out[p]=toks[start:end]
    return out

def parse_section(product,toks):
    need=7 if product=="Melate" else 6
    nums=[]; prizes=[]
    for t in toks:
        if len(nums)<need and re.fullmatch(r"\d{1,2}",t):
            n=int(t)
            if 1<=n<=56: nums.append(n); continue
        m=PRIZE_RE.match(t)
        if m:
            prizes.append({
                "lugar":int(m.group(1)),
                "descripcion_acierto":norm(m.group(2)),
                "ganadores":int(m.group(3).replace(",","")),
                "premio_individual":float(m.group(4).replace(",",""))
            })
    return nums[:6], nums[6] if product=="Melate" and len(nums)>=7 else None, prizes

def parse_page(requested,html,url):
    toks=tokens(html); head=" ".join(toks[:100])
    m=re.search(r"Sorteo\s+Melate,\s*Revancha\s+y\s+Revanchita\s+(\d+)",head,re.I) or re.search(r"Sorteo.*?(\d{4})",head,re.I)
    concurso=int(m.group(1)) if m else None
    data={"solicitado":requested,"concurso":concurso,"fecha":parse_date(head),"url":url}
    for p,sec in sections(toks).items():
        n,a,pr=parse_section(p,sec)
        data[p]={"numeros":n,"adicional":a,"premios":pr}
    allpr=data["Melate"]["premios"]+data["Revancha"]["premios"]
    if len(data["Melate"]["premios"])>=9 and len(data["Revancha"]["premios"])>=5 and all(r["ganadores"]==0 and r["premio_individual"]==0 for r in allpr):
        data["estado_economico"]="SIN_DATOS_ECONOMICOS"
    elif len(data["Melate"]["premios"])==9 and len(data["Revancha"]["premios"])==5:
        data["estado_economico"]="COMPLETO"
    else:
        data["estado_economico"]="INCOMPLETO"
    return data

def flatten(d):
    rows=[]
    for p in PRODUCTS:
        x=d[p]; nums=x["numeros"]; prs=x["premios"] or [{"lugar":None,"descripcion_acierto":None,"ganadores":None,"premio_individual":None}]
        for pr in prs:
            rows.append({
                "concurso":d["concurso"],"fecha":d["fecha"],"producto":p.upper(),
                **{f"n{i+1}":nums[i] if i<len(nums) else None for i in range(6)},
                "adicional":x["adicional"],**pr,
                "estado_economico":d["estado_economico"],"url":d["url"]
            })
    return rows

def fetch(session,concurso,pause,retries):
    url=BASE_URL.format(concurso=concurso)
    for attempt in range(retries+1):
        try:
            r=session.get(url,timeout=20)
            if r.status_code in (403,429): return None,f"HTTP {r.status_code}",url,None
            r.raise_for_status()
            d=parse_page(concurso,r.text,url); time.sleep(pause)
            return d,None,url,r.text
        except Exception as e:
            if attempt==retries: return None,str(e),url,None
            time.sleep(max(1,pause*2))

with st.expander("⚙️ Configuración",expanded=True):
    c1,c2=st.columns(2)
    inicio=c1.number_input("Concurso inicial",min_value=1,value=3191,step=1)
    fin=c2.number_input("Concurso final",min_value=1,value=3205,step=1)
    c3,c4=st.columns(2)
    pausa=c3.slider("Pausa entre páginas (seg)",0.5,5.0,1.5,0.5)
    retries=c4.slider("Reintentos",0,5,2,1)
    guardar_html=st.checkbox("Conservar HTML crudo",False)

if "data" not in st.session_state: st.session_state.data=[]
if "errors" not in st.session_state: st.session_state.errors=[]
if "raw" not in st.session_state: st.session_state.raw={}

if st.button("🔎 Extraer datos",type="primary",use_container_width=True):
    if fin<inicio: st.error("Rango inválido."); st.stop()
    total=int(fin-inicio+1)
    if total>250: st.warning("Procesa máximo 250 concursos por corrida."); st.stop()
    st.session_state.data=[]; st.session_state.errors=[]; st.session_state.raw={}
    s=requests.Session()
    s.headers.update({"User-Agent":"Mozilla/5.0 (compatible; MelateDataResearch/1.0)"})
    prog=st.progress(0); txt=st.empty()
    for k,c in enumerate(range(int(inicio),int(fin)+1),1):
        txt.write(f"Procesando **{c}** ({k}/{total})…")
        d,err,url,raw=fetch(s,c,float(pausa),int(retries))
        if err:
            st.session_state.errors.append({"concurso":c,"url":url,"tipo_error":"FETCH/PARSE","detalle":err})
            if "HTTP 403" in err or "HTTP 429" in err:
                st.error(f"{err}: proceso detenido por seguridad."); break
        else:
            issues=[]
            if d["concurso"]!=c: issues.append(f"Página reporta {d['concurso']}")
            if len(d["Melate"]["numeros"])!=6 or d["Melate"]["adicional"] is None: issues.append("Melate incompleto")
            if len(d["Revancha"]["numeros"])!=6: issues.append("Revancha incompleta")
            if len(d["Revanchita"]["numeros"])!=6: issues.append("Revanchita incompleta")
            if issues:
                st.session_state.errors.append({"concurso":c,"url":url,"tipo_error":"INTEGRIDAD","detalle":" | ".join(issues)})
            else:
                st.session_state.data.extend(flatten(d))
                if guardar_html: st.session_state.raw[c]=raw
        prog.progress(k/total)
    txt.write("Extracción terminada.")

if st.session_state.data or st.session_state.errors:
    df=pd.DataFrame(st.session_state.data)
    edf=pd.DataFrame(st.session_state.errors,columns=["concurso","url","tipo_error","detalle"])
    if not df.empty:
        resumen=df.groupby(["concurso","fecha","estado_economico"],dropna=False).agg(filas=("producto","size"),productos=("producto","nunique")).reset_index()
        c1,c2,c3,c4=st.columns(4)
        c1.metric("OK",df["concurso"].nunique())
        c2.metric("Completos",df[df.estado_economico=="COMPLETO"]["concurso"].nunique())
        c3.metric("Sin datos",df[df.estado_economico=="SIN_DATOS_ECONOMICOS"]["concurso"].nunique())
        c4.metric("Errores",len(edf))
        st.subheader("Resumen"); st.dataframe(resumen,use_container_width=True,hide_index=True)
        st.subheader("Datos"); st.dataframe(df,use_container_width=True,hide_index=True)
        st.download_button("⬇️ Descargar CSV",df.to_csv(index=False).encode("utf-8-sig"),f"premios_{int(inicio)}_{int(fin)}.csv","text/csv",use_container_width=True)
        b=io.BytesIO()
        with pd.ExcelWriter(b,engine="openpyxl") as w:
            df.to_excel(w,sheet_name="Premios",index=False)
            edf.to_excel(w,sheet_name="Errores",index=False)
            resumen.to_excel(w,sheet_name="Resumen",index=False)
        st.download_button("⬇️ Descargar Excel",b.getvalue(),f"premios_{int(inicio)}_{int(fin)}.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
    if not edf.empty:
        st.subheader("Errores"); st.dataframe(edf,use_container_width=True,hide_index=True)
        st.download_button("⬇️ Descargar errores CSV",edf.to_csv(index=False).encode("utf-8-sig"),f"errores_{int(inicio)}_{int(fin)}.csv","text/csv",use_container_width=True)
    if guardar_html and st.session_state.raw:
        z=io.BytesIO()
        with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as zz:
            for c,h in st.session_state.raw.items(): zz.writestr(f"sorteo-{c}.html",h)
        st.download_button("⬇️ Descargar HTML crudo",z.getvalue(),f"html_{int(inicio)}_{int(fin)}.zip","application/zip",use_container_width=True)

st.caption("Uso de investigación. Si Melate Club responde 403/429, la app se detiene y no intenta evadir el bloqueo.")
