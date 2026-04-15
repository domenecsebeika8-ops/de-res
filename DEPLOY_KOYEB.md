# Deploy de deúres en Koyeb (gratis, sin tarjeta)

## Paso 1 — Subir el código a GitHub

1. Ve a **https://github.com** y crea una cuenta (si no tienes)
2. Haz clic en **New repository**, ponle nombre `deures-chat`, márcalo como **Private** y crea el repo
3. Instala Git desde **https://git-scm.com/download/win** (si no lo tienes)
4. Abre PowerShell en la carpeta del proyecto y ejecuta:

```
cd "C:\Users\domen\Documents\Claude\Projects\deúres\ChatDeberes"
git init
git add .
git commit -m "primera version"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/deures-chat.git
git push -u origin main
```

(Cambia `TU_USUARIO` por tu nombre de usuario de GitHub)

---

## Paso 2 — Crear cuenta en Koyeb

Ve a **https://app.koyeb.com/auth/signup** y regístrate con GitHub (botón "Continue with GitHub").

---

## Paso 3 — Crear la base de datos PostgreSQL

1. En el panel de Koyeb, haz clic en **"Database"** en el menú izquierdo
2. Clic en **"Create Database Service"**
3. Elige el plan **Free**
4. Nombre: `deures-db`, región: **Frankfurt**
5. Haz clic en **"Create"**
6. Espera a que esté lista y copia la **Connection string** (empieza por `postgresql://...`)

---

## Paso 4 — Crear la app

1. En el panel de Koyeb, haz clic en **"App"** → **"Create App"**
2. Elige **GitHub** como fuente
3. Selecciona el repo `deures-chat`
4. En **"Builder"**: elige **Dockerfile**
5. En **"Environment variables"** añade:
   - `DATABASE_URL` = (pega la connection string del paso 3)
   - `SECRET_KEY` = (cualquier texto largo, ej: `miclaveultrasecreta2025`)
6. Puerto: **8080**
7. Región: **Frankfurt**
8. Plan: **Free**
9. Haz clic en **"Deploy"**

---

## Paso 5 — Acceder a la app

En 2-3 minutos la app estará en:
**https://deures-chat-XXXX.koyeb.app**

La URL exacta aparece en el panel de Koyeb.

---

## Actualizar la app tras cambios

Cada vez que hagas cambios en el código:
```
git add .
git commit -m "descripcion del cambio"
git push
```
Koyeb detecta el push y redespliega automáticamente.

---

## Notas importantes

- Los **archivos subidos** (imágenes, docs) no persisten entre redeploys en el plan gratis.
  Para guardarlos permanentemente necesitarías un servicio externo (Cloudflare R2, etc.)
- La **base de datos** (usuarios, salas, amigos) sí persiste siempre en PostgreSQL.
- Si la app da error al arrancar, ve a **Koyeb → App → Logs** para ver qué falla.
