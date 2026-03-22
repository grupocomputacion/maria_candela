import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Velas Candela - Gestión Pro Cloud", layout="wide")

def conectar():
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()
    # Estructura fiel al original
    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT, 
        unidad TEXT, stock_actual REAL DEFAULT 0, stock_minimo REAL DEFAULT 0,
        costo_u REAL DEFAULT 0, precio_v REAL DEFAULT 0, precio_v2 REAL DEFAULT 0,
        margen1 REAL DEFAULT 100, margen2 REAL DEFAULT 100)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, item_nombre TEXT, 
        cantidad REAL, costo_total REAL, metodo_pago TEXT)''')
    
    conn.commit()
    conn.close()

inicializar_db()

st.title("🕯️ Velas Candela - Sistema Cloud")

menu = st.sidebar.selectbox("MENÚ", ["📦 Inventario", "💰 Calculadora", "🚀 Ventas", "📊 Reportes"])

# ---------------------------------------------------------
# 1. INVENTARIO (CON FILTROS CORREGIDOS A "FINAL")
# ---------------------------------------------------------
if menu == "📦 Inventario":
    st.subheader("Gestión de Stock y Precios")
    
    # FILTROS
    f1, f2, f3 = st.columns(3)
    # Corregido: "Final" en lugar de "Vela Terminada"
    f_tipo = f1.selectbox("Filtrar por Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
    f_stock = f2.selectbox("Estado de Stock", ["TODOS", "Con Stock", "Sin Stock / Crítico"])
    f_busq = f3.text_input("Buscar producto...")

    col_a, col_b = st.columns([1, 3])
    
    with col_a:
        with st.form("nuevo_p"):
            st.write("### Alta de Producto")
            nom = st.text_input("Nombre")
            tip = st.selectbox("Categoría", ["Insumo", "Final", "Packaging"])
            stk = st.number_input("Stock", value=0.0)
            cst = st.number_input("Costo Unitario", value=0.0)
            m1 = st.number_input("Margen 1 %", value=100.0)
            m2 = st.number_input("Margen 2 %", value=70.0)
            
            if st.form_submit_button("Guardar"):
                p1 = cst * (1 + m1/100)
                p2 = cst * (1 + m2/100)
                conn = conectar()
                conn.execute("""INSERT INTO productos (nombre, tipo, stock_actual, costo_u, margen1, margen2, precio_v, precio_v2) 
                             VALUES (?,?,?,?,?,?,?,?)""", (nom, tip, stk, cst, m1, m2, p1, p2))
                conn.commit()
                st.success("Guardado")
                st.rerun()

    with col_b:
        conn = conectar()
        query = "SELECT id, nombre, tipo, stock_actual, costo_u, margen1, precio_v, margen2, precio_v2 FROM productos WHERE 1=1"
        params = []
        
        if f_tipo != "TODOS":
            query += " AND tipo = ?"; params.append(f_tipo)
        if f_stock == "Con Stock":
            query += " AND stock_actual > 0"
        elif f_stock == "Sin Stock / Crítico":
            query += " AND stock_actual <= 0"
        if f_busq:
            query += " AND nombre LIKE ?"; params.append(f"%{f_busq}%")
            
        df = pd.read_sql_query(query, conn, params=params)
        st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# 2. CALCULADORA (Usa Categoría "Insumo")
# ---------------------------------------------------------
elif menu == "💰 Calculadora":
    st.subheader("Costeo de Recetas")
    conn = conectar()
    insumos = pd.read_sql_query("SELECT nombre, costo_u FROM productos WHERE tipo='Insumo'", conn)
    
    if not insumos.empty:
        n = st.number_input("Cantidad de componentes", 1, 10, 3)
        total = 0.0
        for i in range(n):
            c1, c2 = st.columns(2)
            sel = c1.selectbox(f"Componente {i+1}", ["-"] + insumos['nombre'].tolist(), key=f"i{i}")
            cant = c2.number_input(f"Cantidad {i+1}", 0.0, key=f"q{i}")
            if sel != "-":
                pu = insumos[insumos['nombre'] == sel]['costo_u'].values[0]
                total += (pu * cant)
        st.divider()
        st.metric("COSTO TOTAL", f"$ {total:,.2f}")
    else:
        st.warning("Carga 'Insumos' en el inventario para usar esta función.")

# ---------------------------------------------------------
# 3. VENTAS (Filtra por "Final")
# ---------------------------------------------------------
elif menu == "🚀 Ventas":
    st.subheader("Registrar Venta")
    conn = conectar()
    # Cambiado a "Final"
    velas = pd.read_sql_query("SELECT nombre, precio_v, precio_v2 FROM productos WHERE tipo='Final'", conn)
    
    if not velas.empty:
        with st.form("vta"):
            v_nom = st.selectbox("Vela", velas['nombre'].tolist())
            v_cant = st.number_input("Cantidad", min_value=1.0)
            v_lista = st.radio("Lista de Precio", ["Lista 1 (Minorista)", "Lista 2 (Mayorista)"])
            
            # Sugerir precio según lista
            p_sug = velas[velas['nombre'] == v_nom]['precio_v' if "1" in v_lista else 'precio_v2'].values[0]
            monto = st.number_input("Total a cobrar $", value=float(p_sug * v_cant))
            pago = st.selectbox("Método", ["Efectivo", "Transferencia", "MP"])
            
            if st.form_submit_button("Cerrar Venta"):
                c = conn.cursor()
                c.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (?,?,?,?,?)",
                         (datetime.now().strftime("%Y-%m-%d %H:%M"), v_nom, v_cant, monto, pago))
                c.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_cant, v_nom))
                conn.commit()
                st.success("Venta realizada.")
    else:
        st.error("No hay productos marcados como 'Final' en el stock.")

# ---------------------------------------------------------
# 4. REPORTES
# ---------------------------------------------------------
elif menu == "📊 Reportes":
    st.subheader("Historial y Caja")
    conn = conectar()
    df_v = pd.read_sql_query("SELECT * FROM historial_ventas", conn)
    st.dataframe(df_v, use_container_width=True)
    if not df_v.empty:
        st.metric("Total Recaudado", f"$ {df_v['total_venta'].sum():,.2f}")
