@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 원하는 정책브리핑 보도자료 주소를 붙여 넣고 Enter를 누르세요.
echo 예) https://www.korea.kr/briefing/pressReleaseView.do?newsId=156782110
set /p URL=주소: 
if "%URL%"=="" goto end
python -m pip install -q -r requirements.txt
python scripts\laptop_daily.py --url "%URL%" --interactive
echo.
echo 끝났어요. 몇 분 뒤 확인 페이지에서 보세요: https://butonco00-ux.github.io/cardnews/
:end
pause
