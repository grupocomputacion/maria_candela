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
    # Estructura EXACTA del local
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
    
    # Migración segura
    for col, tipo in [("precio_v2", "REAL DEFAULT 0"), ("margen1", "REAL DEFAULT 100"), ("margen2", "REAL DEFAULT 100")]:
        try: cursor.execute(f"ALTER TABLE productos ADD COLUMN {col} {tipo}")
        except: pass
        
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Velas Candela")
menu = st.sidebar.radio("Ir a:", [
    "📦 Inventario", 
    "🧪 Gestión de Recetas", 
    "💰 Compras", 
    "🚀 Registrar Venta", 
    "📊 Caja y Reportes"
])

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
    if t_f != "TODOS":
        df = df[df['tipo'] == t_f]
    if b_f:
        df = df[df['nombre'].str.contains(b_f, case=False)]
    
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# 2. RECETAS (SOLUCIÓN DEFINITIVA AL ERROR SQL)
# ---------------------------------------------------------
elif menu == "🧪 Gestión de Recetas":
    st.subheader("Calculadora de Costos y Determinación de Margen")
    conn = conectar()
    finales = conn.execute("SELECT id, nombre, margen1, margen2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    insumos = conn.execute("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'").fetchall()

    if finales:
        col_i, col_d = st.columns([1, 2])
        with col_i:
            v_sel = st.selectbox("Elegir Vela", [f[1] for f in finales])
            v_data = [f for f in finales if f[1] == v_sel][0]
            id_v_f = v_data[0]
            
            with st.form("add_comp"):
                st.write("### Añadir Insumo")
                i_sel = st.selectbox("Insumo", [i[1] for i in insumos])
                i_cant = st.number_input("Cantidad", min_value=0.0)
                if st.form_submit_button("Añadir a Receta"):
                    id_i = [i for i in insumos if i[1] == i_sel][0][0]
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_f, id_i, i_cant))
                    conn.commit(); st.rerun()

        with col_der:
            st.write(f"### Composición de: {v_sel}")
            # QUERY PARAMETRIZADA: Evita el OperationalError
            rows = conn.execute("""
                SELECT recetas.id, productos.nombre, recetas.cantidad, productos.costo_u, (recetas.cantidad * productos.costo_u)
                FROM recetas 
                INNER JOIN productos ON recetas.id_insumo = productos.id
                WHERE recetas.id_final = ?
            """, (id_v_f,)).fetchall()
            
            if rows:
                df_rec = pd.DataFrame(rows, columns=["ID", "Insumo", "Cant.", "Costo U", "Subtotal"])
                st.table(df_rec[["Insumo", "Cant.", "Costo U", "Subtotal"]])
                costo_t = sum(r[4] for r in rows)
                
                st.divider()
                st.write("### 💰 Calculadora de Precios")
                c1, c2 = st.columns(2)
                
                # Lógica para elegir Margen o Precio Final
                modo = st.radio("Método de cálculo:", ["Por Margen (%)", "Por Precio Final ($)"], horizontal=True)
                
                if modo == "Por Margen (%)":
                    m1 = c1.number_input("Margen Lista 1 %", value=safe_float(v_data[2]))
                    m2 = c2.number_input("Margen Lista 2 %", value=safe_float(v_data[3]))
                    p1 = costo_t * (1 + m1/100)
                    p2 = costo_t * (1 + m2/100)
                else:
                    p1 = c1.number_input("Precio Final Lista 1 $", value=costo_t * (1 + safe_float(v_data[2])/100))
                    p2 = c2.number_input("Precio Final Lista 2 $", value=costo_t * (1 + safe_float(v_data[3])/100))
                    m1 = ((p1 / costo_t) - 1) * 100 if costo_t > 0 else 0
                    m2 = ((p2 / costo_t) - 1) * 100 if costo_t > 0 else 0

                st.info(f"Costo Base: ${costo_t:,.2f} | Margen L1: {m1:.1f}% | Margen L2: {m2:.1f}%")
                
                if st.button("💾 REGISTRAR PRECIOS Y MÁRGENES"):
                    conn.execute("UPDATE productos SET precio_v=?, precio_v2=?, margen1=?, margen2=?, costo_u=? WHERE id=?", 
                                (p1, p2, m1, m2, costo_t, id_v_f))
                    conn.commit(); st.success("Datos guardados en Inventario.")
            else:
                st.info("No hay receta cargada.")

# ---------------------------------------------------------
# 4. REGISTRAR VENTA (EDITABLE)
# ---------------------------------------------------------
elif menu == "🚀 Registrar Venta":
    st.subheader("Nueva Venta")
    conn = conectar()
    velas = conn.execute("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    
    with st.form("form_venta"):
        c1, c2 = st.columns(2)
        f_v = c1.date_input("Fecha", date.today())
        h_v = c2.time_input("Hora", datetime.now().time())
        v_prod = st.selectbox("Producto", [v[0] for v in velas])
        v_cant = st.number_input("Cantidad", min_value=1.0)
        v_lista = st.radio("Lista", ["Minorista (L1)", "Mayorista (L2)"], horizontal=True)
        
        p_ref = [v for v in velas if v[0] == v_prod][0]
        precio_sug = safe_float(p_ref[1] if "1" in v_lista else p_ref[2])
        
        # Campo de monto editable
        v_monto = st.number_input("Monto Total Cobrado $ (Editable)", value=float(precio_sug * v_cant))
        v_pago = st.selectbox("Medio de Pago", ["Efectivo", "Mercado Pago", "Transferencia"])
        
        if st.form_submit_button("Confirmar Venta"):
            fecha_str = f"{f_v.strftime('%Y-%m-%d')} {h_v.strftime('%H:%M')}"
            conn.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (?,?,?,?,?)",
                        (fecha_str, v_prod, v_cant, v_monto, v_pago))
            conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_cant, v_prod))
            conn.commit(); st.success("Venta registrada.")

# ---------------------------------------------------------
# 5. CAJA Y REPORTES (FILTROS Y EXCEL)
# ---------------------------------------------------------
elif menu == "📊 Caja y Reportes":
    st.subheader("Balance de Caja y Filtros")
    conn = conectar()
    
    col1, col2 = st.columns(2)
    d_desde = col1.date_input("Desde", date(date.today().year, date.today().month, 1))
    d_hasta = col2.date_input("Hasta", date.today())
    
    df_v = pd.read_sql_query("SELECT fecha, 'VENTA' as Tipo, producto as Detalle, total_venta as Monto FROM historial_ventas", conn)
    df_c = pd.read_sql_query("SELECT fecha, 'COMPRA' as Tipo, item_nombre as Detalle, -costo_total as Monto FROM historial_compras", conn)
    df_caja = pd.concat([df_v, df_c])
    df_caja['fecha_dt'] = pd.to_datetime(df_caja['fecha']).dt.date
    
    # Aplicar Filtro
    df_filt = df_caja[(df_caja['fecha_dt'] >= d_desde) & (df_caja['fecha_dt'] <= d_hasta)].sort_values(by="fecha", ascending=False)
    
    if not df_filt.empty:
        st.metric("SALDO TOTAL PERÍODO", f"$ {df_filt['Monto'].sum():,.2f}")
        st.dataframe(df_filt[["fecha", "Tipo", "Detalle", "Monto"]], use_container_width=True)
        
        # EXCEL (Usando motor compatible)
        output = io.BytesIO()
        df_filt.to_excel(output, index=False, engine='openpyxl')
        st.download_button(label="📊 Descargar este filtro a Excel", data=output.getvalue(), 
                           file_name=f"caja_{d_desde}_{d_hasta}.xlsx", 
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.warning("No hay movimientos en las fechas seleccionadas.")
