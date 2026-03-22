from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import os
from datetime import datetime

# 1. DEFINICIÓN DE LA APLICACIÓN (Esto debe ir antes de las rutas)
app = Flask(__name__)
app.secret_key = "velas_ultra_secret_key"

# 2. CONFIGURACIÓN DE RUTAS DE BASE DE DATOS
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_velas.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# 3. RUTA PRINCIPAL
@app.route('/')
def index():
    db = get_db()
    productos = db.execute('SELECT * FROM productos').fetchall()
    caja = db.execute('SELECT * FROM caja WHERE id=1').fetchone()
    # Fecha de hoy para los formularios
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    
    # Procesar márgenes para la tabla
    lista_p = []
    for p in productos:
        item = dict(p)
        costo = item['costo_u'] or 0
        p1 = item['precio_v'] or 0
        p2 = item['precio_v2'] or 0
        item['m1'] = ((p1 - costo) / costo * 100) if costo > 0 else 0
        item['m2'] = ((p2 - costo) / costo * 100) if costo > 0 else 0
        lista_p.append(item)
    
    db.close()
    return render_template('index.html', productos=lista_p, caja=caja, fecha_hoy=fecha_hoy)

# 4. RUTA VENTAS (Monto y Fecha editables)
@app.route('/registrar_venta', methods=['POST'])
def registrar_venta():
    db = get_db()
    try:
        id_p = request.form['producto']
        cant = float(request.form['cantidad'])
        monto_final = float(request.form['total_venta']) # Editable por el usuario
        metodo = request.form['metodo']
        fecha = request.form['fecha'] # Fecha elegida por el usuario

        prod = db.execute('SELECT nombre, costo_u FROM productos WHERE id=?', (id_p,)).fetchone()
        costo_total = (prod['costo_u'] or 0) * cant

        db.execute('''INSERT INTO historial_ventas 
                      (producto, cantidad, total_venta, fecha, metodo_pago, costo_total) 
                      VALUES (?,?,?,?,?,?)''', 
                   (prod['nombre'], cant, monto_final, fecha, metodo, costo_total))
        
        db.execute('UPDATE productos SET stock_actual = stock_actual - ? WHERE id=?', (cant, id_p))
        
        col_caja = "saldo_efectivo" if metodo == "Efectivo" else "saldo_banco"
        db.execute(f"UPDATE caja SET {col_caja} = {col_caja} + ? WHERE id=1", (monto_final,))
        
        db.commit()
        flash("Venta registrada con éxito", "success")
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
    finally:
        db.close()
    return redirect(url_for('index'))

# 5. RUTA COMPRAS (Suma stock y resta dinero/suma deuda)
@app.route('/registrar_compra', methods=['POST'])
def registrar_compra():
    db = get_db()
    try:
        id_p = request.form['insumo']
        cant = float(request.form['cantidad'])
        total = float(request.form['total'])
        metodo = request.form['metodo']
        fecha = request.form['fecha']
        
        prod = db.execute('SELECT nombre FROM productos WHERE id=?', (id_p,)).fetchone()
        
        # Actualizar stock y costo unitario
        db.execute('UPDATE productos SET stock_actual = stock_actual + ?, costo_u = ? WHERE id=?', 
                   (cant, total/cant, id_p))
        
        # Registrar compra
        db.execute('INSERT INTO historial_compras (item_nombre, cantidad, costo_total, fecha, metodo_pago) VALUES (?,?,?,?,?)',
                   (prod['nombre'], cant, total, fecha, metodo))
        
        # Afectar caja o deuda
        if metodo == "Efectivo":
            db.execute('UPDATE caja SET saldo_efectivo = saldo_efectivo - ? WHERE id=1', (total,))
        elif metodo == "Transferencia":
            db.execute('UPDATE caja SET saldo_banco = saldo_banco - ? WHERE id=1', (total,))
        else: # Tarjeta de Crédito
            db.execute('UPDATE caja SET saldo_tarjeta = saldo_tarjeta + ? WHERE id=1', (total,))
            
        db.commit()
        flash("Compra cargada exitosamente", "info")
    except Exception as e:
        flash(f"Error en compra: {str(e)}", "danger")
    finally:
        db.close()
    return redirect(url_for('index'))

# 6. RUTA AJUSTE DE CAJA (Sumar/Restar manual)
@app.route('/operacion_caja', methods=['POST'])
def operacion_caja():
    db = get_db()
    try:
        tipo = request.form['tipo'] # INGRESO / EGRESO
        cuenta = request.form['cuenta'] # Efectivo / Banco
        monto = float(request.form['monto'])
        detalle = request.form['detalle']
        
        col = "saldo_efectivo" if cuenta == "Efectivo" else "saldo_banco"
        op = "+" if tipo == "INGRESO" else "-"
        
        db.execute(f"UPDATE caja SET {col} = {col} {op} ? WHERE id=1", (monto,))
        db.commit()
        flash(f"Ajuste de {cuenta} realizado", "secondary")
    except Exception as e:
        flash(f"Error en caja: {str(e)}", "danger")
    finally:
        db.close()
    return redirect(url_for('index'))

#7.  RUTA PARA AUDITORIA 
@app.route('/auditoria')
def auditoria():
    db = get_db()
    
    # 1. Datos para Balance (Ventas vs Compras)
    ventas_total = db.execute("SELECT SUM(total_venta) FROM historial_ventas").fetchone()[0] or 0
    compras_total = db.execute("SELECT SUM(costo_total) FROM historial_compras").fetchone()[0] or 0
    
    # 2. Datos para Gráfico de Producción (Top 5 productos más fabricados)
    produccion = db.execute('''
        SELECT producto, SUM(cantidad) as total 
        FROM historial_fabricacion 
        GROUP BY producto 
        ORDER BY total DESC LIMIT 5
    ''').fetchall()
    
    # Convertimos los datos de producción a listas para JavaScript
    labels_prod = [p['producto'] for p in produccion]
    values_prod = [p['total'] for p in produccion]
    
    db.close()
    return render_template('auditoria.html', 
                           v_total=ventas_total, 
                           c_total=compras_total, 
                           labels_prod=labels_prod, 
                           values_prod=values_prod)

if __name__ == '__main__':
    app.run()
#    app.run(debug=True, port=5000)