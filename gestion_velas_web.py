import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Velas Candela Pro - Cloud", layout="wide")

def conectar():
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
    
    # 2. Tabla de RECETAS
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
st.sidebar.title("🕯️ Menú de Gestión")
# RESTAURADO: Opción de Caja y Reportes
menu = st.sidebar.radio("Ir a:", ["📦 Stock e Inventario", "🧪 Gestión de Recetas", "🚀 Registrar Venta", "📊 Caja y Reportes"])

# ---------------------------------------------------------
# 1. STOCK E INVENTARIO
# ---------------------------------------------------------
if menu == "📦 Stock e Inventario":
    st.subheader("Gestión de Existencias")
    conn = conectar()
    f1, f2 = st.columns(2)
    tipo_f = f1.selectbox("Filtrar por Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
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
        with st.form("nuevo_prod"):
            c1, c2 = st.columns(2)
            n_nom = c1.text_input("Nombre")
            n_tip = c2.selectbox("Categoría", ["Insumo", "Final", "Packaging"])
            n_stk = c1.number_input("Stock Inicial", value=0.0)
            n_cst = c2.number_input("Costo Unitario", value=0.0)
            n_m1 = c1.number_input("Margen L1 %", value=100.0)
            n_m2 = c2.number_input("Margen L2 %", value=70.0)
            if st.form_submit_button("Guardar"):
                p1 = n_cst * (1 + n_m1/100); p2 = n_cst * (1 + n_m2/100)
                conn.execute("INSERT INTO productos (nombre, tipo, stock_actual, costo_u, margen1, margen2, precio_v, precio_v2) VALUES (?,?,?,?,?,?,?,?)", (n_nom, n_tip, n_stk, n_cst, n_m1, n_m2, p1, p2))
                conn.commit(); st.success("Guardado."); st.rerun()

# ---------------------------------------------------------
# 2. GESTIÓN DE RECETAS (CORREGIDO: Levanta datos existentes)
# ---------------------------------------------------------
elif menu == "🧪 Gestión de Recetas":
    st.subheader("Fórmulas y Producción")
    conn = conectar()
    velas_finales = pd.read_sql_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    todos_insumos = pd.read_sql_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'INSUMO'", conn)

    if not velas_finales.empty:
        c1, c2 = st.columns([1, 2])
        with c1:
            v_sel = st.selectbox("Seleccionar Vela Final", velas_finales['nombre'].tolist())
            id_v_final = int(velas_finales[velas_finales['nombre'] == v_sel]['id'].values[0])
            
            with st.form("form_receta"):
                st.write("### Vincular Insumo")
                i_sel = st.selectbox("Insumo", todos_insumos['nombre'].tolist()) if not todos_insumos.empty else st.warning("Cargá insumos")
                i_cant = st.number_input("Cantidad (Gr/Un)", min_value=0.0, format="%.2f")
                if st.form_submit_button("Añadir a Receta"):
                    id_i = int(todos_insumos[todos_insumos['nombre'] == i_sel]['id'].values[0])
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_final, id_i, i_cant))
                    conn.commit(); st.success("Añadido."); st.rerun()

        with c2:
            st.write(f"### Composición Actual: {v_sel}")
            # CORRECCIÓN: Query robusta para levantar recetas ya cargadas
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
                
                cant_f = st.number_input("Unidades a producir", min_value=1, value=1)
                if st.button("🚀 REGISTRAR PRODUCCIÓN"):
                    cur = conn.cursor()
                    for _, row in df_receta.iterrows():
                        cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (row['Cantidad'] * cant_f, row['Insumo']))
                    cur.execute("UPDATE productos SET stock_actual = stock_actual + ? WHERE id = ?", (cant_f, id_v_final))
                    conn.commit(); st.success("Producción registrada e insumos descontados."); st.rerun()
            else:
                st.info("Esta vela no tiene receta cargada aún.")
    else:
        st.warning("Cargá productos 'Finales' en Stock.")

# ---------------------------------------------------------
# 3. REGISTRAR VENTA (Incluye Lista 1 y 2)
# ---------------------------------------------------------
elif menu == "🚀 Registrar Venta":
    st.subheader("Punto de Venta")
    conn = conectar()
    velas = pd.read_sql_query("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    
    if not velas.empty:
        with st.form("vta"):
            v_nom = st.selectbox("Vela", velas['nombre'].tolist())
            v_cant = st.number_input("Cantidad", min_value=1.0)
            v_lista = st.radio("Lista de Precios", ["Lista 1 (Minorista)", "Lista 2 (Mayorista)"])
            p_ref = velas[velas['nombre'] == v_nom]['precio_v' if "1" in v_lista else 'precio_v2'].values[0]
            v_pago = st.number_input("Total cobrado $", value=float(p_ref * v_cant))
            
            if st.form_submit_button("Confirmar Venta"):
                cur = conn.cursor()
                cur.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)", (datetime.now().strftime("%Y-%m-%d %H:%M"), v_nom, v_cant, v_pago))
                cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_cant, v_nom))
                conn.commit(); st.success("Venta guardada."); st.rerun()

# ---------------------------------------------------------
# 4. CAJA Y REPORTES (RESTAURADO)
# ---------------------------------------------------------
elif menu == "📊 Caja y Reportes":
    st.subheader("Historial de Caja y Movimientos")
    conn = conectar()
    df_v = pd.read_sql_query("SELECT fecha, producto as Detalle, total_venta as Monto FROM historial_ventas ORDER BY id DESC", conn)
    
    if not df_v.empty:
        st.metric("Total Ingresos", f"$ {df_v['Monto'].sum():,.2f}")
        st.dataframe(df_v, use_container_width=True)
        fig = px.pie(df_v, values='Monto', names='Detalle', title="Ventas por Producto")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay ventas registradas.")
