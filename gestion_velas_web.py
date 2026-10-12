import streamlit as st
import pandas as pd
from datetime import datetime, date
import io
import os
import base64
from sqlalchemy import create_engine, text

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Velas Candela Pro - Sistema Integral", layout="wide")

# ==========================================
# 1. MOTOR DE BASE DE DATOS (PROTEGIDO)
# ==========================================
@st.cache_resource
def get_engine():
    if "postgres" not in st.secrets:
        st.error("❌ Error de configuración: No existe la clave [postgres] en st.secrets.")
        return None
    try:
        conn_url = st.secrets["postgres"]["url"].strip().replace(" ", "")
        if conn_url.startswith("postgres://"):
            conn_url = conn_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif conn_url.startswith("postgresql://") and not conn_url.startswith("postgresql+psycopg2://"):
            conn_url = conn_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return create_engine(conn_url, pool_pre_ping=True, pool_recycle=300)
    except Exception as e:
        st.error(f"❌ Error al crear motor de base de datos: {e}")
        return None

def db_query(query, params=None, commit=False):
    engine = get_engine()
    if engine is None: 
        return None
    try:
        with engine.connect() as conn:
            if commit:
                conn.execute(text(query), params)
                conn.commit()
                return True
            else:
                return pd.read_sql(text(query), conn, params=params)
    except Exception as e:
        if not commit: 
            st.error(f"Error de BD: {e}")
        return None

def safe_float(val):
    try:
        if pd.isna(val) or str(val).strip() == "": 
            return 0.0
        return float(val)
    except: 
        return 0.0

# --- FUNCIONES DE ESTILO PARA RENTABILIDAD ---
def color_margen(val):
    try:
        color = 'red' if val < 20 else 'orange' if val < 40 else 'green'
        return f'color: {color}; font-weight: bold'
    except: 
        return ''

# --- FUNCIÓN GENERADORA DE DOCUMENTO IMPRIMIBLE ---
def generar_html_pedido(pedido_id, fecha_p, fecha_e, cliente, items, total_gral, sena_val=0.0, estado="Pendiente", logo_path="logo.png"):
    logo_tag = ""
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as img_f:
            b64_logo = base64.b64encode(img_f.read()).decode("utf-8")
            logo_tag = f'<img src="data:image/png;base64,{b64_logo}" style="max-height: 80px; margin-bottom: 10px;" />'
    
    saldo_pendiente = max(0.0, total_gral - sena_val)
    color_estado = "#27ae60" if estado == "Entregado" else "#e67e22"

    filas_html = ""
    for it in items:
        detalle_extra = f"<br><small style='color: #666; font-style: italic;'>↳ Detalle: {it['detalle']}</small>" if it.get('detalle') else ""
        filas_html += f"""
        <tr>
            <td style="padding: 10px 8px; border-bottom: 1px solid #ddd;">
                <strong>{it['producto']}</strong>
                {detalle_extra}
            </td>
            <td style="padding: 10px 8px; border-bottom: 1px solid #ddd; text-align: center;">{it['cantidad']:.2f}</td>
            <td style="padding: 10px 8px; border-bottom: 1px solid #ddd; text-align: right;">$ {it['precio_u']:,.2f}</td>
            <td style="padding: 10px 8px; border-bottom: 1px solid #ddd; text-align: right; font-weight: bold;">$ {it['subtotal']:,.2f}</td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Pedido #{pedido_id:05d} - {cliente}</title>
        <style>
            body {{ font-family: 'Helvetica Neue', Arial, sans-serif; margin: 30px; color: #333; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #444; padding-bottom: 15px; }}
            .info-box {{ margin: 25px 0; padding: 15px; background: #fdfdfd; border: 1px solid #eee; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th {{ background: #2c3e50; color: white; padding: 10px 8px; text-align: left; font-size: 14px; }}
            .totales-wrapper {{ margin-top: 25px; display: flex; justify-content: flex-end; }}
            .totales-table {{ width: 350px; border-collapse: collapse; }}
            .totales-table td {{ padding: 6px 10px; font-size: 15px; }}
            .saldo-destacado {{ font-size: 18px; font-weight: bold; color: #c0392b; border-top: 2px solid #333; }}
            @media print {{
                .no-print {{ display: none !important; }}
                body {{ margin: 0; }}
            }}
        </style>
    </head>
    <body>
        <div class="no-print" style="margin-bottom: 20px;">
            <button onclick="window.print()" style="padding: 10px 20px; font-size: 15px; background-color: #27ae60; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">
                🖨️ Imprimir / Guardar en PDF
            </button>
        </div>
        <div class="header">
            <div>
                {logo_tag}
                <h2 style="margin: 0; color: #2c3e50;">NOTA DE PEDIDO</h2>
                <small style="color: #777;">Velas Candela Pro - Sistema Integral</small>
            </div>
            <div style="text-align: right;">
                <h3 style="margin: 0; color: #c0392b;">Pedido N°: {pedido_id:05d}</h3>
                <p style="margin: 5px 0; font-size: 14px;"><strong>Fecha Emisión:</strong> {fecha_p.strftime('%d/%m/%Y') if hasattr(fecha_p, 'strftime') else fecha_p}</p>
                <p style="margin: 5px 0; font-size: 14px;"><strong>Compromiso Entrega:</strong> {fecha_e.strftime('%d/%m/%Y') if hasattr(fecha_e, 'strftime') else fecha_e}</p>
            </div>
        </div>

        <div class="info-box">
            <p style="margin: 0; font-size: 16px;"><strong>Cliente / Razón Social:</strong> {cliente}</p>
            <span style="background: {color_estado}; color: white; padding: 4px 12px; border-radius: 12px; font-weight: bold; font-size: 14px;">
                {estado.upper()}
            </span>
        </div>

        <table>
            <thead>
                <tr>
                    <th>Producto / Especificación</th>
                    <th style="text-align: center;">Cantidad</th>
                    <th style="text-align: right;">Precio Unitario</th>
                    <th style="text-align: right;">Subtotal</th>
                </tr>
            </thead>
            <tbody>
                {filas_html}
            </tbody>
        </table>

        <div class="totales-wrapper">
            <table class="totales-table">
                <tr>
                    <td style="text-align: right;"><strong>Total Pedido:</strong></td>
                    <td style="text-align: right; font-weight: bold;">$ {total_gral:,.2f}</td>
                </tr>
                <tr>
                    <td style="text-align: right; color: #27ae60;"><strong>Seña / Anticipo:</strong></td>
                    <td style="text-align: right; color: #27ae60; font-weight: bold;">$ {sena_val:,.2f}</td>
                </tr>
                <tr class="saldo-destacado">
                    <td style="text-align: right;">SALDO A COBRAR:</td>
                    <td style="text-align: right;">$ {saldo_pendiente:,.2f}</td>
                </tr>
            </table>
        </div>

        <div style="margin-top: 50px; border-top: 1px dashed #aaa; padding-top: 10px; font-size: 12px; text-align: center; color: #888;">
            Documento emitido para control de fabricación, despacho y cobranza.
        </div>
    </body>
    </html>
    """
    return html

# ==========================================
# 2. MENÚ LATERAL Y SINCRONIZACIÓN GLOBAL
# ==========================================
st.sidebar.title("🕯️ Velas Control")

if st.sidebar.button("🔄 Sincronizar / Refrescar BD", use_container_width=True):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()

st.sidebar.divider()

menu = st.sidebar.radio("Ir a:", [
    "📦 Inventario y Alta", 
    "🧪 Recetas y Costeo", 
    "🏭 Fabricación",
    "📋 Pedidos de Clientes",
    "💰 Registro de Compras", 
    "🚀 Registrar Ventas", 
    "📊 Caja y Filtros",
    "📈 Rentabilidad",
    "💰 Flujo de Caja",
    "📊 Análisis de Resultados",
    "🔄 Actualización Masiva",
    "💾 Backup y Restauración Total"
])

# ==========================================
# 📦 1. INVENTARIO Y ALTA
# ==========================================
if menu == "📦 Inventario y Alta":
    st.subheader("📦 Gestión de Inventario Profesional")

    with st.expander("➕ DAR DE ALTA MANUAL"):
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

    st.divider()
    
    f1, f2, f3 = st.columns(3)
    f_tipo = f1.selectbox("Filtrar por Tipo:", ["Todos", "insumo", "final", "herramienta", "packaging"])
    f_stock = f2.selectbox("Filtrar por Stock:", ["Todos", "Con Stock", "Sin Stock"])
    f_busq = f3.text_input("🔍 Buscar por Nombre:")

    df_inv = db_query("""
        SELECT id, nombre as "Descripción", tipo as "Tipo", unidad as "Unidad", 
               stock_actual as "Stock", costo_u as "Costo", 
               precio_v as "P.V. Lista 1", precio_v2 as "P.V. Lista 2" 
        FROM productos ORDER BY nombre ASC
    """)
    
    if df_inv is not None and not df_inv.empty:
        if f_tipo != "Todos": df_inv = df_inv[df_inv['Tipo'] == f_tipo]
        if f_stock == "Con Stock": df_inv = df_inv[df_inv['Stock'] > 0]
        elif f_stock == "Sin Stock": df_inv = df_inv[df_inv['Stock'] <= 0]
        if f_busq: df_inv = df_inv[df_inv['Descripción'].str.contains(f_busq.upper(), na=False)]

        st.info("💡 Editá directamente en la tabla y presioná 'Guardar Cambios'.")
        
        edited_df = st.data_editor(
            df_inv,
            hide_index=True,
            use_container_width=True,
            key="editor_inventario",
            column_config={
                "id": None,
                "Tipo": st.column_config.SelectboxColumn("Tipo", options=["insumo", "final", "herramienta", "packaging"]),
                "Stock": st.column_config.NumberColumn("Stock", format="%.2f"),
                "Costo": st.column_config.NumberColumn("Costo", format="$ %.2f"),
                "P.V. Lista 1": st.column_config.NumberColumn("P.V. Lista 1", format="$ %.2f"),
                "P.V. Lista 2": st.column_config.NumberColumn("P.V. Lista 2", format="$ %.2f"),
            }
        )

        if st.button("💾 Guardar Cambios en Base de Datos"):
            for _, row in edited_df.iterrows():
                db_query("""UPDATE productos SET nombre = :n, tipo = :t, stock_actual = :s, costo_u = :c, precio_v = :p1, precio_v2 = :p2 WHERE id = :id""",
                         {"n": str(row['Descripción']).upper(), "t": row['Tipo'], "s": row['Stock'], "c": row['Costo'], "p1": row['P.V. Lista 1'], "p2": row['P.V. Lista 2'], "id": row['id']}, commit=True)
            st.success("✅ ¡Base de Datos actualizada!")
            st.cache_data.clear()
            st.rerun()
    else:
        st.info("La base de datos de productos está vacía.")

# ==========================================
# 🧪 2. RECETAS Y COSTEO
# ==========================================
elif menu == "🧪 Recetas y Costeo":
    st.header("🧪 Composición y Costeo")

    df_f = db_query("SELECT id, nombre, precio_v, precio_v2, costo_u FROM productos WHERE UPPER(tipo) = 'FINAL' ORDER BY nombre")
    df_i = db_query("SELECT id, nombre, unidad, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO' ORDER BY nombre")

    if df_f is None or df_f.empty:
        st.warning("No hay productos finales cargados.")
        st.stop()

    sel_f = st.selectbox("Producto Final a costear:", df_f['nombre'].tolist(), key="main_f_selector")
    row_actual = df_f[df_f['nombre'] == sel_f].iloc[0]
    id_f_actual = int(row_actual['id'])

    c1, c2 = st.columns([1, 2])

    with c1:
        st.subheader("Añadir insumo")
        if df_i is not None and not df_i.empty:
            st.write(f"🏷️ **ID Destino:** {id_f_actual}")
            
            ins_nombre = st.selectbox("Insumo:", df_i['nombre'].tolist(), key=f"ins_sel_{id_f_actual}")
            det_i = df_i[df_i['nombre'] == ins_nombre].iloc[0]
            
            u_txt = str(det_i['unidad']) if pd.notna(det_i['unidad']) else "un"
            id_i_real = int(det_i['id'])
            cant_input = st.number_input(f"Cantidad ({u_txt})", min_value=0.0, step=0.1, format="%.3f", key=f"qty_val_{id_f_actual}")

            if st.button("🚀 GRABAR AHORA", use_container_width=True, type="primary"):
                if cant_input > 0:
                    sql_test = "INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (:idf, :idi, :c)"
                    try:
                        db_query(sql_test, {"idf": id_f_actual, "idi": id_i_real, "c": float(cant_input)}, commit=True)
                        check = db_query("SELECT id FROM recetas WHERE id_final = :f AND id_insumo = :i", {"f": id_f_actual, "i": id_i_real})
                        if check is not None and not check.empty:
                            st.success("✅ ¡Grabado correctamente!")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("❌ La base de datos no confirmó la inserción.")
                    except Exception as e:
                        st.error(f"❌ Error de base de datos: {e}")
                else:
                    st.warning("Cantidad debe ser mayor a 0.")

    with c2:
        st.subheader("Estructura de Costos")
        
        if st.button("🔄 Forzar Recarga"):
            st.cache_data.clear()
            st.rerun()

        df_rec = db_query(
            """SELECT r.id, p.nombre, r.cantidad, COALESCE(p.unidad, 'un') as unidad, COALESCE(p.costo_u, 0) as costo_u
               FROM recetas r
               INNER JOIN productos p ON r.id_insumo = p.id
               WHERE r.id_final = :idf""", {"idf": id_f_actual}
        )

        costo_fab = 0.0
        
        if df_rec is not None and not df_rec.empty:
            df_rec['subtotal'] = df_rec['cantidad'] * df_rec['costo_u']
            costo_fab = float(df_rec['subtotal'].sum())
            
            st.metric("Costo Total Fabricación", f"$ {costo_fab:,.2f}")

            for _, r in df_rec.iterrows():
                cn, cq, cs, cb = st.columns([3, 1.5, 1.5, 0.5])
                cn.write(f"**{r['nombre']}**")
                cq.write(f"{r['cantidad']} {r['unidad']}")
                cs.write(f"$ {r['subtotal']:,.2f}")
                
                if cb.button("🗑️", key=f"del_{r['id']}"):
                    db_query("DELETE FROM recetas WHERE id = :id", {"id": int(r['id'])}, commit=True)
                    st.cache_data.clear()
                    st.rerun()

            st.divider()
            st.subheader("📈 Simulador de Precios de Venta")
            st.caption("Calculá tus márgenes antes de impactar en el Inventario")

            m_l1_act = ((float(row_actual['precio_v']) / costo_fab) - 1) * 100 if costo_fab > 0 and row_actual['precio_v'] else 0.0
            m_l2_act = ((float(row_actual['precio_v2']) / costo_fab) - 1) * 100 if costo_fab > 0 and row_actual['precio_v2'] else 0.0

            with st.container(border=True):
                c_l1, c_l2 = st.columns(2)
                
                with c_l1:
                    st.markdown("**Lista 1 (Minorista)**")
                    st.write(f"Actual: ${row_actual['precio_v'] if row_actual['precio_v'] else 0:,.2f} ({m_l1_act:,.1f}%)")
                    tipo_l1 = st.radio("Calcular por:", ["Monto $", "Porcentaje %"], key="tipo_l1", horizontal=True)
                    if tipo_l1 == "Monto $":
                        p1_sim = st.number_input("Precio Final L1:", value=float(row_actual['precio_v']) if row_actual['precio_v'] else 0.0, step=10.0, key="in_p1")
                        margen1 = ((p1_sim / costo_fab) - 1) * 100 if costo_fab > 0 else 0.0
                        st.info(f"Equivale a un **{margen1:,.2f}%** de ganancia")
                    else:
                        m1_sim = st.number_input("Porcentaje L1:", value=m_l1_act, step=1.0, key="in_m1")
                        p1_sim = costo_fab * (1 + m1_sim / 100)
                        st.info(f"Equivale a un precio de **${p1_sim:,.2f}**")

                with c_l2:
                    st.markdown("**Lista 2 (Mayorista)**")
                    st.write(f"Actual: ${row_actual['precio_v2'] if row_actual['precio_v2'] else 0:,.2f} ({m_l2_act:,.1f}%)")
                    tipo_l2 = st.radio("Calcular por:", ["Monto $", "Porcentaje %"], key="tipo_l2", horizontal=True)
                    if tipo_l2 == "Monto $":
                        p2_sim = st.number_input("Precio Final L2:", value=float(row_actual['precio_v2']) if row_actual['precio_v2'] else 0.0, step=10.0, key="in_p2")
                        margen2 = ((p2_sim / costo_fab) - 1) * 100 if costo_fab > 0 else 0.0
                        st.info(f"Equivale a un **{margen2:,.2f}%** de ganancia")
                    else:
                        m2_sim = st.number_input("Porcentaje L2:", value=m_l2_act, step=1.0, key="in_m2")
                        p2_sim = costo_fab * (1 + m2_sim / 100)
                        st.info(f"Equivale a un precio de **${p2_sim:,.2f}**")

                st.divider()
                st.write(f"**RESUMEN A GRABAR:** L1: ${p1_sim:,.2f} | L2: ${p2_sim:,.2f} | Costo: ${costo_fab:,.2f}")
                
                if st.button("💾 CONFIRMAR Y GRABAR EN INVENTARIO", use_container_width=True, type="primary"):
                    try:
                        sql_upd = """
                            UPDATE productos 
                            SET costo_u = :c, precio_v = :p1, precio_v2 = :p2 
                            WHERE id = :id
                        """
                        db_query(sql_upd, {
                            "c": float(costo_fab), 
                            "p1": float(p1_sim), 
                            "p2": float(p2_sim), 
                            "id": int(id_f_actual)
                        }, commit=True)
                        
                        st.cache_data.clear()
                        st.success("✅ Precios e Inventario actualizados correctamente.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al actualizar: {e}")
        else:
            st.info("La receta está vacía. Añadí insumos a la izquierda.")

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
        db_query(
            "UPDATE productos SET stock_actual = stock_actual + :c WHERE id = :id",
            {"c": cantidad, "id": id_f}, commit=True
        )
        for _, r in receta.iterrows():
            db_query(
                "UPDATE productos SET stock_actual = stock_actual - :c WHERE nombre = :n",
                {"c": float(r['necesario']), "n": r['nombre']}, commit=True
            )
        st.success(f"✅ {cantidad} unidades de **{prod_sel}** fabricadas y stock actualizado.")
        st.rerun()

# ==========================================
# 📋 4. PEDIDOS DE CLIENTES (CON LISTADO Y FILTRO DE ENTREGADO)
# ==========================================
elif menu == "📋 Pedidos de Clientes":
    st.header("📋 Gestión Integral de Pedidos")

    tab_alta_ped, tab_lista_ped = st.tabs(["📝 Nuevo Pedido", "📑 Listado y Gestión de Pedidos"])

    # --- PESTAÑA 1: NUEVO PEDIDO ---
    with tab_alta_ped:
        if "items_pedido" not in st.session_state:
            st.session_state["items_pedido"] = []

        with st.container(border=True):
            st.subheader("1. Datos Generales del Pedido")
            c_cli, c_fped, c_fent, c_sena = st.columns([2, 1, 1, 1])
            cliente = c_cli.text_input("Nombre / Razón Social del Cliente:", placeholder="Ej: Marcela Gómez")
            fecha_ped = c_fped.date_input("Fecha de Pedido:", value=date.today())
            fecha_ent = c_fent.date_input("Compromiso de Entrega:", value=date.today())
            sena_pago = c_sena.number_input("Seña / Anticipo ($):", min_value=0.0, step=100.0, format="%.2f")

        with st.container(border=True):
            st.subheader("2. Cargar Productos")
            df_p = db_query("SELECT id, nombre, precio_v, precio_v2, stock_actual FROM productos WHERE UPPER(tipo) = 'FINAL' ORDER BY nombre")
            
            if df_p is not None and not df_p.empty:
                c_prod, c_lista, c_cant = st.columns([3, 1.5, 1.5])
                prod_sel = c_prod.selectbox("Seleccionar Producto:", df_p['nombre'].tolist())
                tipo_lista = c_lista.selectbox("Lista:", ["Lista 1 (Minorista)", "Lista 2 (Mayorista)"])
                cant_input = c_cant.number_input("Cantidad:", min_value=1.0, value=1.0, step=1.0)
                
                c_det, c_add = st.columns([4, 1])
                detalle_input = c_det.text_input("Características / Comentario (fragancia, color, etc.):", placeholder="Ej: Vainilla y Coco, frasco ámbar")
                
                prod_row = df_p[df_p['nombre'] == prod_sel].iloc[0]
                precio_base = safe_float(prod_row['precio_v'] if "Lista 1" in tipo_lista else prod_row['precio_v2'])
                
                if c_add.button("➕ Agregar", use_container_width=True, type="secondary"):
                    nuevo_item = {
                        "producto_id": int(prod_row['id']),
                        "producto": prod_sel,
                        "detalle": detalle_input.strip(),
                        "cantidad": float(cant_input),
                        "precio_u": float(precio_base),
                        "subtotal": float(cant_input * precio_base)
                    }
                    st.session_state["items_pedido"].append(nuevo_item)
                    st.rerun()
            else:
                st.warning("No hay productos de tipo FINAL cargados en inventario.")

        if len(st.session_state["items_pedido"]) > 0:
            st.subheader("3. Detalle de Ítems (Edición directa de valores)")
            df_detalle = pd.DataFrame(st.session_state["items_pedido"])
            
            df_editado = st.data_editor(
                df_detalle[['producto', 'detalle', 'cantidad', 'precio_u', 'subtotal']],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "producto": st.column_config.TextColumn("Producto", disabled=True),
                    "detalle": st.column_config.TextColumn("Características / Fragancia / Color"),
                    "cantidad": st.column_config.NumberColumn("Cantidad", min_value=1.0, step=1.0),
                    "precio_u": st.column_config.NumberColumn("Precio Unitario ($)", min_value=0.0, format="$ %.2f"),
                    "subtotal": st.column_config.NumberColumn("Subtotal ($)", min_value=0.0, format="$ %.2f")
                },
                key="editor_pedidos"
            )
            
            items_actualizados = []
            for idx, row in df_editado.iterrows():
                orig = st.session_state["items_pedido"][idx]
                c_val = safe_float(row['cantidad'])
                p_val = safe_float(row['precio_u'])
                s_val = safe_float(row['subtotal'])
                det_val = str(row['detalle']).strip() if pd.notna(row['detalle']) else ""
                
                if round(s_val, 2) != round(orig['subtotal'], 2) and round(p_val, 2) == round(orig['precio_u'], 2):
                    final_sub = s_val
                    final_pu = s_val / c_val if c_val > 0 else 0.0
                else:
                    final_sub = c_val * p_val
                    final_pu = p_val

                items_actualizados.append({
                    "producto_id": orig['producto_id'],
                    "producto": orig['producto'],
                    "detalle": det_val,
                    "cantidad": c_val,
                    "precio_u": final_pu,
                    "subtotal": final_sub
                })
                
            st.session_state["items_pedido"] = items_actualizados
            total_pedido = sum(it['subtotal'] for it in items_actualizados)
            saldo_pendiente = max(0.0, total_pedido - sena_pago)
            
            c_tot, c_sena_m, c_sal_m, c_limpiar = st.columns([2, 1.5, 1.5, 1])
            c_tot.metric("💰 TOTAL PEDIDO", f"$ {total_pedido:,.2f}")
            c_sena_m.metric("💵 SEÑA RECIBIDA", f"$ {sena_pago:,.2f}")
            c_sal_m.metric("💳 SALDO PENDIENTE", f"$ {saldo_pendiente:,.2f}", delta="- A Cobrar", delta_color="inverse")
            if c_limpiar.button("🗑️ Vaciar Lista", use_container_width=True):
                st.session_state["items_pedido"] = []
                st.rerun()

            st.divider()

            if st.button("💾 Confirmar Pedido y Generar Documento", type="primary", use_container_width=True):
                if not cliente.strip():
                    st.error("⚠️ Ingrese el nombre del cliente para continuar.")
                elif len(items_actualizados) == 0:
                    st.error("⚠️ Debe incluir al menos un producto.")
                else:
                    try:
                        q_ped = """
                            INSERT INTO pedidos (fecha_pedido, fecha_entrega, cliente, total, sena, estado)
                            VALUES (:fp, :fe, :cli, :tot, :sen, 'Pendiente')
                        """
                        db_query(q_ped, {
                            "fp": fecha_ped, 
                            "fe": fecha_ent, 
                            "cli": cliente.strip().upper(), 
                            "tot": total_pedido,
                            "sen": sena_pago
                        }, commit=True)
                        
                        res_id = db_query("SELECT id FROM pedidos ORDER BY id DESC LIMIT 1")
                        pedido_id = int(res_id['id'].iloc[0]) if res_id is not None and not res_id.empty else 1
                        
                        for it in items_actualizados:
                            q_det = """
                                INSERT INTO pedidos_detalle (pedido_id, producto_id, producto_nombre, cantidad, precio_unitario, subtotal, detalle)
                                VALUES (:pid, :prid, :prnom, :cant, :pu, :sub, :det)
                            """
                            db_query(q_det, {
                                "pid": pedido_id,
                                "prid": it['producto_id'],
                                "prnom": it['producto'],
                                "cant": it['cantidad'],
                                "pu": it['precio_u'],
                                "sub": it['subtotal'],
                                "det": it['detalle']
                            }, commit=True)
                        
                        st.success(f"✅ Pedido #{pedido_id:05d} registrado exitosamente.")
                        doc_html = generar_html_pedido(pedido_id, fecha_ped, fecha_ent, cliente.strip().upper(), items_actualizados, total_pedido, sena_val=sena_pago, estado="Pendiente")
                        st.session_state["doc_generado"] = doc_html
                        st.session_state["doc_id"] = pedido_id
                        st.session_state["items_pedido"] = []
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al guardar el pedido: {e}")

        if "doc_generado" in st.session_state:
            st.divider()
            st.subheader(f"📄 Documento Generado: Pedido #{st.session_state.get('doc_id', 0):05d}")
            st.download_button(
                label="📥 Descargar Nota de Pedido (.html / Imprimible)",
                data=st.session_state["doc_generado"],
                file_name=f"Pedido_{st.session_state.get('doc_id', 0):05d}.html",
                mime="text/html"
            )
            st.components.v1.html(st.session_state["doc_generado"], height=650, scrolling=True)

    # --- PESTAÑA 2: LISTADO DE PEDIDOS Y CONTROL DE ENTREGA ---
    with tab_lista_ped:
        st.subheader("📑 Control y Seguimiento de Pedidos")

        # Filtros
        col_f1, col_f2 = st.columns([1, 2])
        filtro_estado = col_f1.selectbox("Filtrar por Estado de Entrega:", ["Todos", "Pendiente", "Entregado"])
        filtro_cliente = col_f2.text_input("🔍 Buscar por Cliente:", placeholder="Escribí el nombre del cliente...")

        # Consulta de pedidos
        query_pedidos = "SELECT id, fecha_pedido, fecha_entrega, cliente, total, COALESCE(sena, 0) as sena, estado FROM pedidos WHERE 1=1"
        params_ped = {}

        if filtro_estado != "Todos":
            query_pedidos += " AND estado = :estado"
            params_ped["estado"] = filtro_estado

        if filtro_cliente.strip():
            query_pedidos += " AND UPPER(cliente) LIKE :cli"
            params_ped["cli"] = f"%{filtro_cliente.strip().upper()}%"

        query_pedidos += " ORDER BY id DESC"
        df_pedidos_db = db_query(query_pedidos, params_ped)

        if df_pedidos_db is not None and not df_pedidos_db.empty:
            df_pedidos_db['saldo'] = df_pedidos_db['total'] - df_pedidos_db['sena']
            
            # Métricas resumen del filtro actual
            cant_total = len(df_pedidos_db)
            cant_pend = len(df_pedidos_db[df_pedidos_db['estado'] == 'Pendiente'])
            saldo_a_cobrar = df_pedidos_db[df_pedidos_db['estado'] == 'Pendiente']['saldo'].sum()
            total_facturado = df_pedidos_db['total'].sum()

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("📦 Total Pedidos", cant_total)
            m2.metric("⏳ Pendientes", cant_pend)
            m3.metric("💳 Saldo por Cobrar (Pendientes)", f"$ {saldo_a_cobrar:,.2f}")
            m4.metric("💰 Total Filtrado", f"$ {total_facturado:,.2f}")

            st.divider()

            # Render de cada pedido en tarjetas expandibles
            for _, ped_row in df_pedidos_db.iterrows():
                p_id = int(ped_row['id'])
                es_entregado = (ped_row['estado'] == 'Entregado')
                icono_estado = "✅" if es_entregado else "⏳"
                badge = "ENTREGADO" if es_entregado else "PENDIENTE"

                titulo_expander = f"{icono_estado} Pedido #{p_id:05d} — {ped_row['cliente']} | Total: ${ped_row['total']:,.2f} | Saldo: ${ped_row['saldo']:,.2f} [{badge}]"

                with st.expander(titulo_expander, expanded=not es_entregado):
                    c_info1, c_info2, c_actions = st.columns([2, 2, 2])
                    
                    with c_info1:
                        st.write(f"**Fecha Pedido:** {ped_row['fecha_pedido']}")
                        st.write(f"**Compromiso Entrega:** {ped_row['fecha_entrega']}")
                    
                    with c_info2:
                        st.write(f"**Total:** $ {ped_row['total']:,.2f}")
                        st.write(f"**Seña entregada:** $ {ped_row['sena']:,.2f}")
                        st.write(f"**Saldo a Cobrar:** $ {ped_row['saldo']:,.2f}")

                    with c_actions:
                        # Cambio de estado de entrega
                        if es_entregado:
                            if st.button("↩️ Reabrir (Marcar como Pendiente)", key=f"reabrir_{p_id}", use_container_width=True):
                                db_query("UPDATE pedidos SET estado = 'Pendiente' WHERE id = :id", {"id": p_id}, commit=True)
                                st.cache_data.clear()
                                st.rerun()
                        else:
                            if st.button("✅ Marcar como ENTREGADO", key=f"entregar_{p_id}", type="primary", use_container_width=True):
                                db_query("UPDATE pedidos SET estado = 'Entregado' WHERE id = :id", {"id": p_id}, commit=True)
                                st.cache_data.clear()
                                st.success(f"Pedido #{p_id:05d} marcado como Entregado.")
                                st.rerun()

                        # Botón para generar e imprimir documento histórico
                        if st.button("🖨️ Ver / Imprimir Nota", key=f"print_{p_id}", use_container_width=True):
                            detalles_db = db_query("SELECT producto_nombre as producto, cantidad, precio_unitario as precio_u, subtotal, COALESCE(detalle, '') as detalle FROM pedidos_detalle WHERE pedido_id = :id", {"id": p_id})
                            if detalles_db is not None and not detalles_db.empty:
                                items_hist = detalles_db.to_dict('records')
                                html_hist = generar_html_pedido(
                                    pedido_id=p_id,
                                    fecha_p=ped_row['fecha_pedido'],
                                    fecha_e=ped_row['fecha_entrega'],
                                    cliente=ped_row['cliente'],
                                    items=items_hist,
                                    total_gral=ped_row['total'],
                                    sena_val=ped_row['sena'],
                                    estado=ped_row['estado']
                                )
                                st.session_state["doc_generado"] = html_hist
                                st.session_state["doc_id"] = p_id
                                st.rerun()

                    # Mostrar tabla con los ítems del pedido
                    df_items_pedido = db_query(
                        """SELECT producto_nombre as "Producto", COALESCE(detalle, '') as "Características / Fragancia", 
                                  cantidad as "Cant.", precio_unitario as "P. Unitario", subtotal as "Subtotal" 
                           FROM pedidos_detalle WHERE pedido_id = :pid""", 
                        {"pid": p_id}
                    )
                    if df_items_pedido is not None and not df_items_pedido.empty:
                        st.dataframe(
                            df_items_pedido, 
                            hide_index=True, 
                            use_container_width=True,
                            column_config={
                                "P. Unitario": st.column_config.NumberColumn(format="$ %.2f"),
                                "Subtotal": st.column_config.NumberColumn(format="$ %.2f")
                            }
                        )
        else:
            st.info("No se encontraron pedidos con los filtros seleccionados.")

# ==========================================
# 💰 5. REGISTRO DE COMPRAS
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
# 🚀 6. REGISTRAR VENTAS
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
    costo_u_actual = safe_float(row['costo_u'])

    col_info, col_form = st.columns([1, 2])
    col_info.metric("📦 Stock disponible", f"{row['stock_actual']} un.")
    col_info.metric("💲 Precio Minorista", f"$ {p1:,.2f}")
    col_info.metric("💲 Precio Mayorista", f"$ {p2:,.2f}")

    with col_form:
        with st.form("venta"):
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
                    ok = db_query(
                        """INSERT INTO historial_ventas
                             (fecha, producto, cantidad, total_venta, metodo_pago, costo_momento)
                           VALUES (:f, :p, :c, :t, :m, :cm)""",
                        {"f": fecha_v, "p": sel_p, "c": cant,
                         "t": total_cobrar, "m": metodo, "cm": costo_u_actual},
                        commit=True
                    )
                    
                    if ok:
                        db_query(
                            "UPDATE productos SET stock_actual = stock_actual - :c WHERE id = :id",
                            {"c": cant, "id": int(row['id'])}, commit=True
                        )
                        
                        if metodo == "Efectivo":
                            db_query("UPDATE saldos_caja SET saldo = saldo + :t WHERE tipo_cuenta = 'Efectivo'", 
                                     {"t": total_cobrar}, commit=True)
                        elif metodo in ["Transferencia", "Mercado Pago"]:
                            db_query("UPDATE saldos_caja SET saldo = saldo + :t WHERE tipo_cuenta = 'Banco'", 
                                     {"t": total_cobrar}, commit=True)

                        st.success(f"✅ Venta registrada: {cant} x {sel_p} = $ {total_cobrar:,.2f}")
                        st.cache_data.clear()
                        st.rerun()

# ==========================================
# 📊 7. CAJA Y FILTROS POR PERÍODO
# ==========================================
elif menu == "📊 Caja y Filtros":
    st.header("📊 Análisis de Caja y Períodos")
    c1, c2 = st.columns(2)
    f_inicio = c1.date_input("Fecha Inicio", value=date.today().replace(day=1))
    f_fin = c2.date_input("Fecha Fin", value=date.today())

    df_v = db_query("SELECT * FROM historial_ventas WHERE fecha BETWEEN :f1 AND :f2 ORDER BY fecha DESC", {"f1": f_inicio, "f2": f_fin})

    if df_v is not None and not df_v.empty:
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
# 📈 8. RENTABILIDAD
# ==========================================
elif menu == "📈 Rentabilidad":
    st.header("📈 Análisis de Margen y Rentabilidad")
    df_r = db_query("SELECT nombre, costo_u, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL' AND costo_u > 0")

    if df_r is not None and not df_r.empty:
        df_r['Ganancia L1 ($)'] = df_r['precio_v'] - df_r['costo_u']
        df_r['Margen L1 (%)'] = (df_r['Ganancia L1 ($)'] / df_r['precio_v'] * 100).fillna(0)
        df_r['Ganancia L2 ($)'] = df_r['precio_v2'] - df_r['costo_u']
        df_r['Margen L2 (%)'] = (df_r['Ganancia L2 ($)'] / df_r['precio_v2'] * 100).fillna(0)
        
        styled = df_r.style.format({
            "costo_u": "$ {:.2f}", "precio_v": "$ {:.2f}", "precio_v2": "$ {:.2f}",
            "Ganancia L1 ($)": "$ {:.2f}", "Ganancia L2 ($)": "$ {:.2f}",
            "Margen L1 (%)": "{:.1f}%", "Margen L2 (%)": "{:.1f}%"
        }).map(color_margen, subset=["Margen L1 (%)", "Margen L2 (%)"])
        
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.warning("Asegurate de tener recetas cargadas con costos para ver este análisis.")

# ==========================================
# 💰 9. CONTROL DE FLUJO DE CAJA
# ==========================================
elif menu == "💰 Flujo de Caja":
    st.header("💰 Control de Flujo de Caja")
    
    df_saldos = db_query("SELECT tipo_cuenta, saldo FROM saldos_caja")
    if df_saldos is not None and not df_saldos.empty:
        efectivo_rows = df_saldos[df_saldos['tipo_cuenta'] == 'Efectivo']['saldo'].values
        banco_rows = df_saldos[df_saldos['tipo_cuenta'] == 'Banco']['saldo'].values
        deuda_rows = df_saldos[df_saldos['tipo_cuenta'] == 'Deuda_TC']['saldo'].values
        
        efectivo = efectivo_rows[0] if len(efectivo_rows) > 0 else 0.0
        banco = banco_rows[0] if len(banco_rows) > 0 else 0.0
        deuda_tc = deuda_rows[0] if len(deuda_rows) > 0 else 0.0
        
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
# 📊 10. ANÁLISIS DE RESULTADOS
# ==========================================
elif menu == "📊 Análisis de Resultados":
    st.header("📊 Análisis de Negocio y Valoración")
    
    df_v = db_query("SELECT fecha, producto, cantidad, total_venta, costo_momento FROM historial_ventas")
    
    if df_v is not None and not df_v.empty:
        df_v['fecha'] = pd.to_datetime(df_v['fecha'])
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

    st.divider()
    st.subheader("📦 Valoración y Proyección de Stock")
    
    df_stk = db_query("""
        SELECT nombre, stock_actual, costo_u, precio_v, precio_v2 
        FROM productos 
        WHERE stock_actual > 0 AND UPPER(tipo) = 'FINAL'
    """)
    
    df_ins = db_query("SELECT stock_actual, costo_u FROM productos WHERE stock_actual > 0 AND UPPER(tipo) = 'INSUMO'")

    if df_stk is not None and not df_stk.empty:
        cap_finales = (df_stk['stock_actual'] * df_stk['costo_u']).sum()
        cap_insumos = (df_ins['stock_actual'] * df_ins['costo_u']).sum() if df_ins is not None else 0.0
        
        forecast_l1 = (df_stk['stock_actual'] * df_stk['precio_v']).sum()
        forecast_l2 = (df_stk['stock_actual'] * df_stk['precio_v2']).sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("📉 Capital en Finales", f"$ {cap_finales:,.2f}")
        c2.metric("💰 Proyección Lista 1", f"$ {forecast_l1:,.2f}")
        c3.metric("💰 Proyección Lista 2", f"$ {forecast_l2:,.2f}")
        
        st.info(f"📦 **Capital Total Inmovilizado (Insumos + Finales):** $ {cap_finales + cap_insumos:,.2f}")

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

# ==========================================
# 🔄 11. ACTUALIZACIÓN MASIVA DE PRECIOS
# ==========================================
elif menu == "🔄 Actualización Masiva":
    st.header("🔄 Recalcular Precios de Venta")
    st.info("Esta función recorre todos los productos FINALES, suma sus costos actuales de insumos y actualiza los precios L1 y L2 manteniendo tus porcentajes de ganancia.")

    if st.button("🚀 Iniciar Recálculo de Todo el Catálogo", use_container_width=True, type="primary"):
        productos_finales = db_query("SELECT id, nombre, precio_v, precio_v2, costo_u FROM productos WHERE UPPER(tipo) = 'FINAL'")
        
        if productos_finales is not None and not productos_finales.empty:
            progreso = st.progress(0)
            contador = 0
            total_prods = len(productos_finales)
            
            for index, prod in productos_finales.iterrows():
                id_f = int(prod['id'])
                
                query_costo = """
                    SELECT SUM(r.cantidad * COALESCE(p.costo_u, 0)) as nuevo_costo
                    FROM recetas r
                    JOIN productos p ON r.id_insumo = p.id
                    WHERE r.id_final = :idf
                """
                res_costo = db_query(query_costo, {"idf": id_f})
                nuevo_costo = float(res_costo['nuevo_costo'].iloc[0]) if res_costo is not None and not res_costo['nuevo_costo'].isnull().all() else 0.0
                
                costo_viejo = float(prod['costo_u']) if prod['costo_u'] and prod['costo_u'] > 0 else nuevo_costo
                
                margen_l1 = (float(prod['precio_v']) / costo_viejo) if costo_viejo > 0 and prod['precio_v'] else 1.0
                margen_l2 = (float(prod['precio_v2']) / costo_viejo) if costo_viejo > 0 and prod['precio_v2'] else 1.0
                
                nuevo_p1 = nuevo_costo * margen_l1
                nuevo_p2 = nuevo_costo * margen_l2
                
                db_query(
                    """UPDATE productos 
                       SET costo_u = :c, precio_v = :p1, precio_v2 = :p2 
                       WHERE id = :id""",
                    {"c": nuevo_costo, "p1": nuevo_p1, "p2": nuevo_p2, "id": id_f},
                    commit=True
                )
                
                contador += 1
                progreso.progress(contador / total_prods)
            
            st.success(f"✅ Se actualizaron {contador} productos finales con éxito.")
            st.cache_data.clear()
        else:
            st.warning("No se encontraron productos finales para actualizar.")

    st.divider()
    st.subheader("Vista Previa de Costos Actuales")
    vista_previa = db_query("""
        SELECT p.nombre, p.costo_u as costo_registrado, 
               (SELECT SUM(r.cantidad * i.costo_u) FROM recetas r JOIN productos i ON r.id_insumo = i.id WHERE r.id_final = p.id) as costo_real_receta
        FROM productos p 
        WHERE UPPER(p.tipo) = 'FINAL'
    """)
    if vista_previa is not None:
        st.dataframe(vista_previa, use_container_width=True)

# ==========================================
# 💾 12. BACKUP Y RESTAURACIÓN TOTAL
# ==========================================
elif menu == "💾 Backup y Restauración Total":
    st.header("💾 Centro de Respaldo y Restauración de Base de Datos")
    st.caption("Generá copias de seguridad descargables en Excel con todas las tablas del sistema o restaurá un archivo previo.")

    tab_backup, tab_restore = st.tabs(["📥 Descargar Backup Completo", "📤 Restaurar desde Archivo"])

    with tab_backup:
        st.subheader("Exportar todas las tablas")
        st.write("Se generará un archivo Excel con una pestaña por cada tabla activa:")
        st.markdown("- `productos`, `recetas`, `historial_compras`, `historial_ventas`, `saldos_caja`, `pedidos`, `pedidos_detalle`")

        if st.button("📦 Generar Archivo de Backup Ahora", type="primary"):
            tablas_a_exportar = [
                "productos", "recetas", "historial_compras", 
                "historial_ventas", "saldos_caja", "pedidos", "pedidos_detalle"
            ]
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                for tbl in tablas_a_exportar:
                    df_t = db_query(f"SELECT * FROM {tbl}")
                    if df_t is not None:
                        df_t.to_excel(writer, sheet_name=tbl, index=False)
                    else:
                        pd.DataFrame().to_excel(writer, sheet_name=tbl, index=False)
            
            buffer.seek(0)
            fecha_str = datetime.now().strftime("%Y%m%d_%H%M")
            st.success("✅ Archivo de respaldo preparado correctamente.")
            st.download_button(
                label="⬇️ Descargar Excel de Backup (.xlsx)",
                data=buffer,
                file_name=f"backup_velas_{fecha_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    with tab_restore:
        st.subheader("Restaurar Base de Datos desde Excel")
        st.warning("⚠️ **ATENCIÓN:** Restaurar reemplazará la información existente con el contenido del archivo subido. Se recomienda descargar un backup antes de proceder.")
        
        archivo_restaurar = st.file_uploader("Seleccionar archivo Excel de respaldo (.xlsx):", type=["xlsx"], key="file_uploader_backup")
        
        if archivo_restaurar is not None:
            if st.button("🚨 EJECUTAR RESTAURACIÓN COMPLETA", type="secondary"):
                with st.status("🚀 Procesando Restauración...", expanded=True) as status:
                    try:
                        xls = pd.ExcelFile(archivo_restaurar)
                        status.write("🧹 Limpiando tablas existentes...")
                        
                        db_query("""
                            TRUNCATE TABLE pedidos_detalle, pedidos, recetas, 
                                           historial_ventas, historial_compras, saldos_caja 
                            RESTART IDENTITY CASCADE
                        """, commit=True)
                        db_query("TRUNCATE TABLE productos RESTART IDENTITY CASCADE", commit=True)

                        if 'productos' in xls.sheet_names:
                            status.write("📦 Restaurando productos...")
                            df_p = pd.read_excel(xls, 'productos')
                            df_p.columns = [str(col).strip().lower() for col in df_p.columns]
                            for _, r in df_p.iterrows():
                                db_query("""
                                    INSERT INTO productos (nombre, tipo, unidad, stock_actual, costo_u, precio_v, precio_v2) 
                                    VALUES (:n, :t, :u, :s, :c, :p1, :p2)
                                """, {
                                    "n": str(r.get('nombre', '')).strip().upper(),
                                    "t": str(r.get('tipo', 'insumo')).lower(),
                                    "u": str(r.get('unidad', 'Un')),
                                    "s": safe_float(r.get('stock_actual', 0)),
                                    "c": safe_float(r.get('costo_u', 0)),
                                    "p1": safe_float(r.get('precio_v', 0)),
                                    "p2": safe_float(r.get('precio_v2', 0))
                                }, commit=True)

                        if 'recetas' in xls.sheet_names:
                            status.write("🧪 Restaurando recetas...")
                            df_rec = pd.read_excel(xls, 'recetas')
                            for _, r in df_rec.iterrows():
                                id_f = int(r['id_final']) if 'id_final' in r and pd.notna(r['id_final']) else None
                                id_i = int(r['id_insumo']) if 'id_insumo' in r and pd.notna(r['id_insumo']) else None
                                if id_f and id_i:
                                    db_query("""
                                        INSERT INTO recetas (id_final, id_insumo, cantidad)
                                        VALUES (:f, :i, :c)
                                    """, {"f": id_f, "i": id_i, "c": safe_float(r.get('cantidad', 0))}, commit=True)

                        if 'saldos_caja' in xls.sheet_names:
                            status.write("💰 Restaurando saldos de caja...")
                            df_sc = pd.read_excel(xls, 'saldos_caja')
                            for _, r in df_sc.iterrows():
                                db_query("""
                                    INSERT INTO saldos_caja (tipo_cuenta, saldo) 
                                    VALUES (:t, :s)
                                """, {"t": str(r.get('tipo_cuenta', '')), "s": safe_float(r.get('saldo', 0))}, commit=True)

                        if 'historial_compras' in xls.sheet_names:
                            status.write("📥 Restaurando historial de compras...")
                            df_hc = pd.read_excel(xls, 'historial_compras')
                            for _, r in df_hc.iterrows():
                                db_query("""
                                    INSERT INTO historial_compras (fecha, insumo, cantidad, monto_total, proveedor) 
                                    VALUES (:f, :i, :c, :m, :p)
                                """, {
                                    "f": r.get('fecha', date.today()), "i": str(r.get('insumo', '')),
                                    "c": safe_float(r.get('cantidad', 0)), "m": safe_float(r.get('monto_total', 0)),
                                    "p": str(r.get('proveedor', ''))
                                }, commit=True)

                        if 'historial_ventas' in xls.sheet_names:
                            status.write("🚀 Restaurando historial de ventas...")
                            df_hv = pd.read_excel(xls, 'historial_ventas')
                            for _, r in df_hv.iterrows():
                                db_query("""
                                    INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago, costo_momento) 
                                    VALUES (:f, :p, :c, :t, :m, :cm)
                                """, {
                                    "f": r.get('fecha', date.today()), "p": str(r.get('producto', '')),
                                    "c": safe_float(r.get('cantidad', 0)), "t": safe_float(r.get('total_venta', 0)),
                                    "m": str(r.get('metodo_pago', 'Efectivo')), "cm": safe_float(r.get('costo_momento', 0))
                                }, commit=True)

                        if 'pedidos' in xls.sheet_names:
                            status.write("📋 Restaurando pedidos y detalles...")
                            df_ped = pd.read_excel(xls, 'pedidos')
                            for _, r in df_ped.iterrows():
                                db_query("""
                                    INSERT INTO pedidos (id, fecha_pedido, fecha_entrega, cliente, total, sena, estado) 
                                    VALUES (:id, :fp, :fe, :cli, :tot, :sen, :est)
                                """, {
                                    "id": int(r['id']), "fp": r.get('fecha_pedido', date.today()),
                                    "fe": r.get('fecha_entrega', date.today()), "cli": str(r.get('cliente', '')),
                                    "tot": safe_float(r.get('total', 0)), "sen": safe_float(r.get('sena', 0)),
                                    "est": str(r.get('estado', 'Pendiente'))
                                }, commit=True)

                        if 'pedidos_detalle' in xls.sheet_names:
                            df_pdet = pd.read_excel(xls, 'pedidos_detalle')
                            for _, r in df_pdet.iterrows():
                                db_query("""
                                    INSERT INTO pedidos_detalle (pedido_id, producto_id, producto_nombre, cantidad, precio_unitario, subtotal, detalle) 
                                    VALUES (:pid, :prid, :prnom, :cant, :pu, :sub, :det)
                                """, {
                                    "pid": int(r.get('pedido_id', 1)),
                                    "prid": int(r.get('producto_id', 1)) if pd.notna(r.get('producto_id')) else None,
                                    "prnom": str(r.get('producto_nombre', '')),
                                    "cant": safe_float(r.get('cantidad', 0)),
                                    "pu": safe_float(r.get('precio_unitario', 0)),
                                    "sub": safe_float(r.get('subtotal', 0)),
                                    "det": str(r.get('detalle', '')) if pd.notna(r.get('detalle')) else ""
                                }, commit=True)

                        status.update(label="✨ ¡Restauración Maestra Exitosa!", state="complete", expanded=False)
                        st.cache_data.clear()
                        st.success("✅ Todas las tablas fueron restauradas correctamente.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Fallo durante la restauración: {e}")
