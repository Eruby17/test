import streamlit as st
from fpdf import FPDF
from datetime import datetime, timedelta
import pandas as pd
import requests
import io

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Cotizador de upsells - Casa Dorada", page_icon="🏨", layout="wide")

# --- 2. ENLACE DE PUBLICACIÓN WEB DIRECTO (INMUNE A FALLAS) ---
# Usamos tu enlace publicado directamente. Para leer las hojas con pandas sin openpyxl,
# transformamos la salida a formato plano CSV para máxima estabilidad.
URL_HOJA_1 = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTa9QMfH9XHV9BTptpHhiMjROI5UdxqY7sQnEPGCC6xTwsQWyRLHt_etNljvwN29hoeYj7wdmOaEdBg/pub?output=csv&gid=481323566"
URL_HOJA_2 = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTa9QMfH9XHV9BTptpHhiMjROI5UdxqY7sQnEPGCC6xTwsQWyRLHt_etNljvwN29hoeYj7wdmOaEdBg/pub?output=csv&gid=0"

@st.cache_data(ttl=600, show_spinner=False)
def descargar_datos_directo():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        
        # Descarga e interpretación instantánea de la Hoja 1 (Configuración)
        r1 = requests.get(URL_HOJA_1, headers=headers, timeout=10)
        df_c = pd.read_csv(io.StringIO(r1.text)) if r1.status_code == 200 else None
        
        # Descarga e interpretación instantánea de la Hoja 2 (Calendario de tarifas)
        r2 = requests.get(URL_HOJA_2, headers=headers, timeout=10)
        df_cal = pd.read_csv(io.StringIO(r2.text)) if r2.status_code == 200 else None
        
        return df_c, df_cal
    except Exception as e:
        return None, None

# Ejecutar la descarga única directa a la memoria caché de la app
df_config, df_calendario_raw = descargar_datos_directo()

# --- 3. PROCESAR CONFIGURACIÓN DE PARÁMETROS ---
tc_base = 17.40
desc_base = 62.0

if df_config is not None and not df_config.empty:
    try:
        df_config.columns = [str(c).strip().lower() for c in df_config.columns]
        df_config['parametro'] = df_config['parametro'].astype(str).str.strip().str.lower()
        
        fila_desc = df_config[df_config['parametro'] == 'descuento']
        fila_tc = df_config[df_config['parametro'] == 'tc']
        
        if not fila_desc.empty:
            desc_base = float(str(fila_desc['valor'].values[0]).replace('%', '').replace(',', '.').strip())
        if not fila_tc.empty:
            tc_base = float(str(fila_tc['valor'].values[0]).replace(',', '.').strip())
    except Exception:
        pass

# --- 4. INDEXAR CALENDARIO DE TARIFAS DINÁMICAS POR DÍA ---
tarifas_por_dia_memoria = {}
if df_calendario_raw is not None and not df_calendario_raw.empty:
    try:
        df_calendario_raw.columns = [str(c).strip() for c in df_calendario_raw.columns]
        
        col_fecha = df_calendario_raw.iloc[:, 0]
        col_tarifa = df_calendario_raw.iloc[:, 1]
        
        fechas_transformadas = pd.to_datetime(col_fecha.astype(str).str.strip(), errors='coerce', dayfirst=True)
        fechas_texto = fechas_transformadas.dt.strftime('%Y-%m-%d')
        
        precios_limpios = pd.to_numeric(col_tarifa.astype(str).str.replace(' ', '').str.replace('$', '').str.replace(',', '.').strip(), errors='coerce')
        
        for f, p in zip(fechas_texto, precios_limpios):
            if pd.notna(f) and pd.notna(p):
                tarifas_por_dia_memoria[f] = float(p)
                
        st.sidebar.success(f"📈 {len(tarifas_por_dia_memoria)} días de tarifas indexados con éxito.")
    except Exception as e:
        st.sidebar.error(f"Error al procesar el archivo: {str(e)}")
else:
    st.sidebar.error("⚠️ Aviso: Usando tarifas fijas de respaldo. No se pudo leer el archivo publicado.")

# --- 5. PANEL LATERAL (SIDEBAR) ---
with st.sidebar:
    st.header("Configuración")
    st.metric("Descuento Aplicado", f"{desc_base}%")
    
    tc_actual = st.number_input(
        "Tipo de Cambio (MXN)",
        min_value=1.0,
        value=float(tc_base),
        step=0.1,
        format="%.2f"
    )
    
    st.divider()
    if st.button("🔄 Actualizar Tarifas de Google"):
        st.cache_data.clear()
        st.rerun()

# --- 6. INTERFAZ PRINCIPAL ---
st.title("🏨 Cotizador de upsells - Temporadas Dinámicas")

col_nom, col_fol = st.columns(2)
with col_nom: cliente = st.text_input("Nombre del Huésped", value="")
with col_fol: n_reserva = st.text_input("Número de Confirmación", value="")

col_in, col_out = st.columns(2)
with col_in: check_in = st.date_input("Check-in", datetime.now().date())
with col_out: check_out = st.date_input("Check-out", datetime.now().date() + timedelta(days=1))

noches = (check_out - check_in).days if check_out and check_in else 1

valores_habitaciones = {
    "Standard Two Double Beds": 0.0, "Junior Suite": 75.0, "Deluxe Suite": 0.0,
    "Executive Suite": 150.0, "One Bedroom Suite Garden": 225.0, "One Bedroom Suite": 300.0,
    "1 Bedroom Suite Plus": 375.0, "1 Bedroom Ocean Front": 475.0, "2 Bedroom Suite": 780.0,
    "2 Bedroom Ocean Front": 980.0, "Penthouse 1PH": 1125.0,
    "Penthouse 2PH": 1875.0, "Penthouse 3PH": 2625.0
}

col_cat1, col_cat2 = st.columns(2)
with col_cat1: cat_orig = st.selectbox("Categoría Original", list(valores_habitaciones.keys()))
with col_cat2: cat_dest = st.selectbox("Upgrade a Categoría", list(valores_habitaciones.keys()), index=1)

st.divider()

# --- 7. MATEMÁTICA EN MEMORIA LOCAL SIN CONEXIONES EXTERNAS ---
if noches <= 0:
    st.error("La fecha de salida debe ser posterior a la de entrada.")
else:
    total_factor_estancia = 0.0
    fechas_no_encontradas = 0
    
    for n in range(noches):
        fecha_noche_texto = (check_in + timedelta(days=n)).strftime('%Y-%m-%d')
        
        if fecha_noche_texto in tarifas_por_dia_memoria:
            total_factor_estancia += tarifas_por_dia_memoria[fecha_noche_texto]
        else:
            fechas_no_encontradas += 1

    gap_fijo_base = valores_habitaciones.get(cat_dest, 0.0) - valores_habitaciones.get(cat_orig, 0.0)
    
    # Si encontramos las tarifas dinámicas en el diccionario, calculamos con factor estacional
    if fechas_no_encontradas == 0 and total_factor_estancia > 0:
        factor_promedio_estancia = total_factor_estancia / noches
        p_noche = (gap_fijo_base * factor_promedio_estancia) * (1 - desc_base/100) * 1.30
    else:
        if df_calendario_raw is not None:
            st.warning("⚠️ Nota: Algunas fechas seleccionadas no se encontraron en el calendario. Se aplicó la tarifa plana base por noche.")
        p_noche = (gap_fijo_base * (1 - desc_base/100)) * 1.30

    t_usd = p_noche * noches
    t_mxn = t_usd * tc_actual
    c_reserva = n_reserva if n_reserva.strip() else "Sin_Numero"

    # Mostrar Métricas en Pantalla
    res1, res2, res3, res4 = st.columns(4)
    res1.metric("Noches", f"{noches}")
    res2.metric("USD / Noche (Dinámico)", f"${p_noche:,.2f}")
    res3.metric("Total USD", f"${t_usd:,.2f}")
    res4.metric("Total MXN", f"${t_mxn:,.2f}")

    # --- 8. GENERACIÓN SEGURA DE PDF ---
    def generar_pdf_bytes():
        pdf = FPDF()
        pdf.add_page()
        
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(0, 10, "CASA DORADA LOS CABOS", ln=True)

        pdf.ln(30)
        pdf.set_font("Helvetica", 'B', 16)
        pdf.cell(0, 10, "ROOM UPGRADE AGREEMENT", ln=True, align='R')
        pdf.set_font("Helvetica", '', 10)
        pdf.cell(0, 5, f"Date: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align='R')
        pdf.ln(10)

        # Información del Huésped
        pdf.set_fill_color(30, 55, 110) 
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", 'B', 11)
        pdf.cell(0, 8, "   GUEST INFORMATION", ln=True, fill=True)
        
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", '', 11)
        pdf.ln(2)
        
        g_name = cliente.upper() if cliente else "VALUED GUEST"
        pdf.cell(95, 8, f"Guest: {g_name}".encode('latin-1', 'replace').decode('latin-1'))
        pdf.cell(95, 8, f"Confirmation: {c_reserva}".encode('latin-1', 'replace').decode('latin-1'), ln=True)
        pdf.cell(95, 8, f"Check-in: {check_in.strftime('%d %b, %Y')}")
        pdf.cell(95, 8, f"Check-out: {check_out.strftime('%d %b, %Y')}", ln=True)
        pdf.cell(95, 8, f"Number of Nights: {noches}", ln=True)
        pdf.ln(5)

        # Detalles del Upgrade
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", 'B', 11)
        pdf.cell(0, 8, "   ROOM UPGRADE DETAILS", ln=True, fill=True)
        
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)
        pdf.set_fill_color(240, 240, 240)
        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(60, 10, "   Original Room:", border='B', fill=True)
        pdf.set_font("Helvetica", '', 10)
        pdf.cell(130, 10, f"   {cat_orig}".encode('latin-1', 'replace').decode('latin-1'), border='B', ln=True)
        
        pdf.set_fill_color(230, 240, 255) 
        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(60, 12, "   UPGRADED TO:", border='B', fill=True)
        pdf.set_font("Helvetica", 'B', 11)
        pdf.cell(130, 12, f"   {cat_dest}".encode('latin-1', 'replace').decode('latin-1'), border='B', ln=True)
        pdf.ln(5)

        # Costos final
        pdf.set_font("Helvetica", '', 11)
        pdf.cell(120, 10, f"Upgrade Fee per Night ({noches} nights):")
        pdf.cell(70, 10, f"USD ${p_noche:,.2f}", align='R', ln=True)
        
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(120, 10, "Total Upgrade Fee (Including Taxes):", border='T')
        pdf.set_font("Helvetica", 'B', 14)
        pdf.cell(70, 10, f"USD ${t_usd:,.2f}", border='T', align='R', ln=True)
        
        pdf.set_font("Helvetica", 'I', 10)
        pdf.cell(120, 8, f"Exchange Rate / Tipo de Cambio (1 USD = {tc_actual} MXN):")
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(70, 8, f"MXN ${t_mxn:,.2f}", align='R', ln=True)
        
        pdf.ln(15)
        pdf.set_font("Helvetica", 'I', 9)
        
        terminos_texto = (
            "Terms: This upgrade is non-refundable and applies for the entire stay. "
            "In the event of an early departure, no refund will be issued for the upsell.\n"
            "Este upgrade no es reembolsable y aplica por la estancia completa. "
            "En caso de salida anticipada, no aplicara ningun reembolso por el upsell."
        )
        pdf.multi_cell(0, 5, terminos_texto.encode('latin-1', 'replace').decode('latin-1'))
        
        pdf.ln(25)
        pdf.line(10, pdf.get_y(), 85, pdf.get_y())
        pdf.line(125, pdf.get_y(), 200, pdf.get_y())
        pdf.set_font("Helvetica", '', 10)
        pdf.cell(75, 10, "Guest Signature", align='C')
        pdf.set_x(125)
        pdf.cell(75, 10, "Front Office Representative", align='C')

        return bytes(pdf.output())

    st.download_button(
        label="📥 Descargar PDF de Upgrade", 
        data=generar_pdf_bytes(), 
        file_name=f"Upsell_{c_reserva}.pdf", 
        mime="application/pdf"
    )
