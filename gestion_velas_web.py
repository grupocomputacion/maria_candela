import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Velas Candela Pro - Cloud", layout="wide")

# --- FUNCIONES DE APOYO ORIGINALES ---
def safe_float(val):
    try:
        return float(val) if val is not None else 0.0
    except:
        return 0.0

def conectar():
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()
    # Estructura EXACTA de tu gestion_velas.py
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
    
    # MIGRACIÓN SEGURA (Tu lógica original para no romper la DB existente)
    columnas = [("precio_v2", "REAL DEFAULT 0"), ("margen1", "REAL DEFAULT 100"), ("margen2", "REAL DEFAULT 100")]
    for col, tipo in columnas:
        try: cursor.execute(f"ALTER TABLE productos ADD COLUMN {col} {tipo}")
        except: pass
        
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Menú Gestión")
menu = st.sidebar.radio("Ir a:", ["📦 Inventario", "🧪 Recetas y Costeo", "🚀 Ventas", "📊 Caja"])

# ---------------------------------------------------------
# 1. INVENTARIO (Tu lógica de visualización)
# ---------------------------------------------------------
if menu == "📦 Inventario":
    st.subheader("Gestión de Stock")
    conn = conectar()
    f1, f2 = st.columns(2)
    tipo_filtro = f1.selectbox("Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
    busq = f2.text_input("Buscar por nombre...")
    
    query = "SELECT id, nombre, tipo, stock_actual, costo_u, precio_v, precio_v2 FROM productos WHERE 1=1"
    params = []
    if tipo_filtro != "TODOS":
        query += " AND UPPER(tipo) = UPPER(?)"; params.append(tipo_filtro)
    if busq:
        query += " AND UPPER(nombre) LIKE UPPER(?)"; params.append(f"%{busq}%")
    
    df = pd.read_sql_query(query, conn, params=params)
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# 2. RECETAS Y COSTEO (LÓGICA 100% FIEL AL ORIGINAL)
# ---------------------------------------------------------
elif menu == "🧪 Recetas y Costeo":
    st.subheader("Calculadora de Producción y Márgenes")
    conn = conectar()
    
    # Cargamos datos base respetando tu lógica
    finales = conn.execute("SELECT id, nombre, margen1, margen2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    insumos = conn.execute("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'").fetchall()

    if finales:
        c1, c2 = st.columns([1, 2])
        
        with c1:
            # Selector de Vela (Usamos los nombres para la UI)
            nombres_finales = [f[1] for f in finales]
            v_sel = st.selectbox("Seleccionar Producto Final", nombres_finales)
            
            # Buscamos los datos del producto seleccionado (id, margen1, margen2)
            prod_data = [f for f in finales if f[1] == v_sel][0]
            id_v_final = prod_data[0]
            m1_orig = safe_float(prod_data[2])
            m2_orig = safe_float(prod_data[3])
            
            with st.form("form_insumo"):
                st.write("### Añadir Materia Prima")
                nombres_ins = [i[1] for i in insumos]
                i_sel = st.selectbox("Insumo", nombres_ins) if nombres_ins else st.error("No hay insumos")
                i_cant = st.number_input("Cantidad necesaria", min_value=0.0)
                
                if st.form_submit_button("Vincular a Receta"):
                    id_i = [i for i in insumos if i[1] == i_sel][0][0]
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_final, id_i, i_cant))
                    conn.commit()
                    st.success("Añadido")
                    st.rerun()

        with c2:
            st.write(f"### Composición Guardada: {v_sel}")
            # QUERY ROBUSTA: Recupera tus datos precargados
            query_receta = f"""
                SELECT r.id, i.nombre, r.cantidad, i.costo_u, (r.cantidad * i.costo_u)
                FROM recetas r JOIN productos i ON r.id_insumo = i.id
                WHERE r.id_final = {id_v_final}
            """
            rows = conn.execute(query_receta).fetchall()
            
            if rows:
                df_rec = pd.DataFrame(rows, columns=["ID", "Insumo", "Cantidad", "Costo U", "Subtotal"])
                st.table(df_rec[["Insumo", "Cantidad", "Costo U", "Subtotal"]])
                
                costo_total = sum(safe_float(r[4]) for r in rows)
                
                st.divider()
                st.write("### 💰 Determinación de Precios de Venta")
                col1, col2 = st.columns(2)
                
                # Input de márgenes
                m1 = col1.number_input("Margen 1 %", value=m1_orig)
                m2 = col2.number_input("Margen 2 %", value=m2_orig)
                
                p1 = costo_total * (1 + m1/100)
                p2 = costo_total * (1 + m2/100)
                
                st.metric("COSTO TOTAL FABRICACIÓN", f"$ {costo_total:,.2f}")
                col1.metric("PRECIO LISTA 1", f"$ {p1:,.2f}")
                col2.metric("PRECIO LISTA 2", f"$ {p2:,.2f}")
                
                if st.button("💾 Guardar Precios y Márgenes"):
                    conn.execute("UPDATE productos SET precio_v=?, precio_v2=?, margen1=?, margen2=?, costo_u=? WHERE id=?", 
                                (p1, p2, m1, m2, costo_total, id_v_final))
                    conn.commit()
                    st.success("Inventario actualizado")
            else:
                st.info("No hay receta cargada para esta vela.")
    else:
        st.warning("Cargá un producto 'Final' para gestionar recetas.")

# ---------------------------------------------------------
# 3. VENTAS (Lista 1 y 2)
# ---------------------------------------------------------
elif menu == "🚀 Ventas":
    st.subheader("Registrar Venta")
    conn = conectar()
    velas = conn.execute("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    
    if velas:
        with st.form("venta_v"):
            v_n = st.selectbox("Vela", [v[0] for v in velas])
            v_c = st.number_input("Cantidad", min_value=1.0)
            v_l = st.radio("Lista", ["L1 (Minorista)", "L2 (Mayorista)"])
            
            # Buscamos precio según lista
            p_sel = [v for v in velas if v[0] == v_n][0]
            p_ref = safe_float(p_sel[1] if "1" in v_l else p_sel[2])
            
            v_total = st.number_input("Monto Cobrado $", value=float(p_ref * v_cant))
            
            if st.form_submit_button("Confirmar"):
                conn.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)", 
                            (datetime.now().strftime("%Y-%m-%d %H:%M"), v_n, v_c, v_total))
                conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_c, v_n))
                conn.commit()
                st.success("Venta guardada.")
