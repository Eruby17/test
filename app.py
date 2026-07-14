import streamlit as st
from fpdf import FPDF
from datetime import datetime, timedelta
import pandas as pd

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Cotizador de upsells - Casa Dorada", page_icon="🏨", layout="wide")

# --- 2. BASE DE DATOS LOCAL EN MEMORIA (ESTADO DE SESIÓN) ---
PASSWORD_ADMIN = "Revenue2026"

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

CATEGORIAS = [
    "Standard Two Double Beds", "Junior Suite", "Deluxe Suite", "Executive Suite",
    "One Bedroom Suite Garden", "One Bedroom Suite", "1 Bedroom Suite Plus",
    "1 Bedroom Ocean Front", "2 Bedroom Suite", "2 Bedroom Ocean Front",
    "Penthouse 1PH", "Penthouse 2PH", "Penthouse 3PH"
]

# Definimos las proporciones fijas en base a la Junior Suite ($75.0)
PROPORCIONES = {
    "Standard Two Double Beds": 0.0,
    "Junior Suite": 1.0,  # Habitación Base para cálculos
    "Deluxe Suite": 0.0,
    "Executive Suite": 2.0,
    "One Bedroom Suite Garden": 3.0,
    "One Bedroom Suite": 4.0,
    "1 Bedroom Suite Plus": 5.0,
    "1 Bedroom Ocean Front": 6.3333,
    "2 Bedroom Suite": 10.40,
    "2 Bedroom Ocean Front": 13.0667,  # Se mantiene su proporción histórica pero editable
    "Penthouse 1PH": 15.0,
    "Penthouse 2PH": 25.0,
    "Penthouse 3PH": 35.0
}

# Inicializamos la matriz de diferenciales mensuales
if 'matriz_diferenciales' not in st.session_state:
    # Valor inicial de partida para la Junior Suite
    valor_base_junior = 75.0
    
    base_data = {}
    for cat in CATEGORIAS:
        factor = PROPORCIONES.get(cat, 0.0)
        # Multiplicamos el valor base de Junior por la proporción correspondiente
        base_data[cat] = [float(round(valor_base_junior * factor, 2)) for _ in range(12)]
        
    df_base = pd.DataFrame(base_data, index=MESES)
    st.session_state['matriz_diferenciales'] = df_base

if 'config_global' not in st.session_state:
    st.session_state['config_global'] = {"descuento": 62.0, "tc": 17.40}

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
            st.subheader("Editar Diferenciales ($ USD)")
            st.info("💡 Consejo: Modifica el valor de la columna **Junior Suite** en cualquier mes. Las demás habitaciones (excepto si las editas a mano) se recalcularán automáticamente en cascada.")
            
            # Cargamos la matriz actual
            matriz_actual = st.session_state['matriz_diferenciales'].copy()
            
            # Interfaz interactiva para el Revenue
            df_editado = st.data_editor(matriz_actual, use_container_width=True)
            
            # Detectar cambios para propagar la proporcionalidad automáticamente
            for mes in MESES:
                valor_junior_actual = st.session_state['matriz_diferenciales'].loc[mes, "Junior Suite"]
                valor_junior_nuevo = df_editado.loc[mes, "Junior Suite"]
                
                # Si el Revenue cambió el valor base de la Junior Suite para ese mes:
                if valor_junior_actual != valor_junior_nuevo:
                    for cat in CATEGORIAS:
                        # Recalculamos todas las categorías del mes basándonos en la nueva Junior Suite
                        factor = PROPORCIONES.get(cat, 0.0)
                        df_editado.loc[mes, cat] = float(round(valor_junior_nuevo * factor, 2))
            
            st.session_state['matriz_diferenciales'] = df_editado
            
            if st.button("💾 Guardar y Aplicar Cambios"):
                st.toast("Estructura de tarifas proporcionales actualizada", icon="✅")
        elif clave != "":
            st.error("Contraseña Incorrecta")
    else:
        st.metric("Descuento Operativo", f"{st.session_state['config_global']['descuento']}%")
        st.metric("Tipo de Cambio", f"${st.session_state['config_global']['tc']:.2f} MXN")

# --- 4. INTERFAZ PRINCIPAL PARA RECEPCIÓN ---
st.title("🏨 Cotizador de Upsells Estacionales")
st.subheader("Módulo Operativo de Recepción")

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

ejecutar_calculo = st.button("🧮 Calcular Cotización Justa", type="primary")

# --- 5. LÓGICA DE CÁLCULO ESTACIONAL MENSUAL ---
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
        res1.metric("Noches de Estancia", f"{noches}")
        res2.metric("Tarifa Upgrade / Noche", f"${p_noche:,.2f} USD")
        res3.metric("Total USD (Neto)", f"${t_usd:,.2f} USD")
        res4.metric("Total MXN", f"${t_mxn:,.2f} MXN")

        st.divider()

        # --- 6. GENERACIÓN DE PDF SEGURO ---
        def generar_pdf_bytes():
            pdf = FPDF()
            pdf.add_page()
            
            pdf.set_font("Helvetica", 'B', 12)
            pdf.cell(0, 10, "CASA DORADA LOS CABOS", ln=True)

            pdf.ln(25)
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
            label="📥 Descargar Contrato de Upgrade PDF", 
            data=generar_pdf_bytes(), 
            file_name=f"Upgrade_{c_reserva}.pdf", 
            mime="application/pdf"
        )
