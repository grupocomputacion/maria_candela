import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Velas Candela Pro - Cloud", layout="wide")

def conectar():
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()
    # 1. Tabla de Productos (Mantiene columnas originales)
    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT, 
        unidad TEXT, stock_actual REAL DEFAULT 0, costo_u REAL DEFAULT 0, 
        precio_v REAL DEFAULT 0, precio_v2 REAL DEFAULT 0, 
        margen1 REAL DEFAULT 100, margen2 REAL DEFAULT 100)''')
    
    # 2. Tabla de RECETAS (Vínculo Insumo -> Final)
    cursor.execute('''CREATE TABLE IF NOT EXISTS recetas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, id_final INTEGER, 
        id_insumo INTEGER, cantidad REAL)''')
    
    # 3. Historiales de Movimientos
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, item_nombre TEXT, 
        cantidad REAL, costo_total REAL, metodo_pago TEXT)''')
    
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Menú de Gestión")
menu = st.sidebar.radio("Ir a:", ["📦 Stock e Inventario", "🧪 Gestión de Recetas", "🚀 Registrar Venta", "📊 Caja y Reportes"])

# ---------------------------------------------------------
# 1. STOCK E INVENTARIO
# ---------------------------------------------------------
if menu == "📦 Stock e Inventario":
    st.subheader("Gestión de Existencias y Precios")
    
    f1, f2 = st.columns(2)
    # Filtro Case-Insensitive
    tipo_f = f1.selectbox("Filtrar por Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
    busq = f2.text_input("Buscar por nombre")
    
    conn = conectar()
    query = "SELECT id, nombre, tipo, stock_actual as Stock, costo_u as 'Costo U$', precio_v as 'Lista 1', precio_v2 as 'Lista 2' FROM productos WHERE 1=1"
    params = []
    if tipo_f != "TODOS":
        query += " AND UPPER(tipo) = UPPER(?)"; params.append(tipo_f)
    if busq:
        query += " AND UPPER(nombre) LIKE UPPER(?)"; params.append(f"%{busq}%")
    
    df_p = pd.read_sql_query(query, conn, params=params)
    st.dataframe(df_p, use_container_width=True, hide_index=True)

    with st.expander("➕ Cargar Nuevo Artículo"):
        with st.form("nuevo_prod"):
            c1, c2 = st.columns(2)
            n_nom = c1.text_input("Nombre")
            n_tip = c2.selectbox("Categoría", ["Insumo", "Final", "Packaging"])
            n_stk = c1.number_input("Stock Inicial", value=0.0)
            n_cst = c2.number_input("Costo Unitario", value=0.0)
            n_m1 = c1.number_input("Margen L1 % (Minorista)", value=100.0)
            n_m2 = c2.number_input("Margen L2 % (Mayorista)", value=70.0)
            
            if st.form_submit_button("Guardar Producto"):
                p1 = n_cst * (1 + n_m1/100)
                p2 = n_cst * (1 + n_m2/100)
                conn.execute("""INSERT INTO productos (nombre, tipo, stock_actual, costo_u, margen1, margen2, precio_v, precio_v2) 
                             VALUES (?,?,?,?,?,?,?,?)""", (n_nom, n_tip, n_stk, n_cst, n_m1, n_m2, p1, p2))
                conn.commit()
                st.success("Producto guardado correctamente.")
                st.rerun()

# ---------------------------------------------------------
# 2. GESTIÓN DE RECETAS (Blindado contra errores de SQL)
# ---------------------------------------------------------
elif menu == "🧪 Gestión de Recetas":
    st.subheader("Configuración de Fórmulas y Producción")
    conn = conectar()
    
    # Selectores dinámicos
    velas_finales = pd.read_sql_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    todos_insumos = pd.read_sql_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'INSUMO'", conn)

    if not velas_finales.empty:
        c_rec1, c_rec2 = st.columns([1, 2])
        
        with c_rec1:
            v_sel = st.selectbox("Seleccionar Vela Final", velas_finales['nombre'].tolist())
            id_v_final = int(velas_finales[velas_finales['nombre'] == v_sel]['id'].values[0])
            
            with st.form("form_receta"):
                st.write("### Agregar Insumo a la Receta")
                i_sel = st.selectbox("Elegir Insumo", todos_insumos['nombre'].tolist())
                i_cant = st.number_input("Cantidad (Gramos/Unidad)", min_value=0.0, format="%.2f")
                if st.form_submit_button("Vincular a Receta"):
                    id_i = int(todos_insumos[todos_insumos['nombre'] == i_sel]['id'].values[0])
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_final, id_i, i_cant))
                    conn.commit()
                    st.success("Insumo añadido a la fórmula.")

        with c_rec2:
            st.write(f"### Composición de Receta: {v_sel}")
            # BLINDAJE: Solo consultamos si id_v_final es válido
            query_receta = f"""
                SELECT r.id, i.nombre as Insumo, r.cantidad as Cantidad, i.costo_u, (r.cantidad * i.costo_u) as Subtotal
                FROM recetas r JOIN productos i ON r.id_insumo = i.id
                WHERE r.id_final = {id_v_final}"""
            
            df_receta = pd.read_sql_query(query_receta, conn)
            
            if not df_receta.empty:
                st.table(df_receta)
                costo_u = df_receta['Subtotal'].sum()
                st.metric("Costo Real de Producción", f"$ {costo_u:,.2f}")
                
                # --- LÓGICA DE PRODUCCIÓN ---
                cant_fab = st.number_input("Cantidad a fabricar", min_value=1, value=1)
                if st.button("🚀 REGISTRAR PRODUCCIÓN (Baja automática de Stock)"):
                    cur = conn.cursor()
                    for _, row in df_receta.iterrows():
                        # Descontar insumos del stock
                        cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (row['Cantidad'] * cant_fab, row['Insumo']))
                    # Sumar producto final al stock
                    cur.execute("UPDATE productos SET stock_actual = stock_actual + ? WHERE id = ?", (cant_fab, id_v_final))
                    conn.commit()
                    st.success(f"Producción exitosa: +{cant_fab} {v_sel} en stock.")
            else:
                st.info("Esta vela aún no tiene una receta cargada. Use el formulario de la izquierda.")
    else:
        st.warning("Primero debe cargar productos de categoría 'Final' en la pestaña de Stock.")

# ---------------------------------------------------------
# 3. VENTAS (Lista 1 y Lista 2)
# ---------------------------------------------------------
elif menu == "🚀 Registrar Venta":
    st.subheader("Punto de Venta")
    conn = conectar()
    velas = pd.read_sql_query("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    
    if not velas.empty:
        with st.form("vta_form"):
            v_nom = st.selectbox("Seleccionar Producto", velas['nombre'].tolist())
            v_cant = st.number_input("Cantidad", min_value=1.0)
            v_lista = st.radio("Lista de Precios", ["Lista 1 (Minorista)", "Lista 2 (Mayorista)"])
            
            # Sugerencia de precio automático
            p_ref = velas[velas['nombre'] == v_nom]['precio_v' if "1" in v_lista else 'precio_v2'].values[0]
            v_monto = st.number_input("Total a cobrar $", value=float(p_ref * v_cant))
            
            if st.form_submit_button("Finalizar Venta"):
                cur = conn.cursor()
                cur.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)",
                         (datetime.now().strftime("%Y-%m-%d %H:%M"), v_nom, v_cant, v_monto))
                cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_cant, v_nom))
                conn.commit()
                st.success("Venta registrada y stock actualizado.")
    else:
        st.error("No hay productos 'Finales' disponibles para la venta.")

# ---------------------------------------------------------
# 4. REPORTES Y CAJA
# ---------------------------------------------------------
elif menu == "📊 Caja y Reportes":
    st.subheader("Análisis de Movimientos")
    conn = conectar()
    df_v = pd.read_sql_query("SELECT fecha, producto as Detalle, total_venta as Monto FROM historial_ventas", conn)
    
    if not df_v.empty:
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("Total de Ingresos", f"$ {df_v['Monto'].sum():,.2f}")
        col_m2.metric("Ventas Realizadas", len(df_v))
        
        st.dataframe(df_v, use_container_width=True)
        
        # Gráfico dinámico para el iPad
        fig = px.bar(df_v, x='fecha', y='Monto', title="Evolución de Ventas Diarias")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay movimientos registrados en el historial de ventas.")
