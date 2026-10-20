# ClaimApp (Django)

Aplicación web para subir archivos CSV/Excel de reclamos, revisarlos en un dashboard, marcar y eliminar registros (cero, Respond Code 50, duplicados OT/OS/OR/OM) y ver totales.

## Instalación local

```bash
git clone <tu-repo> && cd ClaimApp_Django
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # edita DJANGO_SECRET_KEY; deja DJANGO_DEBUG=1 en local
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Pruebas: `DJANGO_DEBUG=1 python manage.py test` (en Windows: `set DJANGO_DEBUG=1` antes).

## Cómo funciona

- **Subir archivo** (`.csv` o `.xlsx`, máx. 10 MB, 6000 filas, 22 columnas). La primera fila es el encabezado.
  Las columnas *Amount, Trxn Code, Merchants, Respond Code* se buscan por nombre; si falta un encabezado se usa la columna E, F, G o I y la app te avisa. Las columnas A, B y C se guardan como `col1`, `col2`, `col3`.
- Un Amount ilegible queda **vacío**, nunca en 0, y se informa cuántos fueron.
- Por defecto el archivo se **agrega**; marca «Reemplazar datos existentes» para borrar lo anterior. «Deshacer» elimina la última importación.
- Los botones **Marcar…** solo *marcan* filas (fondo amarillo, filtro «Marcados»). Nada se borra hasta pulsar **Eliminar marcados**.
- Reglas de duplicados: se agrupa por Amount + Merchant (filas sin Amount se ignoran). Si hay OT y OS → se marcan los OS. Si hay OR u OM → se marcan los OT y OS. OT repetidos sin OS/OR/OM se conservan.

## Si ya tenías datos (migración)

La migración `0002` renombra `col4→amount`, `col5→trxn_code`, `col6→merchant`, agrega `respond_code`, convierte vacíos/`nan` en texto vacío y crea el modelo de importaciones. **Haz copia antes**: `cp db.sqlite3 db.sqlite3.bak`, luego `python manage.py migrate`.
Los registros antiguos no tienen Respond Code; vuelve a importar el archivo con «Reemplazar datos existentes» para llenarlo.

## Despliegue en cPanel (Namecheap)

1. Sube el proyecto (sin `.venv`, `.env`, `db.sqlite3`) a una carpeta **fuera de `public_html`**, p. ej. `~/claimapp`.
2. cPanel → **Setup Python App** → Create: Python **3.12 o superior**, Application root `claimapp`, URL = un subdominio nuevo (p. ej. `claims.tudominio.com`), startup file `passenger_wsgi.py`, entry point `application`.
3. Variables de entorno (en esa pantalla, o en un `.env` dentro de `~/claimapp`):
   `DJANGO_SECRET_KEY` (nueva), `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS=claims.tudominio.com`, `DJANGO_DB_PATH=/home/USUARIO/claimapp_data/db.sqlite3` (crea esa carpeta), opcional `DJANGO_ADMIN_URL=ruta-privada/`.
4. **Run Pip Install** con `requirements.txt`.
5. Por SSH/Terminal (con el `source .../activate` que muestra cPanel):
   `python manage.py migrate && python manage.py createsuperuser && python manage.py collectstatic --noinput`
6. **Restart** y entra por `https://`. Cuando HTTPS funcione, añade `DJANGO_SSL_REDIRECT=1`.
7. Errores 500: revisa `stderr.log` en la carpeta de la app. Tras cada cambio de código, reinicia la app.
8. Haz copias periódicas de `db.sqlite3` (cron o descarga manual).
