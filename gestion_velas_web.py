import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io

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
    
    # Historial Ventas (COMILLAS CORREGIDAS AQUÍ)
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''')
    
    # Migración de columnas (Tu lógica original)
    columnas_nuevas = [("precio_v2", "REAL DEFAULT 0"), ("margen1", "REAL DEFAULT 100"), ("margen2", "REAL DEFAULT 100")]
    for col, tipo in columnas_nuevas:
        try:
            cursor.execute(f"ALTER TABLE productos ADD COLUMN {col} {tipo}")
        except sqlite3.OperationalError:
            pass 
        
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Menú Gestión")
menu = st.sidebar.radio("Ir a:", ["📦 Stock", "🧪 Gestión de Recetas", "🚀 Registrar Venta", "📊 Reportes y Excel"])

# ---------------------------------------------------------
# 1. STOCK
# ---------------------------------------------------------
if menu == "📦 Stock":
    st.subheader("Gestión de Inventario")
    conn = conectar()
    f1, f2 = st.columns(2)
    t_f = f1.selectbox("Filtrar por Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
    b_f = f2.text_input("Buscar por nombre...")
    
    query = "SELECT id, nombre, tipo, stock_actual, costo_u, precio_v, precio_v2 FROM productos WHERE 1=1"
    params = []
    if t_f != "TODOS":
        query += " AND UPPER(tipo) = UPPER(?)"; params.append(t_f)
    if b_f:
        query += " AND UPPER(nombre) LIKE UPPER(?)"; params.append(f"%{b_f}%")
    
    df = pd.read_sql_query(query, conn, params=params)
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# 2. RECETAS (LÓGICA ESPEJO DEL LOCAL - RECUPERA DATOS)
# ---------------------------------------------------------
elif menu == "🧪 Gestión de Recetas":
    st.subheader("Calculadora de Producción y Precios")
    conn = conectar()
    
    # Cargamos listas usando fetchall para evitar errores de tipo
    finales = conn.execute("SELECT id, nombre, margen1, margen2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    insumos = conn.execute("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'").fetchall()

    if finales:
        col_i, col_d = st.columns([1, 2])
        
        with col_i:
            v_sel = st.selectbox("Elegir Vela", [f[1] for f in finales])
            v_data = [f for f in finales if f[1] == v_sel][0]
            id_v_final = v_data[0]
            m1_db = safe_float(v_data[2])
            m2_db = safe_float(v_data[3])
            
            with st.form("add_ins"):
                st.write("### Vincular Materia Prima")
                i_sel = st.selectbox("Insumo", [i[1] for i in insumos]) if insumos else st.error("Sin insumos")
                i_cant = st.number_input("Cantidad", min_value=0.0)
                if st.form_submit_button("Añadir"):
                    id_i = [i for i in insumos if i[1] == i_sel][0][0]
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_final, id_i, i_cant))
                    conn.commit()
                    st.success("Añadido")
                    st.rerun()

        with col_d:
            st.write(f"### Composición Guardada: {v_sel}")
            # Query corregida: nombres de tabla explícitos para evitar OperationalError
            query_rec = f"""
                SELECT recetas.id, productos.nombre, recetas.cantidad, productos.costo_u, (recetas.cantidad * productos.costo_u)
                FROM recetas 
                JOIN productos ON recetas.id_insumo = productos.id
                WHERE recetas.id_final = {id_v_final}
            """
            rows = conn.execute(query_rec).fetchall()
            
            if rows:
                df_rec = pd.DataFrame(rows, columns=["ID", "Materia Prima", "Cantidad", "Costo U", "Subtotal"])
                st.table(df_rec[["Materia Prima", "Cantidad", "Costo U", "Subtotal"]])
                
                # Sumatoria de costos usando safe_float original
                costo_total = sum(safe_float(r[4]) for r in rows)
                
                st.divider()
                st.write("### 💰 Determinación de Precios de Venta")
                cm1, cm2 = st.columns(2)
                m1_in = cm1.number_input("Margen 1 %", value=m1_db)
                m2_in = cm2.number_input("Margen 2 %", value=m2_db)
                
                p1 = costo_total * (1 + m1_in/100)
                p2 = costo_total * (1 + m2_in/100)
                
                st.metric("COSTO TOTAL", f"$ {costo_total:,.2f}")
                cm1.metric("PRECIO L1", f"$ {p1:,.2f}")
                cm2.metric("PRECIO L2", f"$ {p2:,.2f}")
                
                if st.button("💾 GUARDAR PRECIOS EN STOCK"):
                    conn.execute("UPDATE productos SET precio_v=?, precio_v2=?, margen1=?, margen2=?, costo_u=? WHERE id=?", 
                                (p1, p2, m1_in, m2_in, costo_total, id_v_final))
                    conn.commit()
                    st.success("Inventario actualizado con éxito.")

                if st.button("🚀 REGISTRAR PRODUCCIÓN"):
                    cur = conn.cursor()
                    for r in rows:
                        cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (r[2], r[1]))
                    cur.execute("UPDATE productos SET stock_actual = stock_actual + 1 WHERE id = ?", (id_v_final,))
                    conn.commit()
                    st.success("Producción impactada e insumos descontados.")
            else:
                st.info("No hay componentes cargados para esta vela.")
    else:
        st.warning("Cargá un producto 'Final' en Stock primero.")

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
            p_s = [v for v in velas if v[0] == v_n][0]
            p_r = safe_float(p_s[1] if "1" in v_l else p_s[2])
            v_tot = st.number_input("Total Cobrado $", value=float(p_r * v_c))
            if st.form_submit_button("Confirmar Venta"):
                conn.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)", 
                            (datetime.now().strftime("%Y-%m-%d %H:%M"), v_n, v_c, v_tot))
                conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_c, v_n))
                conn.commit()
                st.success("Venta guardada.")

# ---------------------------------------------------------
# 4. REPORTES Y EXCEL (LÓGICA ORIGINAL)
# ---------------------------------------------------------
elif menu == "📊 Reportes y Excel":
    st.subheader("Historial de Caja y Exportación")
    conn = conectar()
    df_v = pd.read_sql_query("SELECT fecha, producto, total_venta FROM historial_ventas ORDER BY fecha DESC", conn)
    
    if not df_v.empty:
        st.metric("Total Ingresos", f"$ {df_v['total_venta'].sum():,.2f}")
        st.dataframe(df_v, use_container_width=True)
        
        # Función espejo de exportar_caja de tu archivo original
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_v.to_excel(writer, index=False, sheet_name='Ventas')
        
        st.download_button(
            label="📊 Exportar Historial a Excel",
            data=output.getvalue(),
            file_name=f"caja_velas_{datetime.now().strftime('%d_%m')}.xlsx",
            mime="application/vnd.ms-excel"
        )
