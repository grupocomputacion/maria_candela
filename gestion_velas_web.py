import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Velas Candela Pro - Cloud", layout="wide")

# ==========================================
# 1. FUNCIONES DE APOYO
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
    conn.commit()
    conn.close()

inicializar_db()

st.sidebar.title("🕯️ Velas Candela")
menu = st.sidebar.radio("Ir a:", ["📦 Inventario", "🧪 Recetas", "💰 Compras", "🚀 Ventas", "📊 Caja"])

# ---------------------------------------------------------
# 1. INVENTARIO
# ---------------------------------------------------------
if menu == "📦 Inventario":
    st.subheader("Control de Stock")
    conn = conectar()
    f1, f2 = st.columns(2)
    t_f = f1.selectbox("Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
    b_f = f2.text_input("Buscar producto...")
    df = pd.read_sql_query("SELECT id, nombre, tipo, stock_actual, costo_u, precio_v, precio_v2 FROM productos", conn)
    if t_f != "TODOS": df = df[df['tipo'] == t_f]
    if b_f: df = df[df['nombre'].str.contains(b_f, case=False)]
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# 2. RECETAS (CORREGIDO NAMEERROR)
# ---------------------------------------------------------
elif menu == "🧪 Recetas":
    st.subheader("Calculadora de Costos y Márgenes")
    conn = conectar()
    finales = conn.execute("SELECT id, nombre, margen1, margen2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    insumos = conn.execute("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'").fetchall()

    if finales:
        col_izq, col_der = st.columns([1, 2]) # Definición clara de columnas
        with col_izq:
            v_sel = st.selectbox("Elegir Vela", [f[1] for f in finales])
            v_data = [f for f in finales if f[1] == v_sel][0]
            id_v_f = v_data[0]
            with st.form("add_comp"):
                i_sel = st.selectbox("Insumo", [i[1] for i in insumos])
                i_cant = st.number_input("Cantidad", min_value=0.0)
                if st.form_submit_button("Añadir"):
                    id_i = [i for i in insumos if i[1] == i_sel][0][0]
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_f, id_i, i_cant))
                    conn.commit(); st.rerun()

        with col_der: # Ahora col_der existe correctamente
            st.write(f"### Composición: {v_sel}")
            rows = conn.execute("""
                SELECT recetas.id, productos.nombre, recetas.cantidad, productos.costo_u, (recetas.cantidad * productos.costo_u)
                FROM recetas JOIN productos ON recetas.id_insumo = productos.id
                WHERE recetas.id_final = ?""", (id_v_f,)).fetchall()
            if rows:
                df_rec = pd.DataFrame(rows, columns=["ID", "Insumo", "Cant.", "Costo U", "Subtotal"])
                st.table(df_rec[["Insumo", "Cant.", "Costo U", "Subtotal"]])
                costo_t = sum(r[4] for r in rows)
                
                st.divider()
                modo = st.radio("Cálculo por:", ["Margen %", "Precio Final $"], horizontal=True)
                c1, c2 = st.columns(2)
                if modo == "Margen %":
                    m1 = c1.number_input("Margen L1 %", value=safe_float(v_data[2]))
                    m2 = c2.number_input("Margen L2 %", value=safe_float(v_data[3]))
                    p1, p2 = costo_t * (1 + m1/100), costo_t * (1 + m2/100)
                else:
                    p1 = c1.number_input("Precio L1 $", value=costo_t * (1 + safe_float(v_data[2])/100))
                    p2 = c2.number_input("Precio L2 $", value=costo_t * (1 + safe_float(v_data[3])/100))
                    m1 = ((p1 / costo_t) - 1) * 100 if costo_t > 0 else 0
                    m2 = ((p2 / costo_t) - 1) * 100 if costo_t > 0 else 0
                
                st.info(f"Costo: ${costo_t:,.2f} | L1: {m1:.1f}% | L2: {m2:.1f}%")
                if st.button("💾 GUARDAR PRECIOS"):
                    conn.execute("UPDATE productos SET precio_v=?, precio_v2=?, margen1=?, margen2=?, costo_u=? WHERE id=?", (p1, p2, m1, m2, costo_t, id_v_f))
                    conn.commit(); st.success("Guardado")
            else: st.info("Sin receta.")

# ---------------------------------------------------------
# 4. VENTAS (EDITABLE)
# ---------------------------------------------------------
elif menu == "🚀 Ventas":
    st.subheader("Registrar Venta")
    conn = conectar()
    velas = conn.execute("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    with st.form("f_v"):
        c1, c2 = st.columns(2)
        f_v, h_v = c1.date_input("Fecha", date.today()), c2.time_input("Hora", datetime.now().time())
        v_prod = st.selectbox("Producto", [v[0] for v in velas])
        v_cant = st.number_input("Cantidad", min_value=1.0)
        v_lista = st.radio("Lista", ["L1", "L2"], horizontal=True)
        p_ref = [v for v in velas if v[0] == v_prod][0]
        p_sug = safe_float(p_ref[1] if "1" in v_lista else p_ref[2])
        v_monto = st.number_input("Monto Total $", value=float(p_sug * v_cant))
        if st.form_submit_button("Confirmar"):
            f_str = f"{f_v.strftime('%Y-%m-%d')} {h_v.strftime('%H:%M')}"
            conn.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)", (f_str, v_prod, v_cant, v_monto))
            conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_cant, v_prod))
            conn.commit(); st.success("Venta guardada.")

# ---------------------------------------------------------
# 5. CAJA (CORREGIDO VALUEERROR FECHAS)
# ---------------------------------------------------------
elif menu == "📊 Caja":
    st.subheader("Balance y Filtros")
    conn = conectar()
    col1, col2 = st.columns(2)
    d1, d2 = col1.date_input("Desde", date(date.today().year, date.today().month, 1)), col2.date_input("Hasta", date.today())
    
    df_v = pd.read_sql_query("SELECT fecha, 'VENTA' as Tipo, producto as Detalle, total_venta as Monto FROM historial_ventas", conn)
    df_c = pd.read_sql_query("SELECT fecha, 'COMPRA' as Tipo, item_nombre as Detalle, -costo_total as Monto FROM historial_compras", conn)
    df_caja = pd.concat([df_v, df_c])
    
    # BLINDAJE CONTRA FECHAS MAL FORMADAS
    df_caja['fecha_dt'] = pd.to_datetime(df_caja['fecha'], errors='coerce').dt.date
    df_filt = df_caja[(df_caja['fecha_dt'] >= d1) & (df_caja['fecha_dt'] <= d2)].sort_values(by="fecha", ascending=False)
    
    if not df_filt.empty:
        st.metric("SALDO PERÍODO", f"$ {df_filt['Monto'].sum():,.2f}")
        st.dataframe(df_filt[["fecha", "Tipo", "Detalle", "Monto"]], use_container_width=True)
        output = io.BytesIO()
        df_filt.to_excel(output, index=False, engine='openpyxl')
        st.download_button("📊 Excel", output.getvalue(), f"caja_{d1}_{d2}.xlsx")
    else: st.warning("Sin movimientos.")
