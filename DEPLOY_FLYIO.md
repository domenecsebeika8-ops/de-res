# Deploy de deúres en Fly.io

## 1. Instalar flyctl

Abre PowerShell y ejecuta:
```
powershell -ExecutionPolicy Bypass -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

Luego cierra y vuelve a abrir PowerShell para que se actualice el PATH.

## 2. Crear cuenta y hacer login

```
fly auth signup
```
(o `fly auth login` si ya tienes cuenta)

## 3. Ir a la carpeta del proyecto

```
cd "C:\Users\domen\Documents\Claude\Projects\deúres\ChatDeberes"
```

## 4. Lanzar la app (primera vez)

```
fly launch --name deures-chat --region mad --no-deploy
```

Cuando pregunte si quieres sobreescribir el fly.toml existente, di **No**.

## 5. Crear el volumen persistente (para la base de datos y archivos)

```
fly volumes create deures_data --size 1 --region mad
```

## 6. Hacer el primer deploy

```
fly deploy
```

Esto tarda 2-3 minutos la primera vez (construye el Docker).

## 7. Abrir la app

```
fly open
```

La URL será algo como: **https://deures-chat.fly.dev**

---

## Comandos útiles

| Comando | Para qué sirve |
|---------|---------------|
| `fly deploy` | Actualizar la app tras cambios |
| `fly logs` | Ver logs en tiempo real |
| `fly status` | Estado de la app |
| `fly open` | Abrir en el navegador |
| `fly ssh console` | Acceder al servidor |

## Notas

- El plan gratuito incluye 3 VMs y 3 GB de almacenamiento.
- La app está configurada con `min_machines_running = 1` para que nunca se duerma.
- La base de datos y los archivos subidos se guardan en `/data` (volumen persistente).
- Si cambias algo en app.py o templates, solo ejecuta `fly deploy`.
