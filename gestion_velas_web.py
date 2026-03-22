import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Velas Candela Pro - Cloud", layout="wide")

def conectar():
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()
    # Estructura idéntica a tu original
    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT, 
        unidad TEXT, stock_actual REAL DEFAULT 0, stock_minimo REAL DEFAULT 0,
        costo_u REAL DEFAULT 0, precio_v REAL DEFAULT 0, 
        precio_v2 REAL DEFAULT 0, margen1 REAL DEFAULT 100, margen2 REAL DEFAULT 100)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS recetas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, id_final INTEGER, 
        id_insumo INTEGER, cantidad REAL)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''')
    
    conn.commit()
    conn.close()

inicializar_db()

st.sidebar.title("🕯️ Menú Gestión")
menu = st.sidebar.radio("Ir a:", ["📦 Stock", "🧪 Gestión de Recetas", "🚀 Registrar Venta", "📊 Reportes"])

# ---------------------------------------------------------
# 1. STOCK
# ---------------------------------------------------------
if menu == "📦 Stock":
    st.subheader("Control de Inventario")
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
    
    df = pd.read_sql_query(query, conn, params=params)
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# 2. GESTIÓN DE RECETAS (SOLUCIÓN DEFINITIVA AL ERROR DE DATOS)
# ---------------------------------------------------------
elif menu == "🧪 Gestión de Recetas":
    st.subheader("Costeo de Fabricación y Márgenes de Venta")
    conn = conectar()
    
    # Cargamos productos
    df_f = pd.read_sql_query("SELECT id, nombre, margen1, margen2 FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    df_i = pd.read_sql_query("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'", conn)

    if not df_f.empty:
        c1, c2 = st.columns([1, 2])
        
        with c1:
            v_sel = st.selectbox("Elegir Vela para Costeo", df_f['nombre'].tolist())
            row_v = df_f[df_f['nombre'] == v_sel].iloc[0]
            id_v = int(row_v['id'])
            
            with st.form("add_insumo_form"):
                st.write("### Añadir Insumo")
                ins_sel = st.selectbox("Materia Prima", df_i['nombre'].tolist()) if not df_i.empty else st.error("No hay insumos")
                ins_cant = st.number_input("Cantidad", min_value=0.0, format="%.2f")
                if st.form_submit_button("Vincular a Receta"):
                    id_ins = int(df_i[df_i['nombre'] == ins_sel]['id'].values[0])
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v, id_ins, ins_cant))
                    conn.commit()
                    st.success("Añadido.")
                    st.rerun()

        with c2:
            st.write(f"### Composición y Cálculo de Precios: {v_sel}")
            # BLINDAJE SQL: Usamos COALESCE para evitar errores de multiplicación con Nulos
            query_rec = f"""
                SELECT r.id, i.nombre as Insumo, 
                COALESCE(r.cantidad, 0) as Cantidad, 
                COALESCE(i.costo_u, 0) as Costo_U,
                (COALESCE(r.cantidad, 0) * COALESCE(i.costo_u, 0)) as Subtotal
                FROM recetas r 
                INNER JOIN productos i ON r.id_insumo = i.id
                WHERE r.id_final = {id_v}
            """
            try:
                df_rec = pd.read_sql_query(query_rec, conn)
                
                if not df_rec.empty:
                    st.table(df_rec)
                    costo_total = df_rec['Subtotal'].sum()
                    
                    st.divider()
                    st.write("### 📈 Determinación de Precio de Venta")
                    cm1, cm2 = st.columns(2)
                    
                    # Lógica de Márgenes de tu archivo original
                    m1_val = cm1.number_input("Margen 1 % (Minorista)", value=float(row_v['margen1']))
                    m2_val = cm2.number_input("Margen 2 % (Mayorista)", value=float(row_v['margen2']))
                    
                    p1 = costo_total * (1 + m1_val/100)
                    p2 = costo_total * (1 + m2_val/100)
                    
                    st.metric("COSTO DE FABRICACIÓN", f"$ {costo_total:,.2f}")
                    cm1.metric("PRECIO L1 SUGERIDO", f"$ {p1:,.2f}")
                    cm2.metric("PRECIO L2 SUGERIDO", f"$ {p2:,.2f}")
                    
                    if st.button("💾 ACTUALIZAR PRECIOS EN INVENTARIO"):
                        conn.execute("UPDATE productos SET precio_v=?, precio_v2=?, margen1=?, margen2=?, costo_u=? WHERE id=?", 
                                    (p1, p2, m1_val, m2_val, costo_total, id_v))
                        conn.commit()
                        st.success("Precios guardados en Stock.")

                    if st.button("🚀 REGISTRAR PRODUCCIÓN (+1 Stock)"):
                        cur = conn.cursor()
                        for _, r in df_rec.iterrows():
                            cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (r['Cantidad'], r['Insumo']))
                        cur.execute("UPDATE productos SET stock_actual = stock_actual + 1 WHERE id = ?", (id_v,))
                        conn.commit()
                        st.success("Producción impactada.")
                        st.rerun()
                else:
                    st.info("No hay componentes guardados para esta receta.")
            except Exception as e:
                st.error(f"Error en datos: {e}")
    else:
        st.warning("Cargá productos 'Finales' para gestionar recetas.")

# ---------------------------------------------------------
# 3. VENTAS
# ---------------------------------------------------------
elif menu == "🚀 Registrar Venta":
    st.subheader("Registrar Venta")
    conn = conectar()
    vls = pd.read_sql_query("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    if not vls.empty:
        with st.form("v_form"):
            v_n = st.selectbox("Vela", vls['nombre'].tolist())
            v_c = st.number_input("Cantidad", min_value=1.0)
            v_l = st.radio("Lista de Venta", ["Minorista (L1)", "Mayorista (L2)"])
            p_r = vls[vls['nombre'] == v_n]['precio_v' if "1" in v_l else 'precio_v2'].values[0]
            v_t = st.number_input("Total cobrado $", value=float(p_r * v_c))
            if st.form_submit_button("Confirmar Venta"):
                conn.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)", 
                            (datetime.now().strftime("%Y-%m-%d %H:%M"), v_n, v_c, v_t))
                conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_c, v_n))
                conn.commit()
                st.success("Venta guardada.")

# ---------------------------------------------------------
# 4. REPORTES
# ---------------------------------------------------------
elif menu == "📊 Reportes":
    st.subheader("Resumen de Caja")
    conn = conectar()
    df_h = pd.read_sql_query("SELECT fecha, producto, total_venta FROM historial_ventas ORDER BY id DESC", conn)
    if not df_h.empty:
        st.metric("Recaudación Total", f"$ {df_h['total_venta'].sum():,.2f}")
        st.dataframe(df_h, use_container_width=True)
