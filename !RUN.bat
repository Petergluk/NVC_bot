@ECHO OFF

REM --- Системная информация ---
ECHO =================================
ECHO System Information:
ECHO Timestamp: %DATE% %TIME%
ECHO Working Directory: %CD%
python --version
ECHO =================================
ECHO.

REM --- Заголовок ---
ECHO Starting Python script: run.py
ECHO.

REM --- Выполнение скрипта ---
REM Запускаем интерпретатор Python для выполнения файла
python run.py

ECHO.
ECHO Script execution finished. The window will remain open.
cmd /k