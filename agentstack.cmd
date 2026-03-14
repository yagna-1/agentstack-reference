@echo off
setlocal
set ROOT_DIR=%~dp0
python "%ROOT_DIR%agentstack.py" %*
