import streamlit as st
import pandas as pd
from datetime import datetime, date
import io
import os
from sqlalchemy import create_engine, text

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Velas Candela Pro - Supabase Edition", layout="wide")

# ==========================================
# 1. MOTOR DE BASE DE DATOS (SUPABASE)
# ==========================================
def db_query(query, params=None, commit=False):
    try:
        engine = create_engine(st.secrets["postgres"]["url"])
        with engine.connect() as conn:
            if commit:
                conn.execute(text(query), params)
                conn.commit()
                return True
            else:
                result = pd.read_sql(text(query), conn, params=params)
                return result
    except Exception as e:
        st.error(f"Error de base de datos: {e}")
        return None

def safe_float(val):
    try:
        return float(val) if val is not None else 0.0
    except:
        return 0.0

def safe_int(val):
    try:
        if val is None or str(val).strip() == "":
            return 0
        return int(float(val))
    except:
        return 0

# ==========================================
# 2. MENÚ LATERAL
# ==========================================
st.sidebar.title("🕯️ Velas Control")
st.sidebar.info("Sincronizado con Supabase Cloud")

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
# 1. INVENTARIO Y ALTA (CORREGIDA CON EXCEL)
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

    # --- NUEVA FUNCIONALIDAD: IMPORTAR DESDE EXCEL ---
    with col_imp.expander("📥 IMPORTAR DESDE EXCEL (MIGRACIÓN)"):
        uploaded_file = st.file_uploader("Subir archivo Excel", type=["xlsx", "xls"])
        if uploaded_file is not None:
            df_excel = pd.read_excel(uploaded_file)
            st.write(f"📊 Registros detectados: {len(df_excel)}")
            
            if st.button("🚀 INICIAR CARGA A SUPABASE"):
                with st.spinner('⏳ Procesando...'):
                    progress_bar = st.progress(0)
                    exitos = 0
                    
                    for i, row in df_excel.iterrows():
                        try:
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
                            
                            # Intentamos insertar
                            if db_query(sql, params, commit=True):
                                exitos += 1
                            
                            progress_bar.progress((i + 1) / len(df_excel))
                            
                        except Exception as e:
                            # EL CAMBIO CLAVE: Mostramos el error y DETENEMOS la app
                            st.error(f"❌ ERROR CRÍTICO en fila {i} ({row.get('nombre')}):")
                            st.code(str(e)) # Muestra el error técnico detallado
                            st.stop() # Evita que desaparezca el mensaje

                    st.success(f"✅ Carga completa: {exitos} registros subidos.")
                    st.balloons()

    st.divider()
    
    # Ajuste de precios (con blindaje contra error base 10)
    with st.expander("⚙️ AJUSTE DE PRECIOS / MÁRGENES"):
        df_f = db_query("SELECT id, nombre, costo_u, margen1, margen2 FROM productos WHERE tipo = 'Final' ORDER BY nombre")
        if df_f is not None and not df_f.empty:
            sel_p = st.selectbox("Producto a Modificar", df_f['nombre'].tolist())
            row_p = df_f[df_f['nombre'] == sel_p].iloc[0]
            
            c1, c2 = st.columns(2)
            m1 = c1.number_input("Margen Lista 1 (%)", value=float(row_p['margen1']))
            m2 = c2.number_input("Margen Lista 2 (%)", value=float(row_p['margen2']))
            
            p1 = row_p['costo_u'] * (1 + m1/100)
            p2 = row_p['costo_u'] * (1 + m2/100)
            
            st.warning(f"Nuevos Precios: L1: ${p1:,.2f} | L2: ${p2:,.2f}")
            
            if st.button("Actualizar Precios"):
                id_limpio = safe_int(row_p['id'])
                if id_limpio > 0:
                    sql = "UPDATE productos SET margen1=:m1, margen2=:m2, precio_v=:p1, precio_v2=:p2 WHERE id=:id"
                    db_query(sql, {"m1": m1, "m2": m2, "p1": p1, "p2": p2, "id": id_limpio}, commit=True)
                    st.success("Precios actualizados")
                    st.rerun()

    df_ver = db_query("SELECT nombre, tipo, stock_actual, stock_minimo, unidad, costo_u, precio_v as \"Lista 1\", precio_v2 as \"Lista 2\" FROM productos ORDER BY tipo, nombre")
    if df_ver is not None:
        st.dataframe(df_ver, use_container_width=True, hide_index=True)

# ... El resto del código de Recetas, Ventas y Caja se mantiene igual ...
