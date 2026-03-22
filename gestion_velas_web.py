import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Velas Candela - Gestión Pro Cloud", layout="wide")

# --- CONEXIÓN Y MANTENIMIENTO DE DB ---
def conectar():
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()
    # Estructura completa original
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
    
    # Parche de migración de columnas
    columnas_extra = [("precio_v2", "REAL DEFAULT 0"), ("margen1", "REAL DEFAULT 100"), ("margen2", "REAL DEFAULT 100")]
    for col, tipo in columnas_extra:
        try: cursor.execute(f"ALTER TABLE productos ADD COLUMN {col} {tipo}")
        except: pass
    
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.title("🕯️ Velas Candela - Sistema Integral")

menu = st.sidebar.selectbox("MENÚ PRINCIPAL", [
    "📦 Inventario y Precios", 
    "💰 Calculadora de Costos", 
    "🚀 Registrar Venta", 
    "🛒 Compras y Gastos",
    "📊 Reportes y Caja"
])

# ---------------------------------------------------------
# 1. INVENTARIO Y PRECIOS (CON FILTROS SOLICITADOS)
# ---------------------------------------------------------
if menu == "📦 Inventario y Precios":
    st.subheader("Gestión de Stock y Listas de Precios")
    
    # FILTROS SUPERIORES [NUEVO]
    st.write("### 🔍 Filtros de Búsqueda")
    f1, f2, f3 = st.columns(3)
    filtro_tipo = f1.selectbox("Tipo de Producto", ["TODOS", "Insumo", "Vela Terminada", "Packaging"])
    filtro_stock = f2.selectbox("Disponibilidad", ["TODOS", "Con Stock (>0)", "Sin Stock / Crítico (<=0)"])
    busqueda_nombre = f3.text_input("Buscar por Nombre")

    st.divider()

    col_form, col_tabla = st.columns([1, 3])
    
    with col_form:
        st.write("### Alta / Edición")
        with st.form("form_producto"):
            nombre = st.text_input("Nombre del Artículo")
            tipo_p = st.selectbox("Categoría", ["Insumo", "Vela Terminada", "Packaging"])
            uni = st.selectbox("Unidad", ["Gr", "Unidad", "Ml", "Kg"])
            stk = st.number_input("Stock Actual", min_value=-1000.0, value=0.0)
            cst = st.number_input("Costo Unitario $", min_value=0.0)
            m1 = st.number_input("Margen Lista 1 %", value=100.0)
            m2 = st.number_input("Margen Lista 2 %", value=70.0)
            
            p1 = cst * (1 + m1/100)
            p2 = cst * (1 + m2/100)
            
            if st.form_submit_button("Guardar Producto"):
                conn = conectar()
                conn.execute("""INSERT INTO productos 
                             (nombre, tipo, unidad, stock_actual, costo_u, margen1, margen2, precio_v, precio_v2) 
                             VALUES (?,?,?,?,?,?,?,?,?)""", 
                             (nombre, tipo_p, uni, stk, cst, m1, m2, p1, p2))
                conn.commit()
                st.success("Producto registrado")
                st.rerun()

    with col_tabla:
        conn = conectar()
        # Construcción dinámica de la consulta SQL con filtros
        query = "SELECT id, nombre, tipo, stock_actual as Stock, costo_u as 'Costo $', margen1 as 'M1 %', precio_v as 'Lista 1 $', margen2 as 'M2 %', precio_v2 as 'Lista 2 $' FROM productos WHERE 1=1"
        params = []

        if filtro_tipo != "TODOS":
            query += " AND tipo = ?"
            params.append(filtro_tipo)
        
        if filtro_stock == "Con Stock (>0)":
            query += " AND stock_actual > 0"
        elif filtro_stock == "Sin Stock / Crítico (<=0)":
            query += " AND stock_actual <= 0"
            
        if busqueda_nombre:
            query += " AND nombre LIKE ?"
            params.append(f"%{busqueda_nombre}%")

        df_p = pd.read_sql_query(query, conn, params=params)
        
        # Resaltado visual para Mac/iPad
        st.dataframe(df_p, use_container_width=True, hide_index=True)
        
        st.write("---")
        del_id = st.number_input("ID a eliminar", min_value=1, step=1)
        if st.button("🗑️ Eliminar Producto"):
            conn.execute("DELETE FROM productos WHERE id=?", (del_id,))
            conn.commit()
            st.rerun()

# ---------------------------------------------------------
# 2. CALCULADORA DE COSTOS
# ---------------------------------------------------------
elif menu == "💰 Calculadora de Costos":
    st.subheader("Calculadora Dinámica de Producción")
    conn = conectar()
    insumos = pd.read_sql_query("SELECT nombre, costo_u FROM productos WHERE tipo='Insumo'", conn)
    
    if not insumos.empty:
        n_filas = st.slider("¿Cuántos componentes lleva la receta?", 1, 10, 3)
        costo_total = 0.0
        
        for i in range(n_filas):
            c1, c2, c3 = st.columns([2, 1, 1])
            sel = c1.selectbox(f"Componente {i+1}", ["-"] + insumos['nombre'].tolist(), key=f"sel_{i}")
            cant = c2.number_input("Cantidad", min_value=0.0, key=f"q_{i}", format="%.2f")
            if sel != "-":
                precio_u = insumos[insumos['nombre'] == sel]['costo_u'].values[0]
                sub = precio_u * cant
                costo_total += sub
                c3.write(f"Sub: ${sub:,.2f}")
        
        st.divider()
        st.metric("COSTO TOTAL DE PRODUCCIÓN", f"$ {costo_total:,.2f}")
    else:
        st.warning("Debe cargar Insumos en el Inventario primero.")

# ---------------------------------------------------------
# 3. REGISTRAR VENTA
# ---------------------------------------------------------
elif menu == "🚀 Registrar Venta":
    st.subheader("Venta Directa")
    conn = conectar()
    velas = pd.read_sql_query("SELECT nombre, stock_actual FROM productos WHERE tipo='Vela Terminada'", conn)
    
    with st.form("form_venta"):
        v_sel = st.selectbox("Producto", velas['nombre'].tolist())
        v_cant = st.number_input("Cantidad", min_value=1.0, step=1.0)
        v_monto = st.number_input("Monto total cobrado $", min_value=0.0)
        v_pago = st.selectbox("Método de Pago", ["Efectivo", "Transferencia", "Mercado Pago"])
        
        if st.form_submit_button("Registrar Venta"):
            c = conn.cursor()
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
            c.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (?,?,?,?,?)",
                     (fecha, v_sel, v_cant, v_monto, v_pago))
            c.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_cant, v_sel))
            conn.commit()
            st.success("Venta e inventario actualizados.")

# ---------------------------------------------------------
# 4. COMPRAS Y GASTOS
# ---------------------------------------------------------
elif menu == "🛒 Compras y Gastos":
    st.subheader("Registro de Gastos y Compras de Insumos")
    with st.form("form_gasto"):
        item = st.text_input("Detalle (Insumo o Gasto)")
        cant = st.number_input("Cantidad", min_value=0.0)
        costo = st.number_input("Costo Total $", min_value=0.0)
        pago = st.selectbox("Pagar desde:", ["Efectivo", "Transferencia", "Mercado Pago"])
        
        if st.form_submit_button("Registrar Movimiento"):
            conn = conectar()
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute("INSERT INTO historial_compras (fecha, item_nombre, cantidad, costo_total, metodo_pago) VALUES (?,?,?,?,?)",
                        (fecha, item, cant, costo, pago))
            conn.commit()
            st.success("Gasto registrado en el historial de caja.")

# ---------------------------------------------------------
# 5. REPORTES Y EXPORTACIÓN
# ---------------------------------------------------------
elif menu == "📊 Reportes y Caja":
    st.subheader("Análisis de Rendimiento")
    conn = conectar()
    
    df_v = pd.read_sql_query("SELECT fecha, 'VENTA' as Tipo, producto as Detalle, total_venta as Monto, metodo_pago as Cuenta FROM historial_ventas", conn)
    df_c = pd.read_sql_query("SELECT fecha, 'GASTO' as Tipo, item_nombre as Detalle, costo_total as Monto, metodo_pago as Cuenta FROM historial_compras", conn)
    
    caja_final = pd.concat([df_v, df_c]).sort_values(by="fecha", ascending=False)
    
    m1, m2, m3 = st.columns(3)
    ingresos = df_v['Monto'].sum()
    egresos = df_c['Monto'].sum()
    m1.metric("Ingresos (Ventas)", f"$ {ingresos:,.2f}")
    m2.metric("Egresos (Gastos)", f"$ {egresos:,.2f}")
    m3.metric("Saldo Final", f"$ {(ingresos - egresos):,.2f}", delta=float(ingresos-egresos))
    
    if not df_v.empty:
        fig = px.pie(df_v, values='Monto', names='Detalle', title="Ventas por Producto")
        st.plotly_chart(fig, use_container_width=True)
    
    st.dataframe(caja_final, use_container_width=True, hide_index=True)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        caja_final.to_excel(writer, index=False, sheet_name='Caja')
    
    st.download_button(
        label="📥 Exportar Caja Completa a Excel",
        data=output.getvalue(),
        file_name=f"caja_velas_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.ms-excel"
    )
