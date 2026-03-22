import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Velas Candela Pro - Cloud", layout="wide")

# ==========================================
# 1. FUNCIONES ORIGINALES
# ==========================================
def safe_float(val):
    try:
        return float(val) if val is not None else 0.0
    except:
        return 0.0

def conectar():
    # check_same_thread=False es vital para evitar el DatabaseError en la nube
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()
    
    # Tabla Productos
    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT, 
        unidad TEXT, stock_actual REAL DEFAULT 0, stock_minimo REAL DEFAULT 0,
        costo_u REAL DEFAULT 0, precio_v REAL DEFAULT 0, 
        precio_v2 REAL DEFAULT 0, margen1 REAL DEFAULT 100, margen2 REAL DEFAULT 100)''')
    
    # Tabla Recetas
    cursor.execute('''CREATE TABLE IF NOT EXISTS recetas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, id_final INTEGER, 
        id_insumo INTEGER, cantidad REAL)''')
    
    # Historial Ventas
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''')
    
    # MIGRACIÓN SEGURA (Tu lógica original)
    for col, tipo in [("precio_v2", "REAL DEFAULT 0"), ("margen1", "REAL DEFAULT 100"), ("margen2", "REAL DEFAULT 100")]:
        try: cursor.execute(f"ALTER TABLE productos ADD COLUMN {col} {tipo}")
        except: pass
        
    conn.commit()
    conn.close()

# Inicialización forzada
inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Menú Gestión")
menu = st.sidebar.radio("Ir a:", ["📦 Stock", "🧪 Recetas y Costeo Pro", "🚀 Registrar Venta", "📊 Caja"])

# ---------------------------------------------------------
# 1. STOCK
# ---------------------------------------------------------
if menu == "📦 Stock":
    st.subheader("Gestión de Inventario")
    conn = conectar()
    f1, f2 = st.columns(2)
    tipo_f = f1.selectbox("Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
    busq = f2.text_input("Buscar por nombre...")
    
    query = "SELECT id, nombre, tipo, stock_actual, costo_u, precio_v, precio_v2 FROM productos WHERE 1=1"
    params = []
    if tipo_f != "TODOS":
        query += " AND UPPER(tipo) = UPPER(?)"; params.append(tipo_f)
    if busq:
        query += " AND UPPER(nombre) LIKE UPPER(?)"; params.append(f"%{busq}%")
    
    df = pd.read_sql_query(query, conn, params=params)
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# 2. RECETAS Y COSTEO (LÓGICA ORIGINAL COMPLETA)
# ---------------------------------------------------------
elif menu == "🧪 Recetas y Costeo Pro":
    st.subheader("Fórmulas, Costos y Márgenes (M1/M2)")
    conn = conectar()
    
    # Cargamos listas usando fetchall para evitar errores de tipo
    finales = conn.execute("SELECT id, nombre, margen1, margen2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    insumos = conn.execute("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'").fetchall()

    if finales:
        col1, col2 = st.columns([1, 2])
        
        with col1:
            nombres_f = [f[1] for f in finales]
            v_sel = st.selectbox("Seleccionar Vela Final", nombres_f)
            
            # Datos de la vela (id, nombre, margen1, margen2)
            v_data = [f for f in finales if f[1] == v_sel][0]
            id_v_final = v_data[0]
            m1_db = safe_float(v_data[2])
            m2_db = safe_float(v_data[3])
            
            with st.form("add_i"):
                st.write("### Vincular Materia Prima")
                nombres_i = [i[1] for i in insumos]
                i_sel = st.selectbox("Insumo", nombres_i) if nombres_i else st.error("Sin insumos")
                i_cant = st.number_input("Cantidad", min_value=0.0)
                if st.form_submit_button("Añadir"):
                    id_ins = [i for i in insumos if i[1] == i_sel][0][0]
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_final, id_ins, i_cant))
                    conn.commit()
                    st.success("Añadido")
                    st.rerun()

        with col2:
            st.write(f"### Composición Guardada: {v_sel}")
            # Query robusta basada en tu código original
            query_receta = f"""
                SELECT r.id, i.nombre, r.cantidad, i.costo_u, (r.cantidad * i.costo_u)
                FROM recetas r 
                INNER JOIN productos i ON r.id_insumo = i.id
                WHERE r.id_final = {id_v_final}
            """
            try:
                rows = conn.execute(query_receta).fetchall()
                if rows:
                    df_rec = pd.DataFrame(rows, columns=["ID", "Insumo", "Cantidad", "Costo U", "Subtotal"])
                    st.table(df_rec[["Insumo", "Cantidad", "Costo U", "Subtotal"]])
                    
                    # Cálculo de costo total
                    costo_fabricacion = sum(safe_float(r[4]) for r in rows)
                    
                    st.divider()
                    st.write("### 💰 Determinación de Precios de Venta")
                    cm1, cm2 = st.columns(2)
                    m1_input = cm1.number_input("Margen 1 %", value=m1_db)
                    m2_input = cm2.number_input("Margen 2 %", value=m2_db)
                    
                    p1 = costo_fabricacion * (1 + m1_input/100)
                    p2 = costo_fabricacion * (1 + m2_input/100)
                    
                    st.metric("COSTO TOTAL COMPONENTES", f"$ {costo_fabricacion:,.2f}")
                    cm1.metric("PRECIO L1 (Sugerido)", f"$ {p1:,.2f}")
                    cm2.metric("PRECIO L2 (Sugerido)", f"$ {p2:,.2f}")
                    
                    if st.button("💾 GUARDAR PRECIOS EN STOCK"):
                        conn.execute("UPDATE productos SET precio_v=?, precio_v2=?, margen1=?, margen2=?, costo_u=? WHERE id=?", 
                                    (p1, p2, m1_input, m2_input, costo_fabricacion, id_v_final))
                        conn.commit()
                        st.success("Precios e historial de costos actualizados")
                else:
                    st.info("No se encontraron componentes cargados para esta vela.")
            except:
                st.error("Error al leer receta. Asegurese de que los insumos tengan costo asignado.")
    else:
        st.warning("Cargá un producto 'Final' para gestionar recetas.")

# ---------------------------------------------------------
# 3. VENTAS
# ---------------------------------------------------------
elif menu == "🚀 Registrar Venta":
    st.subheader("Registrar Venta")
    conn = conectar()
    velas = conn.execute("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    if velas:
        with st.form("vt"):
            v_n = st.selectbox("Vela", [v[0] for v in velas])
            v_c = st.number_input("Cantidad", min_value=1.0)
            v_l = st.radio("Lista", ["L1 (Minorista)", "L2 (Mayorista)"])
            p_sel = [v for v in velas if v[0] == v_n][0]
            p_r = safe_float(p_sel[1] if "1" in v_l else p_sel[2])
            if st.form_submit_button("Cerrar Venta"):
                conn.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)", 
                            (datetime.now().strftime("%Y-%m-%d %H:%M"), v_n, v_c, p_r * v_c))
                conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_c, v_n))
                conn.commit()
                st.success("Venta guardada.")
