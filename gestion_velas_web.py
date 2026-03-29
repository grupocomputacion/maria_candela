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



# ==========================================
# MENÚ LATERAL - VERSIÓN 8.6 (REVISIÓN)
# ==========================================
st.sidebar.title("🕯️ Velas Control")
# Añadimos el número de versión para confirmar que el código se actualizó
st.sidebar.info("Versión del Sistema: 8.6.3 (Sincronizada)")

menu = st.sidebar.radio("Ir a:", [
    "📦 Inventario y Alta", 
    "🧪 Recetas y Costeo", 
    "🏭 Fabricación",
    "💰 Registro de Compras", 
    "🚀 Registrar Venta", 
    "📊 Caja y Filtros",
    "📈 Rentabilidad x Producto"
])

st.sidebar.divider()
if st.sidebar.button("Limpiar Caché de Sesión"):
    st.session_state.clear()
    st.rerun()
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


# ==========================================
# 🛍️ REGISTRAR VENTAS (V.8.5 - REPARACIÓN TOTAL)
# ==========================================
elif menu == "🛍️ Registrar Ventas":
    st.header("Registro de Ventas")
    
    # 1. Traemos los productos (quitamos filtros complejos para asegurar visibilidad)
    # Agregamos un try/except interno para capturar errores de base de datos
    try:
        df_prod = db_query("SELECT id, nombre, precio_sugerido, stock FROM productos")
    except Exception as e:
        st.error(f"Error técnico al leer productos: {e}")
        df_prod = None

    if df_prod is not None and not df_prod.empty:
        # Filtramos en memoria los que tienen stock para el selector
        productos_con_stock = df_prod[df_prod['stock'] > 0]
        
        if productos_con_stock.empty:
            st.warning("⚠️ Todos los productos figuran con Stock 0 en la base de datos.")
        else:
            with st.form("f_venta_corregida", clear_on_submit=False):
                st.subheader("Nueva Venta")
                
                # Selección de producto
                idx_prod = st.selectbox(
                    "Producto:",
                    productos_con_stock.index.tolist(),
                    format_func=lambda x: f"{productos_con_stock.loc[x, 'nombre']} (Stock: {productos_con_stock.loc[x, 'stock']})"
                )
                
                col_cant, col_precio = st.columns(2)
                
                cantidad = col_cant.number_input("Cantidad:", min_value=1, value=1)
                
                # Lógica de precio: Tomamos el sugerido pero permitimos edición TOTAL
                precio_unit_sug = float(productos_con_stock.loc[idx_prod, 'precio_sugerido'])
                sugerido_total = precio_unit_sug * cantidad
                
                # KEY IMPORTANTE: Para que Streamlit no pise lo que vos escribís
                monto_real_venta = col_precio.number_input(
                    "Monto TOTAL cobrado ($):", 
                    min_value=0.0, 
                    value=sugerido_total,
                    key="precio_venta_manual",
                    help="Si hiciste un descuento o cobraste extra, editá este número."
                )
                
                st.caption(f"💡 Referencia: El precio de lista para esta cantidad es ${sugerido_total}")
                
                c1, c2 = st.columns(2)
                cliente_nombre = c1.text_input("Cliente (opcional):")
                metodo_pago_sel = c2.selectbox("Forma de Pago:", ["Efectivo", "Transferencia", "Tarjeta"])
                
                # Agregamos fecha por si querés registrar una venta de ayer
                fecha_v = st.date_input("Fecha de la venta:", date.today())
                
                btn_guardar = st.form_submit_button("✅ CONFIRMAR Y REGISTRAR VENTA")

            # --- PROCESAMIENTO AL PRESIONAR BOTÓN ---
            if btn_guardar:
                # Recuperamos el valor que vos escribiste del session_state
                # Esto garantiza que si pusiste 800 en vez de 1000, se graben 800.
                precio_final_a_grabar = st.session_state.precio_venta_manual
                id_p = int(productos_con_stock.loc[idx_prod, 'id'])
                nombre_p = productos_con_stock.loc[idx_prod, 'nombre']
                
                try:
                    # 1. INSERTAR VENTA (Con commit explícito para que aparezca en la caja)
                    db_query("""
                        INSERT INTO ventas (id_producto, cantidad, precio_total, cliente, metodo_pago, fecha)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (id_p, cantidad, precio_final_a_grabar, cliente_nombre, metodo_pago_sel, fecha_v), commit=True)

                    # 2. DESCONTAR STOCK (Con commit explícito)
                    db_query("UPDATE productos SET stock = stock - ? WHERE id = ?", (cantidad, id_p), commit=True)

                    st.success(f"✔️ ¡Venta registrada! {nombre_p} por ${precio_final_a_grabar}")
                    
                    # Limpiamos el valor manual para la próxima venta
                    if 'precio_venta_manual' in st.session_state:
                        del st.session_state['precio_venta_manual']
                    
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al grabar: {e}. Avisar si el error persiste.")
    else:
        st.error("No se encontraron productos en la base de datos. Verifique la tabla 'productos'.")

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
