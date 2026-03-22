import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Velas Candela Pro - Cloud", layout="wide")

# --- GESTIÓN DE BASE DE DATOS ---
def conectar():
    # check_same_thread=False evita errores de concurrencia en la nube
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()
    # Tabla de Productos original
    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT, 
        unidad TEXT, stock_actual REAL DEFAULT 0, costo_u REAL DEFAULT 0, 
        precio_v REAL DEFAULT 0, precio_v2 REAL DEFAULT 0, 
        margen1 REAL DEFAULT 100, margen2 REAL DEFAULT 100)''')
    
    # Tabla de RECETAS
    cursor.execute('''CREATE TABLE IF NOT EXISTS recetas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, id_final INTEGER, 
        id_insumo INTEGER, cantidad REAL)''')
    
    # Historial de Ventas
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''')
    
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Velas Candela Pro")
menu = st.sidebar.radio("Ir a:", ["📦 Stock", "🧪 Recetas y Producción", "🚀 Ventas", "📊 Reportes"])

# ---------------------------------------------------------
# 1. STOCK
# ---------------------------------------------------------
if menu == "📦 Stock":
    st.subheader("Gestión de Inventario")
    conn = conectar()
    
    col_f1, col_f2 = st.columns(2)
    tipo_f = col_f1.selectbox("Filtrar por Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
    busq = col_f2.text_input("Buscar por nombre")
    
    query = "SELECT id, nombre, tipo, stock_actual as Stock, costo_u as 'Costo U$' FROM productos WHERE 1=1"
    params = []
    if tipo_f != "TODOS":
        query += " AND UPPER(tipo) = UPPER(?)"; params.append(tipo_f)
    if busq:
        query += " AND UPPER(nombre) LIKE UPPER(?)"; params.append(f"%{busq}%")
    
    df_p = pd.read_sql_query(query, conn, params=params)
    st.dataframe(df_p, use_container_width=True, hide_index=True)

    with st.expander("➕ Cargar Nuevo Artículo"):
        with st.form("form_nuevo"):
            c1, c2 = st.columns(2)
            n_nom = c1.text_input("Nombre")
            n_tip = c2.selectbox("Categoría", ["Insumo", "Final", "Packaging"])
            n_stk = c1.number_input("Stock Inicial", value=0.0)
            n_cst = c2.number_input("Costo Unitario", value=0.0)
            if st.form_submit_button("Guardar"):
                conn.execute("INSERT INTO productos (nombre, tipo, stock_actual, costo_u) VALUES (?,?,?,?)", (n_nom, n_tip, n_stk, n_cst))
                conn.commit()
                st.success("Guardado.")
                st.rerun()

# ---------------------------------------------------------
# 2. RECETAS (SOLUCIÓN AL ERROR DE DATABASE)
# ---------------------------------------------------------
elif menu == "🧪 Recetas y Producción":
    st.subheader("Configuración de Recetas")
    conn = conectar()
    
    # Traemos listas de forma segura
    df_finales = pd.read_sql_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    df_insumos = pd.read_sql_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'INSUMO'", conn)

    if not df_finales.empty:
        c1, c2 = st.columns([1, 2])
        
        with c1:
            v_sel = st.selectbox("Seleccionar Vela", df_finales['nombre'].tolist())
            id_v_final = int(df_finales[df_finales['nombre'] == v_sel]['id'].values[0])
            
            with st.form("vincular_insumo"):
                st.write("### Añadir Insumo a la Fórmula")
                if not df_insumos.empty:
                    i_sel = st.selectbox("Insumo", df_insumos['nombre'].tolist())
                    i_cant = st.number_input("Cantidad (Gr/Ml)", min_value=0.0, format="%.2f")
                    if st.form_submit_button("Vincular"):
                        id_i = int(df_insumos[df_insumos['nombre'] == i_sel]['id'].values[0])
                        conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_final, id_i, i_cant))
                        conn.commit()
                        st.success("Añadido.")
                else:
                    st.warning("Cargá insumos en Stock primero.")

        with c2:
            st.write(f"### Composición: {v_sel}")
            # PROTECCIÓN: Solo consultamos si id_v_final es válido y existe en recetas
            query_receta = f"""
                SELECT r.id, i.nombre as Insumo, r.cantidad as Cantidad, i.costo_u, (r.cantidad * i.costo_u) as Subtotal
                FROM recetas r JOIN productos i ON r.id_insumo = i.id
                WHERE r.id_final = {id_v_final}"""
            
            df_receta = pd.read_sql_query(query_receta, conn)
            
            if not df_receta.empty:
                st.table(df_receta)
                st.metric("Costo de Fabricación Unitario", f"$ {df_receta['Subtotal'].sum():,.2f}")
                
                # Botón de Producción
                if st.button("🚀 REGISTRAR PRODUCCIÓN (+1 Stock)"):
                    cur = conn.cursor()
                    for _, row in df_receta.iterrows():
                        # Restar de insumos
                        cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (row['Cantidad'], row['Insumo']))
                    # Sumar al producto final
                    cur.execute("UPDATE productos SET stock_actual = stock_actual + 1 WHERE id = ?", (id_v_final,))
                    conn.commit()
                    st.success(f"Stock de {v_sel} actualizado e insumos descontados.")
            else:
                st.info("No hay una receta guardada para esta vela.")
    else:
        st.warning("Debe cargar productos de categoría 'Final' en el Stock primero.")

# ---------------------------------------------------------
# 3. VENTAS
# ---------------------------------------------------------
elif menu == "🚀 Ventas":
    st.subheader("Registrar Venta Directa")
    conn = conectar()
    df_velas = pd.read_sql_query("SELECT nombre, precio_v FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    
    if not df_velas.empty:
        with st.form("vta"):
            v_n = st.selectbox("Vela", df_velas['nombre'].tolist())
            v_c = st.number_input("Cantidad", min_value=1.0)
            v_t = st.number_input("Total cobrado $")
            if st.form_submit_button("Confirmar Venta"):
                cur = conn.cursor()
                cur.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)",
                         (datetime.now().strftime("%Y-%m-%d"), v_n, v_c, v_t))
                cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_c, v_n))
                conn.commit()
                st.success("Venta guardada.")
    else:
        st.error("No hay productos 'Finales' registrados.")

# ---------------------------------------------------------
# 4. REPORTES
# ---------------------------------------------------------
elif menu == "📊 Reportes":
    st.subheader("Caja e Historial")
    conn = conectar()
    df_h = pd.read_sql_query("SELECT * FROM historial_ventas ORDER BY id DESC", conn)
    if not df_h.empty:
        st.metric("Total Facturado", f"$ {df_h['total_venta'].sum():,.2f}")
        st.dataframe(df_h, use_container_width=True)
