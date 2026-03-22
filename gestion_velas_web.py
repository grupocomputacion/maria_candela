import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Velas Candela - Gestión Pro Cloud", layout="wide")

def conectar():
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()
    # Estructura de Productos
    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT, 
        unidad TEXT, stock_actual REAL DEFAULT 0, stock_minimo REAL DEFAULT 0,
        costo_u REAL DEFAULT 0, precio_v REAL DEFAULT 0, precio_v2 REAL DEFAULT 0,
        margen1 REAL DEFAULT 100, margen2 REAL DEFAULT 100)''')
    
    # NUEVA TABLA: RECETAS (Para guardar la composición)
    cursor.execute('''CREATE TABLE IF NOT EXISTS recetas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, id_final INTEGER, id_insumo INTEGER, cantidad REAL)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''')
    
    conn.commit()
    conn.close()

inicializar_db()

st.title("🕯️ Velas Candela - Gestión Integral")

menu = st.sidebar.selectbox("MENÚ", ["📦 Inventario", "🧪 Recetas y Producción", "💰 Calculadora", "🚀 Ventas", "📊 Reportes"])

# ---------------------------------------------------------
# 1. INVENTARIO (Filtros Case-Insensitive)
# ---------------------------------------------------------
if menu == "📦 Inventario":
    st.subheader("Gestión de Stock")
    f1, f2 = st.columns(2)
    # Buscamos 'Final' o 'Insumo' tal como en el original
    tipo_f = f1.selectbox("Filtrar Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
    busq = f2.text_input("Buscar por nombre")

    conn = conectar()
    query = "SELECT id, nombre, tipo, stock_actual, costo_u, precio_v, precio_v2 FROM productos WHERE 1=1"
    params = []
    if tipo_f != "TODOS":
        query += " AND UPPER(tipo) = UPPER(?)"; params.append(tipo_f)
    if busq:
        query += " AND UPPER(nombre) LIKE UPPER(?)"; params.append(f"%{busq}%")
    
    df = pd.read_sql_query(query, conn, params=params)
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# 2. RECETAS Y PRODUCCIÓN (La funcionalidad que faltaba)
# ---------------------------------------------------------
elif menu == "🧪 Recetas y Producción":
    st.subheader("Configuración de Recetas de Producción")
    conn = conectar()
    finales = pd.read_sql_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    insumos = pd.read_sql_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'INSUMO'", conn)

    if not finales.empty and not insumos.empty:
        col_rec1, col_rec2 = st.columns([1, 2])
        
        with col_rec1:
            st.write("### Definir Receta")
            v_final = st.selectbox("Elegir Vela Final", finales['nombre'].tolist())
            id_v_final = finales[finales['nombre'] == v_final]['id'].values[0]
            
            # Formulario para agregar componentes a la receta
            with st.form("add_insumo_receta"):
                ins_nombre = st.selectbox("Insumo a agregar", insumos['nombre'].tolist())
                id_ins = insumos[insumos['nombre'] == ins_nombre]['id'].values[0]
                cant_ins = st.number_input("Cantidad (Gr/Ml/Un)", min_value=0.01)
                if st.form_submit_button("Añadir a Receta"):
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (int(id_v_final), int(id_ins), cant_ins))
                    conn.commit()
                    st.success(f"Añadido {ins_nombre} a la receta de {v_final}")

        with col_rec2:
            st.write(f"### Composición de: {v_final}")
            df_receta = pd.read_sql_query(f"""
                SELECT r.id, i.nombre as Insumo, r.cantidad as Cantidad, i.unidad
                FROM recetas r JOIN productos i ON r.id_insumo = i.id
                WHERE r.id_final = {id_v_final}""", conn)
            st.table(df_receta)
            
            if st.button("🚀 REGISTRAR PRODUCCIÓN (Descontar Stock)"):
                # Lógica de producción: suma al producto final, resta a los insumos
                c = conn.cursor()
                for _, fila in df_receta.iterrows():
                    # Restar insumos (necesitamos el ID del insumo de nuevo)
                    c.execute("UPDATE productos SET stock_actual = stock_actual - (SELECT cantidad FROM recetas WHERE id=?) WHERE nombre=?", (fila['id'], fila['Insumo']))
                c.execute("UPDATE productos SET stock_actual = stock_actual + 1 WHERE id=?", (int(id_v_final),))
                conn.commit()
                st.success(f"Producción terminada: +1 {v_final} en stock. Insumos descontados.")

# ---------------------------------------------------------
# 3. CALCULADORA (Usa las recetas guardadas o manual)
# ---------------------------------------------------------
elif menu == "💰 Calculadora":
    st.subheader("Calculadora de Costos")
    conn = conectar()
    opcion_calc = st.radio("Modo:", ["Manual", "Desde Receta Guardada"])
    
    if opcion_calc == "Desde Receta Guardada":
        finales = pd.read_sql_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
        v_sel = st.selectbox("Seleccionar Vela", finales['nombre'].tolist())
        id_v = finales[finales['nombre'] == v_sel]['id'].values[0]
        
        df_c = pd.read_sql_query(f"""
            SELECT i.nombre, r.cantidad, i.costo_u, (r.cantidad * i.costo_u) as Subtotal
            FROM recetas r JOIN productos i ON r.id_insumo = i.id
            WHERE r.id_final = {id_v}""", conn)
        
        st.dataframe(df_c)
        st.metric("COSTO TOTAL RECETA", f"$ {df_c['Subtotal'].sum():,.2f}")
    else:
        # Lógica manual anterior
        st.write("Cálculo rápido manual...")
        # ... (código calculadora manual)

# ---------------------------------------------------------
# 4. VENTAS
# ---------------------------------------------------------
elif menu == "🚀 Ventas":
    st.subheader("Registrar Venta")
    conn = conectar()
    velas = pd.read_sql_query("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    
    if not velas.empty:
        with st.form("venta"):
            v_nom = st.selectbox("Vela", velas['nombre'].tolist())
            v_cant = st.number_input("Cantidad", min_value=1.0)
            v_lista = st.radio("Lista", ["Minorista (L1)", "Mayorista (L2)"])
            
            p_sug = velas[velas['nombre'] == v_nom]['precio_v' if "1" in v_lista else 'precio_v2'].values[0]
            monto = st.number_input("Total cobrado $", value=float(p_sug * v_cant))
            
            if st.form_submit_button("Cerrar Venta"):
                c = conn.cursor()
                c.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)",
                         (datetime.now().strftime("%Y-%m-%d %H:%M"), v_nom, v_cant, monto))
                c.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_cant, v_nom))
                conn.commit()
                st.success("Venta finalizada.")

# ---------------------------------------------------------
# 5. REPORTES
# ---------------------------------------------------------
elif menu == "📊 Reportes":
    st.subheader("Historial de Ventas")
    conn = conectar()
    df_v = pd.read_sql_query("SELECT * FROM historial_ventas ORDER BY id DESC", conn)
    st.dataframe(df_v, use_container_width=True)
    st.metric("Total Facturado", f"$ {df_v['total_venta'].sum():,.2f}")
