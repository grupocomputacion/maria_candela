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
    "📈 Rentabilidad"
])

# ==========================================
# 📦 1. INVENTARIO Y ALTA (VERSIÓN PROFESIONAL)
# ==========================================
if menu == "📦 Inventario y Alta":
    st.subheader("📦 Gestión de Inventario Profesional")
    
    # Botón de sincronización con feedback directo
    if st.sidebar.button("🔄 Sincronizar Base de Datos"):
        st.cache_data.clear()
        st.rerun()

    col_alta, col_imp = st.columns(2)

    with col_alta.expander("➕ DAR DE ALTA MANUAL"):
        with st.form("alta"):
            c1, c2 = st.columns(2)
            n = c1.text_input("Nombre")
            t = c2.selectbox("Tipo", ["Insumo", "Final", "Herramienta", "Packaging"])
            u = c1.selectbox("Unidad", ["Gr", "Ml", "Un", "Kg"])
            s = c2.number_input("Stock Inicial", min_value=0.0)
            c = c1.number_input("Costo Unitario ($)", min_value=0.0)
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
                xls = pd.ExcelFile(uploaded_file)
                for sheet in xls.sheet_names:
                    df_ex = pd.read_excel(uploaded_file, sheet_name=sheet)
                    df_ex.columns = [str(c).strip().lower() for c in df_ex.columns]
                    for _, row in df_ex.iterrows():
                        if "nombre" in df_ex.columns:
                            db_query("""INSERT INTO productos (nombre, tipo, unidad, stock_actual, costo_u, precio_v, precio_v2) 
                                     VALUES (:n, :t, :u, :s, :c, :p1, :p2)""",
                                     {"n": str(row.get('nombre', '')).strip().upper(), "t": str(row.get('tipo', 'Insumo')),
                                      "u": str(row.get('unidad', 'Un')), "s": safe_float(row.get('stock_actual', 0)),
                                      "c": safe_float(row.get('costo_u', 0)), "p1": safe_float(row.get('precio_v', 0)),
                                      "p2": safe_float(row.get('precio_v2', 0))}, commit=True)
                st.cache_data.clear()
                st.rerun()

        st.divider()
        clave_b = st.text_input("Clave de Seguridad:", type="password")
        if st.button("🗑️ LIMPIAR TODAS LAS TABLAS"):
            if clave_b == "3280":
                db_query("TRUNCATE TABLE recetas, historial_ventas, productos RESTART IDENTITY CASCADE", commit=True)
                st.cache_data.clear()
                st.rerun()

    st.divider()
    
    # --- FILTROS PROFESIONALES UNIFORMES ---
    f1, f2, f3 = st.columns(3)
    with f1:
        f_tipo = st.selectbox("Filtrar por Tipo:", ["Todos", "insumo", "final", "herramienta", "packaging"])
    with f2:
        f_stock = st.selectbox("Filtrar por Stock:", ["Todos", "Con Stock", "Sin Stock"])
    with f3:
        f_busq = st.text_input("🔍 Buscar por Nombre:")

    # --- CONSULTA Y RENDERIZADO ---
    df_inv = db_query("""
        SELECT nombre as "Nombre", tipo as "Tipo", unidad as "Unidad", 
               stock_actual as "Stock Actual", costo_u as "Costo", 
               precio_v as "P.V. Lista 1", precio_v2 as "P.V. Lista 2" 
        FROM productos WHERE nombre IS NOT NULL
    """)
    
    if df_inv is not None and not df_inv.empty:
        # Aplicación de filtros
        if f_tipo != "Todos":
            df_inv = df_inv[df_inv['Tipo'] == f_tipo]
        
        if f_stock == "Con Stock":
            df_inv = df_inv[df_inv['Stock Actual'] > 0]
        elif f_stock == "Sin Stock":
            df_inv = df_inv[df_inv['Stock Actual'] <= 0]
            
        if f_busq:
            df_inv = df_inv[df_inv['Nombre'].str.contains(f_busq.upper(), na=False)]

        # Lógica de Color Profesional (Status Indicator)
        # Creamos una columna visual que Streamlit reconoce para mostrar colores
        df_inv['Estado'] = df_inv['Stock Actual'].apply(lambda x: "🟢" if x > 0 else "🔴")
        
        # Reordenar para que el estado esté al principio
        cols = ['Estado'] + [c for c in df_inv.columns if c != 'Estado']
        df_inv = df_inv[cols]

        # Configuración de columnas (Decimales y Visualización)
        st.dataframe(
            df_inv,
            hide_index=True,
            width='stretch', # Reemplazo de use_container_width según log
            column_config={
                "Stock Actual": st.column_config.NumberColumn("Stock Actual", format="%.2f"),
                "Costo": st.column_config.NumberColumn("Costo", format="$ %.2f"),
                "P.V. Lista 1": st.column_config.NumberColumn("P.V. Lista 1", format="$ %.2f"),
                "P.V. Lista 2": st.column_config.NumberColumn("P.V. Lista 2", format="$ %.2f"),
                "Estado": st.column_config.TextColumn(" ", width="small")
            }
        )
        
        # Exportación
        towrite = io.BytesIO()
        df_inv.to_excel(towrite, index=False, engine='openpyxl')
        st.download_button("📥 Exportar Inventario", towrite.getvalue(), "inventario_velas.xlsx")
    else:
        st.info("Sin registros que coincidan con los filtros.")

        
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
