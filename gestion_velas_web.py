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
    # check_same_thread=False es vital para evitar errores de concurrencia en la nube
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()
    
    # Tabla Productos (Estructura Base idéntica al local)
    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT, 
        unidad TEXT, stock_actual REAL DEFAULT 0, stock_minimo REAL DEFAULT 0,
        costo_u REAL DEFAULT 0, precio_v REAL DEFAULT 0, 
        precio_v2 REAL DEFAULT 0, margen1 REAL DEFAULT 100, margen2 REAL DEFAULT 100)''')
    
    # Tabla Recetas
    cursor.execute('''CREATE TABLE IF NOT EXISTS recetas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, id_final INTEGER, 
        id_insumo INTEGER, cantidad REAL)''')
    
    # Tabla Historial Ventas
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''')
    
    # MIGRACIÓN SEGURA: Forzamos que existan las columnas de tu local
    columnas_chequeo = [("precio_v2", "REAL DEFAULT 0"), ("margen1", "REAL DEFAULT 100"), ("margen2", "REAL DEFAULT 100")]
    for col, tipo in columnas_chequeo:
        try:
            cursor.execute(f"ALTER TABLE productos ADD COLUMN {col} {tipo}")
        except sqlite3.OperationalError:
            pass 
        
    conn.commit()
    conn.close()

# Inicialización al arrancar
inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Menú Gestión")
menu = st.sidebar.radio("Ir a:", ["📦 Stock", "🧪 Recetas y Costeo", "🚀 Ventas", "📊 Reportes y Excel"])

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
# 2. RECETAS (LÓGICA 100% ESPEJO - RECUPERA DATOS EXISTENTES)
# ---------------------------------------------------------
elif menu == "🧪 Recetas y Costeo":
    st.subheader("Calculadora de Producción y Precios")
    conn = conectar()
    
    # Obtenemos datos para los selectores
    finales = conn.execute("SELECT id, nombre, margen1, margen2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    insumos = conn.execute("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'").fetchall()

    if finales:
        col_izq, col_der = st.columns([1, 2])
        
        with col_izq:
            v_sel = st.selectbox("Elegir Vela", [f[1] for f in finales])
            v_data = [f for f in finales if f[1] == v_sel][0]
            id_v_final = v_data[0]
            
            with st.form("add_insumo_web"):
                st.write("### Vincular Materia Prima")
                n_ins = [i[1] for i in insumos]
                i_sel = st.selectbox("Insumo", n_ins) if n_ins else st.error("Sin insumos")
                i_cant = st.number_input("Cantidad", min_value=0.0)
                if st.form_submit_button("Añadir"):
                    id_i = [i for i in insumos if i[1] == i_sel][0][0]
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_final, id_i, i_cant))
                    conn.commit()
                    st.success("Añadido")
                    st.rerun()

        with col_der:
            st.write(f"### Composición Guardada: {v_sel}")
            # QUERY BLINDADA: Sin alias para evitar OperationalError
            query_rec = f"""
                SELECT recetas.id, productos.nombre, recetas.cantidad, productos.costo_u, (recetas.cantidad * productos.costo_u)
                FROM recetas 
                JOIN productos ON recetas.id_insumo = productos.id
                WHERE recetas.id_final = {id_v_final}
            """
            cur_r = conn.cursor()
            cur_r.execute(query_rec)
            rows = cur_r.fetchall()
            
            if rows:
                # Usamos los índices numéricos exactos de tu fetchall local
                df_rec = pd.DataFrame(rows, columns=["ID", "Insumo", "Cantidad", "Costo U", "Subtotal"])
                st.table(df_rec[["Insumo", "Cantidad", "Costo U", "Subtotal"]])
                
                costo_total = sum(safe_float(r[4]) for r in rows)
                
                st.divider()
                st.write("### 💰 Determinación de Precios (M1/M2)")
                cm1, cm2 = st.columns(2)
                m1_val = cm1.number_input("Margen 1 %", value=safe_float(v_data[2]))
                m2_val = cm2.number_input("Margen 2 %", value=safe_float(v_data[3]))
                
                p1 = costo_total * (1 + m1_val/100)
                p2 = costo_total * (1 + m2_val/100)
                
                st.metric("COSTO TOTAL COMPONENTES", f"$ {costo_total:,.2f}")
                cm1.metric("PRECIO L1", f"$ {p1:,.2f}")
                cm2.metric("PRECIO L2", f"$ {p2:,.2f}")
                
                if st.button("💾 GUARDAR PRECIOS EN STOCK"):
                    conn.execute("UPDATE productos SET precio_v=?, precio_v2=?, margen1=?, margen2=?, costo_u=? WHERE id=?", 
                                (p1, p2, m1_val, m2_val, costo_total, id_v_final))
                    conn.commit()
                    st.success("Precios actualizados en inventario")

                if st.button("🚀 REGISTRAR PRODUCCIÓN (+1)"):
                    cur_p = conn.cursor()
                    for r in rows: # r[2] es cantidad, r[1] es nombre_insumo
                        cur_p.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (r[2], r[1]))
                    cur_p.execute("UPDATE productos SET stock_actual = stock_actual + 1 WHERE id = ?", (id_v_final,))
                    conn.commit()
                    st.success("Stock impactado e insumos descontados.")
                    st.rerun()
            else:
                st.info("No hay componentes cargados para esta vela.")
    else:
        st.warning("Cargá un producto 'Final' en Stock.")

# ---------------------------------------------------------
# 3. VENTAS (LÓGICA LISTA 1 / LISTA 2)
# ---------------------------------------------------------
elif menu == "🚀 Ventas":
    st.subheader("Registrar Venta")
    conn = conectar()
    velas = conn.execute("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    if velas:
        with st.form("venta_web"):
            v_n = st.selectbox("Vela", [v[0] for v in velas])
            v_c = st.number_input("Cantidad", min_value=1.0)
            v_l = st.radio("Lista", ["L1 (Minorista)", "L2 (Mayorista)"])
            # v[1] es precio_v, v[2] es precio_v2
            p_s = [v for v in velas if v[0] == v_n][0]
            p_r = safe_float(p_s[1] if "1" in v_l else p_s[2])
            v_tot = st.number_input("Monto Cobrado $", value=float(p_r * v_c))
            if st.form_submit_button("Confirmar Venta"):
                conn.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)", 
                            (datetime.now().strftime("%Y-%m-%d %H:%M"), v_n, v_c, v_tot))
                conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_c, v_n))
                conn.commit()
                st.success("Venta guardada.")

# ---------------------------------------------------------
# 4. REPORTES Y EXCEL (EXPORTACIÓN FIEL AL LOCAL)
# ---------------------------------------------------------
elif menu == "📊 Reportes y Excel":
    st.subheader("Historial de Caja y Exportación")
    conn = conectar()
    df_v = pd.read_sql_query("SELECT fecha, producto, total_venta FROM historial_ventas ORDER BY fecha DESC", conn)
    
    if not df_v.empty:
        st.metric("Total Recaudado", f"$ {df_v['total_venta'].sum():,.2f}")
        st.dataframe(df_v, use_container_width=True)
        
        # Función espejo de exportar_caja de tu local
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_v.to_excel(writer, index=False, sheet_name='Ventas')
        
        st.download_button(
            label="📊 Exportar a Excel",
            data=output.getvalue(),
            file_name=f"caja_velas_{datetime.now().strftime('%d_%m')}.xlsx",
            mime="application/vnd.ms-excel"
        )
