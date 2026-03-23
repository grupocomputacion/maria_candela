import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Velas Candela Pro - Sistema Integral", layout="wide")

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
    # Estructura EXACTA de tu desarrollo local
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

    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, item_nombre TEXT, 
        cantidad REAL, costo_total REAL, metodo_pago TEXT)''')
    
    # Migración segura de columnas
    for col, tipo in [("precio_v2", "REAL DEFAULT 0"), ("margen1", "REAL DEFAULT 100"), ("margen2", "REAL DEFAULT 100")]:
        try: cursor.execute(f"ALTER TABLE productos ADD COLUMN {col} {tipo}")
        except sqlite3.OperationalError: pass
        
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Menú Gestión")
menu = st.sidebar.radio("Ir a:", [
    "📦 Stock e Inventario", 
    "🧪 Gestión de Recetas", 
    "💰 Registro de Compras", 
    "🚀 Registrar Venta", 
    "📊 Caja y Excel"
])

# ---------------------------------------------------------
# 1. STOCK
# ---------------------------------------------------------
if menu == "📦 Stock e Inventario":
    st.subheader("Control de Inventario")
    conn = conectar()
    f1, f2 = st.columns(2)
    t_f = f1.selectbox("Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
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
# 2. RECETAS (SOLUCIÓN DEFINITIVA AL OPERATIONALERROR)
# ---------------------------------------------------------
elif menu == "🧪 Gestión de Recetas":
    st.subheader("Calculadora de Producción y Costos")
    conn = conectar()
    finales = conn.execute("SELECT id, nombre, margen1, margen2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    insumos = conn.execute("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'").fetchall()

    if finales:
        col_i, col_d = st.columns([1, 2])
        with col_i:
            v_sel = st.selectbox("Elegir Vela", [f[1] for f in finales])
            v_data = [f for f in finales if f[1] == v_sel][0]
            id_v_f = v_data[0]
            
            with st.form("add_ins"):
                st.write("### Vincular Materia Prima")
                i_sel = st.selectbox("Insumo", [i[1] for i in insumos]) if insumos else st.error("Sin insumos")
                i_cant = st.number_input("Cantidad", min_value=0.0)
                if st.form_submit_button("Añadir"):
                    id_i = [i for i in insumos if i[1] == i_sel][0][0]
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_f, id_i, i_cant))
                    conn.commit(); st.success("Añadido"); st.rerun()

        with col_d:
            st.write(f"### Composición: {v_sel}")
            # Query blindada usando nombres de tabla explícitos sin alias
            query_rec = f"""
                SELECT recetas.id, productos.nombre, recetas.cantidad, productos.costo_u, (recetas.cantidad * productos.costo_u)
                FROM recetas JOIN productos ON recetas.id_insumo = productos.id
                WHERE recetas.id_final = {id_v_f}
            """
            rows = conn.execute(query_rec).fetchall()
            if rows:
                df_rec = pd.DataFrame(rows, columns=["ID", "Insumo", "Cantidad", "Costo U", "Subtotal"])
                st.table(df_rec[["Insumo", "Cantidad", "Costo U", "Subtotal"]])
                costo_t = sum(safe_float(r[4]) for r in rows)
                
                st.divider()
                cm1, cm2 = st.columns(2)
                m1_in = cm1.number_input("Margen 1 %", value=safe_float(v_data[2]))
                m2_in = cm2.number_input("Margen 2 %", value=safe_float(v_data[3]))
                p1 = costo_t * (1 + m1_in/100); p2 = costo_t * (1 + m2_in/100)
                
                st.metric("COSTO TOTAL", f"$ {costo_t:,.2f}")
                cm1.metric("PRECIO L1", f"$ {p1:,.2f}"); cm2.metric("PRECIO L2", f"$ {p2:,.2f}")
                
                if st.button("💾 GUARDAR PRECIOS EN STOCK"):
                    conn.execute("UPDATE productos SET precio_v=?, precio_v2=?, margen1=?, margen2=?, costo_u=? WHERE id=?", (p1, p2, m1_in, m2_in, costo_t, id_v_f))
                    conn.commit(); st.success("Precios actualizados")
            else:
                st.info("No hay receta cargada.")

# ---------------------------------------------------------
# 3. REGISTRO DE COMPRAS
# ---------------------------------------------------------
elif menu == "💰 Registro de Compras":
    st.subheader("Cargar Insumos y Gastos")
    conn = conectar()
    insumos_db = conn.execute("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'").fetchall()
    
    with st.form("compra_form"):
        i_nom = st.selectbox("Insumo Comprado", [i[1] for i in insumos_db])
        i_cant = st.number_input("Cantidad Comprada", min_value=0.0)
        i_total = st.number_input("Costo Total $")
        i_pago = st.selectbox("Método de Pago", ["Efectivo", "Mercado Pago", "Transferencia"])
        
        if st.form_submit_button("Confirmar Compra"):
            nuevo_costo_u = i_total / i_cant if i_cant > 0 else 0
            conn.execute("UPDATE productos SET stock_actual = stock_actual + ?, costo_u = ? WHERE nombre = ?", (i_cant, nuevo_costo_u, i_nom))
            conn.execute("INSERT INTO historial_compras (fecha, item_nombre, cantidad, costo_total, metodo_pago) VALUES (?,?,?,?,?)",
                        (datetime.now().strftime("%Y-%m-%d %H:%M"), i_nom, i_cant, i_total, i_pago))
            conn.commit(); st.success("Stock y costos actualizados."); st.rerun()

# ---------------------------------------------------------
# 4. REGISTRAR VENTA (CORREGIDO: FECHA Y MONTO EDITABLE)
# ---------------------------------------------------------
elif menu == "🚀 Registrar Venta":
    st.subheader("Registrar Venta")
    conn = conectar()
    velas = conn.execute("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    
    if velas:
        with st.form("vt_editable"):
            c1, c2 = st.columns(2)
            v_fecha = c1.date_input("Fecha de la venta", datetime.now())
            v_hora = c2.time_input("Hora", datetime.now().time())
            v_n = st.selectbox("Producto", [v[0] for v in velas])
            v_c = st.number_input("Cantidad", min_value=1.0)
            v_l = st.radio("Lista de Precios", ["L1 (Minorista)", "L2 (Mayorista)"], horizontal=True)
            
            p_s = [v for v in velas if v[0] == v_n][0]
            precio_ref = safe_float(p_s[1] if "1" in v_l else p_s[2])
            
            # Campo de monto editable
            v_monto = st.number_input("Monto Total Cobrado $", value=float(precio_ref * v_c))
            pago = st.selectbox("Método de Pago", ["Efectivo", "Mercado Pago", "Transferencia"])
            
            if st.form_submit_button("Confirmar Venta"):
                fecha_f = f"{v_fecha.strftime('%Y-%m-%d')} {v_hora.strftime('%H:%M')}"
                conn.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (?,?,?,?,?)", 
                            (fecha_f, v_n, v_c, v_monto, pago))
                conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_c, v_n))
                conn.commit(); st.success("Venta guardada exitosamente.")

# ---------------------------------------------------------
# 5. CAJA Y EXCEL (CORREGIDO: MOTOR OPENPYXL)
# ---------------------------------------------------------
elif menu == "📊 Caja y Excel":
    st.subheader("Historial de Movimientos")
    conn = conectar()
    df_v = pd.read_sql_query("SELECT fecha, 'VENTA' as Tipo, producto as Detalle, total_venta as Monto FROM historial_ventas", conn)
    df_c = pd.read_sql_query("SELECT fecha, 'COMPRA' as Tipo, item_nombre as Detalle, -costo_total as Monto FROM historial_compras", conn)
    df_final = pd.concat([df_v, df_c]).sort_values(by="fecha", ascending=False)
    
    if not df_final.empty:
        st.metric("Saldo Neto", f"$ {df_final['Monto'].sum():,.2f}")
        st.dataframe(df_final, use_container_width=True)
        
        # EXCEL CON MOTOR COMPATIBLE (openpyxl)
        output = io.BytesIO()
        df_final.to_excel(output, index=False, engine='openpyxl')
        
        st.download_button(label="📊 Descargar Caja en Excel", data=output.getvalue(), 
                           file_name=f"caja_{datetime.now().strftime('%d_%m')}.xlsx", 
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
