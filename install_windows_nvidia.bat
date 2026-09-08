@echo off
echo ========================================================
echo Instalador Cuantitativo con Soporte NVIDIA (CUDA 12)
echo ========================================================
echo.

where uv >nul 2>nul
if %errorlevel% equ 0 goto USE_UV

:USE_PYTHON
echo [INFO] 'uv' no detectado. Usando Python estandar (puede ser lento).
if not exist ".venv" (
    python -m venv .venv
)
call .venv\Scripts\activate.bat
echo.
echo Paso 2: Instalando dependencias base...
pip install yfinance pandas numpy scikit-learn
echo.
echo Paso 3: Instalando ecosistema de IA...
pip install transformers accelerate huggingface-hub xgboost tsai fastai
echo.
echo Paso 4: Instalando PyTorch optimizado para NVIDIA (Serie 3000/4000)...
echo Descargando binarios CUDA 12.1+ (Esto tomara varios minutos...)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
goto DOWNLOAD_MODELS

:USE_UV
echo [INFO] Acelerador 'uv' detectado. La instalacion sera ultra-rapida.
if not exist ".venv" (
    uv venv .venv
)
call .venv\Scripts\activate.bat
echo.
echo Paso 2: Instalando dependencias base...
uv pip install yfinance pandas numpy scikit-learn
echo.
echo Paso 3: Instalando ecosistema de IA...
uv pip install transformers accelerate huggingface-hub xgboost tsai fastai
echo.
echo Paso 4: Instalando PyTorch optimizado para NVIDIA (Serie 3000/4000) y librería de series temporales (tsai)...
echo Descargando binarios CUDA 12.4+...
uv pip install tsai torch torchvision --index-url https://download.pytorch.org/whl/cu124 --extra-index-url https://pypi.org/simple --index-strategy unsafe-best-match

:DOWNLOAD_MODELS
echo.
echo Paso 5: Descargando pesos de los modelos IA (TimesFM y TSPulse)...
echo Esto descargara varios Gigabytes de redes neuronales desde HuggingFace.
echo Por favor ten paciencia, depende de tu conexion a internet...
.venv\Scripts\python -c "from huggingface_hub import snapshot_download; print('Descargando Google TimesFM...'); snapshot_download(repo_id='google/timesfm-2.0-500m-pytorch'); print('Descargando IBM TSPulse...'); snapshot_download(repo_id='ibm-granite/granite-timeseries-patchtsmixer')"

echo.
echo ========================================================
echo INSTALACION COMPLETADA EXITOSAMENTE
echo ========================================================
echo.
echo Para arrancar tu actualizacion diaria de IA:
echo   actualizar_ia.bat
echo.
echo Para arrancar el Dashboard web:
echo   .venv\Scripts\python web/server.py
echo.
pause

