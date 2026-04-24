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
# 1. INVENTARIO Y ALTA
# ==========================================
if menu == "📦 Inventario y Alta":
    st.subheader("📦 Gestión de Productos e Insumos")
    
    col_alta, col_ajuste = st.columns(2)

    with col_alta.expander("➕ DAR DE ALTA NUEVO"):
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

    with col_ajuste.expander("⚙️ AJUSTE DE PRECIOS / MÁRGENES"):
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
                sql = "UPDATE productos SET margen1=:m1, margen2=:m2, precio_v=:p1, precio_v2=:p2 WHERE id=:id"
                db_query(sql, {"m1": m1, "m2": m2, "p1": p1, "p2": p2, "id": int(row_p['id'])}, commit=True)
                st.success("Precios actualizados")
                st.rerun()

    st.divider()
    df_ver = db_query("SELECT nombre, tipo, stock_actual, stock_minimo, unidad, costo_u, precio_v as \"Lista 1\", precio_v2 as \"Lista 2\" FROM productos ORDER BY tipo, nombre")
    if df_ver is not None:
        st.dataframe(df_ver, use_container_width=True, hide_index=True)

# ==========================================
# 🧪 RECETAS Y COSTEO
# ==========================================
elif menu == "🧪 Recetas y Costeo":
    st.header("🧪 Composición de Productos")
    
    df_finales = db_query("SELECT id, nombre FROM productos WHERE tipo = 'Final'")
    df_insumos = db_query("SELECT id, nombre, unidad, costo_u FROM productos WHERE tipo = 'Insumo'")

    if df_finales is not None and not df_finales.empty:
        col_r1, col_r2 = st.columns([1, 2])
        
        with col_r1:
            sel_f = st.selectbox("Producto Final", df_finales['nombre'].tolist())
            id_f = df_finales[df_finales['nombre'] == sel_f].iloc[0]['id']
            
            with st.form("add_insumo"):
                sel_i = st.selectbox("Agregar Insumo", df_insumos['nombre'].tolist())
                ins_row = df_insumos[df_insumos['nombre'] == sel_i].iloc[0]
                cant_i = st.number_input(f"Cantidad ({ins_row['unidad']})", min_value=0.01)
                if st.form_submit_button("Añadir a Receta"):
                    db_query("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (:idf, :idi, :c)",
                             {"idf": int(id_f), "idi": int(ins_row['id']), "c": cant_i}, commit=True)
                    st.rerun()

        with col_r2:
            st.subheader(f"Ficha Técnica: {sel_f}")
            query_r = """
                SELECT r.id, i.nombre, r.cantidad, i.unidad, i.costo_u, (r.cantidad * i.costo_u) as subtotal
                FROM recetas r 
                JOIN productos i ON r.id_insumo = i.id
                WHERE r.id_final = :id
            """
            df_rec = db_query(query_r, {"id": int(id_f)})
            if df_rec is not None and not df_rec.empty:
                st.table(df_rec[['nombre', 'cantidad', 'unidad', 'subtotal']])
                costo_total = df_rec['subtotal'].sum()
                st.metric("COSTO DE FABRICACIÓN", f"$ {costo_total:,.2f}")
                
                # Actualizar costo_u en tabla productos automáticamente
                db_query("UPDATE productos SET costo_u = :c WHERE id = :id", {"c": costo_total, "id": int(id_f)}, commit=True)

# ==========================================
# 🏭 FABRICACIÓN
# ==========================================
elif menu == "🏭 Fabricación":
    st.header("🏭 Registro de Producción")
    df_f = db_query("SELECT id, nombre FROM productos WHERE tipo = 'Final'")
    
    if df_f is not None:
        sel_f = st.selectbox("¿Qué fabricaste?", df_f['nombre'].tolist())
        id_f = df_f[df_f['nombre'] == sel_f].iloc[0]['id']
        cant_fab = st.number_input("Cantidad fabricada", min_value=1)

        if st.button("Confirmar Producción (Descontar Insumos)"):
            receta = db_query("SELECT id_insumo, cantidad FROM recetas WHERE id_final = :id", {"id": int(id_f)})
            if receta is not None:
                # 1. Sumar al producto final
                db_query("UPDATE productos SET stock_actual = stock_actual + :c WHERE id = :id", 
                         {"c": cant_fab, "id": int(id_f)}, commit=True)
                # 2. Restar insumos
                for _, item in receta.iterrows():
                    db_query("UPDATE productos SET stock_actual = stock_actual - :c WHERE id = :id", 
                             {"c": item['cantidad'] * cant_fab, "id": int(item['id_insumo'])}, commit=True)
                st.success(f"Producción de {cant_fab} {sel_f} registrada.")

# ==========================================
# 🚀 REGISTRAR VENTAS
# ==========================================
elif menu == "🚀 Registrar Ventas":
    st.header("🚀 Nueva Venta")
    df_prod = db_query("SELECT id, nombre, precio_v, precio_v2, stock_actual FROM productos WHERE tipo = 'Final'")

    if df_prod is not None and not df_prod.empty:
        sel_nombre = st.selectbox("Seleccione Producto:", df_prod['nombre'].tolist())
        row = df_prod[df_prod['nombre'] == sel_nombre].iloc[0]
        
        st.info(f"💰 Lista 1: ${safe_float(row['precio_v']):,.0f} | 💰 Lista 2: ${safe_float(row['precio_v2']):,.0f} | 📦 Stock: {row['stock_actual']}")

        with st.form("f_venta"):
            c1, c2 = st.columns(2)
            tipo_l = c1.radio("Lista aplicada:", ["Lista 1", "Lista 2"], horizontal=True)
            cant = c2.number_input("Cantidad:", min_value=1.0, step=1.0)
            metodo = st.selectbox("Forma de Pago:", ["Efectivo", "Mercado Pago", "Transferencia"])
            
            monto_sug = safe_float(row['precio_v']) * cant if tipo_l == "Lista 1" else safe_float(row['precio_v2']) * cant
            monto_final = st.number_input("Confirmar Monto Cobrado ($)", value=monto_sug)

            if st.form_submit_button("✅ REGISTRAR VENTA"):
                # Historial
                db_query("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (:f, :p, :c, :t, :m)",
                         {"f": date.today(), "p": sel_nombre, "c": cant, "t": monto_final, "m": metodo}, commit=True)
                # Stock
                db_query("UPDATE productos SET stock_actual = stock_actual - :c WHERE id = :id", 
                         {"c": cant, "id": int(row['id'])}, commit=True)
                st.success("Venta guardada.")
                st.rerun()

# ==========================================
# 📊 CAJA Y FILTROS
# ==========================================
elif menu == "📊 Caja y Filtros":
    st.header("📊 Movimientos de Caja")
    df_v = db_query("SELECT * FROM historial_ventas ORDER BY id DESC")
    if df_v is not None:
        st.subheader("Listado de Ventas")
        st.dataframe(df_v, use_container_width=True, hide_index=True)
        st.metric("TOTAL RECAUDADO", f"$ {df_v['total_venta'].sum():,.2f}")

# ==========================================
# 📈 RENTABILIDAD
# ==========================================
elif menu == "📈 Rentabilidad x Producto":
    st.header("📈 Análisis de Rentabilidad")
    df_rent = db_query("""
        SELECT producto, SUM(cantidad) as cant, SUM(total_venta) as recaudado 
        FROM historial_ventas GROUP BY producto
    """)
    if df_rent is not None:
        # Aquí podrías cruzar con el costo_u para ver margen real
        st.dataframe(df_rent, use_container_width=True)
