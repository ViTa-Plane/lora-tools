cls
@echo off
cd /d "%~dp0"
@echo.
set ENV_DIR=.venv
@echo activate virtual environment
call .\%ENV_DIR%\Scripts\deactivate.bat
call .\%ENV_DIR%\Scripts\activate.bat

@echo start LoRa Tools...
python lora_tools.py


