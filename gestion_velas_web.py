import streamlit as st
import pandas as pd
from datetime import date
import io
from sqlalchemy import create_engine, text

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Velas Candela Pro - Sistema Integral", layout="wide")

# ==========================================
# 1. MOTOR DE BASE DE DATOS
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
    if engine is None:
        st.error("⚠️ Sin conexión a la base de datos. Verificá los secrets.")
        return None
    try:
        with engine.connect() as conn:
            if commit:
                conn.execute(text(query), params or {})
                conn.commit()
                return True
            else:
                return pd.read_sql(text(query), conn, params=params)
    except Exception as e:
        st.error(f"Error de BD: {e}")
        return None

def safe_float(val):
    try:
        if pd.isna(val) or str(val).strip() == "":
            return 0.0
        return float(val)
    except:
        return 0.0

def safe_int(val):
    try:
        return int(val)
    except:
        return 0

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
    "📈 Rentabilidad"
])

# ==========================================
# 📦 1. INVENTARIO Y ALTA
# ==========================================
if menu == "📦 Inventario y Alta":
    st.subheader("📦 Gestión de Inventario")

    col_alta, col_imp = st.columns(2)

    with col_alta.expander("➕ DAR DE ALTA MANUAL"):
        with st.form("alta"):
            c1, c2 = st.columns(2)
            n  = c1.text_input("Nombre")
            t  = c2.selectbox("Tipo", ["Insumo", "Final", "Herramienta", "Packaging"])
            u  = c1.selectbox("Unidad", ["Gr", "Ml", "Un", "Kg"])
            s  = c2.number_input("Stock Inicial", min_value=0.0)
            c  = c1.number_input("Costo Unitario ($)", min_value=0.0)
            p1 = c2.number_input("Precio Minorista ($)", min_value=0.0)
            p2 = c1.number_input("Precio Mayorista ($)", min_value=0.0)
            if st.form_submit_button("Guardar"):
                if not n.strip():
                    st.warning("El nombre no puede estar vacío.")
                else:
                    ok = db_query(
                        """INSERT INTO productos (nombre, tipo, unidad, stock_actual, costo_u, precio_v, precio_v2)
                           VALUES (:n, :t, :u, :s, :c, :p1, :p2)""",
                        {"n": n.strip(), "t": t, "u": u, "s": s, "c": c, "p1": p1, "p2": p2},
                        commit=True
                    )
                    if ok:
                        st.success(f"✅ '{n}' dado de alta.")
                        st.rerun()

    with col_imp.expander("📥 RESTAURACIÓN MAESTRA (Productos y Recetas)"):
        # ── BUG FIX: leer bytes UNA vez para que el stream no se agote al cambiar pestaña ──
        uploaded_file = st.file_uploader("Subir backup.xlsx", type=["xlsx"])
        if uploaded_file:
            file_bytes = uploaded_file.read()  # leer una vez en memoria
            xls = pd.ExcelFile(io.BytesIO(file_bytes))
            pestana = st.selectbox("Seleccione pestaña a restaurar:", xls.sheet_names)

            # preview
            df_preview = pd.read_excel(io.BytesIO(file_bytes), sheet_name=pestana)
            df_preview.columns = [str(c).strip().lower() for c in df_preview.columns]
            st.caption(f"Vista previa: {len(df_preview)} filas · columnas: {', '.join(df_preview.columns)}")
            st.dataframe(df_preview.head(5), use_container_width=True, hide_index=True)

            # ── Detección inteligente del tipo de pestaña ──
            cols = set(df_preview.columns)
            es_receta   = {'id_final', 'id_insumo', 'cantidad'}.issubset(cols)
            es_producto = {'nombre'}.issubset(cols) or {'producto'}.issubset(cols)
            es_venta    = {'producto', 'total_venta', 'metodo_pago'}.issubset(cols)

            if es_receta:
                st.info("🧪 Detectado: **Recetas** (id_final, id_insumo, cantidad)")
            elif es_venta:
                st.info("🚀 Detectado: **Historial de Ventas**")
            elif es_producto:
                st.info("📦 Detectado: **Productos**")
            else:
                st.warning("⚠️ No se reconoce el tipo de pestaña. Revisá las columnas.")

            modo_upsert = st.checkbox(
                "🔄 Usar UPSERT (actualizar si ya existe, requiere columna 'id')",
                value=False
            )

            if st.button(f"🚀 Iniciar Restauración de '{pestana}'"):
                df_excel = df_preview  # ya normalizado
                exitos, errores = 0, 0

                with st.spinner("Procesando..."):
                    for _, row in df_excel.iterrows():
                        sql, params = None, None

                        # ── RECETAS ──
                        if es_receta:
                            if pd.isna(row.get('id_final')) or pd.isna(row.get('id_insumo')):
                                errores += 1
                                continue
                            sql = """INSERT INTO recetas (id_final, id_insumo, cantidad)
                                     VALUES (:idf, :idi, :c)
                                     ON CONFLICT DO NOTHING"""
                            params = {
                                "idf": safe_int(row['id_final']),
                                "idi": safe_int(row['id_insumo']),
                                "c":   safe_float(row['cantidad'])
                            }

                        # ── VENTAS ──
                        elif es_venta:
                            producto = row.get('producto', '')
                            if pd.isna(producto) or str(producto).strip() == "":
                                errores += 1
                                continue
                            sql = """INSERT INTO historial_ventas
                                       (fecha, producto, cantidad, total_venta, metodo_pago)
                                     VALUES (:f, :p, :c, :t, :m)"""
                            params = {
                                "f": str(row.get('fecha', date.today())),
                                "p": str(producto),
                                "c": safe_float(row.get('cantidad', 1)),
                                "t": safe_float(row.get('total_venta', 0)),
                                "m": str(row.get('metodo_pago', ''))
                            }

                        # ── PRODUCTOS ──
                        elif es_producto:
                            nombre = row.get('nombre', row.get('producto', ''))
                            if pd.isna(nombre) or str(nombre).strip() == "":
                                errores += 1
                                continue
                            if modo_upsert and 'id' in cols and not pd.isna(row.get('id')):
                                sql = """INSERT INTO productos
                                           (id, nombre, tipo, unidad, stock_actual, costo_u, precio_v, precio_v2)
                                         VALUES (:id, :n, :t, :u, :s, :c, :p1, :p2)
                                         ON CONFLICT (id) DO UPDATE SET
                                           nombre=EXCLUDED.nombre, tipo=EXCLUDED.tipo,
                                           unidad=EXCLUDED.unidad, stock_actual=EXCLUDED.stock_actual,
                                           costo_u=EXCLUDED.costo_u, precio_v=EXCLUDED.precio_v,
                                           precio_v2=EXCLUDED.precio_v2"""
                                params = {
                                    "id": safe_int(row['id']),
                                    "n": str(nombre).strip(), "t": str(row.get('tipo', 'Insumo')),
                                    "u": str(row.get('unidad', 'Un')),
                                    "s": safe_float(row.get('stock_actual', 0)),
                                    "c": safe_float(row.get('costo_u', 0)),
                                    "p1": safe_float(row.get('precio_v', 0)),
                                    "p2": safe_float(row.get('precio_v2', 0))
                                }
                            else:
                                sql = """INSERT INTO productos
                                           (nombre, tipo, unidad, stock_actual, costo_u, precio_v, precio_v2)
                                         VALUES (:n, :t, :u, :s, :c, :p1, :p2)"""
                                params = {
                                    "n": str(nombre).strip(), "t": str(row.get('tipo', 'Insumo')),
                                    "u": str(row.get('unidad', 'Un')),
                                    "s": safe_float(row.get('stock_actual', 0)),
                                    "c": safe_float(row.get('costo_u', 0)),
                                    "p1": safe_float(row.get('precio_v', 0)),
                                    "p2": safe_float(row.get('precio_v2', 0))
                                }
                        else:
                            st.error("No se pudo determinar el tipo de datos. Revisá las columnas.")
                            break

                        if sql:
                            ok = db_query(sql, params, commit=True)
                            if ok:
                                exitos += 1
                            else:
                                errores += 1

                st.success(f"✅ {exitos} registros importados correctamente.")
                if errores:
                    st.warning(f"⚠️ {errores} filas con errores o vacías (omitidas).")
                st.rerun()

    st.divider()

    # Tabla con edición de precios inline
    df_ver = db_query(
        "SELECT id, nombre, tipo, unidad, stock_actual, costo_u, precio_v, precio_v2 "
        "FROM productos WHERE nombre IS NOT NULL ORDER BY tipo, nombre"
    )
    if df_ver is not None and not df_ver.empty:
        st.caption(f"Total: {len(df_ver)} productos")
        st.dataframe(df_ver, use_container_width=True, hide_index=True)

        # Botón para eliminar producto
        with st.expander("🗑️ Eliminar producto"):
            id_del = st.selectbox(
                "Seleccioná el producto a eliminar:",
                options=df_ver['id'].tolist(),
                format_func=lambda x: df_ver[df_ver['id'] == x]['nombre'].values[0]
            )
            if st.button("🗑️ Confirmar eliminación", type="primary"):
                db_query("DELETE FROM recetas WHERE id_final = :id OR id_insumo = :id", {"id": id_del}, commit=True)
                db_query("DELETE FROM productos WHERE id = :id", {"id": id_del}, commit=True)
                st.success("Producto eliminado.")
                st.rerun()

# ==========================================
# 🧪 2. RECETAS Y COSTEO
# ==========================================
elif menu == "🧪 Recetas y Costeo":
    st.header("🧪 Composición y Costeo")

    df_f = db_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL' ORDER BY nombre")
    df_i = db_query("SELECT id, nombre, unidad, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO' ORDER BY nombre")

    if df_f is None or df_f.empty:
        st.warning("No hay productos finales. Dá de alta uno primero en 'Inventario y Alta'.")
        st.stop()

    sel_f = st.selectbox("Producto Final:", df_f['nombre'].tolist())
    id_f  = int(df_f[df_f['nombre'] == sel_f].iloc[0]['id'])

    c1, c2 = st.columns([1, 2])

    with c1:
        st.subheader("Añadir insumo")
        if df_i is not None and not df_i.empty:
            with st.form("receta"):
                sel_i = st.selectbox("Insumo:", df_i['nombre'].tolist())
                row_i = df_i[df_i['nombre'] == sel_i].iloc[0]
                cant  = st.number_input(f"Cantidad ({row_i['unidad']})", min_value=0.001, format="%.3f")
                if st.form_submit_button("➕ Añadir"):
                    # Actualizar si ya existe, insertar si no
                    db_query(
                        """INSERT INTO recetas (id_final, id_insumo, cantidad)
                           VALUES (:idf, :idi, :c)
                           ON CONFLICT (id_final, id_insumo) DO UPDATE SET cantidad = EXCLUDED.cantidad""",
                        {"idf": id_f, "idi": int(row_i['id']), "c": cant},
                        commit=True
                    )
                    st.rerun()
        else:
            st.info("Sin insumos cargados.")

    with c2:
        st.subheader("Receta actual")
        df_rec = db_query(
            """SELECT r.id as receta_id, i.nombre, r.cantidad, i.unidad,
                      i.costo_u, (r.cantidad * i.costo_u) as subtotal
               FROM recetas r
               JOIN productos i ON r.id_insumo = i.id
               WHERE r.id_final = :id
               ORDER BY i.nombre""",
            {"id": id_f}
        )
        if df_rec is not None and not df_rec.empty:
            costo_total = df_rec['subtotal'].sum()
            st.metric("💰 Costo Total de Receta", f"$ {costo_total:,.2f}")

            # Mostrar receta con botón eliminar por fila
            for _, r in df_rec.iterrows():
                col_n, col_c, col_s, col_btn = st.columns([3, 1, 1, 1])
                col_n.write(f"**{r['nombre']}**")
                col_c.write(f"{r['cantidad']} {r['unidad']}")
                col_s.write(f"$ {r['subtotal']:,.2f}")
                if col_btn.button("🗑️", key=f"del_rec_{r['receta_id']}"):
                    db_query("DELETE FROM recetas WHERE id = :id", {"id": int(r['receta_id'])}, commit=True)
                    st.rerun()

            # Actualizar precio de venta sugerido
            st.divider()
            st.caption("💡 Actualizá precios de venta basado en el costo calculado")
            with st.form("actualizar_precio"):
                margen_l1 = st.number_input("Margen L1 Minorista (%)", min_value=0.0, value=100.0)
                margen_l2 = st.number_input("Margen L2 Mayorista (%)", min_value=0.0, value=60.0)
                p1_sug = costo_total * (1 + margen_l1 / 100)
                p2_sug = costo_total * (1 + margen_l2 / 100)
                st.write(f"Precio L1 sugerido: **$ {p1_sug:,.2f}** | Precio L2 sugerido: **$ {p2_sug:,.2f}**")
                if st.form_submit_button("💾 Aplicar precios y costo a producto"):
                    db_query(
                        "UPDATE productos SET costo_u = :c, precio_v = :p1, precio_v2 = :p2 WHERE id = :id",
                        {"c": costo_total, "p1": p1_sug, "p2": p2_sug, "id": id_f},
                        commit=True
                    )
                    st.success("✅ Precios actualizados.")
                    st.rerun()
        else:
            st.info("Esta receta no tiene insumos aún.")

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
        "WHERE UPPER(tipo) != 'FINAL' AND stock_actual < 100 ORDER BY stock_actual"
    )
    if df_bajo is not None and not df_bajo.empty:
        st.dataframe(df_bajo, use_container_width=True, hide_index=True)
    else:
        st.success("Todos los insumos tienen stock suficiente.")

# ==========================================
# 🚀 5. REGISTRAR VENTAS
# ==========================================
elif menu == "🚀 Registrar Ventas":
    st.header("🚀 Nueva Venta")

    df_p = db_query(
        "SELECT id, nombre, precio_v, precio_v2, stock_actual "
        "FROM productos WHERE UPPER(tipo) = 'FINAL' ORDER BY nombre"
    )

    if df_p is None or df_p.empty:
        st.warning("No hay productos finales cargados.")
        st.stop()

    sel_p = st.selectbox("Producto:", df_p['nombre'].tolist())
    row   = df_p[df_p['nombre'] == sel_p].iloc[0]

    p1 = safe_float(row['precio_v'])
    p2 = safe_float(row['precio_v2'])

    col_info, col_form = st.columns([1, 2])
    col_info.metric("📦 Stock disponible", f"{row['stock_actual']} un.")
    col_info.metric("💲 Precio Minorista", f"$ {p1:,.2f}")
    col_info.metric("💲 Precio Mayorista", f"$ {p2:,.2f}")

    with col_form:
        with st.form("venta"):
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
                    ok = db_query(
                        """INSERT INTO historial_ventas
                             (fecha, producto, cantidad, total_venta, metodo_pago)
                           VALUES (:f, :p, :c, :t, :m)""",
                        {"f": date.today(), "p": sel_p, "c": cant,
                         "t": total_cobrar, "m": metodo},
                        commit=True
                    )
                    if ok:
                        db_query(
                            "UPDATE productos SET stock_actual = stock_actual - :c WHERE id = :id",
                            {"c": cant, "id": int(row['id'])}, commit=True
                        )
                        st.success(f"✅ Venta registrada: {cant} x {sel_p} = $ {total_cobrar:,.2f}")
                        st.rerun()

# ==========================================
# 📊 6. CAJA Y FILTROS
# ==========================================
elif menu == "📊 Caja y Filtros":
    st.header("📊 Movimientos de Caja")

    col_f1, col_f2 = st.columns(2)
    desde = col_f1.date_input("Desde:", value=date.today().replace(day=1))
    hasta = col_f2.date_input("Hasta:", value=date.today())

    df_v = db_query(
        """SELECT fecha, producto, cantidad, total_venta, metodo_pago
           FROM historial_ventas
           WHERE fecha BETWEEN :d AND :h
           ORDER BY fecha DESC""",
        {"d": str(desde), "h": str(hasta)}
    )

    if df_v is not None and not df_v.empty:
        total_gral = df_v['total_venta'].sum()

        def total_por_metodo(palabras):
            patron = '|'.join(palabras)
            mask   = df_v['metodo_pago'].str.contains(patron, case=False, na=False)
            return df_v[mask]['total_venta'].sum()

        t_efectivo = total_por_metodo(['Efectivo'])
        t_banco    = total_por_metodo(['Transferencia', 'Banco', 'Mercado Pago', 'MP'])
        t_tarjeta  = total_por_metodo(['Tarjeta', 'Crédito', 'Débito'])

        m0, m1, m2, m3 = st.columns(4)
        m0.metric("💰 Total General",    f"$ {total_gral:,.2f}")
        m1.metric("💵 Efectivo",         f"$ {t_efectivo:,.2f}")
        m2.metric("🏦 Banco / Virtual",  f"$ {t_banco:,.2f}")
        m3.metric("💳 Tarjeta / Deuda",  f"$ {t_tarjeta:,.2f}")

        st.divider()

        # Mini gráfico de ventas diarias
        df_v['fecha'] = pd.to_datetime(df_v['fecha'])
        df_diario = df_v.groupby('fecha')['total_venta'].sum().reset_index()
        st.bar_chart(df_diario.set_index('fecha')['total_venta'])

        st.subheader("Detalle de operaciones")
        st.dataframe(df_v, use_container_width=True, hide_index=True)

        # Exportar CSV
        csv = df_v.to_csv(index=False).encode('utf-8')
        st.download_button(
            "⬇️ Descargar CSV",
            data=csv,
            file_name=f"ventas_{desde}_{hasta}.csv",
            mime="text/csv"
        )
    else:
        st.info("No hay ventas registradas en este período.")

# ==========================================
# 📈 7. RENTABILIDAD
# ==========================================
elif menu == "📈 Rentabilidad":
    st.header("📈 Análisis de Margen y Rentabilidad")

    df_r = db_query(
        "SELECT nombre, costo_u, precio_v, precio_v2 "
        "FROM productos WHERE UPPER(tipo) = 'FINAL' ORDER BY nombre"
    )

    if df_r is None or df_r.empty:
        st.warning("No hay productos finales cargados.")
        st.stop()

    # Calcular márgenes evitando división por cero
    df_r['Ganancia L1 ($)'] = df_r['precio_v'] - df_r['costo_u']
    df_r['Ganancia L2 ($)'] = df_r['precio_v2'] - df_r['costo_u']

    df_r['Margen L1 (%)'] = df_r.apply(
        lambda x: (x['Ganancia L1 ($)'] / x['precio_v'] * 100) if x['precio_v'] > 0 else 0, axis=1
    )
    df_r['Margen L2 (%)'] = df_r.apply(
        lambda x: (x['Ganancia L2 ($)'] / x['precio_v2'] * 100) if x['precio_v2'] > 0 else 0, axis=1
    )

    # Semáforo visual de márgenes
    def color_margen(val):
        if val >= 50:   return 'background-color: #d4edda'  # verde
        elif val >= 25: return 'background-color: #fff3cd'  # amarillo
        else:           return 'background-color: #f8d7da'  # rojo

    styled = df_r.style.format({
        "costo_u":      "$ {:.2f}",
        "precio_v":     "$ {:.2f}",
        "precio_v2":    "$ {:.2f}",
        "Ganancia L1 ($)": "$ {:.2f}",
        "Ganancia L2 ($)": "$ {:.2f}",
        "Margen L1 (%)":   "{:.1f}%",
        "Margen L2 (%)":   "{:.1f}%",
    }).applymap(color_margen, subset=["Margen L1 (%)", "Margen L2 (%)"])

    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Resumen ejecutivo
    st.divider()
    col1, col2 = st.columns(2)
    col1.metric("📊 Margen L1 promedio", f"{df_r['Margen L1 (%)'].mean():.1f}%")
    col2.metric("📊 Margen L2 promedio", f"{df_r['Margen L2 (%)'].mean():.1f}%")

    productos_sin_receta = df_r[df_r['costo_u'] == 0]['nombre'].tolist()
    if productos_sin_receta:
        st.warning(f"⚠️ Productos sin costo calculado (sin receta): {', '.join(productos_sin_receta)}")
