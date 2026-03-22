import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Velas Candela - Sistema Integral", layout="wide")

# --- CONEXIÓN Y MIGRACIÓN DE DB ---
def conectar():
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()
    # Tabla de productos con todas las columnas originales
    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT, 
        unidad TEXT, stock_actual REAL DEFAULT 0, stock_minimo REAL DEFAULT 0,
        costo_u REAL DEFAULT 0, precio_v REAL DEFAULT 0, precio_v2 REAL DEFAULT 0,
        margen1 REAL DEFAULT 100, margen2 REAL DEFAULT 100)''')
    
    # Tablas de historial
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, item_nombre TEXT, 
        cantidad REAL, costo_total REAL, metodo_pago TEXT)''')
    
    # Migración de columnas por si la DB es vieja
    columnas = [("precio_v2", "REAL DEFAULT 0"), ("margen1", "REAL DEFAULT 100"), ("margen2", "REAL DEFAULT 100")]
    for col, tipo in columnas:
        try: cursor.execute(f"ALTER TABLE productos ADD COLUMN {col} {tipo}")
        except: pass
    
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.title("🕯️ Gestión de Velas Candela - Pro")

menu = st.sidebar.selectbox("MENÚ PRINCIPAL", [
    "📦 Stock e Insumos", 
    "💰 Calculadora de Costos", 
    "🚀 Registrar Venta", 
    "🛒 Registrar Gasto/Compra",
    "📊 Reportes y Caja"
])

# ---------------------------------------------------------
# 1. STOCK E INSUMOS (Equivalente a Pestaña Stock)
# ---------------------------------------------------------
if menu == "📦 Stock e Insumos":
    st.subheader("Gestión de Inventario")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.write("### Alta / Edición")
        with st.form("form_prod"):
            nombre = st.text_input("Nombre del Artículo")
            tipo = st.selectbox("Tipo", ["Insumo", "Vela Terminada", "Packaging"])
            unidad = st.selectbox("Unidad", ["Gr", "Unidad", "Ml", "Kg"])
            stock = st.number_input("Stock Actual", min_value=0.0)
            costo = st.number_input("Costo Unitario $", min_value=0.0)
            if st.form_submit_button("Guardar Producto"):
                conn = conectar()
                conn.execute("INSERT INTO productos (nombre, tipo, unidad, stock_actual, costo_u) VALUES (?,?,?,?,?)",
                            (nombre, tipo, unidad, stock, costo))
                conn.commit()
                st.success("Guardado correctamente")
                st.rerun()

    with col2:
        conn = conectar()
        df = pd.read_sql_query("SELECT id, nombre, tipo, stock_actual, unidad, costo_u FROM productos", conn)
        st.dataframe(df, use_container_width=True)
        
        # Eliminar registro
        del_id = st.number_input("ID a eliminar", min_value=1, step=1)
        if st.button("🗑️ Eliminar Seleccionado"):
            conn.execute("DELETE FROM productos WHERE id=?", (del_id,))
            conn.commit()
            st.rerun()

# ---------------------------------------------------------
# 2. CALCULADORA DE COSTOS (Lógica de márgenes M1 y M2)
# ---------------------------------------------------------
elif menu == "💰 Calculadora de Costos":
    st.subheader("Calculadora de Producción y Precios")
    conn = conectar()
    insumos = pd.read_sql_query("SELECT nombre, costo_u, unidad FROM productos WHERE tipo='Insumo'", conn)
    
    if not insumos.empty:
        # Replicamos la tabla dinámica del código original
        num_filas = st.slider("Cantidad de componentes", 1, 10, 3)
        costo_receta = 0.0
        
        for i in range(num_filas):
            c1, c2, c3 = st.columns([2, 1, 1])
            ins = c1.selectbox(f"Componente {i+1}", ["Seleccionar..."] + insumos['nombre'].tolist(), key=f"c_{i}")
            cant = c2.number_input(f"Cantidad", min_value=0.0, key=f"q_{i}")
            if ins != "Seleccionar...":
                precio_u = insumos[insumos['nombre'] == ins]['costo_u'].values[0]
                subtotal = precio_u * cant
                costo_receta += subtotal
                c3.write(f"Sub: ${subtotal:,.2f}")
        
        st.divider()
        col_res, col_m1, col_m2 = st.columns(3)
        
        m1 = col_m1.number_input("Margen Minorista % (M1)", value=100)
        m2 = col_m2.number_input("Margen Mayorista % (M2)", value=70)
        
        precio1 = costo_receta * (1 + m1/100)
        precio2 = costo_receta * (1 + m2/100)
        
        col_res.metric("COSTO TOTAL", f"$ {costo_receta:,.2f}")
        col_m1.metric("PRECIO M1 (Minorista)", f"$ {precio1:,.2f}")
        col_m2.metric("PRECIO M2 (Mayorista)", f"$ {precio2:,.2f}")
    else:
        st.warning("Cargue insumos en el Stock para usar la calculadora.")

# ---------------------------------------------------------
# 3. REGISTRAR VENTA (Descuento de Stock)
# ---------------------------------------------------------
elif menu == "🚀 Registrar Venta":
    st.subheader("Venta de Productos")
    conn = conectar()
    velas = pd.read_sql_query("SELECT nombre, stock_actual, costo_u FROM productos WHERE tipo='Vela Terminada'", conn)
    
    with st.form("venta"):
        prod = st.selectbox("Seleccionar Vela", velas['nombre'].tolist())
        cant = st.number_input("Cantidad", min_value=1.0)
        pago = st.selectbox("Cuenta/Método", ["Efectivo", "Transferencia", "Mercado Pago"])
        monto = st.number_input("Monto total cobrado $", min_value=0.0)
        
        if st.form_submit_button("Finalizar Venta"):
            c = conn.cursor()
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
            c.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (?,?,?,?,?)",
                     (fecha, prod, cant, monto, pago))
            c.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (cant, prod))
            conn.commit()
            st.success("Venta registrada y stock actualizado.")

# ---------------------------------------------------------
# 4. REGISTRAR GASTO (Nueva funcionalidad integrada)
# ---------------------------------------------------------
elif menu == "🛒 Registrar Gasto/Compra":
    st.subheader("Registro de Egresos / Compras de Insumos")
    with st.form("gasto"):
        item = st.text_input("Detalle del gasto o Insumo comprado")
        cant = st.number_input("Cantidad", min_value=0.0)
        costo = st.number_input("Costo Total $", min_value=0.0)
        pago = st.selectbox("Pagado desde", ["Efectivo", "Transferencia", "Mercado Pago"])
        
        if st.form_submit_button("Registrar Gasto"):
            conn = conectar()
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute("INSERT INTO historial_compras (fecha, item_nombre, cantidad, costo_total, metodo_pago) VALUES (?,?,?,?,?)",
                        (fecha, item, cant, costo, pago))
            conn.commit()
            st.success("Gasto/Compra registrado en caja.")

# ---------------------------------------------------------
# 5. REPORTES Y CAJA (Exportación a Excel)
# ---------------------------------------------------------
elif menu == "📊 Reportes y Caja":
    st.subheader("Análisis de Caja e Historial")
    conn = conectar()
    
    # Unificamos ventas y compras para la caja
    df_v = pd.read_sql_query("SELECT fecha, 'VENTA' as Tipo, producto as Detalle, total_venta as Monto, metodo_pago as Cuenta FROM historial_ventas", conn)
    df_c = pd.read_sql_query("SELECT fecha, 'MOV/COMP' as Tipo, item_nombre as Detalle, costo_total as Monto, metodo_pago as Cuenta FROM historial_compras", conn)
    
    caja_total = pd.concat([df_v, df_c]).sort_values(by="fecha", ascending=False)
    
    col_m1, col_m2, col_m3 = st.columns(3)
    ingresos = df_v['Monto'].sum()
    egresos = df_c['Monto'].sum()
    col_m1.metric("Ingresos Totales", f"$ {ingresos:,.2f}")
    col_m2.metric("Egresos Totales", f"$ {egresos:,.2f}")
    col_m3.metric("Saldo Caja", f"$ {(ingresos - egresos):,.2f}", delta=float(ingresos-egresos))
    
    st.write("### Últimos Movimientos")
    st.dataframe(caja_total, use_container_width=True)

    # Gráfico de ventas
    if not df_v.empty:
        fig = px.pie(df_v, values='Monto', names='Detalle', title="Distribución de Ventas por Producto")
        st.plotly_chart(fig, use_container_width=True)

    # Botón de exportación a Excel
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        caja_total.to_excel(writer, index=False, sheet_name='Caja')
    
    st.download_button(
        label="📥 Descargar Caja en Excel",
        data=buffer,
        file_name=f"caja_velas_{datetime.now().strftime('%d_%m')}.xlsx",
        mime="application/vnd.ms-excel"
    )
