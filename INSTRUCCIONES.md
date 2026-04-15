# 📚 Chat de Deberes — Instrucciones

## ¿Qué es esto?
Una app de chat en tiempo real para hablar con compañeros sobre los deberes.  
- 10 salas por asignatura (Mates, Lengua, Inglés, Ciencias…)
- Nicknames personalizados
- Subir imágenes y archivos (hasta 20 MB)
- Funciona en móvil y PC desde el navegador

---

## OPCIÓN A — Compilar el .exe (recomendado para Windows)

1. Instala Python desde https://python.org (marca "Add Python to PATH")
2. Haz doble clic en **build_exe.bat**
3. Espera ~2 minutos → se crea `dist/ChatDeberes.exe`
4. ¡Haz doble clic en el .exe para arrancar!
5. El navegador se abrirá en http://localhost:5000

> Los compañeros en la misma red WiFi pueden conectarse poniendo tu IP local:  
> `http://TU_IP:5000`  (puedes ver tu IP con el comando `ipconfig`)

---

## OPCIÓN B — Correr directamente con Python (sin compilar)

```
pip install -r requirements.txt
python app.py
```

---

## OPCIÓN C — Servidor online GRATIS (para acceder desde cualquier red)

1. Crea cuenta gratis en https://railway.app
2. Sube esta carpeta como nuevo proyecto
3. Railway te da una URL pública tipo `https://xxx.railway.app`
4. ¡Comparte esa URL con tus compañeros y ya pueden entrar desde cualquier sitio!

---

## Estructura de archivos
```
ChatDeberes/
├── app.py              ← Servidor Python (Flask + SocketIO)
├── templates/
│   └── index.html      ← Interfaz web (móvil + PC)
├── static/uploads/     ← Archivos subidos
├── requirements.txt    ← Dependencias Python
├── build_exe.bat       ← Script para crear el .exe
└── Procfile            ← Para desplegar en Railway
```
