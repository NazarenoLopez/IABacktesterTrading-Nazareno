@echo off
title Actualizador IA — universo US live (5y, GPU)
echo ========================================================
echo AIS11 cores para el universo US (sin crypto)
echo TimesFM + TSPulse + MiniRocket GPU
echo Primera corrida puede tardar horas. Requiere CUDA.
echo ========================================================
echo.

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    set PYTHON_CMD=.venv\Scripts\python.exe
) else (
    set PYTHON_CMD=python
)

set YF_CACHE_SECONDS=3600
set AI_TICKERS=live_us

echo [1/3] Google TimesFM...
%PYTHON_CMD% models\precalculate_timesfm.py
if errorlevel 1 echo FALLO TimesFM

echo [2/3] IBM TSPulse Univariate...
%PYTHON_CMD% models\finetune_tspulse.py
if errorlevel 1 echo FALLO TSPulse

echo [3/3] MiniRocketPlus GPU...
%PYTHON_CMD% models\train_minirocket_gpu.py
if errorlevel 1 echo FALLO MiniRocket GPU

echo.
echo Listo. Sincroniza JSON a Oracle con:
echo   powershell -File scripts\export_ai_signals_for_oracle.ps1
echo.
pause
