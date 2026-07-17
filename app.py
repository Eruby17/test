import streamlit as st
from fpdf import FPDF
from datetime import datetime, timedelta
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import traceback

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Cotizador de upsells - Casa Dorada", page_icon="🏨", layout="wide")

# --- 2. BASE DE DATOS LOCAL Y CONEXIÓN GOOGLE DRIVE ---
PASSWORD_ADMIN = "Revenue2026"
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

CATEGORIAS = [
    "Standard Two Double Beds", 
    "Junior Suite", 
    "Deluxe Suite", 
    "Executive Suite",
    "One Bedroom Suite", 
    "One Bedroom Plus", 
    "One Bedroom Ocean Front", 
    "Two Bedroom Suite", 
    "Two Bedroom Ocean Front",
    "One Bedroom Penthouse", 
    "Two Bedroom Penthouse", 
    "Three Bedroom Penthouse"
]

PROPORCIONES = {
    "Standard Two Double Beds": 0.0,
    "Junior Suite": 1.0,
    "Deluxe Suite": 0.0,
    "Executive Suite": 2.0,
    "One Bedroom Suite": 4.0,
    "One Bedroom Plus": 5.0,
    "One Bedroom Ocean Front": 6.3333,
    "Two Bedroom Suite": 10.40,
    "Two Bedroom Ocean Front": 13.0667,
    "One Bedroom Penthouse": 15.0,
    "Two Bedroom Penthouse": 25.0,
    "Three Bedroom Penthouse": 35.0
}

# Inicializar conexión con Google Sheets
@st.cache_resource(show_spinner=False)
def obtener_cliente_gspread():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_info = st.secrets["gcp_service_account"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    return gspread.authorize(credentials)

def limpiar_valor_moneda(val):
    """Limpia formatos de texto como $150,00 o $100.0 a floats de Python"""
    if pd.isna(val) or val == "":
        return 0.0
    val_str = str(val).strip().replace('$', '').replace(' ', '')
    if ',' in val_str and '.' not in val_str:
        val_str = val_str.replace(',', '.')
    elif ',' in val_str and '.' in val_str:
        val_str = val_str.replace(',', '')
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def cargar_datos_desde_drive():
    try:
        gc = obtener_cliente_gspread()
        url_doc = st.secrets["connections"]["gsheets"]["spreadsheet"]
        doc = gc.open_by_url(url_doc)
        
        # 1. Leer pestaña 'config'
        ws_config = doc.worksheet("config")
        datos_config = ws_config.get_all_records()
        df_c = pd.DataFrame(datos_config)
        
        # 2. Leer pestaña 'diferenciales'
        ws_dif = doc.worksheet("diferenciales")
        datos_dif = ws_dif.get_all_records()
        df_d = pd.DataFrame(datos_dif)
        
        # Normalizar la columna 'mes' a tipo título (Enero, Febrero...)
        if 'mes' in df_d.columns:
            df_d['mes'] = df_d['mes'].astype(str).str.strip().str.capitalize()
            df_d.set_index("mes", inplace=True)
            
            # Limpiar el formato de moneda de la matriz
            for col in df_d.columns:
                df_d[col] = df_d[col].apply(limpiar_valor_moneda)
        
        return df_c, df_d, doc
    except Exception as e:
        # Se muestra el diagnóstico detallado en la barra lateral
        st.sidebar.error("❌ Error de conexión con Google Drive")
        st.sidebar.markdown(f"**Tipo de error:** `{type(e).__name__}`")
        st.sidebar.markdown(f"**Detalle:** {str(e)}")
        with st.sidebar.expander("Ver Traza Completa (Traceback)"):
            st.code(traceback.format_exc(), language="python")
        return None, None, None

df_config_raw, df_diferenciales_raw, doc_sheets = cargar_datos_desde_drive()

# Inicializar memoria interna con datos de la nube
if df_diferenciales_raw is not None and 'matriz_diferenciales' not in st.session_state:
    st.session_state['matriz_diferenciales'] = df_diferenciales_raw

if df_config_raw is not None and 'config_global' not in st.session_state:
    config_dict = {}
    for _, fila in df_config_raw.iterrows():
        param = str(fila['parametro']).strip().lower()
        val = limpiar_valor_moneda(fila['valor'])
        config_dict[param] = val
    st.session_state['config_global'] = {
        "descuento": config_dict.get("descuento", 60.0),
        "tc": config_dict.get("tc", 17.40)
    }

# Respaldos de emergencia en caso de fallar Google Sheets
if 'matriz_diferenciales' not in st.session_state:
    base_data = {}
    for cat in CATEGORIAS:
        factor = PROPORCIONES.get(cat, 0.0)
        base_data[cat] = [float(round(75.0 * factor, 2)) for _ in range(12)]
    st.session_state['matriz_diferenciales'] = pd.DataFrame(base_data, index=MESES)

if 'config_global' not in st.session_state:
    st.session_state['config_global'] = {"descuento": 60.0, "tc": 17.40}

# --- 3. MENÚ LATERAL: PANEL DE CONTROL DE REVENUE ---
with st.sidebar:
    st.header("🔑 Administración")
    modo_admin = st.checkbox("Entrar como Revenue Manager")
    
    if modo_admin:
        clave = st.text_input("Contraseña", type="password")
        if clave == PASSWORD_ADMIN:
            st.success("Acceso Autorizado")
            st.subheader("Configuración Global")
            
            desc_input = st.number_input("Descuento Base (%)", min_value=0.0, max_value=100.0, value=st.session_state['config_global']['descuento'], step=1.0)
            tc_input = st.number_input("Tipo de Cambio Oficial", min_value=1.0, value=st.session_state['config_global']['tc'], step=0.1)
            
            st.session_state['config_global']['descuento'] = desc_input
            st.session_state['config_global']['tc'] = tc_input
            
            st.divider()
            st.subheader("Editar Tarifas ($ USD)")
            st.info("💡 Modifica la **Junior Suite** de cualquier mes para recalcular proporcionalmente las demás.")
            
            matriz_actual = st.session_state['matriz_diferenciales'].copy()
            df_editado = st.data_editor(matriz_actual, use_container_width=True)
            
            # Recálculo automático proporcional
            for mes in MESES:
                valor_junior_actual = st.session_state['matriz_diferenciales'].loc[mes, "Junior Suite"]
                valor_junior_nuevo = df_editado.loc[mes, "Junior Suite"]
                
                if valor_junior_actual != valor_junior_nuevo:
                    for cat in CATEGORIAS:
                        factor = PROPORCIONES.get(cat, 0.0)
                        df_editado.loc[mes, cat] = float(round(valor_junior_nuevo * factor, 2))
            
            st.session_state['matriz_diferenciales'] = df_editado
            
            if st.button("💾 Guardar y Sincronizar en Drive"):
                if doc_sheets is not None:
                    try:
                        with st.spinner("Sincronizando con Google Drive..."):
                            # 1. Guardar pestaña 'config'
                            ws_config = doc_sheets.worksheet("config")
                            ws_config.clear()
                            ws_config.append_row(["parametro", "valor"])
                            ws_config.append_row(["descuento", str(st.session_state['config_global']['descuento']).replace('.', ',')])
                            ws_config.append_row(["tc", str(st.session_state['config_global']['tc']).replace('.', ',')])
                            
                            # 2. Guardar pestaña 'diferenciales'
                            ws_dif = doc_sheets.worksheet("diferenciales")
                            ws_dif.clear()
                            
                            df_subida = st.session_state['matriz_diferenciales'].reset_index()
                            df_subida.rename(columns={"index": "mes"}, inplace=True)
                            
                            ws_dif.update([df_subida.columns.values.tolist()] + df_subida.values.tolist())
                            
                            st.success("¡Datos guardados con éxito!")
                            st.toast("Base de datos actualizada en la nube", icon="☁️")
                    except Exception as err:
                        st.error(f"Error al escribir en Google Drive: {str(err)}")
                else:
                    st.error("Sin conexión de escritura con Google Drive. Revisa los errores del diagnóstico.")
        elif clave != "":
            st.error("Contraseña Incorrecta")
    else:
        st.metric("Descuento Operativo", f"{st.session_state['config_global']['descuento']}%")
        st.metric("Tipo de Cambio", f"${st.session_state['config_global']['tc']:.2f} MXN")

# --- 4. INTERFAZ PRINCIPAL PARA RECEPCIÓN ---
st.title("🏨 Cotizador de Upsells - Casa Dorada")

col_nom, col_fol = st.columns(2)
with col_nom: cliente = st.text_input("Nombre del Huésped", value="")
with col_fol: n_reserva = st.text_input("Número de Confirmación", value="")

col_in, col_out = st.columns(2)
with col_in: check_in = st.date_input("Check-in", datetime.now().date())
with col_out: check_out = st.date_input("Check-out", datetime.now().date() + timedelta(days=1))

noches = (check_out - check_in).days if check_out and check_in else 1

col_cat1, col_cat2 = st.columns(2)
with col_cat1: cat_orig = st.selectbox("Categoría Original", CATEGORIAS, index=0)
with col_cat2: cat_dest = st.selectbox("Upgrade a Categoría", CATEGORIAS, index=1)

st.divider()

ejecutar_calculo = st.button("🧮 Calcular", type="primary")

# --- 5. LÓGICA DE CÁLCULO ---
if noches <= 0:
    st.error("La fecha de salida debe ser posterior a la de entrada.")
else:
    if ejecutar_calculo or 'p_noche_estacional' in st.session_state:
        total_diferenciales = 0.0
        
        for n in range(noches):
            fecha_noche = check_in + timedelta(days=n)
            mes_indice = fecha_noche.month - 1
            nombre_mes = MESES[mes_indice]
            
            matriz = st.session_state['matriz_diferenciales']
            tarifa_orig_mes = matriz.loc[nombre_mes, cat_orig]
            tarifa_dest_mes = matriz.loc[nombre_mes, cat_dest]
            
            diferencial_noche = float(tarifa_dest_mes) - float(tarifa_orig_mes)
            total_diferenciales += max(diferencial_noche, 0.0)

        gap_promedio_estacional = total_diferenciales / noches
        
        desc_actual = st.session_state['config_global']['descuento']
        tc_actual = st.session_state['config_global']['tc']
        
        p_noche = gap_promedio_estacional * (1 - desc_actual / 100)
        st.session_state['p_noche_estacional'] = p_noche
        
        t_usd = p_noche * noches
        t_mxn = t_usd * tc_actual
        c_reserva = n_reserva if n_reserva.strip() else "Sin_Numero"

        res1, res2, res3, res4 = st.columns(4)
        res1.metric("Noches", f"{noches}")
        res2.metric("USD / Noche", f"${p_noche:,.2f}")
        res3.metric("Total USD", f"${t_usd:,.2f}")
        res4.metric("Total MXN", f"${t_mxn:,.2f}")

        st.divider()

        # --- 6. GENERACIÓN DE PDF ---
        def generar_pdf_bytes():
            pdf = FPDF()
            pdf.add_page()
            
            pdf.set_font("Helvetica", 'B', 12)
            pdf.cell(0, 10, "CASA DORADA LOS CABOS", new_x="LMARGIN", new_y="NEXT")

            pdf.ln(25)
            pdf.set_font("Helvetica", 'B', 16)
            pdf.cell(0, 10, "ROOM UPGRADE AGREEMENT", align='R', new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", '', 10)
            pdf.cell(0, 5, f"Date: {datetime.now().strftime('%d/%m/%Y')}", align='R', new_x="LMARGIN", new_y="NEXT")
            pdf.ln(10)

            # Información del Huésped
            pdf.set_fill_color(30, 55, 110) 
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", 'B', 11)
            pdf.cell(0, 8, "   GUEST INFORMATION", fill=True, new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", '', 11)
            pdf.ln(2)
            
            g_name = cliente.upper() if cliente else "VALUED GUEST"
            pdf.cell(95, 8, f"Guest: {g_name}".encode('latin-1', 'replace').decode('latin-1'))
            pdf.cell(95, 8, f"Confirmation: {c_reserva}".encode('latin-1', 'replace').decode('latin-1'), new_x="LMARGIN", new_y="NEXT")
            pdf.cell(95, 8, f"Check-in: {check_in.strftime('%d %b, %Y')}")
            pdf.cell(95, 8, f"Check-out: {check_out.strftime('%d %b, %Y')}", new_x="LMARGIN", new_y="NEXT")
            pdf.cell(95, 8, f"Number of Nights: {noches}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(5)

            # Detalles del Upgrade
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", 'B', 11)
            pdf.cell(0, 8, "   ROOM UPGRADE DETAILS", fill=True, new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_text_color(0, 0, 0)
            pdf.ln(2)
            pdf.set_fill_color(240, 240, 240)
            pdf.set_font("Helvetica", 'B', 10)
            pdf.cell(60, 10, "   Original Room:", border='B', fill=True)
            pdf.set_font("Helvetica", '', 10)
            pdf.cell(130, 10, f"   {cat_orig}".encode('latin-1', 'replace').decode('latin-1'), border='B', new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_fill_color(230, 240, 255) 
            pdf.set_font("Helvetica", 'B', 10)
            pdf.cell(60, 12, "   UPGRADED TO:", border='B', fill=True)
            pdf.set_font("Helvetica", 'B', 11)
            pdf.cell(130, 12, f"   {cat_dest}".encode('latin-1', 'replace').decode('latin-1'), border='B', new_x="LMARGIN", new_y="NEXT")
            pdf.ln(5)

            # Costos final
            pdf.set_font("Helvetica", '', 11)
            pdf.cell(120, 10, f"Upgrade Fee per Night ({noches} nights):")
            pdf.cell(70, 10, f"USD ${p_noche:,.2f}", align='R', new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_font("Helvetica", 'B', 12)
            pdf.cell(120, 10, "Total Upgrade Fee (Including Taxes):", border='T')
            pdf.set_font("Helvetica", 'B', 14)
            pdf.cell(70, 10, f"USD ${t_usd:,.2f}", border='T', align='R', new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_font("Helvetica", 'I', 10)
            pdf.cell(120, 8, f"Exchange Rate / Tipo de Cambio (1 USD = {tc_actual} MXN):")
            pdf.set_font("Helvetica", 'B', 12)
            pdf.cell(70, 8, f"MXN ${t_mxn:,.2f}", align='R', new_x="LMARGIN", new_y="NEXT")
            
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

        # Botón de descarga
        st.download_button(
            label="📥 Descargar PDF", 
            data=generar_pdf_bytes(), 
            file_name=f"Upgrade_{c_reserva}.pdf", 
            mime="application/pdf"
        )
