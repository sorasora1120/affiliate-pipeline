@echo off
REM 手動でダブルクリックして実行する用。Windowsタスクスケジューラの定期実行は
REM cmd.exe/バッチ処理がこのプロジェクトパスの日本語文字と相性が悪く常に失敗したため、
REM python.exeを直接呼ぶ run_crowdworks.py を使うよう設定を変更済み（タスクの
REM 「操作」を参照）。手動実行はこの.batのままでも動くのでそのまま残してある。
cd /d "%~dp0"
"C:\Users\優空\AppData\Local\Programs\Python\Python312\python.exe" run_crowdworks.py
