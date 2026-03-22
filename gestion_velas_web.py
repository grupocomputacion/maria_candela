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
    # Estructura completa original
    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT, 
        unidad TEXT, stock_actual REAL DEFAULT 0, costo_u REAL DEFAULT 0, 
        precio_v REAL DEFAULT 0, precio_v2 REAL DEFAULT 0, 
        margen1 REAL DEFAULT 100, margen2 REAL DEFAULT 100)''')
    
    # Tabla de RECETAS (Fundamental para producción)
    cursor.execute('''CREATE TABLE IF NOT EXISTS recetas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, id_final INTEGER, 
        id_insumo INTEGER, cantidad REAL)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''")
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, item_nombre TEXT, 
        cantidad REAL, costo_total REAL, metodo_pago TEXT)''')
    
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Menú de Gestión")
menu = st.sidebar.radio("Ir a:", ["📦 Inventario y Precios", "🧪 Recetas y Producción", "💰 Calculadora Manual", "🚀 Ventas", "📊 Reportes de Caja"])

# ---------------------------------------------------------
# 1. INVENTARIO Y PRECIOS
# ---------------------------------------------------------
if menu == "📦 Inventario y Precios":
    st.subheader("Gestión de Stock e Insumos")
    
    f1, f2 = st.columns(2)
    # Buscamos 'Final' o 'Insumo' como en tu original
    tipo_f = f1.selectbox("Filtrar Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
    busq = f2.text_input("Buscar por nombre")
    
    conn = conectar()
    query = "SELECT id, nombre, tipo, stock_actual as Stock, costo_u as 'Costo U$', margen1 as 'M1%', precio_v as 'Lista 1', margen2 as 'M2%', precio_v2 as 'Lista 2' FROM productos WHERE 1=1"
    params = []
    if tipo_f != "TODOS":
        query += " AND UPPER(tipo) = UPPER(?)"; params.append(tipo_f)
    if busq:
        query += " AND UPPER(nombre) LIKE UPPER(?)"; params.append(f"%{busq}%")
    
    df_p = pd.read_sql_query(query, conn, params=params)
    st.dataframe(df_p, use_container_width=True, hide_index=True)

    with st.expander("➕ Alta de Nuevo Producto / Insumo"):
        with st.form("nuevo_prod"):
            c1, c2 = st.columns(2)
            n_nom = c1.text_input("Nombre")
            n_tip = c2.selectbox("Categoría", ["Insumo", "Final", "Packaging"])
            n_stk = c1.number_input("Stock Inicial", value=0.0)
            n_cst = c2.number_input("Costo Unitario", value=0.0)
            n_m1 = c1.number_input("Margen Lista 1 %", value=100.0)
            n_m2 = c2.number_input("Margen Lista 2 %", value=70.0)
            
            if st.form_submit_button("Guardar"):
                p1 = n_cst * (1 + n_m1/100)
                p2 = n_cst * (1 + n_m2/100)
                conn.execute("""INSERT INTO productos (nombre, tipo, stock_actual, costo_u, margen1, margen2, precio_v, precio_v2) 
                             VALUES (?,?,?,?,?,?,?,?)""", (n_nom, n_tip, n_stk, n_cst, n_m1, n_m2, p1, p2))
                conn.commit()
                st.success("Guardado.")
                st.rerun()

# ---------------------------------------------------------
# 2. RECETAS Y PRODUCCIÓN (CORREGIDO Y COMPLETO)
# ---------------------------------------------------------
elif menu == "🧪 Recetas y Producción":
    st.subheader("Configuración de Fórmulas y Fabricación")
    conn = conectar()
    
    velas_finales = pd.read_sql_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    todos_insumos = pd.read_sql_query("SELECT id, nombre FROM productos WHERE UPPER(tipo) = 'INSUMO'", conn)

    if not velas_finales.empty:
        c_rec1, c_rec2 = st.columns([1, 2])
        
        with c_rec1:
            v_sel = st.selectbox("Seleccionar Vela Final", velas_finales['nombre'].tolist())
            id_v_final = int(velas_finales[velas_finales['nombre'] == v_sel]['id'].values[0])
            
            with st.form("add_receta"):
                st.write("### Agregar Insumo a la Receta")
                i_sel = st.selectbox("Insumo", todos_insumos['nombre'].tolist())
                i_cant = st.number_input("Cantidad necesaria (Gr/Ml/Un)", min_value=0.0, format="%.2f")
                if st.form_submit_button("Añadir a Receta"):
                    id_i = int(todos_insumos[todos_insumos['nombre'] == i_sel]['id'].values[0])
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_final, id_i, i_cant))
                    conn.commit()
                    st.success("Componente añadido.")

        with c_rec2:
            st.write(f"### Receta Guardada: {v_sel}")
            # Verificación de ID para evitar el error anterior
            df_receta = pd.read_sql_query(f"""
                SELECT r.id, i.nombre as Insumo, r.cantidad as Cantidad, i.costo_u, (r.cantidad * i.costo_u) as Subtotal
                FROM recetas r JOIN productos i ON r.id_insumo = i.id
                WHERE r.id_final = {id_v_final}""", conn)
            
            if not df_receta.empty:
                st.table(df_receta)
                st.metric("Costo de Producción (Unitario)", f"$ {df_receta['Subtotal'].sum():,.2f}")
                
                cant_prod = st.number_input("Cantidad de velas a fabricar", min_value=1, value=1)
                if st.button("🚀 REGISTRAR PRODUCCIÓN (Descontar Stock)"):
                    c = conn.cursor()
                    for _, row in df_receta.iterrows():
                        # Restar insumos proporcionalmente
                        c.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (row['Cantidad'] * cant_prod, row['Insumo']))
                    # Sumar al stock del producto final
                    c.execute("UPDATE productos SET stock_actual = stock_actual + ? WHERE id = ?", (cant_prod, id_v_final))
                    conn.commit()
                    st.success(f"Se fabricaron {cant_prod} unidades. Stock de insumos actualizado.")
            else:
                st.info("Esta vela aún no tiene una receta cargada.")
    else:
        st.warning("Debe cargar productos de categoría 'Final' para armar recetas.")

# ---------------------------------------------------------
# 3. CALCULADORA MANUAL (Usa Insumos Reales)
# ---------------------------------------------------------
elif menu == "💰 Calculadora de Costos":
    st.subheader("Cálculo rápido de costos")
    conn = conectar()
    insumos_db = pd.read_sql_query("SELECT nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'", conn)
    
    if not insumos_db.empty:
        lineas = st.number_input("Nº de Insumos a sumar", 1, 15, 3)
        costo_suma = 0.0
        for i in range(lineas):
            cx1, cx2 = st.columns(2)
            n_i = cx1.selectbox(f"Insumo {i+1}", ["-"] + insumos_db['nombre'].tolist(), key=f"cal_{i}")
            q_i = cx2.number_input(f"Cantidad {i+1}", 0.0, key=f"qcal_{i}")
            if n_i != "-":
                precio_u = insumos_db[insumos_db['nombre'] == n_i]['costo_u'].values[0]
                costo_suma += (precio_u * q_i)
        
        st.divider()
        st.metric("COSTO TOTAL CALCULADO", f"$ {costo_suma:,.2f}")
    else:
        st.error("No hay insumos para calcular.")

# ---------------------------------------------------------
# 4. VENTAS
# ---------------------------------------------------------
elif menu == "🚀 Ventas":
    st.subheader("Registrar Venta Directa")
    conn = conectar()
    # Traemos las velas con sus dos precios de lista
    velas = pd.read_sql_query("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    
    if not velas.empty:
        with st.form("vta_form"):
            v_nom = st.selectbox("Vela Vendida", velas['nombre'].tolist())
            v_cant = st.number_input("Cantidad", min_value=1.0, step=1.0)
            v_lista = st.radio("Tipo de Cliente", ["Minorista (L1)", "Mayorista (L2)"])
            
            # Sugerencia de precio automático
            p_ref = velas[velas['nombre'] == v_nom]['precio_v' if "1" in v_lista else 'precio_v2'].values[0]
            v_pago = st.number_input("Total a cobrar $", value=float(p_ref * v_cant))
            v_metodo = st.selectbox("Método", ["Efectivo", "Transferencia", "Mercado Pago"])
            
            if st.form_submit_button("Confirmar Venta"):
                c = conn.cursor()
                c.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (?,?,?,?,?)",
                         (datetime.now().strftime("%Y-%m-%d %H:%M"), v_nom, v_cant, v_pago, v_metodo))
                c.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_cant, v_nom))
                conn.commit()
                st.success("Venta e Inventario actualizados.")
    else:
        st.info("No hay velas terminadas en stock.")

# ---------------------------------------------------------
# 5. REPORTES Y EXPORTACIÓN
# ---------------------------------------------------------
elif menu == "📊 Reportes de Caja":
    st.subheader("Resumen de Movimientos")
    conn = conectar()
    df_v = pd.read_sql_query("SELECT fecha, producto as Detalle, total_venta as Monto, metodo_pago FROM historial_ventas", conn)
    
    if not df_v.empty:
        st.metric("Total Ingresos", f"$ {df_v['Monto'].sum():,.2f}")
        st.dataframe(df_v, use_container_width=True)
        
        # Exportación a Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_v.to_excel(writer, index=False, sheet_name='Ventas')
        
        st.download_button(
            label="📥 Descargar Historial Excel",
            data=output.getvalue(),
            file_name=f"caja_velas_{datetime.now().strftime('%d_%m')}.xlsx",
            mime="application/vnd.ms-excel"
        )
