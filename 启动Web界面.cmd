@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动 Agnes 注册机可视化 Web 控制台，浏览器将自动打开 http://127.0.0.1:8765 ...
uv run agnes --config config.local.toml web
pause
