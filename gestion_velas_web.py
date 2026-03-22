import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Velas Candela - Gestión Pro Cloud", layout="wide")

def conectar():
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()
    # Mantenemos tu estructura idéntica
    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT, 
        unidad TEXT, stock_actual REAL DEFAULT 0, stock_minimo REAL DEFAULT 0,
        costo_u REAL DEFAULT 0, precio_v REAL DEFAULT 0, 
        precio_v2 REAL DEFAULT 0, margen1 REAL DEFAULT 100, margen2 REAL DEFAULT 100)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS recetas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, id_final INTEGER, 
        id_insumo INTEGER, cantidad REAL)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, producto TEXT, 
        cantidad REAL, total_venta REAL, metodo_pago TEXT)''')
    
    conn.commit()
    conn.close()

inicializar_db()

st.sidebar.title("🕯️ Velas Candela")
menu = st.sidebar.radio("MENÚ", ["📦 Stock", "🧪 Recetas y Costeo Pro", "🚀 Ventas", "📊 Caja"])

# ---------------------------------------------------------
# 1. STOCK (Búsqueda Case-Insensitive)
# ---------------------------------------------------------
if menu == "📦 Stock":
    st.subheader("Gestión de Inventario")
    conn = conectar()
    f1, f2 = st.columns(2)
    tipo_sel = f1.selectbox("Tipo", ["TODOS", "Insumo", "Final", "Packaging"])
    busq = f2.text_input("Buscar producto...")
    
    query = "SELECT id, nombre, tipo, stock_actual, costo_u, precio_v, precio_v2 FROM productos WHERE 1=1"
    params = []
    if tipo_sel != "TODOS":
        query += " AND UPPER(tipo) = UPPER(?)"; params.append(tipo_sel)
    if busq:
        query += " AND UPPER(nombre) LIKE UPPER(?)"; params.append(f"%{busq}%")
    
    df = pd.read_sql_query(query, conn, params=params)
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# 2. RECETAS Y COSTEO (LÓGICA ORIGINAL 100%)
# ---------------------------------------------------------
elif menu == "🧪 Recetas y Costeo Pro":
    st.subheader("Gestión de Fórmulas y Determinación de Precios")
    conn = conectar()
    
    # Traemos finales e insumos respetando mayúsculas/minúsculas
    finales = pd.read_sql_query("SELECT id, nombre, margen1, margen2 FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    insumos_list = pd.read_sql_query("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'", conn)

    if not finales.empty:
        col_izq, col_der = st.columns([1, 2])
        
        with col_izq:
            v_nom = st.selectbox("Seleccionar Vela para editar/ver receta", finales['nombre'].tolist())
            v_data = finales[finales['nombre'] == v_nom].iloc[0]
            id_final = int(v_data['id'])
            
            with st.form("add_comp"):
                st.write("### Vincular Materia Prima")
                i_sel = st.selectbox("Insumo", insumos_list['nombre'].tolist())
                i_cant = st.number_input("Cantidad (Gr/Un)", min_value=0.0, format="%.2f")
                if st.form_submit_button("Añadir a Composición"):
                    id_ins = int(insumos_list[insumos_list['nombre'] == i_sel]['id'].values[0])
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_final, id_ins, i_cant))
                    conn.commit()
                    st.success("Componente añadido")
                    st.rerun()

        with col_der:
            st.write(f"### Composición de: {v_nom}")
            # Query exacta para recuperar tus datos precargados
            query_receta = f"""
                SELECT r.id, i.nombre as Materia_Prima, r.cantidad as Cantidad, i.costo_u, (r.cantidad * i.costo_u) as Subtotal
                FROM recetas r 
                INNER JOIN productos i ON r.id_insumo = i.id
                WHERE r.id_final = {id_final}
            """
            df_rec = pd.read_sql_query(query_receta, conn)
            
            if not df_rec.empty:
                st.table(df_rec)
                costo_fabb = df_rec['Subtotal'].sum()
                
                # --- CÁLCULO DE PRECIOS SEGÚN TU LÓGICA ---
                st.divider()
                st.write("### 💰 Calculadora de Precios de Venta")
                c1, c2 = st.columns(2)
                m1 = c1.number_input("Margen 1 % (Minorista)", value=float(v_data['margen1']))
                m2 = c2.number_input("Margen 2 % (Mayorista)", value=float(v_data['margen2']))
                
                p1_calc = costo_fabb * (1 + m1/100)
                p2_calc = costo_fabb * (1 + m2/100)
                
                st.metric("COSTO TOTAL MATERIALES", f"$ {costo_fabb:,.2f}")
                c1.metric("PRECIO L1", f"$ {p1_calc:,.2f}")
                c2.metric("PRECIO L2", f"$ {p2_calc:,.2f}")
                
                if st.button("💾 GUARDAR PRECIOS EN STOCK"):
                    conn.execute("UPDATE productos SET precio_v=?, precio_v2=?, margen1=?, margen2=?, costo_u=? WHERE id=?", 
                                (p1_calc, p2_calc, m1, m2, costo_fabb, id_final))
                    conn.commit()
                    st.success("Precios e historial de costos actualizados")

                if st.button("🚀 REGISTRAR PRODUCCIÓN"):
                    cur = conn.cursor()
                    for _, row in df_rec.iterrows():
                        cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (row['Cantidad'], row['Materia_Prima']))
                    cur.execute("UPDATE productos SET stock_actual = stock_actual + 1 WHERE id = ?", (id_final,))
                    conn.commit()
                    st.success("Insumos descontados y producto final sumado")
            else:
                st.info("No hay receta cargada. Seleccioná insumos a la izquierda para empezar.")
    else:
        st.warning("Cargá productos de tipo 'Final' para gestionar sus recetas.")

# ---------------------------------------------------------
# 3. VENTAS (Lista 1 y Lista 2)
# ---------------------------------------------------------
elif menu == "🚀 Ventas":
    st.subheader("Registrar Venta")
    conn = conectar()
    v_df = pd.read_sql_query("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'", conn)
    
    if not v_df.empty:
        with st.form("venta_rapida"):
            v_sel = st.selectbox("Vela", v_df['nombre'].tolist())
            v_cant = st.number_input("Cantidad", min_value=1.0)
            v_lista = st.radio("Lista de Precios", ["L1 (Minorista)", "L2 (Mayorista)"])
            p_sug = v_df[v_df['nombre'] == v_sel]['precio_v' if "1" in v_lista else 'precio_v2'].values[0]
            v_pago = st.number_input("Monto Cobrado $", value=float(p_sug * v_cant))
            
            if st.form_submit_button("Confirmar"):
                cur = conn.cursor()
                cur.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)", 
                           (datetime.now().strftime("%Y-%m-%d %H:%M"), v_sel, v_cant, v_pago))
                cur.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_cant, v_sel))
                conn.commit()
                st.success("Venta procesada")
