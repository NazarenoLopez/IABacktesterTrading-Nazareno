@echo off
echo Iniciando servidor API local del Dashboard (con recalculador dinámico)...
start chrome "http://localhost:8000/web/"
.venv\Scripts\python web/server.py
