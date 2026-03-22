import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Velas Candela Pro - Cloud", layout="wide")

# --- CONEXIÓN SEGURA Y MIGRACIÓN ---
def conectar():
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()
    # Aseguramos tablas base
    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT, 
        unidad TEXT, stock_actual REAL DEFAULT 0, costo_u REAL DEFAULT 0, 
        precio_v REAL DEFAULT 0, precio_v2 REAL DEFAULT 0, 
        margen1 REAL DEFAULT 100, margen2 REAL DEFAULT 100)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS recetas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, id_final INTEGER, 
        id_insumo INTEGER, cantidad REAL)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''')
    
    # Parche de seguridad para columnas de márgenes
    for col in [("precio_v2", "REAL DEFAULT 0"), ("margen1", "REAL DEFAULT 100"), ("margen2", "REAL DEFAULT 100")]:
        try: cursor.execute(f"ALTER TABLE productos ADD COLUMN {col[0]} {col[1]}")
        except: pass
        
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Menú de Gestión")
menu = st.sidebar.radio("Ir a:", ["📦 Stock e Inventario", "🧪 Recetas y Costos", "🚀 Registrar Venta", "📊 Reportes de Caja"])

# ---------------------------------------------------------
# 1. STOCK E INVENTARIO
# ---------------------------------------------------------
if menu == "📦 Stock e Inventario":
    st.subheader("Control de Existencias")
    conn = conectar()
    f1, f2 = st.columns(2)
    t_f = f1.selectbox("Filtrar Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
    b_f = f2.text_input("Buscar por nombre")
    
    query = "SELECT id, nombre, tipo, stock_actual, costo_u, precio_v, precio_v2 FROM productos WHERE 1=1"
    params = []
    if t_f != "TODOS":
        query += " AND UPPER(tipo) = UPPER(?)"; params.append(t_f)
    if b_f:
        query += " AND UPPER(nombre) LIKE UPPER(?)"; params.append(f"%{b_f}%")
    
    df_p = pd.read_sql_query(query, conn, params=params)
    st.dataframe(df_p, use_container_width=True, hide_index=True)

    with st.expander("➕ Cargar Nuevo"):
        with st.form("n_p"):
            c1, c2 = st.columns(2)
            n = c1.text_input("Nombre")
            t = c2.selectbox("Tipo", ["Insumo", "Final", "Packaging"])
            s = c1.number_input("Stock", value=0.0)
            c = c2.number_input("Costo Unitario", value=0.0)
            if st.form_submit_button("Guardar"):
                conn.execute("INSERT INTO productos (nombre, tipo, stock_actual, costo_u) VALUES (?,?,?,?)", (n, t, s, c))
                conn.commit(); st.rerun()

# ---------------------------------------------------------
# 2. RECETAS Y COSTOS (MÓDULO COMPLETO REPARADO)
# ---------------------------------------------------------
elif menu == "🧪 Recetas y Costos":
    st.subheader("Calculadora de Producción e Insumos")
    conn = conectar()
    
    # Buscamos productos ignorando mayúsculas
    df_f = pd.read_sql_query("SELECT id, nombre, margen1, margen2 FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    df_i = pd.read_sql_query("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'", conn)

    if not df_f.empty:
        c1, c2 = st.columns([1, 2])
        
        with c1:
            v_sel = st.selectbox("Seleccionar Producto Final", df_f['nombre'].tolist())
            row_v = df_f[df_f['nombre'] == v_sel].iloc[0]
            id_v = int(row_v['id'])
            
            with st.form("add_comp"):
                st.write("### Añadir Insumo a la Receta")
                ins_sel = st.selectbox("Insumo", df_i['nombre'].tolist()) if not df_i.empty else st.error("No hay insumos")
                ins_cant = st.number_input("Cantidad (Gr/Ml/Un)", min_value=0.0)
                if st.form_submit_button("Vincular"):
                    id_ins = int(df_i[df_i['nombre'] == ins_sel]['id'].values[0])
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v, id_ins, ins_cant))
                    conn.commit(); st.success("Añadido."); st.rerun()

        with c2:
            st.write(f"### Receta Cargada para: {v_sel}")
            # JOIN Robusto para levantar datos existentes
            query_rec = f"""
                SELECT r.id, i.nombre as Materia_Prima, r.cantidad as Cantidad, i.costo_u, (r.cantidad * i.costo_u) as Subtotal
                FROM recetas r 
                INNER JOIN productos i ON r.id_insumo = i.id
                WHERE r.id_final = {id_v}
            """
            try:
                df_rec = pd.read_sql_query(query_rec, conn)
                
                if not df_rec.empty:
                    st.table(df_rec)
                    costo_total = df_rec['Subtotal'].sum()
                    
                    # --- CÁLCULO DE PRECIOS POR MARGEN ---
                    st.divider()
                    st.write("### 💰 Determinación de Precios de Venta")
                    cm1, cm2 = st.columns(2)
                    m1 = cm1.number_input("Margen Lista 1 %", value=float(row_v['margen1']))
                    m2 = cm2.number_input("Margen Lista 2 %", value=float(row_v['margen2']))
                    
                    p1 = costo_total * (1 + m1/100)
                    p2 = costo_total * (1 + m2/100)
                    
                    st.metric("COSTO DE FABRICACIÓN", f"$ {costo_total:,.2f}")
                    cm1.metric("PRECIO L1", f"$ {p1:,.2f}")
                    cm2.metric("PRECIO L2", f"$ {p2:,.2f}")
                    
                    if st.button("💾 Guardar Precios en el Inventario"):
                        conn.execute("UPDATE productos SET precio_v=?, precio_v2=?, margen1=?, margen2=? WHERE id=?", (p1, p2, m1, m2, id_v))
                        conn.commit(); st.success("Precios actualizados en Stock.")
                    
                    if st.button("🚀 REGISTRAR PRODUCCIÓN (+1 Stock, - Insumos)"):
                        cur = conn.cursor()
                        for _, r in df_rec.iterrows():
                            cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (r['Cantidad'], r['Materia_Prima']))
                        cur.execute("UPDATE productos SET stock_actual = stock_actual + 1 WHERE id = ?", (id_v,))
                        conn.commit(); st.success("Stock actualizado."); st.rerun()
                else:
                    st.info("No hay componentes guardados para esta receta.")
            except:
                st.error("Error al cargar la receta. Verifique los nombres de los insumos.")
    else:
        st.warning("Cargá un producto tipo 'Final' para ver recetas.")

# ---------------------------------------------------------
# 3. VENTAS Y REPORTES
# ---------------------------------------------------------
elif menu == "🚀 Registrar Venta":
    st.subheader("Punto de Venta")
    conn = conectar()
    vls = pd.read_sql_query("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    if not vls.empty:
        with st.form("v"):
            v_n = st.selectbox("Vela", vls['nombre'].tolist())
            v_c = st.number_input("Cantidad", min_value=1.0)
            v_l = st.radio("Lista", ["Minorista (L1)", "Mayorista (L2)"])
            p_r = vls[vls['nombre'] == v_n]['precio_v' if "1" in v_l else 'precio_v2'].values[0]
            v_t = st.number_input("Total $", value=float(p_r * v_c))
            if st.form_submit_button("Vender"):
                conn.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)", (datetime.now().strftime("%Y-%m-%d %H:%M"), v_n, v_c, v_t))
                conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_c, v_n))
                conn.commit(); st.success("Venta guardada.")

elif menu == "📊 Reportes de Caja":
    st.subheader("Historial de Movimientos")
    conn = conectar()
    df_h = pd.read_sql_query("SELECT fecha, producto, total_venta FROM historial_ventas ORDER BY id DESC", conn)
    if not df_h.empty:
        st.metric("Total Ingresos", f"$ {df_h['total_venta'].sum():,.2f}")
        st.dataframe(df_h, use_container_width=True)
        st.plotly_chart(px.pie(df_h, values='total_venta', names='producto', title="Ventas por Producto"))
