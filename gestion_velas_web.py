import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import io

# --- CONFIGURACIÓN ---
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
    
    # Migración de columnas (Tu lógica original)
    for col, tipo in [("precio_v2", "REAL DEFAULT 0"), ("margen1", "REAL DEFAULT 100"), ("margen2", "REAL DEFAULT 100")]:
        try: cursor.execute(f"ALTER TABLE productos ADD COLUMN {col} {tipo}")
        except: pass
    conn.commit()
    conn.close()

inicializar_db()

# --- INTERFAZ ---
st.sidebar.title("🕯️ Menú Gestión")
menu = st.sidebar.radio("Ir a:", ["📦 Inventario", "🧪 Recetas y Costeo", "💰 Compras", "🚀 Ventas", "📊 Caja"])

# ---------------------------------------------------------
# 2. RECETAS Y COSTEO (SOLUCIÓN DEFINITIVA)
# ---------------------------------------------------------
if menu == "🧪 Recetas y Costeo":
    st.subheader("Calculadora de Producción e Ingeniería de Costos")
    conn = conectar()
    
    # Obtenemos productos base usando cursores independientes
    cur_finales = conn.cursor()
    finales = cur_finales.execute("SELECT id, nombre, margen1, margen2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    
    cur_insumos = conn.cursor()
    insumos = cur_insumos.execute("SELECT id, nombre, costo_u FROM productos WHERE UPPER(tipo) = 'INSUMO'").fetchall()

    if finales:
        col_izq, col_der = st.columns([1, 2])
        
        with col_izq:
            v_sel = st.selectbox("Elegir Vela", [f[1] for f in finales])
            v_data = [f for f in finales if f[1] == v_sel][0]
            id_v_f = int(v_data[0])
            
            with st.form("form_receta"):
                st.write("### Vincular Materia Prima")
                i_sel = st.selectbox("Insumo", [i[1] for i in insumos]) if insumos else st.error("Sin insumos")
                i_cant = st.number_input("Cantidad", min_value=0.0, format="%.2f")
                if st.form_submit_button("Añadir a Receta"):
                    id_i = [i for i in insumos if i[1] == i_sel][0][0]
                    conn.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (id_v_f, id_i, i_cant))
                    conn.commit()
                    st.rerun()

        with col_der:
            st.write(f"### Composición y Costeo: {v_sel}")
            
            # ELIMINAMOS EL JOIN PARA EVITAR EL OPERATIONALERROR
            # Paso 1: Buscar componentes en recetas
            cur_r = conn.cursor()
            componentes = cur_r.execute("SELECT id, id_insumo, cantidad FROM recetas WHERE id_final = ?", (id_v_f,)).fetchall()
            
            lista_para_tabla = []
            costo_total_acumulado = 0.0
            
            for comp in componentes:
                id_receta_lin, id_insumo_lin, cantidad_lin = comp
                # Paso 2: Buscar datos del insumo uno por uno (Blindaje total)
                cur_p = conn.cursor()
                p_data = cur_p.execute("SELECT nombre, costo_u FROM productos WHERE id = ?", (id_insumo_lin,)).fetchone()
                
                if p_data:
                    nombre_i = p_data[0]
                    costo_u_i = safe_float(p_data[1])
                    subtotal_i = cantidad_lin * costo_u_i
                    costo_total_acumulado += subtotal_i
                    lista_para_tabla.append([nombre_i, cantidad_lin, costo_u_i, subtotal_i])

            if lista_para_tabla:
                df_rec = pd.DataFrame(lista_para_tabla, columns=["Insumo", "Cant.", "Costo U", "Subtotal"])
                st.table(df_rec)
                
                st.divider()
                st.write("### 💰 Determinación de Precios y Márgenes")
                # Lógica Reversible de tu local
                modo = st.radio("Calcular por:", ["Margen %", "Precio Final $"], horizontal=True)
                cm1, cm2 = st.columns(2)
                
                if modo == "Margen %":
                    m1_in = cm1.number_input("Margen L1 %", value=safe_float(v_data[2]))
                    m2_in = cm2.number_input("Margen L2 %", value=safe_float(v_data[3]))
                    p1 = costo_total_acumulado * (1 + m1_in/100)
                    p2 = costo_total_acumulado * (1 + m2_in/100)
                else:
                    p1 = cm1.number_input("Precio Venta L1 $", value=costo_total_acumulado * (1 + safe_float(v_data[2])/100))
                    p2 = cm2.number_input("Precio Venta L2 $", value=costo_total_acumulado * (1 + safe_float(v_data[3])/100))
                    m1_in = ((p1 / costo_total_acumulado) - 1) * 100 if costo_total_acumulado > 0 else 0
                    m2_in = ((p2 / costo_total_acumulado) - 1) * 100 if costo_total_acumulado > 0 else 0

                st.info(f"Costo Base: ${costo_total_acumulado:,.2f} | Margen L1: {m1_in:.1f}% | L2: {m2_in:.1f}%")
                
                if st.button("💾 GUARDAR PRECIOS EN INVENTARIO"):
                    conn.execute("UPDATE productos SET precio_v=?, precio_v2=?, margen1=?, margen2=?, costo_u=? WHERE id=?", 
                                (p1, p2, m1_in, m2_in, costo_total_acumulado, id_v_f))
                    conn.commit()
                    st.success("Precios actualizados en Stock.")
            else:
                st.info("No hay insumos cargados para esta receta.")

# ---------------------------------------------------------
# FUNCIONALIDADES 3, 4 y 5 (INTEGRADAS Y ESTABLES)
# ---------------------------------------------------------
elif menu == "📦 Inventario":
    st.subheader("Control de Stock")
    conn = conectar()
    df = pd.read_sql_query("SELECT id, nombre, tipo, stock_actual, costo_u, precio_v, precio_v2 FROM productos", conn)
    st.dataframe(df, use_container_width=True, hide_index=True)

elif menu == "💰 Compras":
    st.subheader("Registro de Compras (F4)")
    conn = conectar()
    ins = conn.execute("SELECT nombre FROM productos WHERE UPPER(tipo) = 'INSUMO'").fetchall()
    with st.form("f_c"):
        i_nom = st.selectbox("Insumo", [i[0] for i in ins])
        i_can = st.number_input("Cantidad", min_value=0.01)
        i_tot = st.number_input("Costo Total $", min_value=0.01)
        i_pag = st.selectbox("Pago", ["Efectivo", "Mercado Pago", "Transferencia"])
        if st.form_submit_button("Registrar"):
            conn.execute("UPDATE productos SET stock_actual = stock_actual + ?, costo_u = ? WHERE nombre = ?", (i_can, i_tot/i_can, i_nom))
            conn.execute("INSERT INTO historial_compras (fecha, item_nombre, cantidad, costo_total, metodo_pago) VALUES (?,?,?,?,?)",
                        (datetime.now().strftime("%Y-%m-%d %H:%M"), i_nom, i_can, i_tot, i_pag))
            conn.commit(); st.success("Cargado"); st.rerun()

elif menu == "🚀 Ventas":
    st.subheader("Nueva Venta")
    conn = conectar()
    velas = conn.execute("SELECT nombre, precio_v, precio_v2 FROM productos WHERE UPPER(tipo) = 'FINAL'").fetchall()
    with st.form("f_v"):
        v_prod = st.selectbox("Vela", [v[0] for v in velas])
        v_cant = st.number_input("Cant.", min_value=1.0)
        v_pago = st.selectbox("Pago", ["Efectivo", "Mercado Pago", "Transferencia"])
        if st.form_submit_button("Vender"):
            conn.execute("INSERT INTO historial_ventas (fecha, producto, cantidad, total_venta, metodo_pago) VALUES (?,?,?,?,?)",
                        (datetime.now().strftime("%Y-%m-%d %H:%M"), v_prod, v_cant, 0, v_pago))
            conn.commit(); st.success("Vendido")

elif menu == "📊 Caja":
    st.subheader("Balance y Excel (F5)")
    conn = conectar()
    df_v = pd.read_sql_query("SELECT fecha, 'VENTA' as Tipo, producto as Detalle, total_venta as Monto FROM historial_ventas", conn)
    df_c = pd.read_sql_query("SELECT fecha, 'COMPRA' as Tipo, item_nombre as Detalle, -costo_total as Monto FROM historial_compras", conn)
    df_caja = pd.concat([df_v, df_c]).sort_values(by="fecha", ascending=False)
    st.dataframe(df_caja, use_container_width=True)
    output = io.BytesIO()
    df_caja.to_excel(output, index=False, engine='openpyxl')
    st.download_button("📊 Excel", output.getvalue(), "caja.xlsx")
