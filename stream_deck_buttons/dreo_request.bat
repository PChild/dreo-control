@echo off
setlocal

if "%~1"=="" (
    echo Missing Dreo query parameters. 1>&2
    exit /b 2
)

curl.exe --silent --show-error --fail --max-time 3 "http://127.0.0.1:8765/set?%~1" >NUL
exit /b %ERRORLEVEL%
