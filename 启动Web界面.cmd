@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动网站脚本运行台，浏览器将自动打开 http://127.0.0.1:8765 ...
uv run agnes --config config.local.toml web
pause
