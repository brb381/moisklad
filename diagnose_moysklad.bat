@echo off
setlocal
cd /d "%~dp0"

".venv\Scripts\python.exe" -c "from app.moysklad import MoySkladClient; stores=MoySkladClient().list_retail_stores(); print('stores_count=', len(stores)); [print((s.get('id') or '') + ' | ' + (s.get('name') or '') + ' | archived=' + str(s.get('archived'))) for s in stores]"
