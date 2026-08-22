import io,re,time,zipfile
from datetime import datetime
import pandas as pd, requests, streamlit as st
from bs4 import BeautifulSoup

BASE='https://melate.club/sorteo-{c}'
PRODUCTS=('Melate','Revancha','Revanchita')
MONTHS={'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,'julio':7,'agosto':8,'septiembre':9,'setiembre':9,'octubre':10,'noviembre':11,'diciembre':12}
PRIZE_RE=re.compile(r'(?P<lugar>\d+)\.\s*(?P<desc>.*?)\s*(?P<gan>[\d,]+)\s+ganador(?:es)?\s*(?:\|\s*)?premio\s*\$\s*(?P<premio>[\d,]+\.\d{2})',re.I|re.S)

st.set_page_config(page_title='Melate Club Extractor v2',page_icon='🎟️',layout='centered')
st.title('🎟️ Melate Club Extractor v2')
st.caption('Extrae números, categorías, ganadores y premio individual desde Melate Club.')

def norm(s): return re.sub(r'\s+',' ',(s or '').replace('\xa0',' ')).strip()
def parse_date(text):
    m=re.search(r'(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+del?\s+(\d{4})',text,re.I)
    if not m:return None
    mon=m.group(2).lower().translate(str.maketrans('áéíóú','aeiou'))
    return datetime(int(m.group(3)),MONTHS[mon],int(m.group(1))).strftime('%Y-%m-%d') if mon in MONTHS else None

def tokens(html):
    s=BeautifulSoup(html,'html.parser')
    return [norm(x) for x in s.stripped_strings if norm(x)]

def split_sections(t):
    start=next((i for i,x in enumerate(t) if 'Resultados Melate' in x),0)
    pos={}
    for p in PRODUCTS:
        for i in range(start,len(t)):
            if t[i]==p: pos[p]=i; break
    out={}
    for p in PRODUCTS:
        if p not in pos: out[p]=[]; continue
        a=pos[p]+1
        later=[pos[q] for q in PRODUCTS if q in pos and pos[q]>pos[p]]
        b=min(later) if later else len(t)
        for j in range(a,b):
            low=t[j].lower()
            if low.startswith(('despues de ','después de ','información sobre','necesitas consultar')):
                b=j;break
        out[p]=t[a:b]
    return out

def parse_section(product,t):
    blob=' '.join(t)
    first=re.search(r'\b1\.\s*6\s+n[uú]meros',blob,re.I)
    prefix=blob[:first.start()] if first else blob
    need=7 if product=='Melate' else 6
    nums=[]
    for s in re.findall(r'(?<![\d,.])(\d{1,2})(?![\d,.])',prefix):
        n=int(s)
        if 1<=n<=56:
            nums.append(n)
            if len(nums)==need: break
    prizes=[]
    for m in PRIZE_RE.finditer(blob):
        prizes.append({'lugar':int(m.group('lugar')),'descripcion_acierto':norm(m.group('desc')),'ganadores':int(m.group('gan').replace(',','')),'premio_individual':float(m.group('premio').replace(',',''))})
    return nums[:6],(nums[6] if product=='Melate' and len(nums)>=7 else None),prizes

def parse_page(req,html,url):
    t=tokens(html); head=' '.join(t[:120])
    m=re.search(r'Sorteo\s+Melate,\s*Revancha\s+y\s+Revanchita\s+(\d+)',head,re.I) or re.search(r'\bSorteo\s+(\d{4})\b',head,re.I)
    d={'concurso':int(m.group(1)) if m else None,'fecha':parse_date(head),'url':url}
    for p,sec in split_sections(t).items():
        n,a,pr=parse_section(p,sec); d[p]={'numeros':n,'adicional':a,'premios':pr}
    econ=d['Melate']['premios']+d['Revancha']['premios']
    if len(d['Melate']['premios'])==9 and len(d['Revancha']['premios'])==5 and econ and all(x['ganadores']==0 and x['premio_individual']==0 for x in econ): d['estado_economico']='SIN_DATOS_ECONOMICOS'
    elif len(d['Melate']['premios'])==9 and len(d['Revancha']['premios'])==5 and len(d['Revanchita']['premios'])>=1: d['estado_economico']='COMPLETO'
    else:d['estado_economico']='INCOMPLETO'
    return d

def issues(d,req):
    out=[]
    if d['concurso']!=req: out.append(f"concurso página={d['concurso']}")
    if len(d['Melate']['numeros'])!=6 or d['Melate']['adicional'] is None: out.append('Melate sin 6+adicional')
    if len(d['Revancha']['numeros'])!=6: out.append('Revancha sin 6 números')
    if len(d['Revanchita']['numeros'])!=6: out.append('Revanchita sin 6 números')
    if len(d['Melate']['premios'])!=9: out.append(f"Melate categorías={len(d['Melate']['premios'])}, esperado 9")
    if len(d['Revancha']['premios'])!=5: out.append(f"Revancha categorías={len(d['Revancha']['premios'])}, esperado 5")
    if len(d['Revanchita']['premios'])<1: out.append('Revanchita sin premio')
    if [x['lugar'] for x in d['Melate']['premios']]!=list(range(1,10)): out.append('lugares Melate inválidos')
    if [x['lugar'] for x in d['Revancha']['premios']]!=list(range(1,6)): out.append('lugares Revancha inválidos')
    return out

def flatten(d):
    rows=[]
    for p in PRODUCTS:
        b=d[p]; n=b['numeros']
        for pr in b['premios']:
            rows.append({'concurso':d['concurso'],'fecha':d['fecha'],'producto':p.upper(),**{f'n{i+1}':n[i] if i<len(n) else None for i in range(6)},'adicional':b['adicional'],**pr,'estado_economico':d['estado_economico'],'url':d['url']})
    return rows

with st.expander('⚙️ Configuración',expanded=True):
    c1,c2=st.columns(2); ini=c1.number_input('Concurso inicial',1,value=3191); fin=c2.number_input('Concurso final',1,value=3205)
    c3,c4=st.columns(2); pause=c3.slider('Pausa entre páginas (seg)',0.5,5.0,2.0,0.5); retries=c4.slider('Reintentos',0,5,2)
    raw_on=st.checkbox('Conservar HTML crudo',False)

if 'rows' not in st.session_state: st.session_state.rows=[]
if 'errs' not in st.session_state: st.session_state.errs=[]
if 'raw' not in st.session_state: st.session_state.raw={}

if st.button('🔎 Extraer datos',type='primary',use_container_width=True):
    if fin<ini: st.error('Rango inválido'); st.stop()
    total=int(fin-ini+1)
    if total>250: st.warning('Máximo 250 concursos por corrida'); st.stop()
    st.session_state.rows=[]; st.session_state.errs=[]; st.session_state.raw={}
    s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0 (compatible; MelateDataResearch/2.0)'})
    prog=st.progress(0); status=st.empty()
    for k,c in enumerate(range(int(ini),int(fin)+1),1):
        status.write(f'Procesando **{c}** ({k}/{total})…'); url=BASE.format(c=c); err=None; html=None
        for a in range(int(retries)+1):
            try:
                r=s.get(url,timeout=25)
                if r.status_code in (403,429): err=f'HTTP {r.status_code}'; break
                r.raise_for_status(); html=r.text; break
            except Exception as e:
                err=str(e)
                if a<int(retries): time.sleep(max(1,float(pause)*2))
        if err or html is None:
            st.session_state.errs.append({'concurso':c,'url':url,'tipo_error':'FETCH','detalle':err or 'sin HTML'})
            if err and ('403' in err or '429' in err): st.error(err); break
        else:
            d=parse_page(c,html,url); bad=issues(d,c)
            if bad: st.session_state.errs.append({'concurso':c,'url':url,'tipo_error':'INTEGRIDAD','detalle':' | '.join(bad)})
            else:
                st.session_state.rows.extend(flatten(d))
                if raw_on: st.session_state.raw[c]=html
            time.sleep(float(pause))
        prog.progress(k/total)
    status.write('Extracción terminada.')

if st.session_state.rows or st.session_state.errs:
    df=pd.DataFrame(st.session_state.rows); edf=pd.DataFrame(st.session_state.errs,columns=['concurso','url','tipo_error','detalle'])
    if not df.empty:
        resumen=df.groupby(['concurso','fecha','estado_economico'],dropna=False).agg(filas=('producto','size'),productos=('producto','nunique')).reset_index().sort_values('concurso')
        c1,c2,c3,c4=st.columns(4); c1.metric('OK',df.concurso.nunique()); c2.metric('Completos',df[df.estado_economico=='COMPLETO'].concurso.nunique()); c3.metric('Sin datos',df[df.estado_economico=='SIN_DATOS_ECONOMICOS'].concurso.nunique()); c4.metric('Errores',len(edf))
        st.subheader('Resumen'); st.dataframe(resumen,use_container_width=True,hide_index=True)
        st.subheader('Premios'); st.dataframe(df[['concurso','producto','lugar','descripcion_acierto','ganadores','premio_individual']],use_container_width=True,hide_index=True)
        st.download_button('⬇️ Descargar CSV completo',df.to_csv(index=False).encode('utf-8-sig'),f'premios_{int(ini)}_{int(fin)}.csv','text/csv',use_container_width=True)
        b=io.BytesIO()
        with pd.ExcelWriter(b,engine='openpyxl') as w:
            df.to_excel(w,'Premios',index=False); resumen.to_excel(w,'Resumen',index=False); edf.to_excel(w,'Errores',index=False)
        st.download_button('⬇️ Descargar Excel completo',b.getvalue(),f'premios_{int(ini)}_{int(fin)}.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
    if not edf.empty:
        st.subheader('Errores'); st.dataframe(edf,use_container_width=True,hide_index=True)
    if raw_on and st.session_state.raw:
        z=io.BytesIO()
        with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED) as zz:
            for c,h in st.session_state.raw.items(): zz.writestr(f'sorteo-{c}.html',h)
        st.download_button('⬇️ Descargar HTML crudo',z.getvalue(),f'html_{int(ini)}_{int(fin)}.zip','application/zip',use_container_width=True)

st.caption('v2: exige 9 categorías de Melate, 5 de Revancha y al menos 1 de Revanchita; si falta algo, rechaza el concurso.')
    
