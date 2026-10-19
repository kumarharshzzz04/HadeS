@echo off
setlocal
chcp 65001 >nul
title HadeS - basic front end (Streamlit)
rem Basic front end that ships with this repo: pick a lecture set, ask a question,
rem read the answer, and see the lessons behind it with timestamps. No Node.js,
rem no build step, no changes to the RAG core. The React UI is private.
cd /d "%~dp0"

set "PY=python"
where %PY% >nul 2>nul || (echo  [X] Python is not on PATH - install Python 3.10+ first. & pause & exit /b 1)

%PY% -c "import streamlit" 2>nul
if errorlevel 1 (
    echo  Installing Streamlit for the basic front end - one time only...
    %PY% -m pip install -r requirements.txt || (echo  [X] pip install failed. & pause & exit /b 1)
)

echo.
echo  HadeS on http://localhost:8602  -  Ctrl+C in this window stops it.
echo  The API bridge is not needed here; this page calls rag_chat directly.
echo.
%PY% -m streamlit run streamlit_app.py --server.port 8602 ^
    --browser.gatherUsageStats false
