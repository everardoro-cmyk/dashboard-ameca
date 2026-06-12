import os
import sqlite3
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from shapely.geometry import Point, box
import geopandas as gpd

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(page_title="APEX - Inteligencia Territorial", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .ficha-box { background-color: #262730; padding: 20px; border-radius: 10px; border-left: 5px solid #ff4b4b; }
    .historia-item { font-size: 16px; margin-bottom: 5px; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CARGA DE DATOS DESDE SQLITE
# ==========================================
DB_PATH = "apex_electoral.db"

@st.cache_data
def cargar_datos_ameca():
    if not os.path.exists(DB_PATH):
        return None, None, None
    
    conn = sqlite3.connect(DB_PATH)
    # Extraemos solo Ameca (ID_MUNICIPIO = 6) para optimizar memoria
    df_sec = pd.read_sql("SELECT * FROM secciones WHERE MUNICIPIO_ID = 6", conn)
    df_res = pd.read_sql("SELECT * FROM resultados_resumen WHERE MUNICIPIO_ID = 6", conn)
    df_vot = pd.read_sql("SELECT * FROM resultados_votos WHERE SECCION IN (SELECT SECCION FROM secciones WHERE MUNICIPIO_ID = 6)", conn)
    conn.close()
    return df_sec, df_res, df_vot

df_secciones, df_resumen, df_votos = cargar_datos_ameca()

if df_secciones is None:
    st.error(f"❌ No se encontró la base de datos '{DB_PATH}'. Colócala en la misma carpeta que este script.")
    st.stop()

# Diccionarios de Coordenadas y Colores (Ameca)
posiciones_ameca = {
    74: (0, 0), 77: (16, 0), 73: (2, -1), 76: (6, -1), 50: (10, -1), 79: (13, -1), 78: (15, -1),
    75: (0, -2), 71: (16, -2), 81: (2, -3), 80: (4, -3), 48: (8, -3), 51: (9, -3), 52: (10, -3), 70: (16, -3),
    82: (0, -4), 56: (7, -4), 54: (8, -4), 53: (9, -4), 60: (10, -4), 87: (18, -4),
    57: (7.5,-5), 55: (8.5,-5), 59: (9.5,-5), 64: (10.5,-5), 86: (15, -5),
    84: (2, -6), 58: (7, -6), 61: (8, -6), 65: (9, -6), 63: (10, -6), 62: (11,-6), 72: (18, -6),
    66: (7.5,-7), 3739: (8.5,-7), 69: (9.5,-7), 3738: (7.5,-8), 85: (9, -9),
    92: (4, -11), 91: (9, -11), 90: (13, -11), 88: (14.5,-11), 89: (16,-11), 93: (9, -12)
}

colores_partidos = {
    'MORENA': '#a50f15', 'MC': '#f16913', 'PAN': '#08519c', 'PRI': '#cb181d',
    'PVEM': '#238b45', 'PT': '#ef3b2c', 'PRD': '#ffeda0', 'PANAL': '#1d91c0',
    'HAGAMOS': '#8c564b', 'FUTURO': '#7f7f7f', 'OTROS': '#888888', 'ND': '#333333'
}

emojis_partidos = {
    'MORENA': '🟤', 'MC': '🟠', 'PAN': '🔵', 'PRI': '🔴', 'PVEM': '🟢', 
    'PT': '🟥', 'PRD': '🟡', 'PANAL': '🟦', 'OTROS': '⚪', 'ND': '⚫'
}

# ==========================================
# 3. BARRA LATERAL (FILTROS)
# ==========================================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Logo_del_Instituto_Electoral_y_de_Participaci%C3%B3n_Ciudadana_del_Estado_de_Jalisco.svg/1024px-Logo_del_Instituto_Electoral_y_de_Participaci%C3%B3n_Ciudadana_del_Estado_de_Jalisco.svg.png", width=150)
    st.title("APEX Jalisco")
    st.markdown("---")
    
    modo_mapa = st.radio("👁️ Modo de Visualización", ["Modo Sólido (1 Nivel)", "Modo Franjas (Voto Cruzado)"])
    anio_sel = st.selectbox("📅 Año Electoral", sorted(df_resumen['AÑO'].unique(), reverse=True))
    
    if modo_mapa == "Modo Sólido (1 Nivel)":
        niveles_disp = sorted(df_resumen[df_resumen['AÑO'] == anio_sel]['NIVEL'].unique())
        nivel_sel = st.selectbox("🏛️ Nivel de Elección", niveles_disp)
    else:
        nivel_sel = "Ayuntamiento" # Default para las gráficas de detalle en modo franjas
        st.info("💡 Modo Franjas Activo:\nArriba: Presidencia\nCentro: Gubernatura\nAbajo: Ayuntamiento")
        
    st.markdown("---")
    sec_sel = st.selectbox("📌 Zoom a Sección", sorted(list(posiciones_ameca.keys())))

# ==========================================
# 4. ÁREA CENTRAL (TILEGRAM DINÁMICO)
# ==========================================
col_mapa, col_ficha = st.columns([2.5, 1.2])

with col_mapa:
    titulo_mapa = f"Tilegram Ameca {anio_sel} — {nivel_sel if modo_mapa == 'Modo Sólido (1 Nivel)' else 'Voto Cruzado'}"
    st.subheader(titulo_mapa)
    
    # Preparar el lienzo
    fig, ax = plt.subplots(figsize=(12, 10))
    fig.patch.set_facecolor('#0e1117') # Match con el tema dark de Streamlit
    ax.set_facecolor('#0e1117')
    
    peso_max = df_secciones['LISTA_NOMINAL_2024'].max()
    R_max = 0.45
    geometrias, colores, etiquetas, bordes, grosores = [], [], [], [], []
    
    # Filtrar datos del año seleccionado
    df_anio = df_resumen[df_resumen['AÑO'] == anio_sel]
    
    for sec, (x, y_raw) in posiciones_ameca.items():
        y = y_raw * 0.866
        
        # Tamaño proporcional
        row_sec = df_secciones[df_secciones['SECCION'] == sec]
        peso = row_sec['LISTA_NOMINAL_2024'].values[0] if not row_sec.empty else 100
        R_actual = max(R_max * np.sqrt(peso / peso_max), 0.20)
        
        # Borde brillante si es la sección seleccionada
        b_color = '#ffffff' if sec == sec_sel else '#0e1117'
        b_width = 3.0 if sec == sec_sel else 0.5
        
        circulo = Point(x, y).buffer(R_actual)
        
        if modo_mapa == "Modo Sólido (1 Nivel)":
            ganador = df_anio[(df_anio['SECCION'] == sec) & (df_anio['NIVEL'] == nivel_sel)]['GANADOR'].values
            color = colores_partidos.get(ganador[0], '#333333') if len(ganador) > 0 else '#333333'
            
            geometrias.append(circulo)
            colores.append(color)
            bordes.append(b_color)
            grosores.append(b_width)
            
        else: # MODO FRANJAS
            box_sup = box(x - R_actual, y + R_actual/3, x + R_actual, y + R_actual)
            box_cen = box(x - R_actual, y - R_actual/3, x + R_actual, y + R_actual/3)
            box_inf = box(x - R_actual, y - R_actual, x + R_actual, y - R_actual/3)
            
            gan_pres = df_anio[(df_anio['SECCION']==sec) & (df_anio['NIVEL']=='Presidencia')]['GANADOR'].values
            gan_gob  = df_anio[(df_anio['SECCION']==sec) & (df_anio['NIVEL']=='Gobernatura')]['GANADOR'].values
            gan_ayun = df_anio[(df_anio['SECCION']==sec) & (df_anio['NIVEL']=='Ayuntamiento')]['GANADOR'].values
            
            c_pres = colores_partidos.get(gan_pres[0], '#333333') if len(gan_pres)>0 else '#333333'
            c_gob  = colores_partidos.get(gan_gob[0], '#333333') if len(gan_gob)>0 else '#333333'
            c_ayun = colores_partidos.get(gan_ayun[0], '#333333') if len(gan_ayun)>0 else '#333333'
            
            for geom, col in zip([circulo.intersection(box_sup), circulo.intersection(box_cen), circulo.intersection(box_inf)], [c_pres, c_gob, c_ayun]):
                if not geom.is_empty:
                    geometrias.append(geom)
                    colores.append(col)
                    bordes.append(b_color) # El borde se aplica a los 3 cortes
                    grosores.append(b_width)
        
        # Etiqueta de texto
        etiquetas.append({'x': x, 'y': y, 'text': str(sec), 'size': 11 if R_actual > 0.35 else 8})
    
    # Dibujar usando GeoPandas
    gdf = gpd.GeoDataFrame({'geometry': geometrias, 'color': colores, 'edge': bordes, 'lw': grosores})
    
    # Dibujar cada capa para respetar los bordes individuales
    for _, row in gdf.iterrows():
        gpd.GeoSeries([row['geometry']]).plot(ax=ax, color=row['color'], edgecolor=row['edge'], linewidth=row['lw'])
        
    for et in etiquetas:
        ax.text(et['x'], et['y'], et['text'], color='white', fontsize=et['size'], fontweight='bold', ha='center', va='center')
        
    ax.axis('off')
    ax.set_aspect('equal')
    st.pyplot(fig)

# ==========================================
# 5. PANEL DERECHO (FICHA DE SECCIÓN)
# ==========================================
with col_ficha:
    info_sec = df_secciones[df_secciones['SECCION'] == sec_sel].iloc[0]
    
    st.markdown(f"### Sección **{sec_sel}**")
    st.markdown(f"**Ámbito:** {info_sec['TIPO_SECCION']} | **Lista Nominal:** {info_sec['LISTA_NOMINAL_2024']:,}")
    
    st.markdown("<div class='ficha-box'>", unsafe_allow_html=True)
    
    # Gráfica de Votos del Año Actual
    st.markdown(f"#### 📊 Resultado {anio_sel} ({nivel_sel})")
    votos_sec = df_votos[(df_votos['SECCION'] == sec_sel) & (df_votos['AÑO'] == anio_sel) & (df_votos['NIVEL'] == nivel_sel)]
    
    if not votos_sec.empty:
        votos_sec = votos_sec.sort_values(by='PCT', ascending=False).head(5) # Top 5 partidos
        chart_data = votos_sec[['PARTIDO', 'PCT']].set_index('PARTIDO')
        st.bar_chart(chart_data)
        
        # Mostrar margen
        resumen_sec = df_resumen[(df_resumen['SECCION'] == sec_sel) & (df_resumen['AÑO'] == anio_sel) & (df_resumen['NIVEL'] == nivel_sel)]
        if not resumen_sec.empty:
            margen = resumen_sec.iloc[0]['MARGEN']
            clase = resumen_sec.iloc[0]['CLASIFICACION']
            st.caption(f"**Competitividad:** {clase} (Margen: {margen}%)")
    else:
        st.warning(f"No hay registros de votación para {nivel_sel} en {anio_sel}.")

    st.markdown("---")
    
    # Historial de Tiempo (La Evolución del Ganador)
    st.markdown(f"#### 📈 Historial Histórico ({nivel_sel})")
    historial = df_resumen[(df_resumen['SECCION'] == sec_sel) & (df_resumen['NIVEL'] == nivel_sel)].sort_values(by='AÑO')
    
    if not historial.empty:
        for _, row in historial.iterrows():
            g = row['GANADOR']
            emoji = emojis_partidos.get(g, '⚪')
            st.markdown(f"<div class='historia-item'>**{row['AÑO']}:** {emoji} {g} <span style='font-size:12px; color:#aaa;'>({row['PCT_GANADOR']}%)</span></div>", unsafe_allow_html=True)
    else:
        st.info("Sin historial para este nivel.")
        
    st.markdown("</div>", unsafe_allow_html=True)
