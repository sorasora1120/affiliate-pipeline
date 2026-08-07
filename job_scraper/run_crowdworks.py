"""
CrowdWorks収集専用のエントリポイント（Windowsタスクスケジューラ用）。

.batファイル（cmd.exe経由）だと、このプロジェクトのパスに含まれる日本語文字
（優空/デスクトップ/claudeの家）の扱いが不安定で、タスクスケジューラから実行すると
mkdir/リダイレクトが機能せず常に失敗する事象が発生した（対話的なcmd実行では
症状が出ないこともあり原因特定に時間がかかった）。cmd.exeのバッチ処理は
ANSI/OEMコードページに依存する部分が多く、Unicodeパスの扱いに弱い。

Pythonから直接実行する分にはこの問題が起きない（Win32のワイド文字APIを使うため）。
タスクスケジューラの「操作」はcmd.exeを介さず、このファイルを直接
python.exeに渡す設定にしてある（run_local_crowdworks.batはローカルで手動実行
する用に残してあるが、タスクスケジューラからは使わない）。
"""
import os
import sys
from pathlib import Path

os.environ["PLATFORMS"] = "crowdworks"

BASE_DIR = Path(__file__).parent
log_path = BASE_DIR / "logs" / "crowdworks.log"
log_path.parent.mkdir(exist_ok=True)

log_file = open(log_path, "a", encoding="utf-8")
sys.stdout = log_file
sys.stderr = log_file

os.chdir(BASE_DIR)

import runpy
runpy.run_path(str(BASE_DIR / "main.py"), run_name="__main__")
