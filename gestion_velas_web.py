import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import io

# --- CONFIGURACIÓN ---
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
    
    for col, tipo in [("precio_v2", "REAL DEFAULT 0"), ("margen1", "REAL DEFAULT 100"), ("margen2", "REAL DEFAULT 100")]:
        try: cursor.execute(f"ALTER TABLE productos ADD COLUMN {col} {tipo}")
        except: pass
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Gestión Candela")
menu = st.sidebar.radio("Ir a:", [
    "📦 Inventario y Alta", 
    "🧪 Recetas y Costeo", 
    "🏭 Fabricación",
    "💰 Registro de Compras", 
    "🚀 Registrar Venta", 
    "📊 Caja y Filtros",
    "📈 Rentabilidad x Producto"
])

# ---------------------------------------------------------
# 1. INVENTARIO Y ALTA (RESTAURADO)
# ---------------------------------------------------------
if menu == "📦 Inventario y Alta":
    st.subheader("Gestión de Stock")
    conn = conectar()
    with st.expander("➕ DAR DE ALTA NUEVO PRODUCTO / INSUMO"):
        with st.form("alta_p"):
            c1, c2 = st.columns(2)
            n_nom = c1.text_input("Nombre")
            n_tip = c2.selectbox("Tipo", ["Insumo", "Final", "Herramienta", "Packaging"])
            n_uni = c1.selectbox("Unidad", ["Gr", "Ml", "Un", "Kg"])
            n_stk = c2.number_input("Stock Inicial", min_value=0.0)
            n_min = c1.number_input("Stock Mínimo", min_value=0.0)
            n_cst = c2.number_input("Costo Unitario", min_value=0.0)
            if st.form_submit_button("Guardar"):
                conn.execute("INSERT INTO productos (nombre, tipo, unidad, stock_actual, stock_minimo, costo_u) VALUES (?,?,?,?,?,?)",
                            (n_nom, n_tip, n_uni, n_stk, n_min, n_cst))
                conn.commit(); st.success("Registrado"); st.rerun()
    df = pd.read_sql_query("SELECT * FROM productos", conn)
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# 2. RECETAS Y COSTEO (BLINDADO - SIN JOIN)
# ---------------------------------------------------------
elif menu == "🧪 Recetas y Costeo":
    st.subheader("Ingeniería de Costos y Recetas")
    conn = conectar()
    finales = conn.execute("SELECT id, nombre, margen1, margen2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    insumos_db = conn.execute("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'").fetchall()

    if finales:
        col1, col2 = st.columns([1, 2])
        with col1:
            v_sel = st.selectbox("Producto Final", [f[1] for f in finales])
            v_data = [f for f in finales if f[1] == v_sel][0]
            id_v_f = int(v_data[0])
            with st.form("add_ins"):
                i_sel = st.selectbox("Insumo", [i[1] for i in insumos_db])
                i_cant = st.number_input("Cantidad", min_value=0.0)
                if st.form_submit_button("Vincular"):
                    id_i = [i for i in insumos_db if i[1] == i_sel][0][0]
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_f, id_i, i_cant))
                    conn.commit(); st.rerun()

        with col2:
            st.write(f"### Componentes de {v_sel}")
            # Mapeo manual para evitar OperationalError en la nube
            componentes = conn.execute("SELECT id_insumo, cantidad FROM recetas WHERE id_final = ?", (id_v_f,)).fetchall()
            lista_tabla = []
            costo_acum = 0.0
            for id_i, cant in componentes:
                p = conn.execute("SELECT nombre, costo_u FROM productos WHERE id = ?", (id_i,)).fetchone()
                if p:
                    sub = cant * safe_float(p[1])
                    costo_acum += sub
                    lista_tabla.append([p[0], cant, safe_float(p[1]), sub])
            
            if lista_tabla:
                df_r = pd.DataFrame(lista_tabla, columns=["Insumo", "Cant.", "Costo U", "Subtotal"])
                st.table(df_r)
                st.divider()
                modo = st.radio("Cálculo por:", ["Margen %", "Precio Final $"], horizontal=True)
                c1, c2 = st.columns(2)
                if modo == "Margen %":
                    m1 = c1.number_input("Margen L1 %", value=safe_float(v_data[2]))
                    m2 = c2.number_input("Margen L2 %", value=safe_float(v_data[3]))
                    p1, p2 = costo_acum * (1 + m1/100), costo_acum * (1 + m2/100)
                else:
                    p1 = c1.number_input("Precio L1 $", value=costo_acum * (1 + safe_float(v_data[2])/100))
                    p2 = c2.number_input("Precio L2 $", value=costo_acum * (1 + safe_float(v_data[3])/100))
                    m1 = ((p1 / costo_acum) - 1) * 100 if costo_acum > 0 else 0
                    m2 = ((p2 / costo_acum) - 1) * 100 if costo_acum > 0 else 0
                st.info(f"Costo: ${costo_acum:,.2f} | L1: {m1:.1f}% | L2: {m2:.1f}%")
                if st.button("💾 GUARDAR PRECIOS"):
                    conn.execute("UPDATE productos SET precio_v=?, precio_v2=?, margen1=?, margen2=?, costo_u=? WHERE id=?", (p1, p2, m1, m2, costo_acum, id_v_f))
                    conn.commit(); st.success("Actualizado")
            else: st.info("Sin receta.")

# ---------------------------------------------------------
# 3. FABRICACIÓN (RESTAURADO)
# ---------------------------------------------------------
elif menu == "🏭 Fabricación":
    st.subheader("Registro de Producción")
    conn = conectar()
    finales = conn.execute("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    v_prod = st.selectbox("Producto a Fabricar", [f[1] for f in finales])
    v_cant = st.number_input("Cantidad de Unidades", min_value=1.0, step=1.0)
    
    if st.button("🚀 PROCESAR FABRICACIÓN"):
        id_f = [f for f in finales if f[1] == v_prod][0][0]
        # Buscar receta
        receta = conn.execute("SELECT id_insumo, cantidad FROM recetas WHERE id_final = ?", (id_f,)).fetchall()
        if receta:
            # Descontar insumos y sumar final
            for id_i, cant_u in receta:
                conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE id = ?", (cant_u * v_cant, id_i))
            conn.execute("UPDATE productos SET stock_actual = stock_actual + ? WHERE id = ?", (v_cant, id_f))
            conn.commit(); st.success(f"Fabricación de {v_cant} {v_prod} completada y stock actualizado.")
        else: st.error("Este producto no tiene una receta vinculada.")

# ---------------------------------------------------------
# 4. COMPRAS Y VENTAS (RESTAURADO: FORMA DE PAGO Y EDICIÓN)
# ---------------------------------------------------------
elif menu == "💰 Registro de Compras":
    st.subheader("Cargar Compras")
    conn = conectar()
    ins = conn.execute("SELECT nombre FROM productos WHERE UPPER(tipo) = 'INSUMO'").fetchall()
    with st.form("f_c"):
        i_nom = st.selectbox("Insumo", [i[0] for i in ins])
        i_can = st.number_input("Cantidad", min_value=0.01)
        i_tot = st.number_input("Costo Total $")
        i_pag = st.selectbox("Pago", ["Efectivo", "Mercado Pago", "Transferencia"])
        if st.form_submit_button("Confirmar"):
            conn.execute("UPDATE productos SET stock_actual = stock_actual + ?, costo_u = ? WHERE nombre = ?", (i_can, i_tot/i_can, i_nom))
            conn.execute("INSERT INTO historial_compras (fecha, item_nombre, cantidad, costo_total, metodo_pago) VALUES (?,?,?,?,?)",
                        (datetime.now().strftime("%Y-%m-%d %H:%M"), i_nom, i_can, i_tot, i_pag))
            conn.commit(); st.success("Compra cargada."); st.rerun()

elif menu == "🚀 Registrar Venta":
    st.subheader("Nueva Venta")
    conn = conectar()
    velas = conn.execute("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    with st.form("f_v"):
        c1, c2 = st.columns(2)
        f_v = c1.date_input("Fecha", date.today())
        h_v = c2.time_input("Hora", datetime.now().time())
        v_nom = st.selectbox("Producto", [v[0] for v in velas])
        v_can = st.number_input("Cantidad", min_value=1.0)
        v_pag = st.selectbox("Pago", ["Efectivo", "Mercado Pago", "Transferencia"])
        p_ref = [v for v in velas if v[0] == v_nom][0]
        v_tot = st.number_input("Monto Cobrado $ (Editable)", value=float(p_ref[1] * v_can))
        if st.form_submit_button("Vender"):
            f_s = f"{f_v.strftime('%Y-%m-%d')} {h_v.strftime('%H:%M')}"
            conn.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (?,?,?,?,?)",
                        (f_s, v_nom, v_can, v_tot, v_pag))
            conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_can, v_nom))
            conn.commit(); st.success("Venta registrada.")

# ---------------------------------------------------------
# 5. CAJA Y EXCEL (RESTAURADO: FILTROS POR FECHA Y TOTALES)
# ---------------------------------------------------------
elif menu == "📊 Caja y Filtros":
    st.subheader("Balance Mensual")
    conn = conectar()
    c1, c2 = st.columns(2)
    d1, d2 = c1.date_input("Desde", date(date.today().year, date.today().month, 1)), c2.date_input("Hasta", date.today())
    df_v = pd.read_sql_query("SELECT fecha, 'VENTA' as Tipo, producto as Detalle, total_venta as Monto FROM historial_ventas", conn)
    df_c = pd.read_sql_query("SELECT fecha, 'COMPRA' as Tipo, item_nombre as Detalle, -costo_total as Monto FROM historial_compras", conn)
    df_caja = pd.concat([df_v, df_c])
    df_caja['fecha_dt'] = pd.to_datetime(df_caja['fecha'], errors='coerce').dt.date
    df_f = df_caja[(df_caja['fecha_dt'] >= d1) & (df_caja['fecha_dt'] <= d2)].sort_values(by="fecha", ascending=False)
    if not df_f.empty:
        st.metric("SALDO PERÍODO", f"$ {df_f['Monto'].sum():,.2f}")
        st.dataframe(df_f[["fecha", "Tipo", "Detalle", "Monto"]], use_container_width=True)
        output = io.BytesIO()
        df_f.to_excel(output, index=False, engine='openpyxl')
        st.download_button("📊 Exportar Excel", output.getvalue(), f"caja_{d1}.xlsx")

# ---------------------------------------------------------
# 6. ANÁLISIS DE RENTABILIDAD POR PRODUCTO (NUEVA MEJORA)
# ---------------------------------------------------------
elif menu == "📈 Rentabilidad x Producto":
    st.subheader("Análisis Acumulado de Ventas y Costos")
    conn = conectar()
    
    # Selectores de fecha para el análisis
    c1, c2 = st.columns(2)
    d_ini = c1.date_input("Desde", date(date.today().year, date.today().month, 1), key="rent_desde")
    d_fin = c2.date_input("Hasta", date.today(), key="rent_hasta")

    # Query para traer ventas con el costo guardado en el momento o el actual
    # Usamos un JOIN para obtener el costo_u histórico (o actual) del producto
    query_analisis = """
        SELECT 
            v.producto, 
            SUM(v.cantidad) as cant_total, 
            SUM(v.total_venta) as venta_total,
            p.costo_u
        FROM historial_ventas v
        JOIN productos p ON v.producto = p.nombre
        WHERE v.fecha >= ? AND v.fecha <= ?
        GROUP BY v.producto
    """
    
    # Formateamos fechas para el filtro SQL
    f_ini_s = d_ini.strftime('%Y-%m-%d 00:00')
    f_fin_s = d_fin.strftime('%Y-%m-%d 23:59')
    
    rows = conn.execute(query_analisis, (f_ini_s, f_fin_s)).fetchall()
    
    datos_rentabilidad = []
    for r in rows:
        nombre_p = r[0]
        cant_v = safe_float(r[1])
        monto_v = safe_float(r[2])
        costo_unit = safe_float(r[3])
        
        costo_acumulado = cant_v * costo_unit
        diferencia = monto_v - costo_acumulado
        # Calcular margen real sobre venta
        margen_real = (diferencia / monto_v * 100) if monto_v > 0 else 0
        
        datos_rentabilidad.append({
            "Producto": nombre_p,
            "Cant. Vendida": cant_v,
            "Monto Ventas ($)": monto_v,
            "Costo Total ($)": costo_acumulado,
            "Diferencia ($)": diferencia,
            "Margen Real (%)": f"{margen_real:.1f}%"
        })

    if datos_rentabilidad:
        df_rent = pd.DataFrame(datos_rentabilidad)
        
        # Métricas destacadas
        m1, m2, m3 = st.columns(3)
        m1.metric("Ventas Totales", f"$ {df_rent['Monto Ventas ($)'].sum():,.2f}")
        m2.metric("Costo Mercadería", f"$ {df_rent['Costo Total ($)'].sum():,.2f}")
        m3.metric("Ganancia Bruta", f"$ {df_rent['Diferencia ($)'].sum():,.2f}", delta_color="normal")

        # Tabla de análisis
        st.dataframe(df_rent, use_container_width=True, hide_index=True)
        
        # Botón de exportación a Excel (usando openpyxl para estabilidad en Cloud)
        output = io.BytesIO()
        df_rent.to_excel(output, index=False, engine='openpyxl')
        st.download_button(
            label="📊 Exportar Análisis a Excel",
            data=output.getvalue(),
            file_name=f"rentabilidad_{d_ini}_{d_fin}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("No se registraron ventas en el período seleccionado.")
