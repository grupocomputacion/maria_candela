import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA (ESTO REEMPLAZA A root.geometry) ---
st.set_page_config(page_title="Velas Candela - Gestión Cloud", layout="wide")

# --- CONEXIÓN DB ---
def conectar():
    # check_same_thread=False es obligatorio para Streamlit
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def init_db():
    conn = conectar()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT, 
        unidad TEXT, stock_actual REAL DEFAULT 0, stock_minimo REAL DEFAULT 0,
        costo_u REAL DEFAULT 0, precio_v REAL DEFAULT 0, precio_v2 REAL DEFAULT 0)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- INTERFAZ (MENÚ LATERAL) ---
st.sidebar.title("🕯️ Velas Candela")
menu = st.sidebar.radio("Ir a:", ["📊 Panel de Control", "📦 Inventario", "💰 Calculadora de Costos", "🚀 Registrar Venta"])

# ---------------------------------------------------------
# 1. PANEL DE CONTROL (REEMPLAZA TUS GRÁFICOS DE MATPLOTLIB)
# ---------------------------------------------------------
if menu == "📊 Panel de Control":
    st.header("Resumen del Negocio")
    conn = conectar()
    df_v = pd.read_sql_query("SELECT * FROM historial_ventas", conn)
    
    if not df_v.empty:
        col1, col2, col3 = st.columns(3)
        total_v = df_v['total_venta'].sum()
        col1.metric("Ventas Totales", f"$ {total_v:,.2f}")
        col2.metric("Cant. Ventas", len(df_v))
        
        # Gráfico interactivo (Mejor que el de Tkinter para iPad)
        fig = px.line(df_v, x='fecha', y='total_venta', title="Evolución de Ventas")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Aún no hay ventas registradas.")

# ---------------------------------------------------------
# 2. INVENTARIO (REEMPLAZA TUS TABLAS TREEVIEW)
# ---------------------------------------------------------
elif menu == "📦 Inventario":
    st.header("Gestión de Stock")
    
    with st.expander("➕ Cargar Nuevo Insumo o Vela"):
        with st.form("nuevo_prod"):
            nom = st.text_input("Nombre del artículo")
            cat = st.selectbox("Categoría", ["Insumo", "Vela Terminada", "Packaging"])
            stock = st.number_input("Stock Inicial", min_value=0.0)
            costo = st.number_input("Costo Unitario $", min_value=0.0)
            if st.form_submit_button("Guardar"):
                conn = conectar()
                conn.execute("INSERT INTO productos (nombre, tipo, stock_actual, costo_u) VALUES (?,?,?,?)",
                            (nom, cat, stock, costo))
                conn.commit()
                st.success("Registrado!")
                st.rerun()

    conn = conectar()
    df_p = pd.read_sql_query("SELECT nombre, tipo, stock_actual, costo_u FROM productos", conn)
    st.dataframe(df_p, use_container_width=True)

# ---------------------------------------------------------
# 3. CALCULADORA DE COSTOS
# ---------------------------------------------------------
elif menu == "💰 Calculadora de Costos":
    st.header("Calculadora de Producción")
    conn = conectar()
    insumos = pd.read_sql_query("SELECT nombre, costo_u FROM productos WHERE tipo='Insumo'", conn)
    
    if not insumos.empty:
        # Aquí simulamos tu calculadora de 3 filas
        costo_total = 0.0
        st.write("Seleccioná los componentes de la vela:")
        for i in range(3):
            c1, c2 = st.columns(2)
            ins_sel = c1.selectbox(f"Insumo {i+1}", ["Seleccionar..."] + insumos['nombre'].tolist(), key=f"ins_{i}")
            if ins_sel != "Seleccionar...":
                cant = c2.number_input(f"Cantidad Insumo {i+1}", min_value=0.0, key=f"cant_{i}")
                precio_u = insumos[insumos['nombre'] == ins_sel]['costo_u'].values[0]
                costo_total += (precio_u * cant)
        
        st.divider()
        st.subheader(f"Costo Final de Producción: $ {costo_total:,.2f}")
    else:
        st.warning("Primero cargá insumos en el Inventario.")

# ---------------------------------------------------------
# 4. REGISTRAR VENTA
# ---------------------------------------------------------
elif menu == "🚀 Registrar Venta":
    st.header("Nueva Venta")
    conn = conectar()
    velas = pd.read_sql_query("SELECT nombre FROM productos WHERE tipo='Vela Terminada'", conn)
    
    if not velas.empty:
        with st.form("venta"):
            v_sel = st.selectbox("Vela Vendida", velas['nombre'].tolist())
            v_cant = st.number_input("Cantidad", min_value=1.0)
            v_monto = st.number_input("Monto Cobrado $", min_value=0.0)
            v_pago = st.selectbox("Método", ["Efectivo", "Transferencia", "MP"])
            
            if st.form_submit_button("Confirmar Venta"):
                conn = conectar()
                c = conn.cursor()
                c.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (?,?,?,?,?)",
                         (datetime.now().strftime("%Y-%m-%d"), v_sel, v_cant, v_monto, v_pago))
                c.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_cant, v_sel))
                conn.commit()
                st.success("Venta guardada y stock descontado.")
    else:
        st.error("No hay velas terminadas en el inventario.")
