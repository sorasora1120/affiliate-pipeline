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

# 収集した案件は、実際に応募するまでの間に他の応募者へ決まってしまうことが多い
# （2026-08-11、提案済み358件を全件チェックしたところ61.5%が既に募集終了だった）。
# 収集のたびに合わせてチェックし、Dispatchビューアの「送れる案件」が常に生きている
# 案件だけになるようにする。ここが失敗してもCrowdWorks収集タスク自体は
# 成功扱いのままにしたいため、SystemExitを握りつぶす（収集は既に完了済みのため）。
try:
    runpy.run_path(str(BASE_DIR / "check_expired_main.py"), run_name="__main__")
except SystemExit:
    pass
