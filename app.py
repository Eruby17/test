import streamlit as st
from fpdf import FPDF
from datetime import datetime, timedelta
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

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

@st.cache_resource(show_spinner=False)
def obtener_cliente_gspread():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_info = st.secrets["gcp_service_account"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    return gspread.authorize(credentials)

def limpiar_valor_moneda(val):
    if pd.isna(val) or val == "":
        return 0.0
    val_str = str(val).strip().replace('$', '').replace(' ', '')
    if ',' in val_str and '.' in val_str:
        val_str = val_str.replace(',', '')
    elif ',' in val_str:
        val_str = val_str.replace(',', '.')
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def cargar_datos_desde_drive():
    try:
        gc = obtener_cliente_gspread()
        url_doc = st.secrets["connections"]["gsheets"]["spreadsheet"]
        doc = gc.open_by_url(url_doc)
        
        ws_config = doc.worksheet("config")
        datos_config = ws_config.get_all_records()
        df_c = pd.DataFrame(datos_config)
        
        ws_dif = doc.worksheet("diferenciales")
        datos_dif = ws_dif.get_all_records()
        df_d = pd.DataFrame(datos_dif)
        
        if 'mes' in df_d.columns:
            df_d['mes'] = df_d['mes'].astype(str).str.strip().str.capitalize()
            df_d.set_index("mes", inplace=True)
            for col in df_d.columns:
                df_d[col] = df_d[col].apply(limpiar_valor_moneda)
        
        return df_c, df_d, doc
    except Exception as e:
        st.sidebar.warning(f"⚠️ Error al sincronizar: {str(e)}")
        return None, None, None

df_config_raw, df_diferenciales_raw, doc_sheets = cargar_datos_desde_drive()

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
        "tc": config_dict.get("tc", 17.40),
        "inicio_high_dec": int(config_dict.get("inicio_high_dec", 15)),
        "fin_high_ene": int(config_dict.get("fin_high_ene", 4)),
        "junior_suite_high": config_dict.get("junior_suite_high", 200.0)
    }

# Respaldos internos
if 'matriz_diferenciales' not in st.session_state:
    base_data = {}
    for cat in CATEGORIAS:
        factor = PROPORCIONES.get(cat, 0.0)
        base_data[cat] = [float(round(75.0 * factor, 2)) for _ in range(12)]
    st.session_state['matriz_diferenciales'] = pd.DataFrame(base_data, index=MESES)

if 'config_global' not in st.session_state:
    st.session_state['config_global'] = {
        "descuento": 60.0, "tc": 17.40, 
        "inicio_high_dec": 15, "fin_high_ene": 4, "junior_suite_high": 200.0
    }

# --- 3. MENÚ LATERAL: PANEL DE CONTROL DE REVENUE ---
with st.sidebar:
    st.header("🔑 Administración")
    modo_admin = st.checkbox("Entrar como Revenue Manager")
    
    if modo_admin:
        clave = st.text_input("Contraseña", type="password")
        if clave == PASSWORD_ADMIN:
            st.success("Acceso Autorizado")
            
            with st.form("formulario_revenue"):
                st.subheader("Configuración Global")
                desc_input = st.number_input("Descuento Base (%)", min_value=0.0, value=float(st.session_state['config_global']['descuento']), step=1.0)
                tc_input = st.number_input("Tipo de Cambio Oficial", min_value=1.0, value=float(st.session_state['config_global']['tc']), step=0.1)
                
                st.divider()
                st.subheader("Reglas de Temporada Alta 🎄")
                dec_start = st.number_input("Inicio Dic (Día)", min_value=1, value=int(st.session_state['config_global']['inicio_high_dec']))
                ene_end = st.number_input("Fin Ene (Día)", min_value=1, value=int(st.session_state['config_global']['fin_high_ene']))
                jr_high_val = st.number_input("Jr Suite Premium ($)", min_value=0.0, value=float(st.session_state['config_global']['junior_suite_high']))
                
                st.divider()
                st.subheader("Editar Tarifas Estándar ($ USD)")
                st.info("💡 Edita sin prisas. Las celdas ya no parpadearán.")
                
                matriz_actual = st.session_state['matriz_diferenciales'].copy()
                df_editado = st.data_editor(matriz_actual, use_container_width=True)
                
                boton_guardar = st.form_submit_button("💾 Guardar y Sincronizar Cambios", type="primary")
                
            if boton_guardar:
                for mes in MESES:
                    valor_junior_actual = st.session_state['matriz_diferenciales'].loc[mes, "Junior Suite"]
                    valor_junior_nuevo = df_editado.loc[mes, "Junior Suite"]
                    
                    if valor_junior_actual != valor_junior_nuevo:
                        for cat in CATEGORIAS:
                            factor = PROPORCIONES.get(cat, 0.0)
                            df_editado.loc[mes, cat] = float(round(valor_junior_nuevo * factor, 2))
                
                st.session_state['matriz_diferenciales'] = df_editado
                st.session_state['config_global'] = {
                    "descuento": desc_input,
                    "tc": tc_input,
                    "inicio_high_dec": min(int(dec_start), 31),
                    "fin_high_ene": min(int(ene_end), 31),
                    "junior_suite_high": jr_high_val
                }
                
                if doc_sheets is not None:
                    try:
                        with st.spinner("Sincronizando de forma segura con Google Drive..."):
                            ws_config = doc_sheets.worksheet("config")
                            ws_config.clear()
                            ws_config.append_row(["parametro", "valor"])
                            ws_config.append_row(["descuento", float(st.session_state['config_global']['descuento'])])
                            ws_config.append_row(["tc", float(st.session_state['config_global']['tc'])])
                            ws_config.append_row(["inicio_high_dec", int(st.session_state['config_global']['inicio_high_dec'])])
                            ws_config.append_row(["fin_high_ene", int(st.session_state['config_global']['fin_high_ene'])])
                            ws_config.append_row(["junior_suite_high", float(st.session_state['config_global']['junior_suite_high'])])
                            
                            ws_dif = doc_sheets.worksheet("diferenciales")
                            ws_dif.clear()
                            df_subida = df_editado.reset_index()
                            df_subida.rename(columns={"index": "mes"}, inplace=True)
                            ws_dif.update([df_subida.columns.values.tolist()] + df_subida.values.tolist())
                            
                            st.success("¡Base de datos sincronizada con éxito!")
                            st.toast("Base de datos sincronizada", icon="☁️")
                            st.rerun()
                    except Exception as err:
                        st.error(f"Error al escribir en Google Drive: {str(err)}")
                else:
                    st.error("Sin conexión de escritura con Google Drive.")
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

# --- 5. LÓGICA DE CÁLCULO INTELIGENTE CON EXCEPCIONES ---
if noches <= 0:
    st.error("La fecha de salida debe ser posterior a la de entrada.")
else:
    if ejecutar_calculo or 'p_noche_estacional' in st.session_state:
        total_diferenciales = 0.0
        
        cfg = st.session_state['config_global']
        day_start_dec = cfg.get("inicio_high_dec", 15)
        day_end_ene = cfg.get("fin_high_ene", 4)
        jr_premium_base = cfg.get("junior_suite_high", 200.0)
        
        for n in range(noches):
            fecha_noche = check_in + timedelta(days=n)
            num_mes = fecha_noche.month
            dia_mes = fecha_noche.day
            nombre_mes = MESES[num_mes - 1]
            
            es_temporada_alta = False
            if num_mes == 12 and dia_mes >= day_start_dec:
                es_temporada_alta = True
            elif num_mes == 1 and dia_mes <= day_end_ene:
                es_temporada_alta = True
                
            if es_temporada_alta:
                factor_orig = PROPORCIONES.get(cat_orig, 0.0)
                factor_dest = PROPORCIONES.get(cat_dest, 0.0)
                tarifa_orig_mes = float(round(jr_premium_base * factor_orig, 2))
                tarifa_dest_mes = float(round(jr_premium_base * factor_dest, 2))
            else:
                matriz = st.session_state['matriz_diferenciales']
                tarifa_orig_mes = matriz.loc[nombre_mes, cat_orig]
                tarifa_dest_mes = matriz.loc[nombre_mes, cat_dest]
            
            diferencial_noche = float(tarifa_dest_mes) - float(tarifa_orig_mes)
            total_diferenciales += max(diferencial_noche, 0.0)

        gap_promedio_estacional = total_diferenciales / noches
        desc_actual = cfg['descuento']
        tc_actual = cfg['tc']
        
        p_noche_neto = gap_promedio_estacional * (1 - desc_actual / 100)
        st.session_state['p_noche_estacional'] = p_noche_neto
        
        impuesto_por_noche = p_noche_neto * 0.30
        p_noche_con_impuestos = p_noche_neto + impuesto_por_noche
        
        total_usd_con_impuestos = p_noche_con_impuestos * noches
        total_mxn_con_impuestos = total_usd_con_impuestos * tc_actual
        c_reserva = n_reserva if n_reserva.strip() else "Sin_Numero"

        res1, res2, res3, res4 = st.columns(4)
        res1.metric("Noches", f"{noches}")
        res2.metric("USD / Noche (Con Impuestos)", f"${p_noche_con_impuestos:,.2f}")
        res3.metric("Total Estancia (USD)", f"${total_usd_con_impuestos:,.2f} USD")
        res4.metric("Total Estancia (MXN)", f"${total_mxn_con_impuestos:,.2f} MXN")

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

            # Desglose en PDF
            pdf.set_font("Helvetica", '', 11)
            pdf.cell(120, 8, "Upgrade Fee per Night (Net):")
            pdf.cell(70, 8, f"USD ${p_noche_neto:,.2f}", align='R', new_x="LMARGIN", new_y="NEXT")
            
            pdf.cell(120, 8, "Taxes & Services per Night (30%):")
            pdf.cell(70, 8, f"USD ${impuesto_por_noche:,.2f}", align='R', new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_font("Helvetica", 'B', 11)
            pdf.cell(120, 8, f"Total Upgrade Fee per Night (Taxes Inc. x {noches} nights):")
            pdf.cell(70, 8, f"USD ${p_noche_con_impuestos:,.2f}", align='R', new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_font("Helvetica", 'B', 12)
            pdf.cell(120, 10, "GRAND TOTAL UPGRADE FEE:", border='T')
            pdf.set_font("Helvetica", 'B', 14)
            pdf.cell(70, 10, f"USD ${total_usd_con_impuestos:,.2f}", border='T', align='R', new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_font("Helvetica", 'I', 10)
            pdf.cell(120, 8, f"Exchange Rate / Tipo de Cambio (1 USD = {tc_actual} MXN):")
            pdf.set_font("Helvetica", 'B', 12)
            pdf.cell(70, 8, f"MXN ${total_mxn_con_impuestos:,.2f}", align='R', new_x="LMARGIN", new_y="NEXT")
            
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
            label="📥 Descargar PDF", 
            data=generar_pdf_bytes(), 
            file_name=f"Upgrade_{c_reserva}.pdf", 
            mime="application/pdf"
        )
