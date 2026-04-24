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
        if not conn_url:
            return None
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

# ==========================================
# 2. MENÚ LATERAL
# ==========================================
st.sidebar.title("🕯️ Velas Control")

if st.sidebar.button("🔌 Testear Conexión"):
    engine = get_engine()
    if engine:
        with st.spinner("Conectando..."):
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                st.sidebar.success("✅ ¡Conexión Exitosa!")
            except Exception as e:
                st.sidebar.error(f"❌ Error: {e}")
    else:
        st.sidebar.error("❌ Configuración no encontrada")

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
# 📦 1. INVENTARIO Y ALTA (VERSION CORREGIDA)
# ==========================================
if menu == "📦 Inventario y Alta":
    st.subheader("📦 Gestión de Inventario Profesional")
    
    col_alta, col_imp = st.columns(2)

    with col_alta.expander("➕ DAR DE ALTA MANUAL"):
        with st.form("alta"):
            c1, c2 = st.columns(2)
            n = c1.text_input("Nombre del Producto/Insumo")
            t = c2.selectbox("Tipo", ["Insumo", "Final", "Herramienta", "Packaging"])
            u = c1.selectbox("Unidad", ["Gr", "Ml", "Un", "Kg"])
            s = c2.number_input("Stock Inicial", min_value=0.0)
            c = c1.number_input("Costo Unitario ($)", min_value=0.0)
            if st.form_submit_button("💾 Guardar en Base de Datos"):
                if n.strip():
                    db_query("INSERT INTO productos (nombre, tipo, unidad, stock_actual, costo_u) VALUES (:n, :t, :u, :s, :c)",
                             {"n": n.strip(), "t": t, "u": u, "s": s, "c": c}, commit=True)
                    st.success(f"✅ {n} registrado.")
                    st.rerun()
                else:
                    st.error("El nombre no puede estar vacío.")

    with col_imp.expander("📥 IMPORTAR / EXPORTAR (BACKUP)"):
        # EXPORTAR (BACKUP)
        df_exp = db_query("SELECT * FROM productos")
        if df_exp is not None and not df_exp.empty:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_exp.to_excel(writer, index=False, sheet_name='Inventario')
            st.download_button("📥 Descargar Backup Excel", output.getvalue(), f"backup_velas_{date.today()}.xlsx")
        
        st.divider()

        # IMPORTAR (RESTAURAR)
        uploaded_file = st.file_uploader("Subir backup.xlsx para restaurar", type=["xlsx"])
        if uploaded_file:
            xls = pd.ExcelFile(uploaded_file)
            pestana = st.selectbox("Seleccione pestaña del Excel:", xls.sheet_names)
            df_excel = pd.read_excel(uploaded_file, sheet_name=pestana)
            if st.button("🚀 Iniciar Restauración"):
                with st.spinner("Procesando datos..."):
                    exitos = 0
                    for _, row in df_excel.iterrows():
                        # CORRECCIÓN 3: Evitar "Sin nombre" y nulos
                        nombre_raw = row.get('nombre', '')
                        if pd.isna(nombre_raw) or str(nombre_raw).strip() == "" or str(nombre_raw).lower() == "sin nombre":
                            continue
                        
                        sql = """INSERT INTO productos (nombre, tipo, unidad, stock_actual, costo_u, precio_v, precio_v2) 
                                 VALUES (:n, :t, :u, :s, :c, :p1, :p2)"""
                        params = {
                            "n": str(nombre_raw).strip(),
                            "t": str(row.get('tipo', 'Insumo')),
                            "u": str(row.get('unidad', 'Un')), # CORRECCIÓN 2: Evita el 'nam' asegurando string
                            "s": safe_float(row.get('stock_actual', 0)),
                            "c": safe_float(row.get('costo_u', 0)),
                            "p1": safe_float(row.get('precio_v', 0)),
                            "p2": safe_float(row.get('precio_v2', 0))
                        }
                        if db_query(sql, params, commit=True): exitos += 1
                st.success(f"✅ Restauración finalizada: {exitos} registros válidos.")
                st.rerun()

    st.divider()
    
    # --- FILTROS (CORRECCIÓN 1) ---
    st.markdown("### 🔍 Filtros y Edición")
    c1, c2 = st.columns([1, 3])
    tipo_filtro = c1.multiselect("Filtrar por Tipo:", ["Insumo", "Final", "Herramienta", "Packaging"], default=["Insumo", "Final", "Herramienta", "Packaging"])
    busqueda = c2.text_input("Buscar por nombre:", "")

    # Query con filtros y CORRECCIÓN 3 (No traer "Sin nombre")
    query_inv = "SELECT id, nombre, tipo, unidad, stock_actual, costo_u, precio_v, precio_v2 FROM productos WHERE nombre IS NOT NULL AND nombre != '' AND nombre != 'Sin nombre'"
    df_inv = db_query(query_inv)

    if df_inv is not None and not df_inv.empty:
        # Aplicar filtros de Pandas para velocidad
        df_inv = df_inv[df_inv['tipo'].isin(tipo_filtro)]
        if busqueda:
            df_inv = df_inv[df_inv['nombre'].str.contains(busqueda, case=False)]
        
        # CORRECCIÓN 2: Limpieza de 'NaN' para que no aparezca 'nam'
        df_inv = df_inv.fillna({'unidad': 'Un', 'tipo': 'Insumo', 'stock_actual': 0})

        # --- EDICIÓN (CORRECCIÓN 4) ---
        st.info("💡 Podés editar los valores directamente en la tabla y presionar 'Guardar Cambios'.")
        df_editado = st.data_editor(
            df_inv,
            column_config={
                "id": None, # Ocultamos el ID
                "nombre": st.column_config.TextColumn("Nombre", width="medium", required=True),
                "tipo": st.column_config.SelectboxColumn("Tipo", options=["Insumo", "Final", "Herramienta", "Packaging"]),
                "unidad": st.column_config.SelectboxColumn("Unidad", options=["Gr", "Ml", "Un", "Kg"]),
                "stock_actual": st.column_config.NumberColumn("Stock", min_value=0),
                "costo_u": st.column_config.NumberColumn("Costo ($)", format="$ %.2f"),
                "precio_v": st.column_config.NumberColumn("P. Venta 1 ($)", format="$ %.2f"),
                "precio_v2": st.column_config.NumberColumn("P. Venta 2 ($)", format="$ %.2f"),
            },
            hide_index=True,
            use_container_width=True,
            key="editor_inventario"
        )

        if st.button("💾 Guardar Cambios en Inventario"):
            with st.spinner("Actualizando base de datos..."):
                for index, row in df_editado.iterrows():
                    sql_update = """UPDATE productos SET nombre = :n, tipo = :t, unidad = :u, 
                                    stock_actual = :s, costo_u = :c, precio_v = :p1, precio_v2 = :p2 
                                    WHERE id = :id"""
                    db_query(sql_update, {
                        "n": row['nombre'], "t": row['tipo'], "u": row['unidad'],
                        "s": row['stock_actual'], "c": row['costo_u'], 
                        "p1": row['precio_v'], "p2": row['precio_v2'], "id": int(row['id'])
                    }, commit=True)
            st.success("✅ Cambios guardados correctamente.")
            st.rerun()
    else:
        st.warning("No se encontraron registros que coincidan con los filtros.")

# ==========================================
# 🧪 2. RECETAS Y COSTEO
# ==========================================
elif menu == "🧪 Recetas y Costeo":
    st.header("🧪 Composición y Análisis de Costos")
    
    # Traemos productos finales e insumos (limpios)
    df_f = db_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL' AND nombre IS NOT NULL AND nombre != ''")
    df_i = db_query("SELECT id, nombre, unidad, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO' AND nombre IS NOT NULL AND nombre != ''")

    if df_f is not None and not df_f.empty:
        sel_f = st.selectbox("Seleccione Producto Final para ver/editar receta:", df_f['nombre'].tolist())
        row_f = df_f[df_f['nombre'] == sel_f].iloc[0]
        id_f = int(row_f['id'])
        
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.subheader("➕ Añadir Insumo")
            if df_i is not None and not df_i.empty:
                with st.form("add_insumo_receta"):
                    ins_nom = st.selectbox("Insumo:", df_i['nombre'].tolist())
                    ins_data = df_i[df_i['nombre'] == ins_nom].iloc[0]
                    cant_i = st.number_input(f"Cantidad ({ins_data['unidad']})", min_value=0.0, step=0.1)
                    
                    if st.form_submit_button("Añadir a la Receta"):
                        if cant_i > 0:
                            db_query("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (:idf, :idi, :c)",
                                     {"idf": id_f, "idi": int(ins_data['id']), "c": cant_i}, commit=True)
                            st.success("Insumo añadido")
                            st.rerun()
            else:
                st.warning("Primero cargá insumos en el Inventario.")

        with c2:
            st.subheader(f"📋 Ficha Técnica: {sel_f}")
            query_receta = """
                SELECT r.id, i.nombre, r.cantidad, i.unidad, i.costo_u, (r.cantidad * i.costo_u) as subtotal
                FROM recetas r 
                JOIN productos i ON r.id_insumo = i.id
                WHERE r.id_final = :id
            """
            df_receta = db_query(query_receta, {"id": id_f})
            
            if df_receta is not None and not df_receta.empty:
                st.table(df_receta[['nombre', 'cantidad', 'unidad', 'subtotal']])
                costo_total = df_receta['subtotal'].sum()
                st.metric("COSTO DE FABRICACIÓN", f"$ {costo_total:,.2f}")
                
                # Actualizar el costo del producto final automáticamente
                db_query("UPDATE productos SET costo_u = :c WHERE id = :id", {"c": costo_total, "id": id_f}, commit=True)
                
                if st.button("🗑️ Vaciar Receta"):
                    db_query("DELETE FROM recetas WHERE id_final = :id", {"id": id_f}, commit=True)
                    st.rerun()
            else:
                st.info("Este producto aún no tiene una receta definida.")

# ==========================================
# 🏭 3. FABRICACIÓN
# ==========================================
elif menu == "🏭 Fabricación":
    st.header("🏭 Registro de Producción")
    st.info("Al confirmar, se sumará stock al producto final y se descontarán proporcionalmente los insumos.")

    df_f = db_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'")
    if df_f is not None and not df_f.empty:
        with st.form("fabricar_form"):
            sel_f = st.selectbox("¿Qué producto fabricaste?", df_f['nombre'].tolist())
            cant_f = st.number_input("Cantidad de unidades producidas:", min_value=1, step=1)
            
            if st.form_submit_button("🚀 Confirmar Fabricación"):
                id_f = int(df_f[df_f['nombre'] == sel_f].iloc[0]['id'])
                receta = db_query("SELECT id_insumo, cantidad FROM recetas WHERE id_final = :id", {"id": id_f})
                
                if receta is not None and not receta.empty:
                    # 1. Sumar stock al final
                    db_query("UPDATE productos SET stock_actual = stock_actual + :c WHERE id = :id", 
                             {"c": cant_f, "id": id_f}, commit=True)
                    # 2. Restar insumos
                    for _, row in receta.iterrows():
                        db_query("UPDATE productos SET stock_actual = stock_actual - :c WHERE id = :id", 
                                 {"c": row['cantidad'] * cant_f, "id": int(row['id_insumo'])}, commit=True)
                    st.success(f"✅ Se fabricaron {cant_f} {sel_f}. Stock e insumos actualizados.")
                else:
                    st.error("❌ No se puede fabricar: El producto no tiene receta definida.")

# ==========================================
# 💰 4. REGISTRO DE COMPRAS
# ==========================================
elif menu == "💰 Registro de Compras":
    st.header("💰 Ingreso de Insumos y Mercadería")
    df_i = db_query("SELECT id, nombre, unidad, stock_actual FROM productos WHERE UPPER(tipo) != 'FINAL'")

    if df_i is not None:
        with st.form("compra_form"):
            ins_sel = st.selectbox("Seleccione el Insumo comprado:", df_i['nombre'].tolist())
            row_i = df_i[df_i['nombre'] == ins_sel].iloc[0]
            c1, c2 = st.columns(2)
            cant_c = c1.number_input(f"Cantidad comprada ({row_i['unidad']}):", min_value=0.01)
            cost_c = c2.number_input("Costo Total de la compra ($):", min_value=0.01)
            
            if st.form_submit_button("📥 Registrar Ingreso"):
                nuevo_costo_u = cost_c / cant_c
                db_query("UPDATE productos SET stock_actual = stock_actual + :c, costo_u = :u WHERE id = :id",
                         {"c": cant_c, "u": nuevo_costo_u, "id": int(row_i['id'])}, commit=True)
                st.success(f"✅ Stock actualizado. Nuevo costo unitario: $ {nuevo_costo_u:,.2f}")

# ==========================================
# 🚀 5. REGISTRAR VENTAS
# ==========================================
elif menu == "🚀 Registrar Ventas":
    st.header("🚀 Nueva Venta")
    df_p = db_query("SELECT id, nombre, precio_v, precio_v2, stock_actual FROM productos WHERE UPPER(tipo) = 'FINAL'")

    if df_p is not None and not df_p.empty:
        sel_p = st.selectbox("Producto a vender:", df_p['nombre'].tolist())
        row = df_p[df_p['nombre'] == sel_p].iloc[0]
        
        st.write(f"📦 **Stock disponible:** {row['stock_actual']} unidades")
        
        with st.form("venta_v"):
            c1, c2 = st.columns(2)
            lista = c1.radio("Lista de Precios:", ["Minorista (L1)", "Mayorista (L2)"], horizontal=True)
            cant = c2.number_input("Cantidad:", min_value=1.0, step=1.0)
            
            precio_u = safe_float(row['precio_v']) if "L1" in lista else safe_float(row['precio_v2'])
            total_sugerido = precio_u * cant
            
            monto_final = st.number_input("Monto final cobrado ($):", value=float(total_sugerido))
            metodo = st.selectbox("Medio de Pago:", ["Efectivo", "Transferencia", "Mercado Pago"])
            
            if st.form_submit_button("✅ Finalizar Venta"):
                if cant <= row['stock_actual']:
                    # Grabar Historial
                    db_query("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (:f, :p, :c, :t, :m)",
                             {"f": date.today(), "p": sel_p, "c": cant, "t": monto_final, "m": metodo}, commit=True)
                    # Descontar Stock
                    db_query("UPDATE productos SET stock_actual = stock_actual - :c WHERE id = :id", 
                             {"c": cant, "id": int(row['id'])}, commit=True)
                    st.success(f"✅ Venta registrada. Se descontaron {cant} unidades.")
                    st.rerun()
                else:
                    st.error("❌ No hay suficiente stock para realizar la venta.")

# ==========================================
# 📊 6. CAJA Y FILTROS
# ==========================================
elif menu == "📊 Caja y Filtros":
    st.header("📊 Historial de Movimientos de Caja")
    
    fecha_f = st.date_input("Filtrar por fecha:", value=date.today())
    df_v = db_query("SELECT fecha, producto, cantidad, total_venta, metodo_pago FROM historial_ventas WHERE fecha = :f", {"f": fecha_f})
    
    if df_v is not None and not df_v.empty:
        st.dataframe(df_v, use_container_width=True, hide_index=True)
        col1, col2 = st.columns(2)
        col1.metric("Ventas del Día", len(df_v))
        col2.metric("Total Recaudado", f"$ {df_v['total_venta'].sum():,.2f}")
    else:
        st.info(f"No se registraron ventas el día {fecha_f}.")

# ==========================================
# 📈 7. RENTABILIDAD
# ==========================================
elif menu == "📈 Rentabilidad":
    st.header("📈 Análisis de Rentabilidad Real")
    st.write("Cálculo basado en el Costo de Fabricación actual vs. Precio de Venta.")

    query_rent = """
        SELECT nombre, costo_u, precio_v, precio_v2, stock_actual 
        FROM productos WHERE UPPER(tipo) = 'FINAL'
    """
    df_r = db_query(query_rent)

    if df_r is not None and not df_r.empty:
        df_r['Ganancia L1 ($)'] = df_r['precio_v'] - df_r['costo_u']
        df_r['Margen L1 (%)'] = (df_r['Ganancia L1 ($)'] / df_r['precio_v'] * 100).fillna(0)
        
        # Formateo para visualización
        st.dataframe(df_r.style.format({
            "costo_u": "$ {:.2f}",
            "precio_v": "$ {:.2f}",
            "precio_v2": "$ {:.2f}",
            "Ganancia L1 ($)": "$ {:.2f}",
            "Margen L1 (%)": "{:.1f}%"
        }), use_container_width=True, hide_index=True)        
        
