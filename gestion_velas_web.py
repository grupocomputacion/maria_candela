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
        # EXPORTAR (Funciona igual)
        df_exp = db_query("SELECT * FROM productos WHERE nombre IS NOT NULL")
        if df_exp is not None and not df_exp.empty:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_exp.to_excel(writer, index=False, sheet_name='Inventario')
            st.download_button("📥 Descargar Backup Excel", output.getvalue(), f"backup_velas_{date.today()}.xlsx")
        
        st.divider()

        # IMPORTAR (AQUÍ ESTÁ EL ARREGLO)
        uploaded_file = st.file_uploader("Subir backup.xlsx", type=["xlsx"])
        if uploaded_file:
            xls = pd.ExcelFile(uploaded_file)
            pestana = st.selectbox("Seleccione pestaña del Excel:", xls.sheet_names)
            df_excel = pd.read_excel(uploaded_file, sheet_name=pestana)
            
            # Limpiamos los nombres de las columnas del Excel (minúsculas y sin espacios)
            df_excel.columns = [str(c).strip().lower() for c in df_excel.columns]
            
            st.write(f"📊 Filas detectadas en el Excel: {len(df_excel)}")
            
            if st.button("🚀 FORZAR RESTAURACIÓN"):
                with st.spinner("Subiendo datos a Supabase..."):
                    exitos = 0
                    for i, row in df_excel.iterrows():
                        # Lógica de búsqueda flexible para el NOMBRE
                        nombre = row.get('nombre', row.get('item', row.get('producto', row.get('vela', ''))))
                        
                        # Si la fila está vacía, la saltamos
                        if pd.isna(nombre) or str(nombre).strip() == "":
                            continue
                        
                        # Mapeo flexible de columnas
                        params = {
                            "n": str(nombre).strip(),
                            "t": str(row.get('tipo', 'Insumo')).capitalize(),
                            "u": str(row.get('unidad', 'Un')),
                            "s": safe_float(row.get('stock_actual', row.get('stock', 0))),
                            "c": safe_float(row.get('costo_u', row.get('costo', 0))),
                            "p1": safe_float(row.get('precio_v', row.get('precio', 0))),
                            "p2": safe_float(row.get('precio_v2', row.get('precio2', 0)))
                        }
                        
                        sql = """INSERT INTO productos (nombre, tipo, unidad, stock_actual, costo_u, precio_v, precio_v2) 
                                 VALUES (:n, :t, :u, :s, :c, :p1, :p2)"""
                        
                        if db_query(sql, params, commit=True):
                            exitos += 1
                
                st.success(f"✅ ¡Éxito! Se recuperaron {exitos} registros en Supabase.")
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
    
    # Filtramos para no traer basura o registros vacíos
    query_f = "SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL' AND nombre IS NOT NULL AND nombre != '' AND nombre != 'Sin nombre'"
    query_i = "SELECT id, nombre, unidad, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO' AND nombre IS NOT NULL AND nombre != ''"
    
    df_f = db_query(query_f)
    df_i = db_query(query_i)

    if df_f is not None and not df_f.empty:
        sel_f = st.selectbox("Seleccione Producto Final:", df_f['nombre'].tolist())
        id_f = int(df_f[df_f['nombre'] == sel_f].iloc[0]['id'])
        
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.subheader("➕ Añadir Insumo")
            if df_i is not None and not df_i.empty:
                with st.form("form_receta"):
                    ins_sel = st.selectbox("Insumo:", df_i['nombre'].tolist())
                    row_i = df_i[df_i['nombre'] == ins_sel].iloc[0]
                    cant_i = st.number_input(f"Cantidad ({row_i['unidad']})", min_value=0.0, step=0.1)
                    if st.form_submit_button("Añadir a la Receta"):
                        if cant_i > 0:
                            db_query("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (:idf, :idi, :c)",
                                     {"idf": id_f, "idi": int(row_i['id']), "c": cant_i}, commit=True)
                            st.success("Insumo añadido correctamente.")
                            st.rerun()
            else:
                st.warning("No hay insumos cargados en el Inventario.")

        with c2:
            st.subheader(f"📋 Ficha: {sel_f}")
            df_rec = db_query("""
                SELECT r.id, i.nombre, r.cantidad, i.unidad, i.costo_u, (r.cantidad * i.costo_u) as subtotal
                FROM recetas r JOIN productos i ON r.id_insumo = i.id
                WHERE r.id_final = :id
            """, {"id": id_f})
            
            if df_rec is not None and not df_rec.empty:
                st.table(df_rec[['nombre', 'cantidad', 'unidad', 'subtotal']])
                costo_total = df_rec['subtotal'].sum()
                st.metric("COSTO TOTAL DE INSUMOS", f"$ {costo_total:,.2f}")
                
                # Actualizar el costo unitario del producto final
                db_query("UPDATE productos SET costo_u = :c WHERE id = :id", {"c": costo_total, "id": id_f}, commit=True)
                
                if st.button("🗑️ Borrar Receta"):
                    db_query("DELETE FROM recetas WHERE id_final = :id", {"id": id_f}, commit=True)
                    st.rerun()
            else:
                st.info("No hay insumos cargados para este producto.")

# ==========================================
# 🏭 3. FABRICACIÓN
# ==========================================
elif menu == "🏭 Fabricación":
    st.header("🏭 Registro de Producción")
    st.info("Esta acción sumará stock al producto final y descontará los insumos de la receta.")

    df_f = db_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'")
    if df_f is not None and not df_f.empty:
        with st.form("fabricar"):
            prod_sel = st.selectbox("¿Qué producto fabricaste?", df_f['nombre'].tolist())
            cantidad = st.number_input("Cantidad de unidades:", min_value=1, step=1)
            
            if st.form_submit_button("🚀 Confirmar Fabricación"):
                id_f = int(df_f[df_f['nombre'] == prod_sel].iloc[0]['id'])
                receta = db_query("SELECT id_insumo, cantidad FROM recetas WHERE id_final = :id", {"id": id_f})
                
                if receta is not None and not receta.empty:
                    # 1. Sumar stock al final
                    db_query("UPDATE productos SET stock_actual = stock_actual + :c WHERE id = :id", {"c": cantidad, "id": id_f}, commit=True)
                    # 2. Descontar insumos
                    for _, r in receta.iterrows():
                        db_query("UPDATE productos SET stock_actual = stock_actual - :c WHERE id = :id", 
                                 {"c": r['cantidad'] * cantidad, "id": int(r['id_insumo'])}, commit=True)
                    st.success(f"✅ Producción registrada: {cantidad} unidades de {prod_sel}.")
                else:
                    st.error("El producto no tiene receta. Cargala en 'Recetas y Costeo'.")

# ==========================================
# 💰 4. REGISTRO DE COMPRAS
# ==========================================
elif menu == "💰 Registro de Compras":
    st.header("💰 Compra de Insumos / Mercadería")
    df_i = db_query("SELECT id, nombre, unidad FROM productos WHERE UPPER(tipo) != 'FINAL'")

    if df_i is not None:
        with st.form("compra"):
            ins_nom = st.selectbox("Insumo comprado:", df_i['nombre'].tolist())
            row_i = df_i[df_i['nombre'] == ins_nom].iloc[0]
            c1, c2 = st.columns(2)
            cant_c = c1.number_input(f"Cantidad ({row_i['unidad']}):", min_value=0.01)
            cost_c = c2.number_input("Monto total pagado ($):", min_value=0.01)
            
            if st.form_submit_button("📥 Registrar Compra"):
                n_costo = cost_c / cant_c
                db_query("UPDATE productos SET stock_actual = stock_actual + :c, costo_u = :u WHERE id = :id",
                         {"c": cant_c, "u": n_costo, "id": int(row_i['id'])}, commit=True)
                st.success("✅ Stock y costo actualizados.")

# ==========================================
# 🚀 5. REGISTRAR VENTAS
# ==========================================
elif menu == "🚀 Registrar Ventas":
    st.header("🚀 Nueva Venta")
    df_p = db_query("SELECT id, nombre, precio_v, precio_v2, stock_actual FROM productos WHERE UPPER(tipo) = 'FINAL'")

    if df_p is not None and not df_p.empty:
        sel_p = st.selectbox("Producto:", df_p['nombre'].tolist())
        row = df_p[df_p['nombre'] == sel_p].iloc[0]
        
        st.write(f"📦 Stock actual: **{row['stock_actual']}** unidades")
        
        with st.form("venta"):
            c1, c2 = st.columns(2)
            lista = c1.radio("Lista de Precios:", ["Minorista (L1)", "Mayorista (L2)"])
            cant = c2.number_input("Cantidad:", min_value=1.0, step=1.0)
            
            precio_u = safe_float(row['precio_v']) if "L1" in lista else safe_float(row['precio_v2'])
            total_cobrar = st.number_input("Total a cobrar ($):", value=float(precio_u * cant))
            metodo = st.selectbox("Medio de Pago:", ["Efectivo", "Transferencia", "Mercado Pago"])
            
            if st.form_submit_button("✅ Procesar Venta"):
                if cant <= row['stock_actual']:
                    db_query("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (:f, :p, :c, :t, :m)",
                             {"f": date.today(), "p": sel_p, "c": cant, "t": total_cobrar, "m": metodo}, commit=True)
                    db_query("UPDATE productos SET stock_actual = stock_actual - :c WHERE id = :id", {"c": cant, "id": int(row['id'])}, commit=True)
                    st.success("Venta realizada.")
                    st.rerun()
                else:
                    st.error("Stock insuficiente.")

# ==========================================
# 📊 6. CAJA Y FILTROS
# ==========================================
elif menu == "📊 Caja y Filtros":
    st.header("📊 Resumen de Caja")
    fecha_sel = st.date_input("Ver ventas del día:", value=date.today())
    df_v = db_query("SELECT * FROM historial_ventas WHERE fecha = :f", {"f": fecha_sel})
    
    if df_v is not None and not df_v.empty:
        st.dataframe(df_v, use_container_width=True, hide_index=True)
        st.metric("TOTAL RECAUDADO", f"$ {df_v['total_venta'].sum():,.2f}")
    else:
        st.info("No hay ventas registradas en esta fecha.")

# ==========================================
# 📈 7. RENTABILIDAD
# ==========================================
elif menu == "📈 Rentabilidad":
    st.header("📈 Análisis de Margen y Rentabilidad")
    df_r = db_query("SELECT nombre, costo_u, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL' AND costo_u > 0")

    if df_r is not None and not df_r.empty:
        df_r['Ganancia L1 ($)'] = df_r['precio_v'] - df_r['costo_u']
        df_r['Margen (%)'] = (df_r['Ganancia L1 ($)'] / df_r['precio_v'] * 100).fillna(0)
        
        st.dataframe(df_r.style.format({
            "costo_u": "$ {:.2f}", "precio_v": "$ {:.2f}", 
            "precio_v2": "$ {:.2f}", "Ganancia L1 ($)": "$ {:.2f}",
            "Margen (%)": "{:.1f}%"
        }), use_container_width=True, hide_index=True)
    else:
        st.warning("Cargá las recetas para calcular la rentabilidad basada en costos reales.")
