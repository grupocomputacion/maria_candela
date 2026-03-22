import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Velas Candela Pro - Cloud", layout="wide")

def conectar():
    # check_same_thread=False es vital para evitar el DatabaseError en la nube
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()
    # 1. Tabla de Productos
    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT, 
        unidad TEXT, stock_actual REAL DEFAULT 0, costo_u REAL DEFAULT 0, 
        precio_v REAL DEFAULT 0, precio_v2 REAL DEFAULT 0, 
        margen1 REAL DEFAULT 100, margen2 REAL DEFAULT 100)''')
    
    # 2. Tabla de RECETAS (Relación Insumo-Vela)
    cursor.execute('''CREATE TABLE IF NOT EXISTS recetas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, id_final INTEGER, 
        id_insumo INTEGER, cantidad REAL)''')
    
    # 3. Historiales
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''')
    
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Gestión Candela")
menu = st.sidebar.radio("Ir a:", ["📦 Stock", "🧪 Recetas y Producción", "💰 Calculadora Manual", "🚀 Ventas", "📊 Reportes"])

# ---------------------------------------------------------
# 1. STOCK
# ---------------------------------------------------------
if menu == "📦 Stock":
    st.subheader("Gestión de Inventario")
    conn = conectar()
    f1, f2 = st.columns(2)
    tipo_f = f1.selectbox("Filtrar Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
    busq = f2.text_input("Buscar por nombre")
    
    query = "SELECT id, nombre, tipo, stock_actual as Stock, costo_u as 'Costo U$', precio_v as 'Lista 1', precio_v2 as 'Lista 2' FROM productos WHERE 1=1"
    params = []
    if tipo_f != "TODOS":
        query += " AND UPPER(tipo) = UPPER(?)"; params.append(tipo_f)
    if busq:
        query += " AND UPPER(nombre) LIKE UPPER(?)"; params.append(f"%{busq}%")
    
    df_p = pd.read_sql_query(query, conn, params=params)
    st.dataframe(df_p, use_container_width=True, hide_index=True)

    with st.expander("➕ Cargar Nuevo Artículo"):
        with st.form("nuevo_p"):
            c1, c2 = st.columns(2)
            n_nom = c1.text_input("Nombre")
            n_tip = c2.selectbox("Categoría", ["Insumo", "Final", "Packaging"])
            n_stk = c1.number_input("Stock", value=0.0)
            n_cst = c2.number_input("Costo Unitario", value=0.0)
            n_m1 = c1.number_input("Margen L1 %", value=100.0)
            n_m2 = c2.number_input("Margen L2 %", value=70.0)
            if st.form_submit_button("Guardar"):
                p1 = n_cst * (1 + n_m1/100)
                p2 = n_cst * (1 + n_m2/100)
                conn.execute("INSERT INTO productos (nombre, tipo, stock_actual, costo_u, margen1, margen2, precio_v, precio_v2) VALUES (?,?,?,?,?,?,?,?)", (n_nom, n_tip, n_stk, n_cst, n_m1, n_m2, p1, p2))
                conn.commit(); st.success("Guardado."); st.rerun()

# ---------------------------------------------------------
# 2. RECETAS (SOLUCIÓN AL ERROR DE BASE DE DATOS)
# ---------------------------------------------------------
elif menu == "🧪 Recetas y Producción":
    st.subheader("Fórmulas de Producción")
    conn = conectar()
    finales = pd.read_sql_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    insumos = pd.read_sql_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'INSUMO'", conn)

    if not finales.empty:
        c1, c2 = st.columns([1, 2])
        with c1:
            v_sel = st.selectbox("Seleccionar Vela", finales['nombre'].tolist())
            id_v_final = int(finales[finales['nombre'] == v_sel]['id'].values[0])
            
            with st.form("vincular"):
                st.write("### Vincular Insumo")
                i_sel = st.selectbox("Insumo", insumos['nombre'].tolist()) if not insumos.empty else st.warning("Cargá insumos")
                i_cant = st.number_input("Cantidad (Gr/Ml)", min_value=0.0, format="%.2f")
                if st.form_submit_button("Añadir"):
                    id_i = int(insumos[insumos['nombre'] == i_sel]['id'].values[0])
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_final, id_i, i_cant))
                    conn.commit(); st.success("Añadido."); st.rerun()

        with c2:
            st.write(f"### Receta de: {v_sel}")
            # PROTECCIÓN: Bloque try/except manual para capturar errores de JOIN
            try:
                query_receta = f"""
                    SELECT r.id, i.nombre as Insumo, r.cantidad as Cantidad, i.costo_u, (r.cantidad * i.costo_u) as Subtotal
                    FROM recetas r 
                    INNER JOIN productos i ON r.id_insumo = i.id
                    WHERE r.id_final = {id_v_final}
                """
                df_receta = pd.read_sql_query(query_receta, conn)
                
                if not df_receta.empty:
                    st.table(df_receta)
                    st.metric("Costo de Fabricación", f"$ {df_receta['Subtotal'].sum():,.2f}")
                    
                    if st.button("🚀 REGISTRAR PRODUCCIÓN"):
                        cur = conn.cursor()
                        for _, row in df_receta.iterrows():
                            # Descontar stock basándose en receta
                            cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (row['Cantidad'], row['Insumo']))
                        cur.execute("UPDATE productos SET stock_actual = stock_actual + 1 WHERE id = ?", (id_v_final,))
                        conn.commit(); st.success("Producción registrada."); st.rerun()
                else:
                    st.info("No hay receta cargada para esta vela.")
            except:
                st.error("Error al leer recetas cargadas. Asegúrese de que los insumos existan en el stock.")
    else:
        st.warning("Debe cargar productos de categoría 'Final' primero.")

# ---------------------------------------------------------
# 3. CALCULADORA MANUAL (RECUPERADA)
# ---------------------------------------------------------
elif menu == "💰 Calculadora Manual":
    st.subheader("Calculadora Rápida de Costos")
    conn = conectar()
    insumos_db = pd.read_sql_query("SELECT nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'", conn)
    
    if not insumos_db.empty:
        n = st.number_input("¿Cuántos insumos sumar?", 1, 15, 3)
        costo_total_m = 0.0
        for i in range(n):
            cx1, cx2 = st.columns(2)
            n_i = cx1.selectbox(f"Insumo {i+1}", ["-"] + insumos_db['nombre'].tolist(), key=f"c_{i}")
            q_i = cx2.number_input(f"Cantidad {i+1}", 0.0, key=f"q_{i}")
            if n_i != "-":
                pu = insumos_db[insumos_db['nombre'] == n_i]['costo_u'].values[0]
                costo_total_m += (pu * q_i)
        st.divider()
        st.metric("COSTO TOTAL CALCULADO", f"$ {costo_total_m:,.2f}")
    else:
        st.warning("Cargue insumos en el stock para usar la calculadora.")

# ---------------------------------------------------------
# 4. VENTAS
# ---------------------------------------------------------
elif menu == "🚀 Ventas":
    st.subheader("Registrar Venta")
    conn = conectar()
    velas = pd.read_sql_query("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    if not velas.empty:
        with st.form("vta"):
            v_nom = st.selectbox("Vela", velas['nombre'].tolist())
            v_cant = st.number_input("Cantidad", min_value=1.0)
            v_lista = st.radio("Lista de Precio", ["Lista 1 (Minorista)", "Lista 2 (Mayorista)"])
            p_ref = velas[velas['nombre'] == v_nom]['precio_v' if "1" in v_lista else 'precio_v2'].values[0]
            v_total = st.number_input("Total cobrado $", value=float(p_ref * v_cant))
            if st.form_submit_button("Confirmar Venta"):
                cur = conn.cursor()
                cur.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)", (datetime.now().strftime("%Y-%m-%d %H:%M"), v_nom, v_cant, v_total))
                cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_cant, v_nom))
                conn.commit(); st.success("Venta guardada."); st.rerun()

# ---------------------------------------------------------
# 5. REPORTES
# ---------------------------------------------------------
elif menu == "📊 Reportes":
    st.subheader("Historial de Caja")
    conn = conectar()
    df_v = pd.read_sql_query("SELECT * FROM historial_ventas ORDER BY id DESC", conn)
    if not df_v.empty:
        st.metric("Total Facturado", f"$ {df_v['total_venta'].sum():,.2f}")
        st.dataframe(df_v, use_container_width=True)
        fig = px.pie(df_v, values='total_venta', names='producto', title="Ventas por Producto")
        st.plotly_chart(fig, use_container_width=True)
