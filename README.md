# Melate Club Extractor

App web en Streamlit para extraer concursos desde https://melate.club/sorteo-XXXX.

## Prueba recomendada
3191 a 3205.

## Ejecutar
pip install -r requirements.txt
streamlit run app.py

## Desde celular
Despliega estos archivos en Streamlit Community Cloud o un hosting compatible y abre la URL pública desde tu teléfono.

La app:
- extrae Melate, Revancha y Revanchita;
- detecta falsos ceros;
- exporta CSV y Excel;
- puede guardar HTML crudo;
- se detiene ante HTTP 403/429;
- limita cada corrida a 250 concursos.
