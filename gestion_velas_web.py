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
        # Limpieza extrema de la URL
        conn_url = st.secrets["postgres"]["url"].strip().replace(" ", "").replace("[", "").replace("]", "")
        if not conn_url or "postgresql://" not in conn_url:
            return None
        return create_engine(conn_url, pool_pre_ping=True, connect_args={'connect_timeout': 5})
    except Exception:
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
            st.error(f"⚠️ Error de conexión: {e}")
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
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            st.sidebar.success("✅ ¡Conexión Exitosa!")
        except Exception as e:
            st.sidebar.error(f"❌ Falló: {e}")
    else:
        st.sidebar.error("❌ URL mal configurada en Secrets")

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
# 📦 1. INVENTARIO Y ALTA (IMPORTAR/BACKUP)
# ==========================================
if menu == "📦 Inventario y Alta":
    st.subheader("📦 Gestión de Productos e Insumos")
    
    col_alta, col_imp = st.columns(2)

    with col_alta.expander("➕ DAR DE ALTA MANUAL"):
        with st.form("alta_p"):
            c1, c2 = st.columns(2)
            n_nom = c1.text_input("Nombre")
            n_tip = c2.selectbox("Tipo", ["Insumo", "Final", "Herramienta", "Packaging"])
            n_uni = c1.selectbox("Unidad", ["Gr", "Ml", "Un", "Kg"])
            n_stk = c2.number_input("Stock Inicial", min_value=0.0)
            n_cst = c1.number_input("Costo Unitario ($)", min_value=0.0)
            if st.form_submit_button("💾 Guardar Nuevo"):
                if n_nom:
                    sql = "INSERT INTO productos (nombre, tipo, unidad, stock_actual, costo_u) VALUES (:n, :t, :u, :s, :c)"
                    db_query(sql, {"n": n_nom, "t": n_tip, "u": n_uni, "s": n_stk, "c": n_cst}, commit=True)
                    st.success("Registrado.")
                    st.rerun()

    with col_imp.expander("📥 IMPORTAR / EXPORTAR (BACKUP)"):
        # BACKUP (EXPORTAR)
        df_exp = db_query("SELECT * FROM productos")
        if df_exp is not None and not df_exp.empty:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_exp.to_excel(writer, index=False, sheet_name='Inventario')
            st.download_button("📥 Descargar Backup Excel", output.getvalue(), f"backup_velas_{date.today()}.xlsx")
        
        st.divider()

        # RESTAURAR (IMPORTAR)
        uploaded_file = st.file_uploader("Subir backup.xlsx", type=["xlsx"])
        if uploaded_file:
            xls = pd.ExcelFile(uploaded_file)
            pestana = st.selectbox("Seleccione pestaña:", xls.sheet_names)
            df_excel = pd.read_excel(uploaded_file, sheet_name=pestana)
            st.write(f"📊 Registros encontrados: {len(df_excel)}")
            
            if st.button("🚀 Restaurar a Supabase"):
                with st.spinner("Sincronizando..."):
                    exitos = 0
                    for _, row in df_excel.iterrows():
                        sql = """INSERT INTO productos (nombre, tipo, unidad, stock_actual, costo_u, precio_v, precio_v2) 
                                 VALUES (:n, :t, :u, :s, :c, :p1, :p2)"""
                        params = {
                            "n": str(row.get('nombre', 'Sin nombre')), "t": str(row.get('tipo', 'Insumo')),
                            "u": str(row.get('unidad', 'Un')), "s": safe_float(row.get('stock_actual', 0)),
                            "c": safe_float(row.get('costo_u', 0)), "p1": safe_float(row.get('precio_v', 0)),
                            "p2": safe_float(row.get('precio_v2', 0))
                        }
                        if db_query(sql, params, commit=True): exitos += 1
                st.success(f"✅ Se cargaron {exitos} registros.")
                st.rerun()

    st.divider()
    df_ver = db_query("SELECT nombre, tipo, stock_actual, unidad, costo_u, precio_v, precio_v2 FROM productos ORDER BY nombre")
    if df_ver is not None:
        st.dataframe(df_ver, use_container_width=True, hide_index=True)

# ==========================================
# 🧪 2. RECETAS Y COSTEO
# ==========================================
elif menu == "🧪 Recetas y Costeo":
    st.header("🧪 Composición de Productos")
    df_f = db_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'")
    df_i = db_query("SELECT id, nombre, unidad, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'")

    if df_f is not None and not df_f.empty:
        sel_f = st.selectbox("Producto Final:", df_f['nombre'].tolist())
        id_f = int(df_f[df_f['nombre'] == sel_f].iloc[0]['id'])
        
        c1, c2 = st.columns(2)
        with c1:
            with st.form("receta"):
                sel_i = st.selectbox("Insumo a añadir:", df_i['nombre'].tolist())
                row_i = df_i[df_i['nombre'] == sel_i].iloc[0]
                cant = st.number_input(f"Cantidad ({row_i['unidad']})", min_value=0.0)
                if st.form_submit_button("Añadir"):
                    db_query("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (:idf, :idi, :c)",
                             {"idf": id_f, "idi": int(row_i['id']), "c": cant}, commit=True)
                    st.rerun()
        with c2:
            df_rec = db_query("""SELECT r.id, i.nombre, r.cantidad, i.unidad, i.costo_u, (r.cantidad * i.costo_u) as subtotal 
                                 FROM recetas r JOIN productos i ON r.id_insumo = i.id WHERE r.id_final = :id""", {"id": id_f})
            if df_rec is not None:
                st.table(df_rec[['nombre', 'cantidad', 'unidad', 'subtotal']])
                st.metric("Costo de Producción", f"$ {df_rec['subtotal'].sum():,.2f}")

# ==========================================
# 🏭 3. FABRICACIÓN
# ==========================================
elif menu == "🏭 Fabricación":
    st.header("🏭 Registro de Producción")
    df_f = db_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'")
    if df_f is not None:
        sel_f = st.selectbox("¿Qué vas a fabricar?", df_f['nombre'].tolist())
        id_f = int(df_f[df_f['nombre'] == sel_f].iloc[0]['id'])
        cant_f = st.number_input("Cantidad fabricada", min_value=1)
        
        if st.button("Finalizar Producción"):
            receta = db_query("SELECT id_insumo, cantidad FROM recetas WHERE id_final = :id", {"id": id_f})
            if receta is not None:
                db_query("UPDATE productos SET stock_actual = stock_actual + :c WHERE id = :id", {"c": cant_f, "id": id_f}, commit=True)
                for _, r in receta.iterrows():
                    db_query("UPDATE productos SET stock_actual = stock_actual - :c WHERE id = :id", 
                             {"c": r['cantidad'] * cant_f, "id": int(r['id_insumo'])}, commit=True)
                st.success("Stocks actualizados (insumos descontados).")

# ==========================================
# 💰 4. REGISTRO DE COMPRAS
# ==========================================
elif menu == "💰 Registro de Compras":
    st.header("💰 Cargar Factura de Compra")
    df_i = db_query("SELECT id, nombre, unidad FROM productos WHERE UPPER(tipo) = 'INSUMO'")
    if df_i is not None:
        with st.form("compra"):
            insumo = st.selectbox("Insumo comprado:", df_i['nombre'].tolist())
            row_i = df_i[df_i['nombre'] == insumo].iloc[0]
            c_cant = st.number_input("Cantidad comprada", min_value=0.0)
            c_total = st.number_input("Monto total abonado ($)", min_value=0.0)
            if st.form_submit_button("Registrar Compra"):
                n_costo = c_total / c_cant if c_cant > 0 else 0
                db_query("UPDATE productos SET stock_actual = stock_actual + :c, costo_u = :u WHERE id = :id",
                         {"c": c_cant, "u": n_costo, "id": int(row_i['id'])}, commit=True)
                st.success("Stock y costo unitario actualizados.")

# ==========================================
# 🚀 5. REGISTRAR VENTAS
# ==========================================
elif menu == "🚀 Registrar Ventas":
    st.header("🚀 Nueva Venta")
    df_p = db_query("SELECT id, nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'")
    if df_p is not None:
        sel_p = st.selectbox("Producto:", df_p['nombre'].tolist())
        row = df_p[df_p['nombre'] == sel_p].iloc[0]
        with st.form("venta"):
            c1, c2 = st.columns(2)
            lista = c1.radio("Lista:", ["Lista 1", "Lista 2"], horizontal=True)
            cant = c2.number_input("Cantidad:", min_value=1)
            p_u = safe_float(row['precio_v']) if lista == "Lista 1" else safe_float(row['precio_v2'])
            total = st.number_input("Cobro Total ($)", value=float(p_u * cant))
            if st.form_submit_button("Confirmar Venta"):
                db_query("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (:f, :p, :c, :t)",
                         {"f": date.today(), "p": sel_p, "c": cant, "t": total}, commit=True)
                db_query("UPDATE productos SET stock_actual = stock_actual - :c WHERE id = :id", {"c": cant, "id": int(row['id'])}, commit=True)
                st.success("Venta guardada.")
                st.rerun()

# ==========================================
# 📊 6. CAJA Y RENTABILIDAD
# ==========================================
elif menu == "📊 Caja y Filtros":
    st.header("📊 Historial")
    df_v = db_query("SELECT * FROM historial_ventas ORDER BY id DESC")
    if df_v is not None:
        st.dataframe(df_v, use_container_width=True)
        st.metric("Total Ventas", f"$ {df_v['total_venta'].sum():,.2f}")

elif menu == "📈 Rentabilidad":
    st.header("📈 Análisis")
    df_rent = db_query("SELECT producto, SUM(cantidad) as cant, SUM(total_venta) as total FROM historial_ventas GROUP BY producto")
    if df_rent is not None:
        st.dataframe(df_rent, use_container_width=True)
