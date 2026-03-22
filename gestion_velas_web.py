import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Velas Candela Pro - Sistema Integral", layout="wide")

# --- CONEXIÓN Y BASE DE DATOS ---
def conectar():
    # check_same_thread=False es fundamental para evitar el DatabaseError en Streamlit Cloud
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()
    # Tabla Productos
    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT, 
        unidad TEXT, stock_actual REAL DEFAULT 0, costo_u REAL DEFAULT 0, 
        precio_v REAL DEFAULT 0, precio_v2 REAL DEFAULT 0, 
        margen1 REAL DEFAULT 100, margen2 REAL DEFAULT 100)''')
    
    # Tabla de RECETAS (Relación muchos a muchos)
    cursor.execute('''CREATE TABLE IF NOT EXISTS recetas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, id_final INTEGER, 
        id_insumo INTEGER, cantidad REAL)''')
    
    # Historial de Ventas
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''')
    
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Menú Velas Candela")
menu = st.sidebar.radio("Ir a:", [
    "📦 Stock e Inventario", 
    "🧪 Gestión de Recetas y Costos", 
    "🚀 Registrar Venta", 
    "📊 Caja y Reportes"
])

# ---------------------------------------------------------
# 1. STOCK E INVENTARIO
# ---------------------------------------------------------
if menu == "📦 Stock e Inventario":
    st.subheader("Control de Stock y Precios")
    conn = conectar()
    f1, f2 = st.columns(2)
    tipo_f = f1.selectbox("Filtrar por Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
    busq = f2.text_input("Buscar por nombre")
    
    query = "SELECT id, nombre, tipo, stock_actual as Stock, costo_u as 'Costo U$', precio_v as 'Lista 1', precio_v2 as 'Lista 2' FROM productos WHERE 1=1"
    params = []
    if tipo_f != "TODOS":
        query += " AND UPPER(tipo) = UPPER(?)"; params.append(tipo_f)
    if busq:
        query += " AND UPPER(nombre) LIKE UPPER(?)"; params.append(f"%{busq}%")
    
    df_p = pd.read_sql_query(query, conn, params=params)
    st.dataframe(df_p, use_container_width=True, hide_index=True)

    with st.expander("➕ Cargar / Editar Producto"):
        with st.form("nuevo_p"):
            c1, c2 = st.columns(2)
            n_nom = c1.text_input("Nombre del artículo")
            n_tip = c2.selectbox("Categoría", ["Insumo", "Final", "Packaging"])
            n_stk = c1.number_input("Stock Inicial", value=0.0)
            n_cst = c2.number_input("Costo Unitario $", value=0.0)
            if st.form_submit_button("Guardar en Base de Datos"):
                conn.execute("INSERT INTO productos (nombre, tipo, stock_actual, costo_u) VALUES (?,?,?,?)", (n_nom, n_tip, n_stk, n_cst))
                conn.commit()
                st.success("Registrado correctamente.")
                st.rerun()

# ---------------------------------------------------------
# 2. GESTIÓN DE RECETAS (CALCULADORA DINÁMICA)
# ---------------------------------------------------------
elif menu == "🧪 Gestión de Recetas y Costos":
    st.subheader("Calculadora de Componentes y Precios de Venta")
    conn = conectar()
    
    # Cargamos productos de tipo FINAL e INSUMO
    df_finales = pd.read_sql_query("SELECT id, nombre, margen1, margen2 FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    df_insumos = pd.read_sql_query("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'", conn)

    if not df_finales.empty:
        c1, c2 = st.columns([1, 2])
        
        with c1:
            v_sel = st.selectbox("Seleccionar Vela para analizar", df_finales['nombre'].tolist())
            datos_v = df_finales[df_finales['nombre'] == v_sel].iloc[0]
            id_v_final = int(datos_v['id'])
            
            st.info(f"Márgenes configurados: M1: {datos_v['margen1']}% | M2: {datos_v['margen2']}%")
            
            with st.form("add_materia"):
                st.write("### Vincular Materia Prima")
                ins_sel = st.selectbox("Insumo", df_insumos['nombre'].tolist()) if not df_insumos.empty else st.error("No hay insumos")
                cant_ins = st.number_input("Cantidad necesaria (Gr/Ml/Un)", min_value=0.0, format="%.2f")
                if st.form_submit_button("Añadir a la Receta"):
                    id_i = int(df_insumos[df_insumos['nombre'] == ins_sel]['id'].values[0])
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_final, id_i, cant_ins))
                    conn.commit()
                    st.success("Componente vinculado.")
                    st.rerun()

        with c2:
            st.write(f"### Composición de Receta: {v_sel}")
            # Query para recuperar recetas cargadas
            query_receta = f"""
                SELECT r.id, i.nombre as Materia_Prima, r.cantidad as Cantidad, i.costo_u, (r.cantidad * i.costo_u) as Subtotal
                FROM recetas r 
                INNER JOIN productos i ON r.id_insumo = i.id
                WHERE r.id_final = {id_v_final}
            """
            
            try:
                df_receta = pd.read_sql_query(query_receta, conn)
                
                if not df_receta.empty:
                    st.table(df_receta)
                    costo_total = df_receta['Subtotal'].sum()
                    
                    st.divider()
                    st.write("### 💰 Cálculo de Precios de Venta")
                    col_m1, col_m2 = st.columns(2)
                    
                    # Lógica de Márgenes originales
                    nuevo_m1 = col_m1.number_input("Ajustar Margen Lista 1 %", value=float(datos_v['margen1']))
                    nuevo_m2 = col_m2.number_input("Ajustar Margen Lista 2 %", value=float(datos_v['margen2']))
                    
                    precio1 = costo_total * (1 + nuevo_m1/100)
                    precio2 = costo_total * (1 + nuevo_m2/100)
                    
                    st.metric("COSTO TOTAL DE MATERIALES", f"$ {costo_total:,.2f}")
                    col_m1.metric("PRECIO SUGERIDO L1", f"$ {precio1:,.2f}")
                    col_m2.metric("PRECIO SUGERIDO L2", f"$ {precio2:,.2f}")
                    
                    if st.button("💾 Guardar Precios y Márgenes en Stock"):
                        conn.execute("UPDATE productos SET precio_v=?, precio_v2=?, margen1=?, margen2=? WHERE id=?", 
                                    (precio1, precio2, nuevo_m1, nuevo_m2, id_v_final))
                        conn.commit()
                        st.success("Precios actualizados en la pestaña de Inventario.")
                    
                    st.divider()
                    if st.button("🚀 REGISTRAR PRODUCCIÓN (+1 Stock, - Insumos)"):
                        cur = conn.cursor()
                        for _, row in df_receta.iterrows():
                            cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (row['Cantidad'], row['Materia_Prima']))
                        cur.execute("UPDATE productos SET stock_actual = stock_actual + 1 WHERE id = ?", (id_v_final,))
                        conn.commit()
                        st.success("Producción registrada correctamente.")
                        st.rerun()
                else:
                    st.info("No se encontraron componentes guardados para esta vela.")
            except:
                st.error("Error al conectar con la tabla de recetas. Asegúrese de cargar insumos primero.")
    else:
        st.warning("Cargá un producto de categoría 'Final' para poder armar su receta.")

# ---------------------------------------------------------
# 3. REGISTRAR VENTA
# ---------------------------------------------------------
elif menu == "🚀 Registrar Venta":
    st.subheader("Terminal de Ventas")
    conn = conectar()
    velas = pd.read_sql_query("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    
    if not velas.empty:
        with st.form("venta"):
            v_nom = st.selectbox("Seleccionar Vela", velas['nombre'].tolist())
            v_cant = st.number_input("Cantidad vendida", min_value=1.0)
            v_lista = st.radio("Lista de Precios", ["Lista 1 (Minorista)", "Lista 2 (Mayorista)"])
            
            p_ref = velas[velas['nombre'] == v_nom]['precio_v' if "1" in v_lista else 'precio_v2'].values[0]
            v_total = st.number_input("Monto final a cobrar $", value=float(p_ref * v_cant))
            
            if st.form_submit_button("Confirmar Operación"):
                cur = conn.cursor()
                cur.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)", 
                           (datetime.now().strftime("%Y-%m-%d %H:%M"), v_nom, v_cant, v_total))
                cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_cant, v_nom))
                conn.commit()
                st.success("Venta guardada y stock descontado.")
    else:
        st.error("No hay productos 'Finales' registrados con precio.")

# ---------------------------------------------------------
# 4. CAJA Y REPORTES
# ---------------------------------------------------------
elif menu == "📊 Caja y Reportes":
    st.subheader("Historial de Caja y Rendimiento")
    conn = conectar()
    df_v = pd.read_sql_query("SELECT fecha, producto as Detalle, total_venta as Monto FROM historial_ventas ORDER BY id DESC", conn)
    
    if not df_v.empty:
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("Ingresos Totales", f"$ {df_v['Monto'].sum():,.2f}")
        col_m2.metric("Ventas Totales", len(df_v))
        
        st.dataframe(df_v, use_container_width=True)
        fig = px.pie(df_v, values='Monto', names='Detalle', title="Distribución de Ventas")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay movimientos registrados.")
