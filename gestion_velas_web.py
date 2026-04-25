import streamlit as st
import pandas as pd
from datetime import datetime, date
import io
from sqlalchemy import create_engine, text

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Velas Candela Pro - Sistema Integral", layout="wide")

# ==========================================
# 1. MOTOR DE BASE DE DATOS (PROTEGIDO)
# ==========================================
@st.cache_resource
def get_engine():
    try:
        if "postgres" not in st.secrets:
            return None
        conn_url = st.secrets["postgres"]["url"].strip().replace(" ", "")
        return create_engine(conn_url, pool_pre_ping=True, pool_recycle=300)
    except Exception:
        return None

def db_query(query, params=None, commit=False):
    engine = get_engine()
    if engine is None: return None
    try:
        with engine.connect() as conn:
            if commit:
                conn.execute(text(query), params)
                conn.commit()
                return True
            else:
                return pd.read_sql(text(query), conn, params=params)
    except Exception as e:
        if not commit: st.error(f"Error de BD: {e}")
        return None

def safe_float(val):
    try:
        if pd.isna(val) or str(val).strip() == "": return 0.0
        return float(val)
    except: return 0.0

# --- FUNCIONES DE ESTILO PARA RENTABILIDAD ---
def color_margen(val):
    try:
        color = 'red' if val < 20 else 'orange' if val < 40 else 'green'
        return f'color: {color}; font-weight: bold'
    except: return ''

# ==========================================
# 2. MENÚ LATERAL
# ==========================================
st.sidebar.title("🕯️ Velas Control")
menu = st.sidebar.radio("Ir a:", [
    "📦 Inventario y Alta", 
    "🧪 Recetas y Costeo", 
    "🏭 Fabricación",
    "💰 Registro de Compras", 
    "🚀 Registrar Ventas", 
    "📊 Caja y Filtros",
    "📈 Rentabilidad",
    "💰 Flujo de Caja",
    "📊 Análisis de Resultados"
])

# ==========================================
# 📦 1. INVENTARIO Y ALTA (VERSIÓN FINAL CONSOLIDADA)
# ==========================================
if menu == "📦 Inventario y Alta":
    st.subheader("📦 Gestión de Inventario Profesional")
    
    if st.sidebar.button("🔄 Sincronizar Base de Datos"):
        st.cache_data.clear()
        st.rerun()

    # --- DEFINICIÓN CRÍTICA DE COLUMNAS ---
    col_alta, col_imp = st.columns(2)

    with col_alta.expander("➕ DAR DE ALTA MANUAL"):
        with st.form("alta"):
            ca, cb = st.columns(2)
            n = ca.text_input("Nombre")
            t = cb.selectbox("Tipo", ["insumo", "final", "herramienta", "packaging"])
            u = ca.selectbox("Unidad", ["Gr", "Ml", "Un", "Kg"])
            s = cb.number_input("Stock Inicial", min_value=0.0)
            c = ca.number_input("Costo Unitario ($)", min_value=0.0)
            if st.form_submit_button("💾 Guardar"):
                if n.strip():
                    db_query("INSERT INTO productos (nombre, tipo, unidad, stock_actual, costo_u) VALUES (:n, :t, :u, :s, :c)",
                             {"n": n.strip().upper(), "t": t, "u": u, "s": s, "c": c}, commit=True)
                    st.cache_data.clear()
                    st.success(f"✅ {n} registrado.")
                    st.rerun()

    with col_imp.expander("🚀 GESTIÓN DE DATOS (Restauración / Limpieza)"):
        uploaded_file = st.file_uploader("Subir backup.xlsx", type=["xlsx"])
        if uploaded_file:
            if st.button("🏁 EJECUTAR RESTAURACIÓN"):
                with st.status("🚀 Procesando Restauración Maestra...", expanded=True) as status:
                    try:
                        xls = pd.ExcelFile(uploaded_file)
                        
                        # 1. LIMPIEZA TOTAL
                        status.write("🧹 Limpiando tablas para carga limpia...")
                        db_query("TRUNCATE TABLE recetas, historial_ventas, historial_compras, saldos_caja RESTART IDENTITY CASCADE", commit=True)
                        db_query("TRUNCATE TABLE productos RESTART IDENTITY CASCADE", commit=True)

                        # 2. CARGA DE PRODUCTOS
                        status.write("📥 Cargando Productos...")
                        df_p = pd.read_excel(xls, 'productos')
                        df_p.columns = [str(col).strip().lower() for col in df_p.columns]
                        for _, row in df_p.iterrows():
                            db_query("""INSERT INTO productos (nombre, tipo, unidad, stock_actual, costo_u, precio_v, precio_v2) 
                                     VALUES (:n, :t, :u, :s, :c, :p1, :p2)""",
                                     {"n": str(row.get('nombre', '')).strip().upper(), 
                                      "t": str(row.get('tipo', 'insumo')).lower(),
                                      "u": str(row.get('unidad', 'Un')), 
                                      "s": safe_float(row.get('stock_actual', 0)),
                                      "c": safe_float(row.get('costo_u', 0)), 
                                      "p1": safe_float(row.get('precio_v', 0)),
                                      "p2": safe_float(row.get('precio_v2', 0))}, commit=True)

                        # Mapeos para consistencia
                        prods_db = db_query("SELECT id, nombre FROM productos")
                        mapa_id_real = dict(zip(prods_db['nombre'], prods_db['id']))
                        mapa_nombres_excel = dict(zip(df_p['id'], df_p['nombre'].str.strip().str.upper()))

                        # 3. CARGA DE RECETAS (Usando id_final e id_insumo del Excel)
                        if 'recetas' in xls.sheet_names:
                            status.write("🧪 Vinculando Recetas por ID...")
                            df_r = pd.read_excel(xls, 'recetas')
                            df_r.columns = [str(col).strip().lower() for col in df_r.columns]
                            for _, row in df_r.iterrows():
                                nombre_f = mapa_nombres_excel.get(row.get('id_final'))
                                nombre_i = mapa_nombres_excel.get(row.get('id_insumo'))
                                id_f_real = mapa_id_real.get(nombre_f)
                                id_i_real = mapa_id_real.get(nombre_i)
                                if id_f_real and id_i_real:
                                    db_query("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (:idf, :idi, :c)",
                                             {"idf": id_f_real, "idi": id_i_real, "c": safe_float(row.get('cantidad', 0))}, commit=True)

                        # 4. CARGA DE HISTORIAL DE COMPRAS
                        if 'historial_compras' in xls.sheet_names:
                            status.write("🛍️ Importando Historial de Compras...")
                            df_c = pd.read_excel(xls, 'historial_compras')
                            df_c.columns = [str(col).strip().lower() for col in df_c.columns]
                            for _, row in df_c.iterrows():
                                db_query("""INSERT INTO historial_compras (fecha, insumo, cantidad, costo_u, total, metodo_pago)
                                         VALUES (:f, :i, :c, :cu, :t, :m)""",
                                         {"f": row.get('fecha'), "i": str(row.get('insumo', '')).upper(),
                                          "c": safe_float(row.get('cantidad', 0)), "cu": safe_float(row.get('costo_u', 0)),
                                          "t": safe_float(row.get('total', 0)), "m": str(row.get('metodo_pago', 'Efectivo'))}, commit=True)

                        # 5. CARGA DE HISTORIAL DE VENTAS
                        if 'historial_ventas' in xls.sheet_names:
                            status.write("📈 Importando Historial de Ventas...")
                            df_v = pd.read_excel(xls, 'historial_ventas')
                            df_v.columns = [str(col).strip().lower() for col in df_v.columns]
                            for _, row in df_v.iterrows():
                                prod_n = str(row.get('producto', '')).strip().upper()
                                db_query("""INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago, costo_momento)
                                         VALUES (:f, :p, :c, :t, :m, :cm)""",
                                         {"f": row.get('fecha'), "p": prod_n, "c": safe_float(row.get('cantidad', 1)),
                                          "t": safe_float(row.get('total_venta', row.get('total_ven', 0))),
                                          "m": str(row.get('metodo_pago', 'Efectivo')),
                                          "cm": safe_float(row.get('costo_momento', row.get('costo_tot', 0)))}, commit=True)

                        # 6. SINCRONIZACIÓN FINAL DE CAJA
                        status.write("💰 Sincronizando Caja...")
                        db_query("INSERT INTO saldos_caja (tipo_cuenta, saldo) VALUES ('Efectivo', 0), ('Banco', 0), ('Deuda_TC', 0) ON CONFLICT DO NOTHING", commit=True)
                        db_query("UPDATE saldos_caja SET saldo = 0", commit=True)
                        db_query("""
                            UPDATE saldos_caja SET saldo = ((SELECT COALESCE(SUM(total_venta), 0) FROM historial_ventas WHERE LOWER(metodo_pago) LIKE '%efectivo%') - (SELECT COALESCE(SUM(total), 0) FROM historial_compras WHERE LOWER(metodo_pago) LIKE '%efectivo%')) WHERE tipo_cuenta = 'Efectivo';
                            UPDATE saldos_caja SET saldo = ((SELECT COALESCE(SUM(total_venta), 0) FROM historial_ventas WHERE LOWER(metodo_pago) NOT LIKE '%efectivo%' AND LOWER(metodo_pago) NOT LIKE '%tarjeta%') - (SELECT COALESCE(SUM(total), 0) FROM historial_compras WHERE LOWER(metodo_pago) NOT LIKE '%efectivo%' AND LOWER(metodo_pago) NOT LIKE '%tarjeta%')) WHERE tipo_cuenta = 'Banco';
                            UPDATE saldos_caja SET saldo = (SELECT COALESCE(SUM(total), 0) FROM historial_compras WHERE LOWER(metodo_pago) LIKE '%tarjeta%') WHERE tipo_cuenta = 'Deuda_TC';
                        """, commit=True)

                        status.update(label="✨ ¡Restauración Maestra Exitosa!", state="complete", expanded=False)
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        status.update(label="❌ Error crítico", state="error")
                        st.error(f"Fallo en: {str(e)}")

        st.divider()
        clave_b = st.text_input("Clave de Seguridad:", type="password")
        if st.button("🗑️ LIMPIAR TODAS LAS TABLAS"):
            if clave_b == "3280":
                db_query("TRUNCATE TABLE recetas, historial_ventas, historial_compras, productos, saldos_caja RESTART IDENTITY CASCADE", commit=True)
                db_query("INSERT INTO saldos_caja (tipo_cuenta, saldo) VALUES ('Efectivo', 0), ('Banco', 0), ('Deuda_TC', 0)", commit=True)
                st.cache_data.clear()
                st.rerun()

    st.divider()
    
    # --- FILTROS ---
    f1, f2, f3 = st.columns(3)
    with f1:
        f_tipo = st.selectbox("Filtrar por Tipo:", ["Todos", "insumo", "final", "herramienta", "packaging"])
    with f2:
        f_stock = st.selectbox("Filtrar por Stock:", ["Todos", "Con Stock", "Sin Stock"])
    with f3:
        f_busq = st.text_input("🔍 Buscar por Nombre:")

    # --- CONSULTA Y TABLA EDITABLE ---
    df_inv = db_query("""
        SELECT id, nombre as "Descripción", tipo as "Tipo", unidad as "Unidad", 
               stock_actual as "Stock", costo_u as "Costo", 
               precio_v as "P.V. Lista 1", precio_v2 as "P.V. Lista 2" 
        FROM productos ORDER BY nombre ASC
    """)
    
    if df_inv is not None and not df_inv.empty:
        if f_tipo != "Todos": df_inv = df_inv[df_inv['Tipo'] == f_tipo]
        if f_stock == "Con Stock": df_inv = df_inv[df_inv['Stock'] > 0]
        elif f_stock == "Sin Stock": df_inv = df_inv[df_inv['Stock'] <= 0

# ==========================================
# 🧪 2. RECETAS Y COSTEO (VERSIÓN DEFINITIVA)
# ==========================================
elif menu == "🧪 Recetas y Costeo":
    st.header("🧪 Composición y Costeo")

    # Traemos productos finales con sus precios y costos actuales
    df_f = db_query("SELECT id, nombre, precio_v, precio_v2, costo_u FROM productos WHERE UPPER(tipo) = 'FINAL' ORDER BY nombre")
    df_i = db_query("SELECT id, nombre, unidad, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO' ORDER BY nombre")

    if df_f is None or df_f.empty:
        st.warning("No hay productos finales cargados. Dá de alta uno en Inventario primero.")
        st.stop()

    sel_f = st.selectbox("Producto Final a costear:", df_f['nombre'].tolist())
    row_actual = df_f[df_f['nombre'] == sel_f].iloc[0]
    id_f = int(row_actual['id'])

    c1, c2 = st.columns([1, 2])

    with c1:
        st.subheader("Añadir insumo")
        if df_i is not None and not df_i.empty:
            with st.form("form_add_insumo"):
                sel_i = st.selectbox("Insumo:", df_i['nombre'].tolist())
                row_i = df_i[df_i['nombre'] == sel_i].iloc[0]
                cant = st.number_input(f"Cantidad ({row_i['unidad']})", min_value=0.001, format="%.3f")
                if st.form_submit_button("➕ Añadir"):
                    db_query(
                        "INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (:idf, :idi, :c) ON CONFLICT (id_final, id_insumo) DO UPDATE SET cantidad = EXCLUDED.cantidad",
                        {"idf": id_f, "idi": int(row_i['id']), "c": cant}, commit=True
                    )
                    st.cache_data.clear()
                    st.rerun()
        else:
            st.info("Sin insumos cargados.")

    with c2:
        st.subheader("Estructura de Costos")
        df_rec = db_query(
            """SELECT r.id as receta_id, i.nombre, r.cantidad, i.unidad, i.costo_u, (r.cantidad * i.costo_u) as subtotal
               FROM recetas r JOIN productos i ON r.id_insumo = i.id
               WHERE r.id_final = :id ORDER BY i.nombre""", {"id": id_f}
        )
        
        costo_receta = 0.0
        if df_rec is not None and not df_rec.empty:
            costo_receta = float(df_rec['subtotal'].sum())
            st.metric("💰 Costo Total Calculado", f"$ {costo_receta:,.2f}")

            # Mostrar tabla de insumos con eliminación
            for _, r in df_rec.iterrows():
                cn, cc, cs, cb = st.columns([3, 1, 1, 0.5])
                cn.write(f"{r['nombre']}")
                cc.write(f"{r['cantidad']} {r['unidad']}")
                cs.write(f"$ {r['subtotal']:,.2f}")
                if cb.button("🗑️", key=f"del_ins_{r['receta_id']}"):
                    db_query("DELETE FROM recetas WHERE id = :id", {"id": int(r['receta_id'])}, commit=True)
                    st.cache_data.clear()
                    st.rerun()

            st.divider()
            st.subheader("📈 Definición de Margen y Precios")
            
            # Precios actuales de la base de datos
            p1_base = float(row_actual['precio_v']) if row_actual['precio_v'] else 0.0
            p2_base = float(row_actual['precio_v2']) if row_actual['precio_v2'] else 0.0
            
            # Formulario de Precios Dual
            with st.form("form_precios_sincro"):
                col_l1, col_l2 = st.columns(2)
                
                with col_l1:
                    st.markdown("🔍 **Lista 1 (Minorista)**")
                    opcion1 = st.radio("Definir por:", ["Precio", "Porcentaje"], key="opt1", horizontal=True)
                    if opcion1 == "Precio":
                        p1_val = st.number_input("Monto Lista 1 ($)", value=p1_base, step=50.0)
                        margen1 = ((p1_val / costo_receta) - 1) * 100 if costo_receta > 0 else 0
                        st.caption(f"Margen resultante: {margen1:.1f}%")
                    else:
                        m1_val = st.number_input("Margen Lista 1 (%)", value=100.0, step=5.0)
                        p1_val = costo_receta * (1 + m1_val / 100)
                        st.caption(f"Precio sugerido: $ {p1_val:,.2f}")

                with col_l2:
                    st.markdown("📦 **Lista 2 (Mayorista)**")
                    opcion2 = st.radio("Definir por:", ["Precio", "Porcentaje"], key="opt2", horizontal=True)
                    if opcion2 == "Precio":
                        p2_val = st.number_input("Monto Lista 2 ($)", value=p2_base, step=50.0)
                        margen2 = ((p2_val / costo_receta) - 1) * 100 if costo_receta > 0 else 0
                        st.caption(f"Margen resultante: {margen2:.1f}%")
                    else:
                        m2_val = st.number_input("Margen Lista 2 (%)", value=60.0, step=5.0)
                        p2_val = costo_receta * (1 + m2_val / 100)
                        st.caption(f"Precio sugerido: $ {p2_val:,.2f}")

                st.write("")
                if st.form_submit_button("💾 APLICAR Y GRABAR EN INVENTARIO"):
                    # El UPDATE debe ser atómico y usar safe_float para evitar errores de tipo
                    sql_upd = """
                        UPDATE productos 
                        SET costo_u = :c, precio_v = :p1, precio_v2 = :p2 
                        WHERE id = :id
                    """
                    success = db_query(sql_upd, {
                        "c": float(costo_receta), 
                        "p1": float(p1_val), 
                        "p2": float(p2_val), 
                        "id": int(id_f)
                    }, commit=True)
                    
                    if success:
                        st.cache_data.clear()
                        st.success(f"✅ Grabado con éxito: Costo ${costo_receta:,.2f} | L1 ${p1_val:,.2f} | L2 ${p2_val:,.2f}")
                        st.rerun()
                    else:
                        st.error("Error crítico al intentar impactar la base de datos.")
        else:
            st.info("Cargá insumos para calcular el costo real de fabricación.")


# ==========================================
# 🏭 3. FABRICACIÓN
# ==========================================
elif menu == "🏭 Fabricación":
    st.header("🏭 Registro de Producción")

    df_f = db_query("SELECT id, nombre, stock_actual FROM productos WHERE UPPER(tipo) = 'FINAL' ORDER BY nombre")

    if df_f is None or df_f.empty:
        st.warning("No hay productos finales cargados.")
        st.stop()

    prod_sel = st.selectbox("¿Qué producto fabricaste?", df_f['nombre'].tolist())
    row_f    = df_f[df_f['nombre'] == prod_sel].iloc[0]
    id_f     = int(row_f['id'])

    # Mostrar receta y advertencia de stock antes de confirmar
    receta = db_query(
        """SELECT i.nombre, r.cantidad, i.unidad, i.stock_actual,
                  (r.cantidad * i.costo_u) as costo_unit
           FROM recetas r
           JOIN productos i ON r.id_insumo = i.id
           WHERE r.id_final = :id""",
        {"id": id_f}
    )

    if receta is None or receta.empty:
        st.error("Este producto no tiene receta. Cargala en '🧪 Recetas y Costeo'.")
        st.stop()

    st.info(f"📦 Stock actual de **{prod_sel}**: {row_f['stock_actual']} unidades")

    cantidad = st.number_input("Cantidad de unidades a fabricar:", min_value=1, step=1)

    # Verificar si hay suficiente stock de insumos
    receta['necesario'] = receta['cantidad'] * cantidad
    receta['alcanza']   = receta['stock_actual'] >= receta['necesario']
    sin_stock = receta[~receta['alcanza']]

    st.subheader("Insumos necesarios")
    st.dataframe(
        receta[['nombre', 'unidad', 'cantidad', 'necesario', 'stock_actual', 'alcanza']],
        use_container_width=True, hide_index=True
    )

    if not sin_stock.empty:
        st.error(f"⚠️ Stock insuficiente para: {', '.join(sin_stock['nombre'].tolist())}")

    if st.button("🚀 Confirmar Fabricación", disabled=not sin_stock.empty, type="primary"):
        # Sumar stock al producto final
        db_query(
            "UPDATE productos SET stock_actual = stock_actual + :c WHERE id = :id",
            {"c": cantidad, "id": id_f}, commit=True
        )
        # Descontar insumos
        for _, r in receta.iterrows():
            db_query(
                "UPDATE productos SET stock_actual = stock_actual - :c WHERE nombre = :n",
                {"c": float(r['necesario']), "n": r['nombre']}, commit=True
            )
        st.success(f"✅ {cantidad} unidades de **{prod_sel}** fabricadas y stock actualizado.")
        st.rerun()

# ==========================================
# 💰 4. REGISTRO DE COMPRAS
# ==========================================
elif menu == "💰 Registro de Compras":
    st.header("💰 Compra de Insumos / Mercadería")

    df_i = db_query(
        "SELECT id, nombre, unidad, stock_actual, costo_u FROM productos "
        "WHERE UPPER(tipo) != 'FINAL' ORDER BY nombre"
    )

    if df_i is None or df_i.empty:
        st.warning("No hay insumos/herramientas cargados.")
        st.stop()

    with st.form("compra"):
        ins_nom = st.selectbox("Insumo comprado:", df_i['nombre'].tolist())
        row_i   = df_i[df_i['nombre'] == ins_nom].iloc[0]

        st.caption(f"Stock actual: {row_i['stock_actual']} {row_i['unidad']} | Costo actual: $ {row_i['costo_u']:,.2f}")

        c1, c2 = st.columns(2)
        cant_c = c1.number_input(f"Cantidad ({row_i['unidad']}):", min_value=0.001, format="%.3f")
        cost_c = c2.number_input("Monto total pagado ($):", min_value=0.01)
        proveedor = st.text_input("Proveedor (opcional):")

        if cost_c > 0 and cant_c > 0:
            nuevo_costo = cost_c / cant_c
            st.caption(f"💡 Nuevo costo unitario resultante: **$ {nuevo_costo:,.4f}**")

        if st.form_submit_button("📥 Registrar Compra"):
            nuevo_costo = cost_c / cant_c
            ok = db_query(
                "UPDATE productos SET stock_actual = stock_actual + :c, costo_u = :u WHERE id = :id",
                {"c": cant_c, "u": nuevo_costo, "id": int(row_i['id'])},
                commit=True
            )
            if ok:
                st.success(f"✅ Stock de **{ins_nom}** actualizado. Nuevo costo: $ {nuevo_costo:,.4f}")

    # Historial simple de stock bajo
    st.divider()
    st.subheader("⚠️ Insumos con stock bajo (< 100)")
    df_bajo = db_query(
        "SELECT nombre, unidad, stock_actual, costo_u FROM productos "
        "WHERE UPPER(tipo) != 'FINAL' AND stock_actual < 100000 ORDER BY stock_actual"
    )
    if df_bajo is not None and not df_bajo.empty:
        st.dataframe(df_bajo, use_container_width=True, hide_index=True)
    else:
        st.success("Todos los insumos tienen stock suficiente.")

# ==========================================
# 🚀 5. REGISTRAR VENTAS (ACTUALIZADO)
# ==========================================
elif menu == "🚀 Registrar Ventas":
    st.header("🚀 Nueva Venta")

    df_p = db_query(
        "SELECT id, nombre, precio_v, precio_v2, stock_actual, costo_u "
        "FROM productos WHERE UPPER(tipo) = 'FINAL' ORDER BY nombre"
    )

    if df_p is None or df_p.empty:
        st.warning("No hay productos finales cargados.")
        st.stop()

    sel_p = st.selectbox("Producto:", df_p['nombre'].tolist())
    row   = df_p[df_p['nombre'] == sel_p].iloc[0]

    p1 = safe_float(row['precio_v'])
    p2 = safe_float(row['precio_v2'])
    costo_u_actual = safe_float(row['costo_u']) # Capturamos el costo actual para la historia

    col_info, col_form = st.columns([1, 2])
    col_info.metric("📦 Stock disponible", f"{row['stock_actual']} un.")
    col_info.metric("💲 Precio Minorista", f"$ {p1:,.2f}")
    col_info.metric("💲 Precio Mayorista", f"$ {p2:,.2f}")

    with col_form:
        with st.form("venta"):
            # AGREGADO: Selector de fecha para permitir edición/registro retroactivo
            fecha_v = st.date_input("Fecha de la venta:", value=date.today())
            
            lista = st.radio("Lista de Precios:", ["Minorista (L1)", "Mayorista (L2)"], horizontal=True)
            cant  = st.number_input("Cantidad:", min_value=1.0, step=1.0)

            precio_u     = p1 if "L1" in lista else p2
            subtotal_sug = precio_u * cant
            st.caption(f"Subtotal sugerido: $ {subtotal_sug:,.2f}")

            total_cobrar = st.number_input(
                "Total a cobrar ($):",
                min_value=0.01,
                value=round(subtotal_sug, 2),
                step=0.01
            )
            metodo = st.selectbox("Medio de Pago:", ["Efectivo", "Transferencia", "Mercado Pago", "Tarjeta"])
            notas  = st.text_input("Notas / cliente (opcional):")

            if st.form_submit_button("✅ Procesar Venta"):
                if cant > safe_float(row['stock_actual']):
                    st.error(f"❌ Stock insuficiente. Disponible: {row['stock_actual']} unidades.")
                else:
                    # Guardamos la venta incluyendo el costo_momento para rentabilidad real
                    ok = db_query(
                        """INSERT INTO historial_ventas
                             (fecha, producto, cantidad, total_venta, metodo_pago, costo_momento)
                           VALUES (:f, :p, :c, :t, :m, :cm)""",
                        {"f": fecha_v, "p": sel_p, "c": cant,
                         "t": total_cobrar, "m": metodo, "cm": costo_u_actual},
                        commit=True
                    )
                    
                    if ok:
                        # 1. Descontamos Stock
                        db_query(
                            "UPDATE productos SET stock_actual = stock_actual - :c WHERE id = :id",
                            {"c": cant, "id": int(row['id'])}, commit=True
                        )
                        
                        # 2. Impactamos en Flujo de Caja (Efectivo vs Banco)
                        if metodo == "Efectivo":
                            db_query("UPDATE saldos_caja SET saldo = saldo + :t WHERE tipo_cuenta = 'Efectivo'", 
                                     {"t": total_cobrar}, commit=True)
                        elif metodo in ["Transferencia", "Mercado Pago"]:
                            db_query("UPDATE saldos_caja SET saldo = saldo + :t WHERE tipo_cuenta = 'Banco'", 
                                     {"t": total_cobrar}, commit=True)
                        # Nota: Si es tarjeta, no suma a efectivo/banco hasta que se liquide, 
                        # pero queda registrado en el historial.

                        st.success(f"✅ Venta registrada: {cant} x {sel_p} = $ {total_cobrar:,.2f}")
                        st.cache_data.clear() # Limpiamos caché para ver stock actualizado
                        st.rerun()

# ==========================================
# 📊 6. CAJA Y FILTROS POR PERÍODO
# ==========================================
elif menu == "📊 Caja y Filtros":
    st.header("📊 Análisis de Caja y Períodos")
    c1, c2 = st.columns(2)
    f_inicio = c1.date_input("Fecha Inicio", value=date.today().replace(day=1))
    f_fin = c2.date_input("Fecha Fin", value=date.today())

    df_v = db_query("SELECT * FROM historial_ventas WHERE fecha BETWEEN :f1 AND :f2 ORDER BY fecha DESC", {"f1": f_inicio, "f2": f_fin})

    if df_v is not None and not df_v.empty:
        # Totales por método
        efectivo = df_v[df_v['metodo_pago'].str.contains("Efectivo", na=False, case=False)]['total_venta'].sum()
        banco = df_v[df_v['metodo_pago'].str.contains("Transferencia|Banco|MP|Mercado", na=False, case=False)]['total_venta'].sum()
        tarjeta = df_v[df_v['metodo_pago'].str.contains("Tarjeta|Crédito", na=False, case=False)]['total_venta'].sum()

        m1, m2, m3 = st.columns(3)
        m1.metric("💵 Efectivo", f"$ {efectivo:,.2f}")
        m2.metric("🏦 Banco / MP", f"$ {banco:,.2f}")
        m3.metric("💳 Tarjeta / Deuda", f"$ {tarjeta:,.2f}")

        st.divider()
        st.dataframe(df_v, use_container_width=True, hide_index=True)
    else:
        st.info("No hay movimientos en este período.")

# ==========================================
# 📈 7. RENTABILIDAD (CORREGIDA)
# ==========================================
elif menu == "📈 Rentabilidad":
    st.header("📈 Análisis de Margen y Rentabilidad")
    df_r = db_query("SELECT nombre, costo_u, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL' AND costo_u > 0")

    if df_r is not None and not df_r.empty:
        df_r['Ganancia L1 ($)'] = df_r['precio_v'] - df_r['costo_u']
        df_r['Margen L1 (%)'] = (df_r['Ganancia L1 ($)'] / df_r['precio_v'] * 100).fillna(0)
        df_r['Ganancia L2 ($)'] = df_r['precio_v2'] - df_r['costo_u']
        df_r['Margen L2 (%)'] = (df_r['Ganancia L2 ($)'] / df_r['precio_v2'] * 100).fillna(0)
        
        # Aplicamos el estilo nuevo (.map en lugar de .applymap)
        styled = df_r.style.format({
            "costo_u": "$ {:.2f}", "precio_v": "$ {:.2f}", "precio_v2": "$ {:.2f}",
            "Ganancia L1 ($)": "$ {:.2f}", "Ganancia L2 ($)": "$ {:.2f}",
            "Margen L1 (%)": "{:.1f}%", "Margen L2 (%)": "{:.1f}%"
        }).map(color_margen, subset=["Margen L1 (%)", "Margen L2 (%)"])
        
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.warning("Asegurate de tener recetas cargadas con costos para ver este análisis.")

# ==========================================
# 💰 8. CONTROL DE FLUJO DE CAJA
# ==========================================
elif menu == "💰 Flujo de Caja":
    st.header("💰 Control de Flujo de Caja")
    
    # Visualización de métricas
    df_saldos = db_query("SELECT tipo_cuenta, saldo FROM saldos_caja")
    if df_saldos is not None:
        efectivo = df_saldos[df_saldos['tipo_cuenta'] == 'Efectivo']['saldo'].values[0]
        banco = df_saldos[df_saldos['tipo_cuenta'] == 'Banco']['saldo'].values[0]
        deuda_tc = df_saldos[df_saldos['tipo_cuenta'] == 'Deuda_TC']['saldo'].values[0]
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💵 Efectivo", f"$ {efectivo:,.2f}")
        c2.metric("🏦 Banco / MP", f"$ {banco:,.2f}")
        c3.metric("💳 Deuda Insumos (TC)", f"$ {deuda_tc:,.2f}", delta="- Pendiente de Pago", delta_color="inverse")

    st.divider()
    col_mov, col_pago = st.columns(2)

    with col_mov:
        st.subheader("🔄 Transferencias")
        with st.form("transf"):
            t_mov = st.selectbox("Movimiento:", ["Efectivo a Banco", "Banco a Efectivo"])
            m_mov = st.number_input("Monto:", min_value=0.0)
            if st.form_submit_button("Ejecutar"):
                if "Efectivo a Banco" in t_mov:
                    db_query("UPDATE saldos_caja SET saldo = saldo - :m WHERE tipo_cuenta = 'Efectivo'", {"m": m_mov}, commit=True)
                    db_query("UPDATE saldos_caja SET saldo = saldo + :m WHERE tipo_cuenta = 'Banco'", {"m": m_mov}, commit=True)
                else:
                    db_query("UPDATE saldos_caja SET saldo = saldo - :m WHERE tipo_cuenta = 'Banco'", {"m": m_mov}, commit=True)
                    db_query("UPDATE saldos_caja SET saldo = saldo + :m WHERE tipo_cuenta = 'Efectivo'", {"m": m_mov}, commit=True)
                st.rerun()

    with col_pago:
        st.subheader("💳 Pagar Tarjeta")
        with st.form("pago_tc"):
            desde = st.selectbox("Pagar desde:", ["Banco", "Efectivo"])
            m_tc = st.number_input("Monto a pagar de TC:", min_value=0.0)
            if st.form_submit_button("Liquidar Deuda"):
                db_query(f"UPDATE saldos_caja SET saldo = saldo - :m WHERE tipo_cuenta = '{desde}'", {"m": m_tc}, commit=True)
                db_query("UPDATE saldos_caja SET saldo = saldo - :m WHERE tipo_cuenta = 'Deuda_TC'", {"m": m_tc}, commit=True)
                st.success("Deuda amortizada.")
                st.rerun()


# ==========================================
# 📊 9. ANÁLISIS DE RESULTADOS (VERSIÓN PRO)
# ==========================================
elif menu == "📊 Análisis de Resultados":
    st.header("📊 Análisis de Negocio y Valoración")
    
    # 1. CÁLCULO DE RENTABILIDAD REAL
    df_v = db_query("SELECT fecha, producto, cantidad, total_venta, costo_momento FROM historial_ventas")
    
    if df_v is not None and not df_v.empty:
        df_v['fecha'] = pd.to_datetime(df_v['fecha'])
        # Si el costo_momento es 0, intentamos recuperarlo del costo actual del producto
        df_v['Ganancia'] = df_v['total_venta'] - (df_v['cantidad'] * df_v['costo_momento'])
        
        df_v['Mes'] = df_v['fecha'].dt.strftime('%Y-%m')
        resumen = df_v.groupby('Mes').agg({
            'total_venta': 'sum',
            'Ganancia': 'sum'
        }).rename(columns={'total_venta': 'Ventas'})
        
        st.subheader("📈 Rentabilidad Mensual")
        st.dataframe(resumen.style.format("$ {:,.2f}"), use_container_width=True)
    else:
        st.warning("⚠️ No hay datos de ventas para analizar rentabilidad.")

    # 2. VALORACIÓN DE STOCK Y PROYECCIÓN (FORECAST)
    st.divider()
    st.subheader("📦 Valoración y Proyección de Stock")
    
    # Traemos solo productos finales para la proyección de ventas
    df_stk = db_query("""
        SELECT nombre, stock_actual, costo_u, precio_v, precio_v2 
        FROM productos 
        WHERE stock_actual > 0 AND UPPER(tipo) = 'FINAL'
    """)
    
    # Traemos insumos solo para el capital inmovilizado
    df_ins = db_query("SELECT stock_actual, costo_u FROM productos WHERE stock_actual > 0 AND UPPER(tipo) = 'INSUMO'")

    if df_stk is not None and not df_stk.empty:
        # Cálculos de Valoración
        cap_finales = (df_stk['stock_actual'] * df_stk['costo_u']).sum()
        cap_insumos = (df_ins['stock_actual'] * df_ins['costo_u']).sum() if df_ins is not None else 0
        
        forecast_l1 = (df_stk['stock_actual'] * df_stk['precio_v']).sum()
        forecast_l2 = (df_stk['stock_actual'] * df_stk['precio_v2']).sum()

        # Métricas principales
        c1, c2, c3 = st.columns(3)
        c1.metric("📉 Capital en Finales", f"$ {cap_finales:,.2f}")
        c2.metric("💰 Proyección Lista 1", f"$ {forecast_l1:,.2f}")
        c3.metric("💰 Proyección Lista 2", f"$ {forecast_l2:,.2f}")
        
        st.info(f"📦 **Capital Total Inmovilizado (Insumos + Finales):** $ {cap_finales + cap_insumos:,.2f}")

        # Tabla de Proyección Detallada
        df_stk['Total L1'] = df_stk['stock_actual'] * df_stk['precio_v']
        df_stk['Total L2'] = df_stk['stock_actual'] * df_stk['precio_v2']
        
        st.write("### 📝 Detalle de Proyección por Producto")
        st.dataframe(
            df_stk[['nombre', 'stock_actual', 'precio_v', 'Total L1', 'precio_v2', 'Total L2']],
            column_config={
                "precio_v": st.column_config.NumberColumn("Precio L1", format="$ %.2f"),
                "Total L1": st.column_config.NumberColumn("Subtotal L1", format="$ %.2f"),
                "precio_v2": st.column_config.NumberColumn("Precio L2", format="$ %.2f"),
                "Total L2": st.column_config.NumberColumn("Subtotal L2", format="$ %.2f"),
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.error("No se encontraron productos de tipo 'FINAL' con stock para proyectar.")
