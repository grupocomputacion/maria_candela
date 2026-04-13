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
st.sidebar.info("Versión del Sistema: 8.6.7 (Sincronizada)")

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

# ==========================================
# 🛡️ SEGURIDAD: BACKUP Y RESTAURACIÓN
# ==========================================
st.sidebar.divider()
st.sidebar.subheader("Mantenimiento")

# --- FUNCIÓN 1: GENERAR BACKUP ---
def generar_backup():
    conn = conectar()
    # Leemos todas las tablas importantes
    tablas = ["productos", "recetas", "historial_ventas", "historial_compras"]
    backup_data = {}
    for t in tablas:
        try:
            backup_data[t] = pd.read_sql_query(f"SELECT * FROM {t}", conn)
        except:
            pass
    conn.close()
    
    # Creamos un archivo Excel con múltiples pestañas (una por tabla)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for nombre_tabla, df_tabla in backup_data.items():
            df_tabla.to_excel(writer, sheet_name=nombre_tabla, index=False)
    return output.getvalue()

# Botón de Descarga
st.sidebar.download_button(
    label="📥 Descargar Backup Total",
    data=generar_backup(),
    file_name=f"backup_velas_{date.today()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    help="Descarga un archivo Excel con todos los datos del sistema."
)

# --- FUNCIÓN 2: RESTAURAR DESDE BACKUP ---
with st.sidebar.expander("⚠️ Restaurar Sistema"):
    st.warning("Al restaurar, se borrarán los datos actuales y se reemplazarán por los del archivo.")
    archivo_backup = st.file_uploader("Subir archivo de backup (.xlsx)", type=["xlsx"])
    
    if archivo_button := st.button("🚀 Iniciar Restauración"):
        if archivo_backup is not None:
            try:
                # Leemos el Excel
                excel_data = pd.read_excel(archivo_backup, sheet_name=None)
                conn = conectar()
                
                for tabla, df_nueva in excel_data.items():
                    # Borramos la tabla actual e insertamos la del backup
                    conn.execute(f"DELETE FROM {tabla}")
                    df_nueva.to_sql(tabla, conn, if_exists='append', index=False)
                
                conn.commit()
                conn.close()
                st.success("✅ Sistema restaurado con éxito.")
                st.rerun()
            except Exception as e:
                st.error(f"Error en la restauración: {e}")
        else:
            st.error("Por favor, sube un archivo primero.")    


# ---------------------------------------------------------
# 1. INVENTARIO Y ALTA (V.9.6 - CIERRE DE BLOQUE CORREGIDO)
# ---------------------------------------------------------
if menu == "📦 Inventario y Alta":
    st.subheader("Gestión de Stock")
    conn = conectar()
    
    # --- COLUMNAS PARA FORMULARIOS ---
    col_alta, col_ajuste = st.columns(2)

    with col_alta.expander("➕ DAR DE ALTA NUEVO"):
        with st.form("alta_p"):
            c1, c2 = st.columns(2)
            n_nom = c1.text_input("Nombre")
            n_tip = c2.selectbox("Tipo", ["Insumo", "Final", "Herramienta", "Packaging"])
            n_uni = c1.selectbox("Unidad", ["Gr", "Ml", "Un", "Kg"])
            n_stk = c2.number_input("Stock Inicial", min_value=0.0)
            n_min = c1.number_input("Stock Mínimo", min_value=0.0)
            n_cst = c2.number_input("Costo Unitario", min_value=0.0)
            if st.form_submit_button("Guardar Nuevo"):
                conn.execute("INSERT INTO productos (nombre, tipo, unidad, stock_actual, stock_minimo, costo_u) VALUES (?,?,?,?,?,?)",
                            (n_nom, n_tip, n_uni, n_stk, n_min, n_cst))
                conn.commit()
                st.success("Registrado")
                st.rerun()

    # --- AJUSTAR STOCK EXISTENTE ---
    with col_ajuste.expander("🔧 AJUSTAR STOCK (SUMAR/RESTAR)"):
        prods_data = conn.execute("SELECT id, nombre, stock_actual FROM productos ORDER BY nombre").fetchall()
        if prods_data:
            with st.form("form_ajuste_stock"):
                p_elegido = st.selectbox("Seleccionar Producto", [p[1] for p in prods_data])
                col_a1, col_a2 = st.columns(2)
                tipo_mov = col_a1.radio("Movimiento", ["Sumar", "Restar"], horizontal=True)
                cant_adj = col_a2.number_input("Cantidad", min_value=0.1, step=0.1)
                
                if st.form_submit_button("Aplicar Cambio"):
                    signo = 1 if tipo_mov == "Sumar" else -1
                    conn.execute("UPDATE productos SET stock_actual = stock_actual + ? WHERE nombre = ?", 
                                (cant_adj * signo, p_elegido))
                    conn.commit()
                    st.success(f"Stock actualizado.")
                    st.rerun()
        else:
            st.info("No hay productos.")

    st.divider()

    # --- CONSULTA Y FILTROS ---
    df = pd.read_sql_query("SELECT * FROM productos", conn)
    
    if not df.empty:
        f1, f2, _ = st.columns([1, 1, 2])
        filtro_tipo = f1.selectbox("Filtrar Tipo:", ["Todos"] + sorted(list(df['tipo'].unique())), label_visibility="collapsed")
        filtro_stock = f2.selectbox("Estado Stock:", ["Todos los Stocks", "Con Stock", "Sin Stock", "Bajo Mínimo"], label_visibility="collapsed")

        df_mostrar = df.copy()
        if filtro_tipo != "Todos": 
            df_mostrar = df_mostrar[df_mostrar['tipo'] == filtro_tipo]
        
        if filtro_stock == "Con Stock": 
            df_mostrar = df_mostrar[df_mostrar['stock_actual'] > 0]
        elif filtro_stock == "Sin Stock": 
            df_mostrar = df_mostrar[df_mostrar['stock_actual'] <= 0]
        elif filtro_stock == "Bajo Mínimo": 
            df_mostrar = df_mostrar[df_mostrar['stock_actual'] < df_mostrar['stock_minimo']]

        st.dataframe(
            df_mostrar, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "costo_u": st.column_config.NumberColumn("Costo U.", format="$ %.2f"),
                "precio_v": st.column_config.NumberColumn("Precio L1", format="$ %.2f"),
                "precio_v2": st.column_config.NumberColumn("Precio L2", format="$ %.2f"),
                "stock_actual": st.column_config.NumberColumn("Stock Actual", format="%.2f")
            }
        )
    else:
        st.info("No hay productos cargados.")
    
    conn.close() # <--- Cerramos conexión y bloque de Inventario.

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
# 🚀 REGISTRAR VENTAS (V.8.9.7 - FINAL FIX)
# ==========================================
elif menu == "🚀 Registrar Ventas":
    st.header("Registro de Ventas")
    
    conn = conectar()
    try:
        # Traemos precios y stock
        df_prod = pd.read_sql_query("SELECT id, nombre, precio_v, precio_v2, stock_actual FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    except Exception as e:
        st.error(f"Error técnico: {e}")
        df_prod = None

    if df_prod is not None and not df_prod.empty:
        # Filtrar solo los que tienen stock
        productos_con_stock = df_prod[df_prod['stock_actual'] > 0]
        
        if productos_con_stock.empty:
            st.warning("⚠️ No hay productos con stock disponible.")
        else:
            # 1. SELECCIÓN DE PRODUCTO (Fuera del form para reactividad total)
            idx_prod = st.selectbox(
                "Seleccione Producto:",
                productos_con_stock.index.tolist(),
                format_func=lambda x: f"{productos_con_stock.loc[x, 'nombre']} (Stock: {productos_con_stock.loc[x, 'stock_actual']})"
            )
            
            # Obtener precios base
            p1 = safe_float(productos_con_stock.loc[idx_prod, 'precio_v'])
            p2 = safe_float(productos_con_stock.loc[idx_prod, 'precio_v2'])

            # --- PRE-FORMATEO PARA EL CUADRO VISUAL ---
            # Formateamos aquí para que el HTML reciba el texto ya procesado
            p1_str = f"{int(p1):,}".replace(",", ".")
            p2_str = f"{int(p2):,}".replace(",", ".")
            
            # Cuadro de referencia visual limpio
            st.markdown(f"""
            <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px; border: 1px solid #d4af37;">
                <strong>Precios de Referencia:</strong><br>
                💰 <b>Lista 1:</b> ${p1_str} | 💰 <b>Lista 2:</b> ${p2_str}
            </div>
            """, unsafe_allow_html=True)
            st.write("")

            # 2. CONFIGURACIÓN DE LA VENTA (Reactiva)
            c_lista, c_cant = st.columns(2)
            tipo_lista = c_lista.radio("¿Qué lista aplicar?", ["Lista 1", "Lista 2"], horizontal=True)
            cantidad = c_cant.number_input("Cantidad de velas:", min_value=1.0, step=1.0, value=1.0)
            
            # Cálculo del monto sugerido
            precio_unitario = p1 if tipo_lista == "Lista 1" else p2
            sugerido_total = int(precio_unitario * cantidad)
            
            # 3. FORMULARIO DE CIERRE
            # La key_dinamica asegura que el monto se refresque si cambia producto, lista o cantidad
            key_dinamica = f"monto_{idx_prod}_{tipo_lista}_{cantidad}"

            with st.form("f_venta_v897"):
                monto_real = st.number_input(
                    f"Monto TOTAL a cobrar (Sugerido {tipo_lista}):", 
                    min_value=0, 
                    value=sugerido_total,
                    key=key_dinamica
                )
                
                c_pago, c_fecha = st.columns(2)
                metodo_pago_sel = c_pago.selectbox("Forma de Pago:", ["Efectivo", "Mercado Pago", "Transferencia"])
                fecha_v = c_fecha.date_input("Fecha de la venta:", date.today())
                
                btn_confirmar = st.form_submit_button("✅ CONFIRMAR Y REGISTRAR VENTA")

            if btn_confirmar:
                # Usamos el valor que quedó en el input (por si el usuario lo editó a mano)
                monto_final_grabar = st.session_state[key_dinamica]
                nombre_p = productos_con_stock.loc[idx_prod, 'nombre']
                
                try:
                    # Grabar en historial
                    conn.execute("""
                        INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago)
                        VALUES (?, ?, ?, ?, ?)
                    """, (fecha_v.strftime("%Y-%m-%d"), nombre_p, cantidad, monto_final_grabar, metodo_pago_sel))

                    # Actualizar stock
                    conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", 
                                (cantidad, nombre_p))

                    conn.commit()
                    
                    # Mensaje de éxito formateado
                    monto_exito = f"{int(monto_final_grabar):,}".replace(",", ".")
                    st.success(f"✔️ Venta registrada: {nombre_p} por ${monto_exito}")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Error al grabar: {e}")
    else:
        st.info("No hay productos 'Final' cargados.")
    conn.close()


# ---------------------------------------------------------
# 5. CAJA Y EXCEL (V.9.1 - ERROR DE FECHA BLINDADO)
# ---------------------------------------------------------
elif menu == "📊 Caja y Filtros":
    st.subheader("Balance y Control de Caja")
    conn = conectar()
    
    # --- PANEL DE AJUSTES ---
    with st.expander("⚙️ AJUSTES DE SALDO Y TRANSFERENCIAS"):
        with st.form("form_ajuste_caja_v91", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            tipo_aj = c1.selectbox("Tipo de Movimiento", ["Ajuste de Saldo", "Transferencia"])
            monto_aj = c2.number_input("Monto $", value=0.0, format="%.2f")
            pago_aj = c3.selectbox("Cuenta/Método", ["Efectivo", "Mercado Pago", "Transferencia", "Tarjeta"])
            det_aj = st.text_input("Detalle")
            
            if st.form_submit_button("💾 APLICAR AJUSTE"):
                fecha_ajuste = date.today().strftime("%Y-%m-%d")
                try:
                    if tipo_aj == "Ajuste de Saldo":
                        if monto_aj >= 0:
                            conn.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (?,?,?,?,?)", (fecha_ajuste, f"AJUSTE: {det_aj}", 0, monto_aj, pago_aj))
                        else:
                            conn.execute("INSERT INTO historial_compras (fecha, item_nombre, cantidad, costo_total, metodo_pago) VALUES (?,?,?,?,?)", (fecha_ajuste, f"AJUSTE: {det_aj}", 0, abs(monto_aj), pago_aj))
                    else:
                        conn.execute("INSERT INTO historial_compras (fecha, item_nombre, cantidad, costo_total, metodo_pago) VALUES (?,?,?,?,?)", (fecha_ajuste, f"EGRESO TRANSF", 0, monto_aj, "Efectivo"))
                        conn.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (?,?,?,?,?)", (fecha_ajuste, f"INGRESO TRANSF", 0, monto_aj, pago_aj))
                    conn.commit()
                    st.success("Ajuste aplicado.")
                    st.rerun()
                except Exception as e: st.error(f"Error: {e}")

    # --- VISUALIZACIÓN (AQUÍ ESTABA EL ERROR) ---
    c_f1, c_f2 = st.columns(2)
    d_desde = c_f1.date_input("Desde", date(date.today().year, date.today().month, 1))
    d_hasta = c_f2.date_input("Hasta", date.today())
    
    df_v = pd.read_sql_query("SELECT fecha, 'VENTA' as Tipo, producto as Detalle, total_venta as Monto, metodo_pago as Pago FROM historial_ventas", conn)
    df_c = pd.read_sql_query("SELECT fecha, 'COMPRA' as Tipo, item_nombre as Detalle, -costo_total as Monto, metodo_pago as Pago FROM historial_compras", conn)
    
    if not df_v.empty or not df_c.empty:
        df_caja = pd.concat([df_v, df_c], ignore_index=True)
        
        # --- CORRECCIÓN CRÍTICA ---
        # errors='coerce' transforma las fechas malas en "NaT" (Not a Time) en lugar de dar error
        df_caja['fecha_dt'] = pd.to_datetime(df_caja['fecha'], errors='coerce').dt.date
        
        # Eliminamos filas donde la fecha sea inválida para que no rompa el filtro
        df_caja = df_caja.dropna(subset=['fecha_dt'])
        
        # Filtro
        df_f = df_caja[(df_caja['fecha_dt'] >= d_desde) & (df_caja['fecha_dt'] <= d_hasta)].sort_values(by="fecha", ascending=False)

        if not df_f.empty:
            efectivo = df_f[df_f['Pago'] == 'Efectivo']['Monto'].sum()
            banco = df_f[df_f['Pago'].isin(['Transferencia', 'Mercado Pago', 'Virtual'])]['Monto'].sum()
            tarjeta = df_f[(df_f['Pago'] == 'Tarjeta') & (df_f['Tipo'] == 'COMPRA')]['Monto'].sum()

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("SALDO TOTAL", f"$ {df_f['Monto'].sum():,.2f}")
            m2.metric("EFECTIVO", f"$ {efectivo:,.2f}")
            m3.metric("BANCO / MP", f"$ {banco:,.2f}")
            m4.metric("DEUDA TARJETA", f"$ {tarjeta:,.2f}")

            st.divider()
            st.dataframe(df_f[["fecha", "Tipo", "Detalle", "Monto", "Pago"]], use_container_width=True, hide_index=True)
        else:
            st.info("No hay movimientos válidos en este período.")
    else:
        st.info("No hay datos en el historial.")
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
