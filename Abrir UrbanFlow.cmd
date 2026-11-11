@echo off
title UrbanFlow - servidor local
python -B "%~dp0abrir_urbanflow.py"
if errorlevel 1 pause
