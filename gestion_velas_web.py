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
    
    # 2. Tabla de RECETAS
    cursor.execute('''CREATE TABLE IF NOT EXISTS recetas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, id_final INTEGER, 
        id_insumo INTEGER, cantidad REAL)''')
    
    # 3. Historial de Ventas
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''')
    
    conn.commit()
    conn.close()

# Ejecutar inicialización al arranque
inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Menú Pro")
menu = st.sidebar.radio("Ir a:", ["📦 Stock", "🧪 Recetas y Producción", "💰 Calculadora", "🚀 Ventas"])

# ---------------------------------------------------------
# 1. STOCK
# ---------------------------------------------------------
if menu == "📦 Stock":
    st.subheader("Gestión de Inventario")
    conn = conectar()
    
    f1, f2 = st.columns(2)
    tipo_f = f1.selectbox("Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
    busq = f2.text_input("Buscar por nombre")
    
    query = "SELECT id, nombre, tipo, stock_actual as Stock, costo_u as 'Costo U$', precio_v as 'Lista 1' FROM productos WHERE 1=1"
    params = []
    if tipo_f != "TODOS":
        query += " AND UPPER(tipo) = UPPER(?)"; params.append(tipo_f)
    if busq:
        query += " AND UPPER(nombre) LIKE UPPER(?)"; params.append(f"%{busq}%")
    
    df_p = pd.read_sql_query(query, conn, params=params)
    st.dataframe(df_p, use_container_width=True, hide_index=True)

    with st.expander("➕ Nuevo Producto / Insumo"):
        with st.form("nuevo_p"):
            n_nom = st.text_input("Nombre")
            n_tip = st.selectbox("Categoría", ["Insumo", "Final", "Packaging"])
            n_stk = st.number_input("Stock Inicial", value=0.0)
            n_cst = st.number_input("Costo Unitario", value=0.0)
            if st.form_submit_button("Guardar"):
                conn.execute("INSERT INTO productos (nombre, tipo, stock_actual, costo_u) VALUES (?,?,?,?)", (n_nom, n_tip, n_stk, n_cst))
                conn.commit()
                st.success("Guardado.")
                st.rerun()

# ---------------------------------------------------------
# 2. RECETAS (BLINDADO CONTRA DATABASE ERROR)
# ---------------------------------------------------------
elif menu == "🧪 Recetas y Producción":
    st.subheader("Configuración de Recetas y Fabricación")
    conn = conectar()
    
    velas_finales = pd.read_sql_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    todos_insumos = pd.read_sql_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'INSUMO'", conn)

    if not velas_finales.empty:
        c_rec1, c_rec2 = st.columns([1, 2])
        
        with c_rec1:
            v_sel = st.selectbox("Seleccionar Vela Final", velas_finales['nombre'].tolist())
            id_v_final = int(velas_finales[velas_finales['nombre'] == v_sel]['id'].values[0])
            
            with st.form("add_ins_rec"):
                st.write("### Agregar Insumo a la Receta")
                ins_n = st.selectbox("Insumo", todos_insumos['nombre'].tolist()) if not todos_insumos.empty else st.error("No hay insumos")
                ins_q = st.number_input("Cantidad (Gr/Ml)", min_value=0.0, format="%.2f")
                if st.form_submit_button("Vincular"):
                    id_i = int(todos_insumos[todos_insumos['nombre'] == ins_n]['id'].values[0])
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_final, id_i, ins_q))
                    conn.commit()
                    st.success("Añadido.")

        with c_rec2:
            st.write(f"### Composición de {v_sel}")
            # PROTECCIÓN: Bloque Try/Except para evitar el crash de base de datos
            try:
                df_receta = pd.read_sql_query(f"""
                    SELECT r.id, i.nombre as Insumo, r.cantidad as Cantidad, i.costo_u, (r.cantidad * i.costo_u) as Subtotal
                    FROM recetas r JOIN productos i ON r.id_insumo = i.id
                    WHERE r.id_final = {id_v_final}""", conn)
                
                if not df_receta.empty:
                    st.table(df_receta)
                    st.metric("Costo de Producción", f"$ {df_receta['Subtotal'].sum():,.2f}")
                    
                    if st.button("🚀 REGISTRAR PRODUCCIÓN"):
                        cur = conn.cursor()
                        for _, row in df_receta.iterrows():
                            # Descontar stock
                            cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (row['Cantidad'], row['Insumo']))
                        cur.execute("UPDATE productos SET stock_actual = stock_actual + 1 WHERE id = ?", (id_v_final,))
                        conn.commit()
                        st.success("Producción exitosa: Stock actualizado.")
                else:
                    st.info("Esta vela no tiene receta.")
            except Exception as e:
                st.error("Error al cargar receta. Verifique la base de datos.")
    else:
        st.warning("Debe cargar productos de categoría 'Final' primero.")

# ---------------------------------------------------------
# 3. CALCULADORA (Manual)
# ---------------------------------------------------------
elif menu == "💰 Calculadora":
    st.subheader("Cálculo Manual de Costos")
    conn = conectar()
    insumos_db = pd.read_sql_query("SELECT nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'", conn)
    
    if not insumos_db.empty:
        n = st.number_input("Insumos a sumar", 1, 10, 3)
        total_m = 0.0
        for i in range(n):
            cx1, cx2 = st.columns(2)
            n_i = cx1.selectbox(f"Insumo {i+1}", ["-"] + insumos_db['nombre'].tolist(), key=f"calc_{i}")
            q_i = cx2.number_input(f"Cant {i+1}", 0.0, key=f"q_{i}")
            if n_i != "-":
                pu = insumos_db[insumos_db['nombre'] == n_i]['costo_u'].values[0]
                total_m += (pu * q_i)
        st.divider()
        st.metric("COSTO TOTAL", f"$ {total_m:,.2f}")

# ---------------------------------------------------------
# 4. VENTAS
# ---------------------------------------------------------
elif menu == "🚀 Ventas":
    st.subheader("Registrar Venta")
    conn = conectar()
    velas = pd.read_sql_query("SELECT nombre, precio_v FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    if not velas.empty:
        with st.form("vta"):
            v_nom = st.selectbox("Vela", velas['nombre'].tolist())
            v_cant = st.number_input("Cantidad", min_value=1.0)
            v_total = st.number_input("Total cobrado $")
            if st.form_submit_button("Cerrar Venta"):
                c = conn.cursor()
                c.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)",
                         (datetime.now().strftime("%Y-%m-%d"), v_nom, v_cant, v_total))
                c.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_cant, v_nom))
                conn.commit()
                st.success("Venta guardada.")
