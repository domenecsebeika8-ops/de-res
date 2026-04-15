@echo off
echo ============================================
echo  Comprobando lo que tienes instalado...
echo ============================================
echo.

:: Python
python --version >nul 2>&1
if %errorlevel%==0 (
    echo [OK] Python:
    python --version
) else (
    echo [FALTA] Python  ^<-- descarga en https://python.org
)

echo.

:: Flask
python -c "import flask; print('[OK] Flask:', flask.__version__)" 2>nul || echo [FALTA] Flask

:: Flask-SocketIO
python -c "import flask_socketio; print('[OK] Flask-SocketIO:', flask_socketio.__version__)" 2>nul || echo [FALTA] Flask-SocketIO

:: Werkzeug
python -c "import werkzeug; print('[OK] Werkzeug:', werkzeug.__version__)" 2>nul || echo [FALTA] Werkzeug

:: PyInstaller (solo necesario para crear el .exe)
python -c "import PyInstaller; print('[OK] PyInstaller:', PyInstaller.__version__)" 2>nul || echo [FALTA] PyInstaller  ^(solo si quieres crear el .exe^)

echo.
echo ============================================
echo  Si algo aparece como FALTA, ejecuta:
echo  pip install NOMBRE_DEL_PAQUETE
echo ============================================
echo.
pause
