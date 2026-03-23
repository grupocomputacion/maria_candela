import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
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
    
    # Migración de columnas (Tu lógica original para no borrar datos)
    for col, tipo in [("precio_v2", "REAL DEFAULT 0"), ("margen1", "REAL DEFAULT 100"), ("margen2", "REAL DEFAULT 100")]:
        try: cursor.execute(f"ALTER TABLE productos ADD COLUMN {col} {tipo}")
        except: pass
        
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Menú Gestión")
menu = st.sidebar.radio("Ir a:", [
    "📦 Inventario y Alta", 
    "🧪 Recetas y Costeo", 
    "💰 Registro Compras", 
    "🚀 Registrar Venta", 
    "📊 Caja y Filtros"
])

# ---------------------------------------------------------
# 1. ALTA Y STOCK (RESTAURADO)
# ---------------------------------------------------------
if menu == "📦 Inventario y Alta":
    st.subheader("Gestión de Inventario")
    conn = conectar()
    
    with st.expander("➕ DAR DE ALTA NUEVO PRODUCTO / INSUMO"):
        with st.form("alta_p"):
            c1, c2 = st.columns(2)
            n_nom = c1.text_input("Nombre del Item")
            n_tip = c2.selectbox("Tipo", ["Insumo", "Final", "Herramienta", "Packaging"])
            n_uni = c1.selectbox("Unidad", ["Gr", "Ml", "Un", "Kg"])
            n_stk = c2.number_input("Stock Inicial", min_value=0.0)
            n_min = c1.number_input("Stock Mínimo", min_value=0.0)
            n_cst = c2.number_input("Costo Unitario Inicial", min_value=0.0)
            if st.form_submit_button("Guardar en Base de Datos"):
                conn.execute("INSERT INTO productos (nombre, tipo, unidad, stock_actual, stock_minimo, costo_u) VALUES (?,?,?,?,?,?)",
                            (n_nom, n_tip, n_uni, n_stk, n_min, n_cst))
                conn.commit()
                st.success(f"{n_nom} registrado.")
                st.rerun()

    df = pd.read_sql_query("SELECT id, nombre, tipo, stock_actual, costo_u, precio_v, precio_v2 FROM productos", conn)
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# 2. RECETAS Y COSTEO (SOLUCIÓN DEFINITIVA)
# ---------------------------------------------------------
elif menu == "🧪 Recetas y Costeo":
    st.subheader("Calculadora de Producción y Rentabilidad")
    conn = conectar()
    cur = conn.cursor()
    
    finales = cur.execute("SELECT id, nombre, margen1, margen2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    insumos = cur.execute("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'").fetchall()

    if finales:
        c_i, c_d = st.columns([1, 2])
        with c_i:
            v_sel = st.selectbox("Elegir Vela", [f[1] for f in finales])
            v_data = [f for f in finales if f[1] == v_sel][0]
            id_v_f = int(v_data[0])
            
            with st.form("add_comp"):
                st.write("### Vincular Materia Prima")
                i_sel = st.selectbox("Insumo", [i[1] for i in insumos])
                i_cant = st.number_input("Cantidad", min_value=0.0, format="%.2f")
                if st.form_submit_button("Añadir"):
                    id_i = [i for i in insumos if i[1] == i_sel][0][0]
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_f, id_i, i_cant))
                    conn.commit(); st.rerun()

        with c_d:
            st.write(f"### Composición: {v_sel}")
            # BLINDAJE: Usamos IFNULL para evitar OperationalError por multiplicar valores vacíos
            sql_r = """
                SELECT r.id, p.nombre, IFNULL(r.cantidad, 0), IFNULL(p.costo_u, 0), (IFNULL(r.cantidad, 0) * IFNULL(p.costo_u, 0))
                FROM recetas r JOIN productos p ON r.id_insumo = p.id
                WHERE r.id_final = ?
            """
            rows = conn.execute(sql_r, (id_v_f,)).fetchall()
            
            if rows:
                df_rec = pd.DataFrame(rows, columns=["ID", "Insumo", "Cant.", "Costo U", "Subtotal"])
                st.table(df_rec[["Insumo", "Cant.", "Costo U", "Subtotal"]])
                
                costo_base = sum(safe_float(r[4]) for r in rows)
                st.divider()
                
                # FUNCIONALIDAD COSTEO ORIGINAL
                st.write("### 💰 Determinación de Precios de Venta")
                modo = st.radio("Método:", ["Margen %", "Precio Final $"], horizontal=True)
                cm1, cm2 = st.columns(2)
                
                if modo == "Margen %":
                    m1 = cm1.number_input("Margen L1 %", value=safe_float(v_data[2]))
                    m2 = cm2.number_input("Margen L2 %", value=safe_float(v_data[3]))
                    p1, p2 = costo_base * (1 + m1/100), costo_base * (1 + m2/100)
                else:
                    p1 = cm1.number_input("Precio Venta L1 $", value=costo_base * (1 + safe_float(v_data[2])/100))
                    p2 = cm2.number_input("Precio Venta L2 $", value=costo_base * (1 + safe_float(v_data[3])/100))
                    m1 = ((p1 / costo_base) - 1) * 100 if costo_base > 0 else 0
                    m2 = ((p2 / costo_base) - 1) * 100 if costo_base > 0 else 0

                st.info(f"Costo: ${costo_base:,.2f} | Margen L1: {m1:.1f}% | L2: {m2:.1f}%")
                
                if st.button("💾 GUARDAR PRECIOS EN INVENTARIO"):
                    conn.execute("UPDATE productos SET precio_v=?, precio_v2=?, margen1=?, margen2=?, costo_u=? WHERE id=?", 
                                (p1, p2, m1, m2, costo_base, id_v_f))
                    conn.commit(); st.success("Inventario actualizado.")
            else: st.info("Sin receta cargada.")

# ---------------------------------------------------------
# 3. REGISTRO COMPRAS (RESTAURADO)
# ---------------------------------------------------------
elif menu == "💰 Registro Compras":
    st.subheader("Cargar Insumos y Gastos")
    conn = conectar()
    ins_db = conn.execute("SELECT nombre FROM productos WHERE UPPER(tipo) = 'INSUMO'").fetchall()
    
    with st.form("form_c"):
        i_nom = st.selectbox("Insumo", [i[0] for i in ins_db])
        i_cant = st.number_input("Cantidad", min_value=0.01)
        i_total = st.number_input("Costo Total $", min_value=0.01)
        i_pago = st.selectbox("Forma de Pago", ["Efectivo", "Mercado Pago", "Transferencia"])
        if st.form_submit_button("Confirmar Compra"):
            costo_u = i_total / i_cant
            conn.execute("UPDATE productos SET stock_actual = stock_actual + ?, costo_u = ? WHERE nombre = ?", (i_cant, costo_u, i_nom))
            conn.execute("INSERT INTO historial_compras (fecha, item_nombre, cantidad, costo_total, metodo_pago) VALUES (?,?,?,?,?)",
                        (datetime.now().strftime("%Y-%m-%d %H:%M"), i_nom, i_cant, i_total, i_pago))
            conn.commit(); st.success("Stock y costos actualizados."); st.rerun()

# ---------------------------------------------------------
# 4. VENTAS (RESTAURADO: FORMA DE PAGO)
# ---------------------------------------------------------
elif menu == "🚀 Registrar Venta":
    st.subheader("Nueva Venta")
    conn = conectar()
    velas = conn.execute("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    with st.form("form_v"):
        c1, c2 = st.columns(2)
        f_v = c1.date_input("Fecha", date.today())
        h_v = c2.time_input("Hora", datetime.now().time())
        v_prod = st.selectbox("Producto", [v[0] for v in velas])
        v_cant = st.number_input("Cantidad", min_value=1.0)
        v_lista = st.radio("Lista", ["L1", "L2"], horizontal=True)
        p_ref = [v for v in velas if v[0] == v_prod][0]
        p_sug = safe_float(p_ref[1] if "1" in v_lista else p_ref[2])
        v_monto = st.number_input("Monto Cobrado $", value=float(p_sug * v_cant))
        v_pago = st.selectbox("Forma de Pago", ["Efectivo", "Mercado Pago", "Transferencia"]) # Restaurado
        if st.form_submit_button("Confirmar"):
            f_str = f"{f_v.strftime('%Y-%m-%d')} {h_v.strftime('%H:%M')}"
            conn.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (?,?,?,?,?)", 
                        (f_str, v_prod, v_cant, v_monto, v_pago))
            conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_cant, v_prod))
            conn.commit(); st.success("Venta guardada.")

# ---------------------------------------------------------
# 5. CAJA Y FILTROS (RESTAURADO: DIA/MES Y TOTALIZADOR)
# ---------------------------------------------------------
elif menu == "📊 Caja y Filtros":
    st.subheader("Balance Mensual y Exportación")
    conn = conectar()
    c1, c2 = st.columns(2)
    d1, d2 = c1.date_input("Desde", date(date.today().year, date.today().month, 1)), c2.date_input("Hasta", date.today())
    
    df_v = pd.read_sql_query("SELECT fecha, 'VENTA' as Tipo, producto as Detalle, total_venta as Monto, metodo_pago FROM historial_ventas", conn)
    df_c = pd.read_sql_query("SELECT fecha, 'COMPRA' as Tipo, item_nombre as Detalle, -costo_total as Monto, metodo_pago FROM historial_compras", conn)
    df_caja = pd.concat([df_v, df_c])
    
    df_caja['fecha_dt'] = pd.to_datetime(df_caja['fecha'], errors='coerce').dt.date
    df_filt = df_caja[(df_caja['fecha_dt'] >= d1) & (df_caja['fecha_dt'] <= d2)].sort_values(by="fecha", ascending=False)
    
    if not df_filt.empty:
        st.metric("SALDO TOTAL FILTRADO", f"$ {df_filt['Monto'].sum():,.2f}") # Totalizador restaurado
        st.dataframe(df_filt[["fecha", "Tipo", "Detalle", "Monto", "metodo_pago"]], use_container_width=True)
        output = io.BytesIO()
        df_filt.to_excel(output, index=False, engine='openpyxl')
        st.download_button("📊 Descargar Excel", output.getvalue(), f"caja_{d1}.xlsx")
    else: st.warning("Sin movimientos.")
