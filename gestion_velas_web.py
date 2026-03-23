import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Velas Candela Pro - Cloud", layout="wide")

# ==========================================
# 1. FUNCIONES ORIGINALES
# ==========================================
def safe_float(val):
    try:
        return float(val) if val is not None else 0.0
    except:
        return 0.0

def conectar():
    return sqlite3.connect("gestion_velas.db", check_same_thread=False)

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()
    # Estructura idéntica a tu desarrollo local
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

    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, item_nombre TEXT, 
        cantidad REAL, costo_total REAL, metodo_pago TEXT)''')
    
    # Migración segura de columnas (Tu lógica original)
    columnas = [("precio_v2", "REAL DEFAULT 0"), ("margen1", "REAL DEFAULT 100"), ("margen2", "REAL DEFAULT 100")]
    for col, tipo in columnas:
        try: cursor.execute(f"ALTER TABLE productos ADD COLUMN {col} {tipo}")
        except: pass
        
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Menú Gestión")
menu = st.sidebar.radio("Ir a:", [
    "📦 Inventario y Alta", 
    "🧪 Recetas y Costeo", 
    "💰 Registro Compras", 
    "🚀 Registrar Venta", 
    "📊 Caja y Reportes"
])

# ---------------------------------------------------------
# 1. ALTA Y STOCK (RESOLUCIÓN PUNTO 1)
# ---------------------------------------------------------
if menu == "📦 Inventario y Alta":
    st.subheader("Gestión de Inventario")
    conn = conectar()
    
    with st.expander("➕ DAR DE ALTA NUEVO PRODUCTO / INSUMO"):
        with st.form("alta_p"):
            c1, c2 = st.columns(2)
            n_nom = c1.text_input("Nombre del Item")
            n_tip = c2.selectbox("Tipo", ["Insumo", "Final", "Herramienta", "Packaging"])
            n_uni = c1.selectbox("Unidad", ["Gr", "Ml", "Un", "Kg"])
            n_stk = c2.number_input("Stock Inicial", min_value=0.0)
            n_min = c1.number_input("Stock Mínimo", min_value=0.0)
            n_cst = c2.number_input("Costo Unitario Inicial", min_value=0.0)
            if st.form_submit_button("Guardar en Base de Datos"):
                conn.execute("INSERT INTO productos (nombre, tipo, unidad, stock_actual, stock_minimo, costo_u) VALUES (?,?,?,?,?,?)",
                            (n_nom, n_tip, n_uni, n_stk, n_min, n_cst))
                conn.commit()
                st.success(f"{n_nom} registrado correctamente.")
                st.rerun()

    st.divider()
    df = pd.read_sql_query("SELECT id, nombre, tipo, stock_actual, stock_minimo, costo_u, precio_v, precio_v2 FROM productos", conn)
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# 2. RECETAS Y COSTEO (RESOLUCIÓN PUNTOS 2 Y 3)
# ---------------------------------------------------------
elif menu == "🧪 Recetas y Costeo":
    st.subheader("Determinación de Costos y Precios de Venta")
    conn = conectar()
    
    # Obtenemos datos base usando cursores explícitos para evitar OperationalError
    cur_base = conn.cursor()
    finales = cur_base.execute("SELECT id, nombre, margen1, margen2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    insumos = cur_base.execute("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'").fetchall()

    if finales:
        col_izq, col_der = st.columns([1, 2])
        
        with col_izq:
            v_sel = st.selectbox("Elegir Vela Final", [f[1] for f in finales])
            v_data = [f for f in finales if f[1] == v_sel][0]
            id_v_f = int(v_data[0])
            
            with st.form("add_comp"):
                st.write("### Vincular Materia Prima")
                i_sel = st.selectbox("Insumo", [i[1] for i in insumos]) if insumos else st.error("Sin insumos")
                i_cant = st.number_input("Cantidad", min_value=0.0, format="%.2f")
                if st.form_submit_button("Añadir a Receta"):
                    id_i = [i for i in insumos if i[1] == i_sel][0][0]
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_f, id_i, i_cant))
                    conn.commit(); st.rerun()

        with col_der:
            st.write(f"### Composición de: {v_sel}")
            # QUERY BLINDADA: Sin alias complejos para evitar OperationalError
            sql_receta = """
                SELECT recetas.id, productos.nombre, recetas.cantidad, productos.costo_u, (recetas.cantidad * productos.costo_u) 
                FROM recetas 
                JOIN productos ON recetas.id_insumo = productos.id 
                WHERE recetas.id_final = ?
            """
            cur_r = conn.cursor()
            rows = cur_r.execute(sql_receta, (id_v_f,)).fetchall()
            
            if rows:
                df_rec = pd.DataFrame(rows, columns=["ID", "Insumo", "Cant.", "Costo U", "Subtotal"])
                st.table(df_rec[["Insumo", "Cant.", "Costo U", "Subtotal"]])
                
                costo_base = sum(safe_float(r[4]) for r in rows)
                
                st.divider()
                st.write("### 💰 Calculadora de Rentabilidad")
                modo = st.radio("Método de cálculo:", ["Margen %", "Precio Final $"], horizontal=True)
                c1, c2 = st.columns(2)
                
                if modo == "Margen %":
                    m1 = c1.number_input("Margen Lista 1 %", value=safe_float(v_data[2]))
                    m2 = c2.number_input("Margen Lista 2 %", value=safe_float(v_data[3]))
                    p1 = costo_base * (1 + m1/100)
                    p2 = costo_base * (1 + m2/100)
                else:
                    p1 = c1.number_input("Precio Venta L1 $", value=costo_base * (1 + safe_float(v_data[2])/100))
                    p2 = c2.number_input("Precio Venta L2 $", value=costo_base * (1 + safe_float(v_data[3])/100))
                    m1 = ((p1 / costo_base) - 1) * 100 if costo_base > 0 else 0
                    m2 = ((p2 / costo_base) - 1) * 100 if costo_base > 0 else 0

                st.info(f"Costo Total: ${costo_base:,.2f} | Rentabilidad L1: {m1:.1f}% | L2: {m2:.1f}%")
                
                if st.button("💾 GUARDAR PRECIOS Y MÁRGENES"):
                    conn.execute("UPDATE productos SET precio_v=?, precio_v2=?, margen1=?, margen2=?, costo_u=? WHERE id=?", 
                                (p1, p2, m1, m2, costo_base, id_v_f))
                    conn.commit()
                    st.success("Precios actualizados en Inventario")
            else:
                st.info("Sin receta cargada.")

# ---------------------------------------------------------
# 4. VENTAS EDITABLES
# ---------------------------------------------------------
elif menu == "🚀 Registrar Venta":
    st.subheader("Nueva Venta")
    conn = conectar()
    velas = conn.execute("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    
    with st.form("form_v"):
        c1, c2 = st.columns(2)
        f_v = c1.date_input("Fecha", date.today())
        h_v = c2.time_input("Hora", datetime.now().time())
        v_prod = st.selectbox("Producto", [v[0] for v in velas])
        v_cant = st.number_input("Cantidad", min_value=1.0)
        v_lista = st.radio("Lista", ["L1", "L2"], horizontal=True)
        
        p_ref = [v for v in velas if v[0] == v_prod][0]
        precio_s = safe_float(p_ref[1] if "1" in v_lista else p_ref[2])
        v_monto = st.number_input("Monto Cobrado $ (Editable)", value=float(precio_s * v_cant))
        
        if st.form_submit_button("Confirmar Venta"):
            fecha_str = f"{f_v.strftime('%Y-%m-%d')} {h_v.strftime('%H:%M')}"
            conn.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta) VALUES (?,?,?,?)",
                        (fecha_str, v_prod, v_cant, v_monto))
            conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE nombre = ?", (v_cant, v_prod))
            conn.commit(); st.success("Venta registrada.")

# ---------------------------------------------------------
# 5. CAJA Y EXCEL
# ---------------------------------------------------------
elif menu == "📊 Caja y Reportes":
    st.subheader("Historial de Movimientos")
    conn = conectar()
    df_v = pd.read_sql_query("SELECT fecha, 'VENTA' as Tipo, producto as Detalle, total_venta as Monto FROM historial_ventas", conn)
    df_c = pd.read_sql_query("SELECT fecha, 'COMPRA' as Tipo, item_nombre as Detalle, -costo_total as Monto FROM historial_compras", conn)
    df_caja = pd.concat([df_v, df_c]).sort_values(by="fecha", ascending=False)
    
    if not df_caja.empty:
        st.metric("SALDO NETO", f"$ {df_caja['Monto'].sum():,.2f}")
        st.dataframe(df_caja, use_container_width=True)
        output = io.BytesIO()
        df_caja.to_excel(output, index=False, engine='openpyxl')
        st.download_button("📊 Descargar Excel", output.getvalue(), f"caja_{date.today()}.xlsx")
