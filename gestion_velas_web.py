import streamlit as st
import pandas as pd
from datetime import datetime, date
import io
import os
from sqlalchemy import create_engine, text

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Velas Candela Pro - Supabase", layout="wide")

# ==========================================
# 1. MOTOR DE BASE DE DATOS (OPTIMIZADO)
# ==========================================

@st.cache_resource
def get_engine():
    """Crea el motor de conexión una sola vez"""
    try:
        conn_url = st.secrets["postgres"]["url"]
        if not conn_url:
            st.error("⚠️ La URL de conexión está vacía en los Secrets.")
            return None
        return create_engine(conn_url, pool_pre_ping=True)
    except Exception as e:
        st.error(f"❌ Error al configurar el motor de BD: {e}")
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
        # Solo mostramos el error si no es una carga masiva para no saturar
        if not commit or "INSERT" not in query:
            st.error(f"Error de base de datos: {e}")
        return None

def safe_float(val):
    try:
        if pd.isna(val) or val == "": return 0.0
        return float(val)
    except:
        return 0.0

def safe_int(val):
    try:
        if pd.isna(val) or str(val).strip() == "": return 0
        return int(float(val))
    except:
        return 0

# ==========================================
# 2. MENÚ LATERAL Y DIAGNÓSTICO
# ==========================================
st.sidebar.title("🕯️ Velas Control")
st.sidebar.info("Sincronizado con Supabase Cloud")

if st.sidebar.button("🔌 Testear Conexión"):
    engine = get_engine()
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            st.sidebar.success("✅ Conexión Exitosa!")
        except Exception as e:
            st.sidebar.error(f"❌ Falló: {e}")

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
# 1. INVENTARIO Y ALTA
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

    with col_imp.expander("📥 IMPORTAR DESDE EXCEL"):
        uploaded_file = st.file_uploader("Subir backup.xlsx", type=["xlsx"])
        if uploaded_file:
            df_excel = pd.read_excel(uploaded_file)
            df_excel.columns = [c.strip().lower() for c in df_excel.columns] # Normalizar nombres
            st.write(f"📊 Registros encontrados: {len(df_excel)}")
            
            if st.button("🚀 SUBIR A SUPABASE"):
                progress = st.progress(0)
                exitos, errores = 0, 0
                for i, row in df_excel.iterrows():
                    sql = """INSERT INTO productos (nombre, tipo, unidad, stock_actual, stock_minimo, costo_u, margen1, margen2, precio_v, precio_v2) 
                             VALUES (:nom, :tip, :uni, :stk, :min, :cst, :m1, :m2, :p1, :p2)"""
                    params = {
                        "nom": str(row.get('nombre', 'Sin nombre')),
                        "tip": str(row.get('tipo', 'Insumo')),
                        "uni": str(row.get('unidad', 'Un')),
                        "stk": safe_float(row.get('stock_actual', 0)),
                        "min": safe_float(row.get('stock_minimo', 0)),
                        "cst": safe_float(row.get('costo_u', 0)),
                        "m1": safe_float(row.get('margen1', 100)),
                        "m2": safe_float(row.get('margen2', 100)),
                        "p1": safe_float(row.get('precio_v', 0)),
                        "p2": safe_float(row.get('precio_v2', 0))
                    }
                    if db_query(sql, params, commit=True): exitos += 1
                    else: errores += 1
                    progress.progress((i + 1) / len(df_excel))
                
                st.success(f"✅ Carga terminada: {exitos} exitosos. ❌ Errores: {errores}")
                st.rerun()

    st.divider()
    # Listado General
    df_ver = db_query("SELECT nombre, tipo, stock_actual, stock_minimo, unidad, costo_u, precio_v, precio_v2 FROM productos ORDER BY tipo, nombre")
    if df_ver is not None and not df_ver.empty:
        st.dataframe(df_ver, use_container_width=True, hide_index=True)
    else:
        st.info("La base de datos está vacía. Por favor, cargue o importe productos.")

# ==========================================
# 🧪 RECETAS Y COSTEO (AJUSTADO PARA NUBE)
# ==========================================
elif menu == "🧪 Recetas y Costeo":
    st.header("🧪 Composición de Productos")
    df_finales = db_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'")
    df_insumos = db_query("SELECT id, nombre, unidad, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'")

    if df_finales is not None and not df_finales.empty:
        sel_f = st.selectbox("Seleccione Producto Final", df_finales['nombre'].tolist())
        id_f = df_finales[df_finales['nombre'] == sel_f].iloc[0]['id']
        
        # ... Resto de la lógica de recetas usando db_query ...
