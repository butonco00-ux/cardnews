@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 오늘 정부 보도자료 카드를 만들어 GitHub에 올려요. (게시는 하지 않아요)
python -m pip install -q -r requirements.txt
python scripts\laptop_daily.py --force --interactive
echo.
echo 끝났어요. 몇 분 뒤 확인 페이지에서 보세요: https://butonco00-ux.github.io/cardnews/
pause
