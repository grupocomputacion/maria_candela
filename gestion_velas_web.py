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
st.sidebar.info("Versión del Sistema: 8.6.5 (Sincronizada)")

menu = st.sidebar.radio("Ir a:", [
    "📦 Inventario y Alta", 
    "🧪 Recetas y Costeo", 
    "🏭 Fabricación",
    "💰 Registro de Compras", 
    "🚀 Registrar Ventas", 
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
# 🚀 REGISTRAR VENTAS (V.8.6.5 - COMPATIBILIDAD TOTAL)
# ==========================================
elif menu == "🚀 Registrar Ventas":
    st.header("Registro de Ventas")
    
    conn = conectar()
    # 1. Traemos los productos finales (que son los que se venden)
    try:
        # En tu tabla la columna se llama 'stock_actual' y el precio 'precio_v'
        df_prod = pd.read_sql_query("SELECT id, nombre, precio_v, stock_actual FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    except Exception as e:
        st.error(f"Error técnico al leer productos: {e}")
        df_prod = None

    if df_prod is not None and not df_prod.empty:
        # Filtramos los que tienen stock
        productos_con_stock = df_prod[df_prod['stock_actual'] > 0]
        
        if productos_con_stock.empty:
            st.warning("⚠️ No hay productos con stock disponible para vender.")
        else:
            with st.form("f_venta_corregida", clear_on_submit=False):
                st.subheader("Nueva Venta")
                
                # Selección de producto
                idx_prod = st.selectbox(
                    "Producto:",
                    productos_con_stock.index.tolist(),
                    format_func=lambda x: f"{productos_con_stock.loc[x, 'nombre']} (Stock: {productos_con_stock.loc[x, 'stock_actual']})"
                )
                
                col_cant, col_precio = st.columns(2)
                cantidad = col_cant.number_input("Cantidad:", min_value=1.0, step=1.0, value=1.0)
                
                # Lógica de precio sugerido
                precio_unit_sug = safe_float(productos_con_stock.loc[idx_prod, 'precio_v'])
                sugerido_total = precio_unit_sug * cantidad
                
                # Permite edición TOTAL (Atenciones o Extras)
                monto_real_venta = col_precio.number_input(
                    "Monto TOTAL cobrado ($):", 
                    min_value=0.0, 
                    value=sugerido_total,
                    key="precio_venta_manual"
                )
                
                st.caption(f"💡 Precio de lista sugerido: ${sugerido_total:,.2f}")
                
                c1, c2 = st.columns(2)
                metodo_pago_sel = c1.selectbox("Forma de Pago:", ["Efectivo", "Mercado Pago", "Transferencia"])
                fecha_v = st.date_input("Fecha de la venta:", date.today())
                
                btn_guardar = st.form_submit_button("✅ CONFIRMAR Y REGISTRAR VENTA")

            if btn_guardar:
                # Recuperamos el valor editado del session_state
                precio_final_a_grabar = st.session_state.precio_venta_manual
                nombre_p = productos_con_stock.loc[idx_prod, 'nombre']
                
                try:
                    # 1. INSERTAR EN HISTORIAL (Para que aparezca en Caja y Rentabilidad)
                    conn.execute("""
                        INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago)
                        VALUES (?, ?, ?, ?, ?)
                    """, (fecha_v.strftime("%Y-%m-%d"), nombre_p, cantidad, precio_final_a_grabar, metodo_pago_sel))

                    # 2. DESCONTAR STOCK ACTUAL
                    conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", 
                                (cantidad, nombre_p))

                    conn.commit()
                    st.success(f"✔️ Venta registrada: {nombre_p} por ${precio_final_a_grabar:,.2f}")
                    
                    # Limpiar memoria de sesión
                    if 'precio_venta_manual' in st.session_state:
                        del st.session_state['precio_venta_manual']
                    
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al grabar: {e}")
    else:
        st.info("No hay productos marcados como 'Final' en el inventario.")
    conn.close()


# ---------------------------------------------------------
# 5. CAJA Y EXCEL (V.8.9 - AJUSTES CON NEGATIVOS Y RESET)
# ---------------------------------------------------------
elif menu == "📊 Caja y Filtros":
    st.subheader("Balance y Control de Caja")
    conn = conectar()
    
    # --- PANEL DE AJUSTES MEJORADO ---
    with st.expander("⚙️ AJUSTES DE SALDO Y TRANSFERENCIAS"):
        # Inicializamos llaves en el session_state si no existen para poder limpiarlas
        if "adj_monto" not in st.session_state: st.session_state.adj_monto = 0.0
        if "adj_det" not in st.session_state: st.session_state.adj_det = ""

        with st.form("form_ajuste_caja_v89", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            tipo_aj = c1.selectbox("Tipo de Movimiento", ["Ajuste de Saldo", "Transferencia (Efectivo -> Destino)"])
            
            # Permitimos valores negativos (min_value=None)
            monto_aj = c2.number_input("Monto $ (use - para restar)", value=0.0, format="%.2f")
            pago_aj = c3.selectbox("Cuenta/Método", ["Efectivo", "Mercado Pago", "Transferencia", "Tarjeta"])
            
            det_aj = st.text_input("Detalle del ajuste", placeholder="Ej: Error de conteo, Gasto no anotado...")
            
            if st.form_submit_button("💾 APLICAR AJUSTE"):
                fecha_f = datetime.now().strftime("%Y-%m-%d %H:%M")
                
                try:
                    if tipo_aj == "Ajuste de Saldo":
                        # Si el monto es positivo va a Ventas, si es negativo a Compras (para que reste)
                        if monto_aj >= 0:
                            conn.execute("""
                                INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) 
                                VALUES (?, ?, ?, ?, ?)
                            """, (fecha_f, f"AJUSTE: {det_aj}", 0, monto_aj, pago_aj))
                        else:
                            # Convertimos el negativo a positivo para el 'costo_total' porque la resta la hace el SQL en el Balance
                            conn.execute("""
                                INSERT INTO historial_compras (fecha, item_nombre, cantidad, costo_total, metodo_pago) 
                                VALUES (?, ?, ?, ?, ?)
                            """, (fecha_f, f"AJUSTE: {det_aj}", 0, abs(monto_aj), pago_aj))
                    
                    else:
                        # Transferencia (Sale de Efectivo, entra a la cuenta seleccionada)
                        # Salida de Efectivo
                        conn.execute("""
                            INSERT INTO historial_compras (fecha, item_nombre, cantidad, costo_total, metodo_pago) 
                            VALUES (?, ?, ?, ?, ?)
                        """, (fecha_f, f"EGRESO TRANSF: {det_aj}", 0, monto_aj, "Efectivo"))
                        # Entrada al Destino
                        conn.execute("""
                            INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) 
                            VALUES (?, ?, ?, ?, ?)
                        """, (fecha_f, f"INGRESO TRANSF: {det_aj}", 0, monto_aj, pago_aj))
                    
                    conn.commit()
                    st.success("✅ Ajuste aplicado con éxito.")
                    # El rerun limpia el formulario por el 'clear_on_submit=True'
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al procesar ajuste: {e}")

    # --- RESTO DE LA LÓGICA DE VISUALIZACIÓN (Saldos y Tabla) ---
    c_f1, c_f2 = st.columns(2)
    d1 = c_f1.date_input("Desde", date(date.today().year, date.today().month, 1), key="caja_desde")
    d2 = c_f2.date_input("Hasta", date.today(), key="caja_hasta")
    
    # Consultas SQL unificadas
    df_v = pd.read_sql_query("SELECT fecha, 'VENTA' as Tipo, producto as Detalle, total_venta as Monto, metodo_pago as Pago FROM historial_ventas", conn)
    df_c = pd.read_sql_query("SELECT fecha, 'COMPRA' as Tipo, item_nombre as Detalle, -costo_total as Monto, metodo_pago as Pago FROM historial_compras", conn)
    
    df_caja = pd.concat([df_v, df_c], ignore_index=True)
    df_caja['fecha_dt'] = pd.to_datetime(df_caja['fecha'], errors='coerce').dt.date
    df_f = df_caja[(df_caja['fecha_dt'] >= d1) & (df_caja['fecha_dt'] <= d2)].sort_values(by="fecha", ascending=False)

    if not df_f.empty:
        # Métricas de Saldo
        efectivo = df_f[df_f['Pago'] == 'Efectivo']['Monto'].sum()
        banco = df_f[df_f['Pago'].isin(['Transferencia', 'Mercado Pago', 'Virtual'])]['Monto'].sum()
        tarjeta_deuda = df_f[(df_f['Pago'] == 'Tarjeta') & (df_f['Tipo'] == 'COMPRA')]['Monto'].sum()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("SALDO TOTAL", f"$ {df_f['Monto'].sum():,.2f}")
        m2.metric("EFECTIVO", f"$ {efectivo:,.2f}")
        m3.metric("BANCO / TRANSF.", f"$ {banco:,.2f}")
        m4.metric("DEUDA TARJETA", f"$ {tarjeta_deuda:,.2f}")

        st.divider()
        st.dataframe(df_f[["fecha", "Tipo", "Detalle", "Monto", "Pago"]], use_container_width=True, hide_index=True)
    else:
        st.info("No hay movimientos en este período.")
    conn.close()


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
