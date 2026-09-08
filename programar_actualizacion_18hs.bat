@echo off
title Programador de Tarea Automatica IA - 18:00hs Lunes a Viernes
echo ========================================================
echo Programando Tarea de Actualizacion de IA en Windows
echo Horario: Lunes a Viernes a las 18:00 hs
echo ========================================================
echo.

set TASK_NAME=IABacktester_ActualizarIA_18hs
set SCRIPT_PATH=%~dp0actualizar_ia.bat

echo [INFO] Creando tarea programada en Windows Task Scheduler...
schtasks /create /tn "%TASK_NAME%" /tr "\"%SCRIPT_PATH%\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 18:00 /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================
    echo TAREA PROGRAMADA CON EXITO.
    echo La IA se actualizara automaticamente todos los dias
    echo habiles (Lunes a Viernes) a las 18:00 hs.
    echo ========================================================
) else (
    echo.
    echo [ERROR] Hubo un error al programar la tarea. Asegurate de ejecutar este script como Administrador si es necesario.
)

echo.
pause
