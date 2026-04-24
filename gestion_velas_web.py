import streamlit as st
import pandas as pd
from datetime import datetime, date
import io
import os
from sqlalchemy import create_engine, text

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Velas Candela Pro - Sistema Integral", layout="wide")

# ==========================================
# 1. MOTOR DE BASE DE DATOS (SUPABASE)
# ==========================================
@st.cache_resource
def get_engine():
    try:
        if "postgres" not in st.secrets:
            return None
        # Limpieza crucial: eliminamos espacios accidentales en la URL
        conn_url = st.secrets["postgres"]["url"].strip()
        if not conn_url:
            return None
        return create_engine(conn_url, pool_pre_ping=True)
    except Exception as e:
        st.error(f"Error de configuración: {e}")
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
        # Mostramos error solo si no es una carga masiva
        if not commit: st.error(f"Error de BD: {e}")
        return None

def safe_float(val):
    try:
        if pd.isna(val) or str(val).strip() == "": return 0.0
        return float(val)
    except: return 0.0

def safe_int(val):
    try:
        if pd.isna(val) or str(val).strip() == "": return 0
        return int(float(val))
    except: return 0

# ==========================================
# 2. MENÚ LATERAL Y TEST
# ==========================================
st.sidebar.title("🕯️ Velas Control")

if st.sidebar.button("🔌 Testear Conexión"):
    engine = get_engine()
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            st.sidebar.success("✅ Conexión Exitosa!")
        except Exception as e:
            st.sidebar.error(f"❌ Falló: {e}")
    else:
        st.sidebar.error("❌ URL no configurada en Secrets")

menu = st.sidebar.radio("Ir a:", [
    "📦 Inventario y Alta", 
    "🧪 Recetas y Costeo", 
    "🏭 Fabricación",
    "💰 Registro de Compras", 
    "🚀 Registrar Ventas", 
    "📊 Caja y Filtros",
    "📈 Rentabilidad x Producto"
])

# ==========================================
# 📦 1. INVENTARIO Y ALTA
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
            n_min = c1.number_input("Stock Mínimo", min_value=0.0)
            n_cst = c2.number_input("Costo Unitario ($)", min_value=0.0)
            
            if st.form_submit_button("💾 Guardar Nuevo"):
                if n_nom:
                    sql = """INSERT INTO productos (nombre, tipo, unidad, stock_actual, stock_minimo, costo_u) 
                             VALUES (:nom, :tip, :uni, :stk, :min, :cst)"""
                    db_query(sql, {"nom": n_nom, "tip": n_tip, "uni": n_uni, "stk": n_stk, "min": n_min, "cst": n_cst}, commit=True)
                    st.success("Registrado correctamente")
                    st.rerun()

    with col_imp.expander("📥 IMPORTAR / EXPORTAR (BACKUP)"):
        # EXPORTAR
        df_exp = db_query("SELECT * FROM productos")
        if df_exp is not None and not df_exp.empty:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_exp.to_excel(writer, index=False, sheet_name='Backup_Inventario')
            st.download_button("📥 Descargar Backup Excel", output.getvalue(), f"backup_velas_{date.today()}.xlsx")
        
        st.divider()

        # IMPORTAR CON SELECTOR DE PESTAÑA
        uploaded_file = st.file_uploader("Subir Excel de Respaldo", type=["xlsx"])
        if uploaded_file:
            xls = pd.ExcelFile(uploaded_file)
            pestaña_sel = st.selectbox("Seleccione la pestaña a importar:", xls.sheet_names)
            df_excel = pd.read_excel(uploaded_file, sheet_name=pestaña_sel)
            df_excel.columns = [c.strip().lower() for c in df_excel.columns]
            
            st.write(f"📊 Filas detectadas en '{pestaña_sel}': {len(df_excel)}")
            
            if st.button("🚀 Restaurar datos a Supabase"):
                with st.spinner("Subiendo datos..."):
                    progress = st.progress(0)
                    exitos = 0
                    for i, row in df_excel.iterrows():
                        sql = """INSERT INTO productos (nombre, tipo, unidad, stock_actual, stock_minimo, costo_u, margen1, margen2, precio_v, precio_v2) 
                                 VALUES (:nom, :tip, :uni, :stk, :min, :cst, :m1, :m2, :p1, :p2)"""
                        params = {
                            "nom": str(row.get('nombre', row.get('item', 'Sin nombre'))),
                            "tip": str(row.get('tipo', 'Insumo')),
                            "uni": str(row.get('unidad', 'Un')),
                            "stk": safe_float(row.get('stock_actual', row.get('stock', 0))),
                            "min": safe_float(row.get('stock_minimo', 0)),
                            "cst": safe_float(row.get('costo_u', row.get('costo', 0))),
                            "m1": safe_float(row.get('margen1', 100)),
                            "m2": safe_float(row.get('margen2', 100)),
                            "p1": safe_float(row.get('precio_v', 0)),
                            "p2": safe_float(row.get('precio_v2', 0))
                        }
                        if db_query(sql, params, commit=True): exitos += 1
                        progress.progress((i + 1) / len(df_excel))
                st.success(f"✅ Se restauraron {exitos} registros.")
                st.rerun()

    st.divider()
    df_ver = db_query("SELECT nombre, tipo, stock_actual, stock_minimo, unidad, costo_u, precio_v as \"Lista 1\", precio_v2 as \"Lista 2\" FROM productos ORDER BY tipo, nombre")
    if df_ver is not None and not df_ver.empty:
        st.dataframe(df_ver, use_container_width=True, hide_index=True)

# ==========================================
# 🧪 2. RECETAS Y COSTEO
# ==========================================
elif menu == "🧪 Recetas y Costeo":
    st.header("🧪 Composición y Costeo")
    df_finales = db_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'")
    df_insumos = db_query("SELECT id, nombre, unidad, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'")

    if df_finales is not None and not df_finales.empty:
        sel_f = st.selectbox("Seleccione Producto Final", df_finales['nombre'].tolist())
        row_f = df_finales[df_finales['nombre'] == sel_f].iloc[0]
        
        c1, c2 = st.columns([1, 2])
        with c1:
            with st.form("add_rec"):
                st.write("Añadir Insumo")
                sel_i = st.selectbox("Insumo", df_insumos['nombre'].tolist())
                row_i = df_insumos[df_insumos['nombre'] == sel_i].iloc[0]
                cant_i = st.number_input(f"Cantidad ({row_i['unidad']})", min_value=0.0)
                if st.form_submit_button("Añadir"):
                    db_query("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (:idf, :idi, :c)",
                             {"idf": int(row_f['id']), "idi": int(row_i['id']), "c": cant_i}, commit=True)
                    st.rerun()
        
        with c2:
            st.write(f"Receta de: {sel_f}")
            df_rec = db_query("""
                SELECT r.id, i.nombre, r.cantidad, i.unidad, i.costo_u, (r.cantidad * i.costo_u) as subtotal
                FROM recetas r JOIN productos i ON r.id_insumo = i.id
                WHERE r.id_final = :id
            """, {"id": int(row_f['id'])})
            if df_rec is not None and not df_rec.empty:
                st.table(df_rec[['nombre', 'cantidad', 'unidad', 'subtotal']])
                total = df_rec['subtotal'].sum()
                st.metric("COSTO TOTAL", f"$ {total:,.2f}")
                db_query("UPDATE productos SET costo_u = :c WHERE id = :id", {"c": total, "id": int(row_f['id'])}, commit=True)

# ==========================================
# 🏭 3. FABRICACIÓN
# ==========================================
elif menu == "🏭 Fabricación":
    st.header("🏭 Registro de Producción")
    df_f = db_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'")
    if df_f is not None:
        sel_f = st.selectbox("Fabricar:", df_f['nombre'].tolist())
        id_f = df_f[df_f['nombre'] == sel_f].iloc[0]['id']
        cant_fab = st.number_input("Cantidad", min_value=1)
        
        if st.button("Procesar Fabricación"):
            receta = db_query("SELECT id_insumo, cantidad FROM recetas WHERE id_final = :id", {"id": int(id_f)})
            if receta is not None:
                db_query("UPDATE productos SET stock_actual = stock_actual + :c WHERE id = :id", {"c": cant_fab, "id": int(id_f)}, commit=True)
                for _, item in receta.iterrows():
                    db_query("UPDATE productos SET stock_actual = stock_actual - :c WHERE id = :id", 
                             {"c": item['cantidad'] * cant_fab, "id": int(item['id_insumo'])}, commit=True)
                st.success("Stock actualizado.")

# ==========================================
# 🚀 5. REGISTRAR VENTAS
# ==========================================
elif menu == "🚀 Registrar Ventas":
    st.header("🚀 Nueva Venta")
    df_p = db_query("SELECT id, nombre, precio_v, precio_v2, stock_actual FROM productos WHERE UPPER(tipo) = 'FINAL'")
    if df_p is not None and not df_p.empty:
        sel_p = st.selectbox("Producto:", df_p['nombre'].tolist())
        row = df_p[df_p['nombre'] == sel_p].iloc[0]
        
        with st.form("venta"):
            c1, c2 = st.columns(2)
            lista = c1.radio("Lista:", ["Lista 1", "Lista 2"])
            cant = c2.number_input("Cantidad:", min_value=1)
            precio = safe_float(row['precio_v']) if lista == "Lista 1" else safe_float(row['precio_v2'])
            total = st.number_input("Total a cobrar:", value=float(precio * cant))
            metodo = st.selectbox("Pago:", ["Efectivo", "MP", "Transferencia"])
            
            if st.form_submit_button("Confirmar Venta"):
                db_query("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (:f, :p, :c, :t, :m)",
                         {"f": date.today(), "p": sel_p, "c": cant, "t": total, "m": metodo}, commit=True)
                db_query("UPDATE productos SET stock_actual = stock_actual - :c WHERE id = :id", {"c": cant, "id": int(row['id'])}, commit=True)
                st.success("Venta registrada")
                st.rerun()

# ==========================================
# 📊 6. CAJA Y FILTROS
# ==========================================
elif menu == "📊 Caja y Filtros":
    st.header("📊 Movimientos de Caja")
    df_v = db_query("SELECT * FROM historial_ventas ORDER BY fecha DESC")
    if df_v is not None:
        st.dataframe(df_v, use_container_width=True)
        st.metric("RECAUDACIÓN TOTAL", f"$ {df_v['total_venta'].sum():,.2f}")

# ==========================================
# 📈 7. RENTABILIDAD
# ==========================================
elif menu == "📈 Rentabilidad x Producto":
    st.header("📈 Análisis de Margen Real")
    df_rent = db_query("""
        SELECT producto, SUM(cantidad) as cant, SUM(total_venta) as total 
        FROM historial_ventas GROUP BY producto
    """)
    if df_rent is not None:
        st.dataframe(df_rent, use_container_width=True)
