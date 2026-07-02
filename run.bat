@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ============================================
echo   StockManager - 주식 투자 관리 워크벤치
echo   브라우저가 자동으로 열립니다 (http://localhost:8501)
echo   종료하려면 이 창에서 Ctrl + C
echo ============================================
python -m streamlit run app.py
pause
