import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ==========================================
# 1. BASE DE DATOS Y APOYO (FUERA DE LA CLASE)
# ==========================================
def safe_float(val):
    try:
        return float(val) if val is not None else 0.0
    except:
        return 0.0

def inicializar_db():
    conn = sqlite3.connect("gestion_velas.db")
    cursor = conn.cursor()
    
    # Crear tabla base si no existe
    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT, 
        unidad TEXT, stock_actual REAL DEFAULT 0, stock_minimo REAL DEFAULT 0,
        costo_u REAL DEFAULT 0, precio_v REAL DEFAULT 0)''')
    
    # MIGRACIÓN SEGURA: Agregar columnas nuevas una por una si no existen (No borra datos)
    columnas_nuevas = [
        ("precio_v2", "REAL DEFAULT 0"),
        ("margen1", "REAL DEFAULT 100"),
        ("margen2", "REAL DEFAULT 100")
    ]
    
    for nombre_col, tipo_col in columnas_nuevas:
        try:
            cursor.execute(f"ALTER TABLE productos ADD COLUMN {nombre_col} {tipo_col}")
        except sqlite3.OperationalError:
            pass # Si ya existe la columna, ignora el error

    # Resto de tablas
    cursor.execute('''CREATE TABLE IF NOT EXISTS recetas (
        id_final INTEGER, id_insumo INTEGER, cantidad REAL,
        FOREIGN KEY(id_final) REFERENCES productos(id), FOREIGN KEY(id_insumo) REFERENCES productos(id))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, producto TEXT, cliente TEXT, cantidad REAL, 
        costo_total REAL, total_venta REAL, fecha DATE, metodo_pago TEXT DEFAULT 'Efectivo')''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT, item_nombre TEXT, 
        cantidad REAL, costo_total REAL, fecha DATE, metodo_pago TEXT DEFAULT 'Efectivo')''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, telefono TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS caja (
        id INTEGER PRIMARY KEY, saldo_efectivo REAL DEFAULT 0, saldo_banco REAL DEFAULT 0, saldo_tarjeta REAL DEFAULT 0)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_fabricacion (
       id INTEGER PRIMARY KEY AUTOINCREMENT, producto TEXT, cantidad REAL, fecha DATE)''')        

    cursor.execute("SELECT COUNT(*) FROM caja")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO caja (id, saldo_efectivo, saldo_banco, saldo_tarjeta) VALUES (1, 0, 0, 0)")
    
    conn.commit()
    conn.close()

# ==========================================
# 2. CLASE PRINCIPAL
# ==========================================
class SistemaVelas:
    def __init__(self, root):
        self.root = root
        self.root.title("GESTIÓN VELAS - DOBLE LISTA DE PRECIOS")
        self.root.geometry("1200x850")
        self.root.configure(bg="#f4f4f9")

        # --- 1. TÍTULO Y BOTONES SUPERIORES ---
        tk.Label(root, text="CONTROL DE PRODUCCIÓN Y DOBLE LISTA", font=("Arial", 22, "bold"), 
                 bg="#f4f4f9", fg="#2c3e50").pack(pady=10)

        btn_frame = tk.Frame(root, bg="#f4f4f9")
        btn_frame.pack(pady=10)

        botones = [
            ("📦 ITEMS", self.abrir_productos, "#bdc3c7"),
            ("📜 RECETAS", self.abrir_recetas, "#bdc3c7"),
            ("⚙️ FABRICAR", self.abrir_fabricacion, "#f39c12"),
            ("💰 COSTOS", self.abrir_calculadora_costos, "#3498db"),
            ("🛒 VENTAS", self.abrir_ventas, "#2ecc71"),
            ("🧾 COMPRAS", self.abrir_compras, "#1abc9c"),
            ("💵 CAJA", self.abrir_caja, "#f1c40f"),
            ("👥 CLIENTES", self.abrir_clientes, "#bdc3c7"),
            ("📊 GRÁFICOS", self.mostrar_graficos, "#9b59b6"),            
            ("🔍 AUDITORÍA", self.abrir_auditoria, "#34495e"),
            ("🔧 AJUSTES", self.abrir_ajustes, "#95a5a6"),
            ("❌ CERRAR", self.root.destroy, "#e74c3c")
        ]

        for i, (texto, comando, color) in enumerate(botones):
            tk.Button(btn_frame, text=texto, font=("Arial", 9, "bold"), width=11, height=2, 
                      bg=color, command=comando).grid(row=0, column=i, padx=2)

        # --- 2. IMPORTANTE: DEFINIR LA TABLA (TREEVIEW) ANTES QUE LOS FILTROS ---
        self.columnas_info = [
            ("ID", 40, "center"), ("Nombre", 220, "w"), ("Tipo", 90, "w"),
            ("Stock", 80, "e"), ("Costo", 100, "e"), ("Lista 1", 100, "e"),
            ("% L1", 70, "e"), ("Lista 2", 100, "e"), ("% L2", 70, "e")
        ]
        
        columnas_ids = [c[0] for c in self.columnas_info]
        self.tree = ttk.Treeview(root, columns=columnas_ids, show='headings')
        
        for col_name, ancho, alineacion in self.columnas_info:
            self.tree.heading(col_name, text=col_name)
            self.tree.column(col_name, width=ancho, anchor=alineacion)

        # --- 3. BARRA DE HERRAMIENTAS (FILTROS) ARRIBA DE LA TABLA ---
        f_herramientas = tk.Frame(root, bg="#f4f4f9", pady=10)
        f_herramientas.pack(fill="x", padx=30)
        
        tk.Label(f_herramientas, text="🔍 Buscar:", bg="#f4f4f9", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        self.ent_busqueda = tk.Entry(f_herramientas, width=25)
        self.ent_busqueda.pack(side=tk.LEFT, padx=10)
        self.ent_busqueda.bind("<KeyRelease>", lambda e: self.actualizar_tabla())

        self.cmb_tipo_f = ttk.Combobox(f_herramientas, values=["Todos", "insumo", "final", "herramienta"], state="readonly", width=12)
        self.cmb_tipo_f.set("Todos")
        self.cmb_tipo_f.pack(side=tk.LEFT, padx=5)
        self.cmb_tipo_f.bind("<<ComboboxSelected>>", lambda e: self.actualizar_tabla())

        self.cmb_stock_f = ttk.Combobox(f_herramientas, values=["Todos", "Con Stock", "Bajo Stock"], state="readonly", width=12)
        self.cmb_stock_f.set("Todos")
        self.cmb_stock_f.pack(side=tk.LEFT, padx=5)
        self.cmb_stock_f.bind("<<ComboboxSelected>>", lambda e: self.actualizar_tabla())

        self.btn_exportar_lista = tk.Button(f_herramientas, text="📊 EXPORTAR EXCEL", 
                                          bg="#1f3a93", fg="black", font=("Arial", 9, "bold"),
                                          command=self.exportar_lista_principal)
        self.btn_exportar_lista.pack(side=tk.RIGHT, padx=5)

        # --- 4. EMPAQUETAR LA TABLA Y LEYENDAS ---
        self.tree.pack(padx=30, fill="both", expand=True, pady=10)
        self.tree.bind("<Double-1>", self.on_double_click)

        f_leyenda = tk.Frame(root, bg="#f4f4f9")
        f_leyenda.pack(fill="x", padx=30, pady=5)
        referencias = [
            ("● Bajo Stock", "red"), ("● Rentable (+200%)", "#27ae60"),
            ("● Medio (100-200%)", "#d35400"), ("● Alerta (-100%)", "#1f3a93")
        ]
        for texto, color in referencias:
            tk.Label(f_leyenda, text=texto, fg=color, bg="#f4f4f9", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=15)

        # 5. CARGAR DATOS
        self.actualizar_tabla()

 
    def actualizar_tabla(self):
        for i in self.tree.get_children(): 
            self.tree.delete(i)
            
        conn = sqlite3.connect("gestion_velas.db")
        busq = self.ent_busqueda.get().lower()
        filtro_tipo = self.cmb_tipo_f.get()
        filtro_stock = self.cmb_stock_f.get()
        
        query = "SELECT id, nombre, tipo, stock_actual, costo_u, precio_v, precio_v2, stock_minimo FROM productos"
        
        for f in conn.execute(query).fetchall():
            id_p, nombre, tipo, stk, costo, p1, p2, stk_min = f
            
            # Filtros base
            if busq not in nombre.lower(): continue
            if filtro_tipo != "Todos" and tipo != filtro_tipo: continue
            if filtro_stock == "Con Stock" and stk <= 0: continue
            if filtro_stock == "Bajo Stock" and stk > stk_min: continue

            # --- CÁLCULO DE MÁRGENES ---
            m1 = ((p1 - costo) / costo * 100) if costo > 0 else 0
            m2 = ((p2 - costo) / costo * 100) if costo > 0 else 0

            # --- FORMATEO DE VALORES ---
            res_formateado = [
                id_p, nombre.upper(), tipo.capitalize(),
                f"{stk:.2f}", f"${costo:,.2f}", f"${p1:,.2f}", f"{m1:.1f}%",
                f"${p2:,.2f}", f"{m2:.1f}%"
            ]
            
            # --- LÓGICA DE COLORES (TAGS) ---
            # Determinamos el tag basado en el margen de la Lista 1 (puedes cambiarlo al que prefieras)
            if stk <= stk_min:
                color_tag = 'bajo_stock'
            elif m1 >= 200:
                color_tag = 'rentable'
            elif m1 >= 100:
                color_tag = 'medio'
            else:
                color_tag = 'alerta'

            self.tree.insert("", "end", values=res_formateado, tags=(color_tag,))
        
            # Color rojo si el stock es bajo
            #tag = 'bajo' if stk <= stk_min else 'normal'
            #self.tree.insert("", "end", values=res_formateado, tags=(tag,))

        # --- CONFIGURACIÓN DE LOS COLORES ---
        self.tree.tag_configure('bajo_stock', foreground='red', font=('Arial', 9, 'bold'))
        self.tree.tag_configure('rentable', foreground='#27ae60') # Verde
        self.tree.tag_configure('medio', foreground='#d35400')    # Naranja
        self.tree.tag_configure('alerta', foreground='#1f3a93')   # Azul
        
        # --- FIN DEL BUCLE ---
        self.tree.tag_configure('bajo', foreground='red')
        conn.close()

    def exportar_lista_principal(self):
        datos = []
        for item_id in self.tree.get_children():
            datos.append(self.tree.item(item_id)['values'])
        
        if not datos:
            messagebox.showwarning("Aviso", "No hay datos para exportar")
            return

        columnas = [col[0] for col in self.columnas_info]
        archivo = filedialog.asksaveasfilename(defaultextension=".xlsx", 
                                             initialfile=f"Lista_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
        if archivo:
            try:
                df = pd.DataFrame(datos, columns=columnas)
                df.to_excel(archivo, index=False)
                messagebox.showinfo("Éxito", "Excel generado")
            except Exception as e:
                messagebox.showerror("Error", str(e))
        
    def abrir_recetas(self):
        v = tk.Toplevel(self.root); v.title("Recetas"); v.geometry("700x650")
        conn = sqlite3.connect("gestion_velas.db")
        velas = [f"{x[0]}-{x[1]}" for x in conn.execute("SELECT id, nombre FROM productos WHERE tipo='final'").fetchall()]
        insumos = [f"{x[0]}-{x[1]}" for x in conn.execute("SELECT id, nombre FROM productos WHERE tipo='insumo'").fetchall()]
        
        f_in = tk.Frame(v, pady=10); f_in.pack(fill="x", padx=10)
        tk.Label(f_in, text="Vela Final:").grid(row=0, column=0); cv = ttk.Combobox(f_in, values=velas, width=30); cv.grid(row=0, column=1)
        tk.Label(f_in, text="Insumo:").grid(row=1, column=0); ci = ttk.Combobox(f_in, values=insumos, width=30); ci.grid(row=1, column=1)
        tk.Label(f_in, text="Cant:").grid(row=2, column=0); eq = tk.Entry(f_in, width=10); eq.grid(row=2, column=1)

        tr = ttk.Treeview(v, columns=("ID", "Insumo", "Cantidad"), show="headings")
        for c in tr["columns"]: tr.heading(c, text=c); tr.column(c, anchor="center")
        tr.pack(fill="both", expand=True, padx=20)

        def cargar_receta_detalle(e=None):
            for i in tr.get_children(): tr.delete(i)
            if not cv.get(): return
            id_f = cv.get().split("-")[0]
            c_int = sqlite3.connect("gestion_velas.db")
            for r in c_int.execute("SELECT r.id_insumo, p.nombre, r.cantidad FROM recetas r JOIN productos p ON r.id_insumo=p.id WHERE r.id_final=?", (id_f,)).fetchall():
                tr.insert("", "end", values=r)
            c_int.close()
        
        cv.bind("<<ComboboxSelected>>", cargar_receta_detalle)

        def guardar():
            if not cv.get() or not ci.get(): return
            c_int = sqlite3.connect("gestion_velas.db")
            c_int.execute("INSERT INTO recetas (id_final, id_insumo, cantidad) VALUES (?,?,?)", (cv.get().split("-")[0], ci.get().split("-")[0], float(eq.get())))
            c_int.commit(); c_int.close(); cargar_receta_detalle()

        def borrar():
            sel = tr.selection()
            if sel and cv.get():
                id_i = tr.item(sel[0])['values'][0]
                c_int = sqlite3.connect("gestion_velas.db")
                c_int.execute("DELETE FROM recetas WHERE id_final=? AND id_insumo=?", (cv.get().split("-")[0], id_i))
                c_int.commit(); c_int.close(); cargar_receta_detalle()

        tk.Button(f_in, text="➕ Añadir", bg="#2ecc71", command=guardar).grid(row=3, column=0, pady=10)
        tk.Button(f_in, text="🗑️ Borrar", bg="#e74c3c", command=borrar).grid(row=3, column=1)
        tk.Button(v, text="Cerrar", command=lambda: [conn.close(), v.destroy()], bg="#bdc3c7").pack(pady=10)
        conn.close()

    def abrir_calculadora_costos(self):
        v = tk.Toplevel(self.root); v.title("Calculadora de Costos Pro"); v.geometry("500x600")
        conn = sqlite3.connect("gestion_velas.db")
        velas = [f"{x[0]}-{x[1]}" for x in conn.execute("SELECT id, nombre FROM productos WHERE tipo='final'").fetchall()]
        
        tk.Label(v, text="Seleccione Vela:").pack(pady=5)
        cv = ttk.Combobox(v, values=velas); cv.pack()
        
        f1 = tk.LabelFrame(v, text=" Lista de Precios 1 ", pady=10, padx=10)
        f1.pack(fill="x", padx=20, pady=5)
        tk.Label(f1, text="Margen %:").grid(row=0, column=0)
        eg1 = tk.Entry(f1, width=10); eg1.insert(0, "100"); eg1.grid(row=0, column=1)
        tk.Label(f1, text="Precio Final:").grid(row=1, column=0)
        ep1 = tk.Entry(f1, width=10); ep1.grid(row=1, column=1)

        f2 = tk.LabelFrame(v, text=" Lista de Precios 2 ", pady=10, padx=10)
        f2.pack(fill="x", padx=20, pady=5)
        tk.Label(f2, text="Margen %:").grid(row=0, column=0)
        eg2 = tk.Entry(f2, width=10); eg2.insert(0, "120"); eg2.grid(row=0, column=1)
        tk.Label(f2, text="Precio Final:").grid(row=1, column=0)
        ep2 = tk.Entry(f2, width=10); ep2.grid(row=1, column=1)
        
        lc = tk.Label(v, text="Costo Base: $0.00", font=("Arial", 12, "bold")); lc.pack(pady=10)

        def obtener_costo():
            if not cv.get(): return 0
            id_v = cv.get().split("-")[0]
            c_int = sqlite3.connect("gestion_velas.db")
            costo = c_int.execute("SELECT SUM(r.cantidad * p.costo_u) FROM recetas r JOIN productos p ON r.id_insumo=p.id WHERE r.id_final=?", (id_v,)).fetchone()[0] or 0
            c_int.close()
            lc.config(text=f"Costo Base: ${costo:,.2f}")
            return costo

        def calcular_desde_margen():
            costo = obtener_costo()
            if costo == 0: return
            p1 = costo * (1 + safe_float(eg1.get())/100)
            p2 = costo * (1 + safe_float(eg2.get())/100)
            ep1.delete(0, tk.END); ep1.insert(0, f"{p1:.2f}")
            ep2.delete(0, tk.END); ep2.insert(0, f"{p2:.2f}")

        def calcular_desde_precio():
            costo = obtener_costo()
            if costo == 0: return
            m1 = ((safe_float(ep1.get()) / costo) - 1) * 100
            m2 = ((safe_float(ep2.get()) / costo) - 1) * 100
            eg1.delete(0, tk.END); eg1.insert(0, f"{m1:.2f}")
            eg2.delete(0, tk.END); eg2.insert(0, f"{m2:.2f}")

        def grabar():
            costo = obtener_costo()
            if not cv.get(): return
            id_v = cv.get().split("-")[0]
            c_int = sqlite3.connect("gestion_velas.db")
            c_int.execute("UPDATE productos SET costo_u=?, precio_v=?, precio_v2=?, margen1=?, margen2=? WHERE id=?", 
                         (costo, safe_float(ep1.get()), safe_float(ep2.get()), safe_float(eg1.get()), safe_float(eg2.get()), id_v))
            c_int.commit(); c_int.close(); self.actualizar_tabla(); messagebox.showinfo("Éxito", "Listas actualizadas")

        tk.Button(v, text="Calcular Precios (desde %)", command=calcular_desde_margen, bg="#bdc3c7").pack(pady=2)
        tk.Button(v, text="Calcular % (desde Precio)", command=calcular_desde_precio, bg="#bdc3c7").pack(pady=2)
        tk.Button(v, text="💾 GRABAR AMBAS LISTAS", bg="#2ecc71", command=grabar).pack(pady=10)
        tk.Button(v, text="Cerrar", command=lambda: [conn.close(), v.destroy()], bg="#bdc3c7").pack(pady=20)
        conn.close()

    def abrir_auditoria(self):
        v = tk.Toplevel(self.root)
        v.title("Auditoría de Gestión y Análisis de Rentabilidad")
        v.geometry("1150x850")

        # --- 1. PANEL SUPERIOR ---
        f_filtros = tk.Frame(v, pady=10)
        f_filtros.pack(fill="x")
        
        tk.Label(f_filtros, text="Fecha Ref (YYYY-MM-DD):").pack(side=tk.LEFT, padx=5)
        ef = tk.Entry(f_filtros, width=15)
        ef.insert(0, datetime.now().strftime('%Y-%m-%d'))
        ef.pack(side=tk.LEFT, padx=10)

        l_total_superior = tk.Label(f_filtros, text="", font=("Arial", 12, "bold"), fg="#16a085")
        l_total_superior.pack(side=tk.RIGHT, padx=20)
        
        # --- PESTAÑAS (Agregamos f7 para el Gráfico de Producción) ---
        nb = ttk.Notebook(v)
        nb.pack(fill="both", expand=True)
        
        f1, f2, f6, f3, f4, f5, f7 = tk.Frame(nb), tk.Frame(nb), tk.Frame(nb), tk.Frame(nb), tk.Frame(nb), tk.Frame(nb), tk.Frame(nb)
        nb.add(f1, text=" Compras ")
        nb.add(f2, text=" Ventas ")
        nb.add(f6, text=" ⚙️ Fabricación ")
        nb.add(f3, text=" Rentabilidad ")
        nb.add(f4, text=" Valuación Stock ")
        nb.add(f5, text=" 📊 Balance General ")
        nb.add(f7, text=" 📊 Producción por Item ") # Nueva pestaña de gráfico

        # --- 2. CONFIGURACIÓN DE TABLAS (Treeviews) ---
        # (Tablas de Compras, Ventas, Fabricación, Rentabilidad y Stock...)
        # Omito el código repetitivo de creación de t1, t2, t3, t4, t6 para ir a la lógica del gráfico
        t1 = ttk.Treeview(f1, columns=(1,2,3,4,5), show="headings")
        for i, (h, a) in enumerate([("Fecha","w"),("Item","w"),("Cant.","e"),("Total","e"),("Metodo","w")], 1):
            t1.heading(i, text=h); t1.column(i, anchor=a)
        t1.pack(fill="both", expand=True, padx=5, pady=5)

        t2 = ttk.Treeview(f2, columns=(1,2,3,4,5), show="headings")
        for i, (h, a) in enumerate([("Fecha","w"),("Producto","w"),("Cant.","e"),("Total","e"),("Metodo","w")], 1):
            t2.heading(i, text=h); t2.column(i, anchor=a)
        t2.pack(fill="both", expand=True, padx=5, pady=5)

        t6 = ttk.Treeview(f6, columns=(1,2,3), show="headings")
        for i, (h, a) in enumerate([("Fecha","w"),("Producto Final","w"),("Cantidad","e")], 1):
            t6.heading(i, text=h); t6.column(i, anchor=a)
        t6.pack(fill="both", expand=True, padx=5, pady=5)

        # Definición de columnas para Rentabilidad Proyectada
        # Definición de columnas extendida para comparar Lista 1 y Lista 2
        # (9 columnas en total)
        t3 = ttk.Treeview(f3, columns=(1,2,3,4,5,6,7,8,9), show="headings")
        columnas_rent = [
            ("Producto", 140), ("Stock", 60), ("Costo U.", 80), 
            ("Venta L1", 80), ("% L1", 60), ("Proy. L1", 100),
            ("Venta L2", 80), ("% L2", 60), ("Proy. L2", 100)
        ]
        for i, (h, ancho) in enumerate(columnas_rent, 1):
            t3.heading(i, text=h)
            t3.column(i, width=ancho, anchor="center" if i != 1 else "w")
        t3.pack(fill="both", expand=True, padx=5, pady=5)

        t4 = ttk.Treeview(f4, columns=(1,2,3,4,5), show="headings")
        for i, (h, a) in enumerate([("Nombre","w"),("Stock","e"),("Costo T.","e"),("Valor L1","e"),("Valor L2","e")], 1):
            t4.heading(i, text=h); t4.column(i, anchor=a)
        t4.pack(fill="both", expand=True, padx=5, pady=5)

        l_resumen = tk.Label(v, text="", font=("Arial", 11, "bold"), fg="#2c3e50", pady=10)
        l_resumen.pack()

        # --- 3. LÓGICA DE CARGA Y GRÁFICOS ---
        def cargar_datos(modo="todo"):
            plt.close('all') 
            for t in [t1, t2, t3, t4, t6]:
                for item in t.get_children(): t.delete(item)
            
            conn = sqlite3.connect("gestion_velas.db")
            fecha_ref = ef.get()
            cond = ""
            if modo == "dia": cond = f" WHERE fecha='{fecha_ref}'"
            elif modo == "mes": cond = f" WHERE fecha LIKE '{fecha_ref[:7]}%'"

            total_compras = total_ventas = ganancia_total = total_fab = 0
            
            # --- CARGA COMPRAS ---
            for r in conn.execute(f"SELECT fecha, item_nombre, cantidad, costo_total, metodo_pago FROM historial_compras {cond}").fetchall():
                total_compras += r[3]
                t1.insert("", "end", values=(r[0], r[1], f"{r[2]:.2f}", f"${r[3]:,.2f}", r[4]))
            
            # --- CARGA VENTAS ---
            for r in conn.execute(f"SELECT fecha, producto, cantidad, total_venta, metodo_pago, costo_total FROM historial_ventas {cond}").fetchall():
                total_ventas += r[3]
    
                # Blindaje contra valores None (Nulos)
                venta_valor = r[3] if r[3] is not None else 0.0
                costo_valor = r[5] if r[5] is not None else 0.0
    
                ganancia_total += (venta_valor - costo_valor)
    
                t2.insert("", "end", values=(r[0], r[1], f"{r[2]:.2f}", f"${r[3]:,.2f}", r[4]))
                
            # --- CARGA RENTABILIDAD (Tabla t3) ---
            # Aquí calculamos el margen real de cada producto basado en su costo actual
            total_proy_l1 = 0
            total_proy_l2 = 0
            
            # Traemos todos los datos necesarios de la tabla productos
            query_rent = "SELECT nombre, costo_u, precio_v, precio_v2, stock_actual FROM productos WHERE tipo='final'"
            for r in conn.execute(query_rent).fetchall():
                nom, costo, p1, p2, stk = r
                
                # Cálculos Lista 1
                m1_pct = ((p1 - costo) / costo * 100) if costo > 0 else 0
                ganancia_u1 = p1 - costo
                proy_l1 = ganancia_u1 * stk
                
                # Cálculos Lista 2
                m2_pct = ((p2 - costo) / costo * 100) if costo > 0 else 0
                ganancia_u2 = p2 - costo
                proy_l2 = ganancia_u2 * stk

                # Acumuladores para el resumen
                total_proy_l1 += proy_l1
                total_proy_l2 += proy_l2

                # Insertar fila con comparación
                t3.insert("", "end", values=(
                    nom.upper(),
                    f"{stk:.1f}",
                    f"${costo:,.2f}",
                    f"${p1:,.2f}",
                    f"{m1_pct:.0f}%",
                    f"${proy_l1:,.2f}",
                    f"${p2:,.2f}",
                    f"{m2_pct:.0f}%",
                    f"${proy_l2:,.2f}"
                ))
            
            # Actualizar etiqueta superior con la comparativa total si la pestaña está activa
            if nb.index(nb.select()) == 3:
                texto_resumen = f"Ganancia Proyectada en Stock -> Lista 1: ${total_proy_l1:,.2f} | Lista 2: ${total_proy_l2:,.2f}"
                l_total_superior.config(text=texto_resumen, fg="#2c3e50")

            # --- CARGA VALUACIÓN DE STOCK (Tabla t4) ---
            total_inventario_costo = 0
            for r in conn.execute("SELECT nombre, stock_actual, costo_u, precio_v, precio_v2 FROM productos WHERE stock_actual > 0").fetchall():
                nom, stk, costo, p1, p2 = r
                v_costo = stk * costo
                v_l1 = stk * p1
                v_l2 = stk * p2
                total_inventario_costo += v_costo
                
                t4.insert("", "end", values=(
                    nom.upper(), 
                    f"{stk:.2f}", 
                    f"${v_costo:,.2f}", 
                    f"${v_l1:,.2f}", 
                    f"${v_l2:,.2f}"
                ))
            
            if nb.index(nb.select()) == 4:
                l_total_superior.config(text=f"Capital Total Invertido en Stock: ${total_inventario_costo:,.2f}", fg="#16a085")            # --- CARGA FABRICACIÓN ---
            dict_fab = {}
            try:
                for r in conn.execute(f"SELECT fecha, producto, cantidad FROM historial_fabricacion {cond}").fetchall():
                    total_fab += r[2]
                    t6.insert("", "end", values=(r[0], r[1], f"{r[2]:.2f}"))
                    dict_fab[r[1]] = dict_fab.get(r[1], 0) + r[2]
            except: pass

            # --- GENERACIÓN DE GRÁFICO 1: BALANCE ---
            for w in f5.winfo_children(): w.destroy()
            fig1, ax1 = plt.subplots(figsize=(5, 4))
            ax1.bar(['Compras', 'Ventas', 'Ganancia'], [total_compras, total_ventas, ganancia_total], color=['#e74c3c', '#2ecc71', '#3498db'])
            ax1.set_title(f"Balance Financiero ({modo.upper()})")
            FigureCanvasTkAgg(fig1, master=f5).get_tk_widget().pack(fill="both", expand=True)

            # --- GENERACIÓN DE GRÁFICO 2: RANKING PRODUCCIÓN ---
            for w in f7.winfo_children(): w.destroy()
            if dict_fab:
                fig2, ax2 = plt.subplots(figsize=(5, 4))
                productos = list(dict_fab.keys())
                cantidades = list(dict_fab.values())
                ax2.barh(productos, cantidades, color='#f39c12')
                ax2.set_title(f"Unidades Fabricadas por Producto ({modo.upper()})")
                ax2.set_xlabel("Unidades")
                plt.tight_layout()
                FigureCanvasTkAgg(fig2, master=f7).get_tk_widget().pack(fill="both", expand=True)
            else:
                tk.Label(f7, text="No hay datos de fabricación para este periodo", font=("Arial", 12)).pack(pady=50)

            # Actualizar etiquetas...
            pestana = nb.index(nb.select())
            if pestana == 0: l_total_superior.config(text=f"Total Compras: ${total_compras:,.2f}", fg="#c0392b")
            elif pestana == 1: l_total_superior.config(text=f"Total Ventas: ${total_ventas:,.2f}", fg="#27ae60")
            elif pestana == 2: l_total_superior.config(text=f"Fabricación Total: {total_fab:.2f} uts", fg="#f39c12")
            
            conn.close()

        # Vinculamos el cambio de pestaña para refrescar totales
        nb.bind("<<NotebookTabChanged>>", lambda e: cargar_datos(modo="todo"))

        # --- BOTONES DE ACCIÓN Y EXPORTAR ---
        f_botones_filtro = tk.Frame(f_filtros)
        f_botones_filtro.pack(side=tk.LEFT, padx=20)
        for t, m in [("Día","dia"), ("Mes","mes"), ("Todo","todo")]:
            tk.Button(f_botones_filtro, text=t, command=lambda mod=m: cargar_datos(mod), width=8).pack(side=tk.LEFT, padx=2)

        f_pie = tk.Frame(v, pady=10)
        f_pie.pack(fill="x")
        
        tk.Button(f_pie, text="📊 EXPORTAR AUDITORÍA", bg="#27ae60", font=("Arial",10,"bold"), command=lambda: self.exportar_auditoria(), width=22).pack(side=tk.LEFT, padx=20)
        tk.Button(f_pie, text="❌ CERRAR VENTANA", bg="#e74c3c", font=("Arial",10,"bold"), command=v.destroy, width=20).pack(side=tk.RIGHT, padx=20)

        cargar_datos("todo")

    def exportar_auditoria(self):
        # Preguntar dónde guardar el archivo
        archivo = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile=f"Auditoria_Completa_{datetime.now().strftime('%Y%m%d')}.xlsx"
        )
        
        if not archivo:
            return

        try:
            conn = sqlite3.connect("gestion_velas.db")
            
            # 1. Obtener datos de Compras
            df_compras = pd.read_sql_query("SELECT * FROM historial_compras ORDER BY fecha DESC", conn)
            
            # 2. Obtener datos de Ventas
            df_ventas = pd.read_sql_query("SELECT * FROM historial_ventas ORDER BY fecha DESC", conn)
            
            # 3. Obtener datos de Fabricación
            df_fab = pd.read_sql_query("SELECT * FROM historial_fabricacion ORDER BY fecha DESC", conn)
            
            # 4. Obtener Rentabilidad Actual e Inventario
            df_inventario = pd.read_sql_query("""
                SELECT nombre, tipo, stock_actual, costo_u, precio_v, precio_v2, 
                (precio_v - costo_u) as ganancia_u1,
                (precio_v2 - costo_u) as ganancia_u2
                FROM productos
            """, conn)

            # Escribir todas las pestañas en el mismo archivo Excel
            with pd.ExcelWriter(archivo, engine='xlsxwriter') as writer:
                df_compras.to_excel(writer, sheet_name='Historial Compras', index=False)
                df_ventas.to_excel(writer, sheet_name='Historial Ventas', index=False)
                df_fab.to_excel(writer, sheet_name='Historial Fabricación', index=False)
                df_inventario.to_excel(writer, sheet_name='Estado Inventario', index=False)

            conn.close()
            messagebox.showinfo("Éxito", "Auditoría exportada correctamente en varias pestañas.")
            
        except Exception as e:
            messagebox.showerror("Error al exportar", f"Hubo un problema al generar el Excel: {str(e)}")
        
    def abrir_productos(self):
        v = tk.Toplevel(self.root)
        v.title("Nuevo Item")
        v.geometry("300x250") # Agregamos tamaño para que no se vea comprimido
        
        tk.Label(v, text="Nombre:").pack(pady=5)
        en = tk.Entry(v)
        en.pack(pady=5)
        
        tk.Label(v, text="Tipo:").pack(pady=5)
        ct = ttk.Combobox(v, values=["insumo", "final", "herramienta"], state="readonly")
        ct.pack(pady=5)
        
        def s():
            # Validación simple para no guardar items vacíos
            if not en.get() or not ct.get():
                messagebox.showwarning("Atención", "Complete nombre y tipo")
                return
            
            c = sqlite3.connect("gestion_velas.db")
            # Agregamos los campos de margen por defecto para que no de error en las listas nuevas
            c.execute("INSERT INTO productos (nombre, tipo, margen1, margen2) VALUES (?,?, 100, 100)", 
                      (en.get(), ct.get()))
            c.commit()
            c.close()
            self.actualizar_tabla()
            v.destroy()
        
        # Botones separados correctamente
        tk.Button(v, text="💾 Guardar", command=s, bg="#2ecc71", fg="black").pack(pady=10)
        tk.Button(v, text="❌ Cerrar", command=v.destroy, bg="#bdc3c7", fg="black").pack()
 
    def abrir_fabricacion(self):
        v = tk.Toplevel(self.root)
        v.title("Fabricación de Velas")
        v.geometry("400x400")
        
        conn = sqlite3.connect("gestion_velas.db")
        velas = [f"{x[0]}-{x[1]}" for x in conn.execute("SELECT id, nombre FROM productos WHERE tipo='final'").fetchall()]
        conn.close()

        tk.Label(v, text="Vela a Fabricar:", font=("Arial", 10, "bold")).pack(pady=10)
        cv = ttk.Combobox(v, values=velas, state="readonly", width=35)
        cv.pack(pady=5)

        tk.Label(v, text="Cantidad de unidades:", font=("Arial", 10)).pack(pady=5)
        eq = tk.Entry(v, justify="center")
        eq.pack(pady=5)

        def fab():
            if not cv.get() or not eq.get():
                messagebox.showwarning("Atención", "Seleccione una vela y cantidad")
                return
            
            try:
                # 1. Preparar datos
                id_v = cv.get().split("-")[0]
                nombre_v = cv.get().split("-")[1] # Extraemos el nombre para el historial
                cant_a_fabricar = float(eq.get())
                fecha_hoy = datetime.now().strftime('%Y-%m-%d')
                
                c_int = sqlite3.connect("gestion_velas.db")
                
                # 2. Buscar la receta
                receta = c_int.execute("SELECT id_insumo, cantidad FROM recetas WHERE id_final=?", (id_v,)).fetchall()
                
                if not receta:
                    messagebox.showwarning("Sin Receta", "Esta vela no tiene insumos asignados.")
                    c_int.close()
                    return

                # 3. Verificar Stock de Insumos
                for id_insumo, cant_necesaria in receta:
                    res = c_int.execute("SELECT stock_actual, nombre FROM productos WHERE id=?", (id_insumo,)).fetchone()
                    if res:
                        stk_actual, nom_insumo = res
                        total_necesario = cant_necesaria * cant_a_fabricar
                        if stk_actual < total_necesario:
                            messagebox.showerror("Falta Stock", f"No hay suficiente {nom_insumo}.\nNecesitas: {total_necesario}\nTienes: {stk_actual}")
                            c_int.close()
                            return

                # 4. Procesar Fabricación (Descontar Insumos y Sumar Producto)
                for id_insumo, cant_necesaria in receta:
                    c_int.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE id = ?", 
                                 (cant_necesaria * cant_a_fabricar, id_insumo))
                
                c_int.execute("UPDATE productos SET stock_actual = stock_actual + ? WHERE id = ?", (cant_a_fabricar, id_v))

                # 5. Insertar en Historial (Aquí es donde daba el error corregido)
                c_int.execute("INSERT INTO historial_fabricacion (producto, cantidad, fecha) VALUES (?,?,?)", 
                             (nombre_v, cant_a_fabricar, fecha_hoy))
                
                c_int.commit()
                c_int.close()
                
                self.actualizar_tabla()
                messagebox.showinfo("Éxito", f"Se fabricaron {cant_a_fabricar} unidades de {nombre_v}.")
                v.destroy()
                
            except ValueError:
                messagebox.showerror("Error", "La cantidad debe ser un número válido.")
            except Exception as e:
                messagebox.showerror("Error", f"Ocurrió un problema: {str(e)}")

        tk.Button(v, text="⚙️ FABRICAR", bg="#f39c12", fg="black", font=("Arial", 10, "bold"), 
                  command=fab, pady=10, width=20).pack(pady=20)
        
        tk.Button(v, text="Cerrar", command=v.destroy, bg="#bdc3c7").pack()


         
    def abrir_ventas(self):
        v = tk.Toplevel(self.root)
        v.title("Nueva Venta")
        v.geometry("400x750")
        
        c = sqlite3.connect("gestion_velas.db")
        velas = [f"{x[0]}-{x[1]}" for x in c.execute("SELECT id, nombre FROM productos WHERE tipo='final'").fetchall()]
        clientes_db = [f"{x[1]}" for x in c.execute("SELECT id, nombre FROM clientes").fetchall()]
        if not clientes_db: clientes_db = ["Consumidor Final"]
        c.close()

        # --- FECHA ---
        tk.Label(v, text="Fecha (AAAA-MM-DD):", font=("Arial", 10, "bold")).pack(pady=5)
        ef = tk.Entry(v, justify="center")
        ef.insert(0, datetime.now().strftime('%Y-%m-%d'))
        ef.pack(pady=5)

        # --- CLIENTE ---
        tk.Label(v, text="Cliente:", font=("Arial", 10, "bold")).pack(pady=5)
        c_cli = ttk.Combobox(v, values=clientes_db, width=35)
        c_cli.set("Consumidor Final")
        c_cli.pack(pady=5)

        # --- PRODUCTO ---
        tk.Label(v, text="Producto:", font=("Arial", 10, "bold")).pack(pady=5)
        cp = ttk.Combobox(v, values=velas, state="readonly", width=35)
        cp.pack(pady=5)

        # --- SELECCIÓN DE LISTA (AQUÍ ESTABA EL DETALLE) ---
        tk.Label(v, text="Lista de Precios:", font=("Arial", 10)).pack(pady=5)
        cl = ttk.Combobox(v, values=["Lista 1", "Lista 2"], state="readonly")
        cl.set("Lista 1")
        cl.pack(pady=5)

        # --- MÉTODO DE PAGO ---
        tk.Label(v, text="Método de Pago:", font=("Arial", 10, "bold")).pack(pady=5)
        cmp = ttk.Combobox(v, values=["Efectivo", "Transferencia / Banco"], state="readonly")
        cmp.set("Efectivo")
        cmp.pack(pady=5)

        # --- CANTIDAD ---
        tk.Label(v, text="Cantidad:", font=("Arial", 10)).pack(pady=5)
        eq = tk.Entry(v, justify="center")
        eq.insert(0, "1")
        eq.pack(pady=5)

        # --- TOTAL ---
        tk.Label(v, text="Total Venta ($):", font=("Arial", 12, "bold")).pack(pady=5)
        et = tk.Entry(v, justify="center", font=("Arial", 14), fg="#27ae60")
        et.pack(pady=5)

        # --- LÓGICA DE CÁLCULO CORREGIDA ---
        def calcular_precio(event=None):
            if not cp.get(): return
            try:
                id_p = cp.get().split("-")[0]
                cant = float(eq.get() if eq.get() else 0)
                
                # CORRECCIÓN: Selección dinámica de la columna
                columna_db = "precio_v" if cl.get() == "Lista 1" else "precio_v2"
                
                c_int = sqlite3.connect("gestion_velas.db")
                # Buscamos el precio según la columna elegida
                res = c_int.execute(f"SELECT {columna_db} FROM productos WHERE id=?", (id_p,)).fetchone()
                c_int.close()
                
                if res:
                    p_unitario = float(res[0] if res[0] is not None else 0)
                    total = p_unitario * cant
                    et.delete(0, tk.END)
                    et.insert(0, f"{total:.2f}")
            except Exception as e:
                print(f"Error: {e}")

        # BINDS PARA QUE EL TOTAL SE ACTUALICE AL INSTANTE
        cp.bind("<<ComboboxSelected>>", calcular_precio)
        cl.bind("<<ComboboxSelected>>", calcular_precio) # Esto detecta el cambio de Lista 1 a Lista 2
        eq.bind("<KeyRelease>", calcular_precio)

        def confirmar_venta():
            if not cp.get() or not et.get():
                messagebox.showwarning("Faltan datos", "Seleccione producto y verifique el total.")
                return
            try:
                id_p, nom = cp.get().split("-")
                cant = float(eq.get())
                total = float(et.get())
                metodo = cmp.get()
                fecha_v = ef.get()
                cliente_v = c_cli.get()
                
                conn = sqlite3.connect("gestion_velas.db")
                costo_u = conn.execute("SELECT costo_u FROM productos WHERE id=?", (id_p,)).fetchone()[0]
                
                conn.execute("""INSERT INTO historial_ventas 
                    (producto, cliente, cantidad, costo_total, total_venta, fecha, metodo_pago) 
                    VALUES (?,?,?,?,?,?,?)""", 
                    (nom, cliente_v, cant, costo_u * cant, total, fecha_v, metodo))
                
                conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE id = ?", (cant, id_p))
                
                col_caja = "saldo_efectivo" if metodo == "Efectivo" else "saldo_banco"
                conn.execute(f"UPDATE caja SET {col_caja} = {col_caja} + ?", (total,))
                
                conn.commit()
                conn.close()
                self.actualizar_tabla()
                messagebox.showinfo("Éxito", "Venta registrada")
                v.destroy()
            except Exception as e:
                messagebox.showerror("Error", str(e))

        tk.Button(v, text="✅ CONFIRMAR VENTA", bg="#27ae60", font=("Arial", 12, "bold"), command=confirmar_venta).pack(pady=20)
        tk.Button(v, text="Cancelar", command=v.destroy, bg="#bdc3c7").pack()

        
    def abrir_compras(self):
        v = tk.Toplevel(self.root)
        v.title("Registrar Compra de Insumos")
        v.geometry("400x650")
        
        c = sqlite3.connect("gestion_velas.db")
        # Traemos insumos y herramientas (tipo != 'final')
        items = [f"{x[0]}-{x[1]}" for x in c.execute("SELECT id, nombre FROM productos WHERE tipo!='final'").fetchall()]
        c.close()

        # --- FECHA (Editable) ---
        tk.Label(v, text="Fecha (AAAA-MM-DD):", font=("Arial", 10, "bold")).pack(pady=5)
        ef = tk.Entry(v, justify="center")
        ef.insert(0, datetime.now().strftime('%Y-%m-%d'))
        ef.pack(pady=5)

        # --- SELECCIÓN DE ITEM ---
        tk.Label(v, text="Item / Insumo:", font=("Arial", 10, "bold")).pack(pady=5)
        ci = ttk.Combobox(v, values=items, state="readonly", width=35)
        ci.pack(pady=5)

        # --- CANTIDAD Y TOTAL ---
        tk.Label(v, text="Cantidad:", font=("Arial", 10)).pack(pady=5)
        eq = tk.Entry(v, justify="center")
        eq.pack(pady=5)

        tk.Label(v, text="Costo Total ($):", font=("Arial", 10)).pack(pady=5)
        et = tk.Entry(v, justify="center")
        et.pack(pady=5)

        # --- MÉTODO DE PAGO ---
        tk.Label(v, text="Método de Pago:", font=("Arial", 10, "bold")).pack(pady=5)
        cmp = ttk.Combobox(v, values=["Efectivo", "Transferencia", "Tarjeta Crédito"], state="readonly")
        cmp.set("Efectivo")
        cmp.pack(pady=5)

        def g():
            if not ci.get() or not eq.get() or not et.get():
                messagebox.showwarning("Atención", "Complete todos los campos")
                return
            
            try:
                id_p, nom = ci.get().split("-")
                q = float(eq.get())
                t = float(et.get())
                fecha = ef.get()
                metodo = cmp.get()
                
                c2 = sqlite3.connect("gestion_velas.db")
                
                # 1. Actualizar Stock y Costo Unitario del Producto
                # El nuevo costo se calcula: Total / Cantidad
                c2.execute("UPDATE productos SET stock_actual = stock_actual + ?, costo_u = ? WHERE id = ?", (q, t/q, id_p))
                
                # 2. Registrar en Historial de Compras (Para Auditoría)
                c2.execute("INSERT INTO historial_compras (item_nombre, cantidad, costo_total, fecha, metodo_pago) VALUES (?,?,?,?,?)",
                          (nom, q, t, fecha, metodo))
                
                # 3. Afectar la Caja o Deuda
                if metodo == "Efectivo":
                    c2.execute("UPDATE caja SET saldo_efectivo = saldo_efectivo - ?", (t,))
                elif metodo == "Transferencia":
                    c2.execute("UPDATE caja SET saldo_banco = saldo_banco - ?", (t,))
                elif metodo == "Tarjeta Crédito":
                    # Si compras con tarjeta, aumenta tu saldo de deuda
                    c2.execute("UPDATE caja SET saldo_tarjeta = saldo_tarjeta + ?", (t,))

                c2.commit()
                c2.close()
                
                self.actualizar_tabla()
                messagebox.showinfo("Éxito", f"Compra de {nom} registrada correctamente.")
                v.destroy()
                
            except ValueError:
                messagebox.showerror("Error", "Verifique que Cantidad y Total sean números.")
            except Exception as e:
                messagebox.showerror("Error", f"Ocurrió un error: {str(e)}")

        # --- BOTONES ---
        tk.Button(v, text="🛒 REGISTRAR COMPRA", bg="#1abc9c", fg="black", 
                  font=("Arial", 11, "bold"), command=g, pady=10).pack(pady=20)
        
        tk.Button(v, text="Cancelar", command=v.destroy, bg="#bdc3c7").pack()

        
    def abrir_ajustes(self):
        v = tk.Toplevel(self.root); v.title("Ajustes de Stock"); v.geometry("400x300")
        conn = sqlite3.connect("gestion_velas.db"); items = [f"{x[0]}-{x[1]}" for x in conn.execute("SELECT id, nombre FROM productos").fetchall()]
        tk.Label(v, text="Item:").pack(); ci = ttk.Combobox(v, values=items); ci.pack()
        tk.Label(v, text="Stock Real:").pack(); eq = tk.Entry(v); eq.pack()
        def s(): 
            if not ci.get(): return
            c_int = sqlite3.connect("gestion_velas.db")
            c_int.execute("UPDATE productos SET stock_actual=? WHERE id=?", (float(eq.get()), ci.get().split("-")[0]))
            c_int.commit(); c_int.close(); self.actualizar_tabla(); v.destroy()
        tk.Button(v, text="Guardar", command=s).pack(pady=20); tk.Button(v, text="Cerrar", command=lambda: [conn.close(), v.destroy()], bg="#bdc3c7").pack()


    def abrir_caja(self):
        v = tk.Toplevel(self.root); v.title("Caja")
        c = sqlite3.connect("gestion_velas.db")
        s = c.execute("SELECT saldo_efectivo, saldo_banco FROM caja").fetchone()
        tk.Label(v, text=f"Efectivo: ${s[0]:,.2f} | Banco: ${s[1]:,.2f}", font=("Arial", 12)).pack(pady=20)
        c.close()

    def mostrar_graficos(self):
        # 1. Cerramos cualquier gráfico previo para liberar memoria
        plt.close('all') 
        
        v = tk.Toplevel(self.root)
        v.title("Ventas Mensuales")
        
        conn = sqlite3.connect("gestion_velas.db")
        df = pd.read_sql("SELECT total_venta, fecha FROM historial_ventas", conn)
        conn.close()
        
        if not df.empty:
            df['fecha'] = pd.to_datetime(df['fecha'])
            res = df.sort_values('fecha').groupby(df['fecha'].dt.strftime('%Y-%m'))['total_venta'].sum()
            
            # 2. Creamos la figura (aquí es donde saltaba el error)
            fig, ax = plt.subplots(figsize=(6, 4))
            res.plot(kind='bar', ax=ax, color='#9b59b6')
            
            canvas = FigureCanvasTkAgg(fig, v)
            canvas.get_tk_widget().pack()
            canvas.draw()
        else:
            tk.Label(v, text="No hay datos de ventas para graficar").pack(pady=20)
            
        tk.Button(v, text="Cerrar", command=v.destroy, bg="#bdc3c7").pack()

    def on_double_click(self, e):
        sel = self.tree.selection()
        if not sel: return
        
        # Obtener el ID del producto desde la fila seleccionada
        item_values = self.tree.item(sel[0])['values']
        id_p = item_values[0]

        # Consultamos la DB para traer los valores actuales exactos
        conn = sqlite3.connect("gestion_velas.db")
        res = conn.execute("SELECT nombre, tipo, stock_minimo FROM productos WHERE id=?", (id_p,)).fetchone()
        conn.close()
        
        if not res: return
        nombre_act, tipo_act, stk_min_act = res

        # --- Ventana Emergente ---
        v = tk.Toplevel(self.root)
        v.title(f"Editar: {nombre_act}")
        v.geometry("350x400")
        v.configure(padx=20, pady=20)

        tk.Label(v, text="Nombre del Producto:", font=("Arial", 10, "bold")).pack(pady=5)
        en = tk.Entry(v, font=("Arial", 10))
        en.insert(0, nombre_act)
        en.pack(fill="x", pady=5)

        tk.Label(v, text="Tipo de Producto:", font=("Arial", 10, "bold")).pack(pady=5)
        ct = ttk.Combobox(v, values=["insumo", "final", "herramienta"], state="readonly")
        ct.set(tipo_act)
        ct.pack(fill="x", pady=5)

        tk.Label(v, text="Stock Mínimo (Alerta):", font=("Arial", 10, "bold")).pack(pady=5)
        esm = tk.Entry(v, font=("Arial", 10), justify="center")
        esm.insert(0, str(stk_min_act))
        esm.pack(fill="x", pady=5)

        def guardar_cambios():
            nuevo_nom = en.get().upper()
            nuevo_tipo = ct.get()
            nuevo_min = safe_float(esm.get())

            if not nuevo_nom:
                messagebox.showwarning("Atención", "El nombre no puede estar vacío")
                return

            try:
                c = sqlite3.connect("gestion_velas.db")
                c.execute("""UPDATE productos SET nombre=?, tipo=?, stock_minimo=? 
                             WHERE id=?""", (nuevo_nom, nuevo_tipo, nuevo_min, id_p))
                c.commit()
                c.close()
                
                self.actualizar_tabla()
                messagebox.showinfo("Éxito", "Producto actualizado correctamente")
                v.destroy()
            except Exception as ex:
                messagebox.showerror("Error", f"No se pudo actualizar: {str(ex)}")

        def borrar_item():
            if messagebox.askyesno("Confirmar", f"¿Desea eliminar permanentemente {nombre_act}?\nEsto puede afectar recetas existentes."):
                c = sqlite3.connect("gestion_velas.db")
                c.execute("DELETE FROM productos WHERE id=?", (id_p,))
                c.commit()
                c.close()
                self.actualizar_tabla()
                v.destroy()

        # Botones de acción
        tk.Button(v, text="💾 GUARDAR CAMBIOS", bg="#2ecc71", fg="black", font=("Arial", 10, "bold"),
                  command=guardar_cambios, pady=5).pack(fill="x", pady=10)
        
        tk.Button(v, text="🗑️ ELIMINAR PRODUCTO", bg="#e74c3c", fg="black", 
                  command=borrar_item).pack(fill="x", pady=5)
        tk.Button(v, text="Cerrar", command=lambda: [conn.close(), v.destroy()], bg="#bdc3c7").pack(side=tk.RIGHT, padx=30)
        

    # ==========================================
    # CLIENTES
    # ==========================================
    def abrir_clientes(self):
        v = tk.Toplevel(self.root); v.title("Administración de Clientes"); v.geometry("500x600")
        conn = sqlite3.connect("gestion_velas.db")
        tk.Label(v, text="Nombre:").pack(); en = tk.Entry(v); en.pack()
        tk.Label(v, text="Teléfono:").pack(); et = tk.Entry(v); et.pack()

        tr = ttk.Treeview(v, columns=("ID", "Nombre", "Tel"), show="headings")
        for c in tr["columns"]: tr.heading(c, text=c); tr.column(c, anchor="w")
        tr.pack(fill="both", expand=True, padx=10, pady=10)

        def actualizar_l():
            for i in tr.get_children(): tr.delete(i)
            c_int = sqlite3.connect("gestion_velas.db")
            for r in c_int.execute("SELECT * FROM clientes").fetchall(): tr.insert("", "end", values=r)
            c_int.close()

        def guardar():
            c_int = sqlite3.connect("gestion_velas.db")
            c_int.execute("INSERT INTO clientes (nombre, telefono) VALUES (?,?)", (en.get(), et.get()))
            c_int.commit(); c_int.close()
            actualizar_l(); en.delete(0, tk.END); et.delete(0, tk.END)

        def borrar():
            sel = tr.selection()
            if sel:
                c_int = sqlite3.connect("gestion_velas.db")
                c_int.execute("DELETE FROM clientes WHERE id=?", (tr.item(sel[0])['values'][0],))
                c_int.commit(); c_int.close()
                actualizar_l()

        tk.Button(v, text="💾 Añadir", bg="#2ecc71", command=guardar).pack(side=tk.LEFT, padx=30)
        tk.Button(v, text="🗑️ Borrar", bg="#e74c3c", command=borrar).pack(side=tk.LEFT)
        tk.Button(v, text="Cerrar", command=lambda: [conn.close(), v.destroy()], bg="#bdc3c7").pack(side=tk.RIGHT, padx=30)
        actualizar_l()
        

    # ==========================================
    # CAJA INTEGRAL CON EXPORTACIÓN
    # ==========================================
    def abrir_caja(self):
        v = tk.Toplevel(self.root); v.title("Gestión de Caja Pro"); v.geometry("1000x850")
        
        def refrescar():
            v.destroy()
            self.abrir_caja()

        conn = sqlite3.connect("gestion_velas.db")
        s = conn.execute("SELECT saldo_efectivo, saldo_banco, saldo_tarjeta FROM caja").fetchone()
        
        # --- PANEL DE SALDOS ---
        f_saldos = tk.Frame(v, pady=15)
        f_saldos.pack(fill="x")
        tk.Label(f_saldos, text=f"EFECTIVO: ${s[0]:,.2f}", font=("Arial", 12, "bold"), fg="green").pack(side=tk.LEFT, padx=20)
        tk.Label(f_saldos, text=f"BANCO: ${s[1]:,.2f}", font=("Arial", 12, "bold"), fg="blue").pack(side=tk.LEFT, padx=20)
        tk.Label(f_saldos, text=f"DEUDA TARJETA: ${s[2]:,.2f}", font=("Arial", 12, "bold"), fg="red").pack(side=tk.LEFT, padx=20)

        # --- PANEL DE ACCIONES ---
        f_acc = tk.LabelFrame(v, text=" Operaciones de Capital y Tarjeta ", padx=10, pady=10)
        f_acc.pack(fill="x", padx=20, pady=10)

        def procesar_operacion(tipo_op, detalle, monto, cuenta_afectada):
            if monto is None or monto <= 0: return
            
            c = sqlite3.connect("gestion_velas.db")
            fecha = datetime.now().strftime('%Y-%m-%d %H:%M')
            
            if tipo_op == "INGRESO":
                col = "saldo_efectivo" if cuenta_afectada == "Efectivo" else "saldo_banco"
                c.execute(f"UPDATE caja SET {col} = {col} + ?", (monto,))
            elif tipo_op == "EGRESO":
                col = "saldo_efectivo" if cuenta_afectada == "Efectivo" else "saldo_banco"
                c.execute(f"UPDATE caja SET {col} = {col} - ?", (monto,))
            elif tipo_op == "DEUDA_TARJETA":
                c.execute("UPDATE caja SET saldo_tarjeta = saldo_tarjeta + ?", (monto,))
            elif tipo_op == "PAGO_TARJETA":
                col = "saldo_efectivo" if cuenta_afectada == "Efectivo" else "saldo_banco"
                c.execute(f"UPDATE caja SET {col} = {col} - ?, saldo_tarjeta = saldo_tarjeta - ?", (monto, monto))

            c.execute("INSERT INTO historial_compras (fecha, item_nombre, cantidad, costo_total, metodo_pago) VALUES (?,?,?,?,?)",
                     (fecha, detalle, 1, monto, cuenta_afectada))
            
            c.commit(); c.close(); refrescar()

        # Botones de Acción
        f1 = tk.Frame(f_acc); f1.pack(fill="x", pady=2)
        tk.Button(f1, text="+ Aporte Ef.", bg="#27ae60", fg="black", width=15, command=lambda: procesar_operacion("INGRESO", "Aporte Capital", simpledialog.askfloat("Aporte", "Monto:"), "Efectivo")).pack(side=tk.LEFT, padx=5)
        tk.Button(f1, text="+ Aporte Ban.", bg="#2980b9", fg="black", width=15, command=lambda: procesar_operacion("INGRESO", "Aporte Capital", simpledialog.askfloat("Aporte", "Monto:"), "Transferencia")).pack(side=tk.LEFT, padx=5)
        tk.Button(f1, text="- Quitar Ef.", bg="#c0392b", fg="black", width=15, command=lambda: procesar_operacion("EGRESO", "Retiro Capital", simpledialog.askfloat("Retiro", "Monto:"), "Efectivo")).pack(side=tk.LEFT, padx=5)
        tk.Button(f1, text="- Quitar Ban.", bg="#8e44ad", fg="black", width=15, command=lambda: procesar_operacion("EGRESO", "Retiro Capital", simpledialog.askfloat("Retiro", "Monto:"), "Transferencia")).pack(side=tk.LEFT, padx=5)

        f2 = tk.Frame(f_acc); f2.pack(fill="x", pady=5)
        tk.Button(f2, text="➕ Deuda TC", bg="#34495e", fg="black", width=15, command=lambda: procesar_operacion("DEUDA_TARJETA", "Ajuste Deuda", simpledialog.askfloat("Deuda", "Monto:"), "Tarjeta Crédito")).pack(side=tk.LEFT, padx=5)
        tk.Button(f2, text="💳 Pago TC (Ef)", bg="#d35400", fg="black", width=15, command=lambda: procesar_operacion("PAGO_TAR_EF", "Pago Tarjeta", simpledialog.askfloat("Pago", "Monto:"), "Efectivo")).pack(side=tk.LEFT, padx=5)
        tk.Button(f2, text="💳 Pago TC (Ban)", bg="#2c3e50", fg="black", width=15, command=lambda: procesar_operacion("PAGO_TAR_BA", "Pago Tarjeta", simpledialog.askfloat("Pago", "Monto:"), "Transferencia")).pack(side=tk.LEFT, padx=5)

        # --- TABLA ---
        tr = ttk.Treeview(v, columns=(1,2,3,4,5), show="headings")
        for i, h in enumerate(["Fecha", "Tipo", "Detalle", "Monto", "Cuenta"], 1): 
            tr.heading(i, text=h); tr.column(i, anchor="w")
        tr.column(4, anchor="e")
        tr.pack(fill="both", expand=True, padx=20)

        query = """
            SELECT fecha, 'VENTA', producto, total_venta, metodo_pago FROM historial_ventas 
            UNION ALL 
            SELECT fecha, 'MOV/COMP', item_nombre, costo_total, metodo_pago FROM historial_compras 
            ORDER BY fecha DESC LIMIT 150
        """
        for r in conn.execute(query).fetchall():
            tr.insert("", "end", values=(r[0], r[1], r[2], f"${r[3]:,.2f}", r[4]))

        # --- EXPORTACIÓN ---
        def exportar_caja():
            path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
            if path:
                c = sqlite3.connect("gestion_velas.db")
                df_v = pd.read_sql("SELECT fecha, 'VENTA' as Tipo, producto as Detalle, total_venta as Monto, metodo_pago as Cuenta FROM historial_ventas", c)
                df_c = pd.read_sql("SELECT fecha, 'MOV/COMP' as Tipo, item_nombre as Detalle, costo_total as Monto, metodo_pago as Cuenta FROM historial_compras", c)
                pd.concat([df_v, df_c]).sort_values(by="fecha", ascending=False).to_excel(path, index=False)
                c.close()
                messagebox.showinfo("Éxito", "Caja exportada correctamente")

        f_bot = tk.Frame(v); f_bot.pack(pady=10)
        tk.Button(f_bot, text="📊 Exportar a Excel", command=exportar_caja, bg="yellow", fg="black", width=20).pack(side=tk.LEFT, padx=10)
        tk.Button(f_bot, text="Cerrar", command=lambda: [conn.close(), v.destroy()], bg="#bdc3c7", width=10).pack(side=tk.LEFT)

   

# ==========================================
# 3. EJECUCIÓN
# ==========================================
if __name__ == "__main__":
    inicializar_db()
    root = tk.Tk()
    app = SistemaVelas(root)
    root.mainloop()
