"""複数プロセスがスプレッドシートの行番号を同時に扱う処理（削除・大量更新）を
同時実行させないための簡易ロック。

check_expired_main.py（募集終了した行を削除）とworker_match_main.py（未チェック
行を大量に更新）は、どちらも実行開始時点の行番号スナップショットを使い続ける。
片方が行を削除している間にもう片方が古い行番号で書き込むと、削除後の行数を
超えた範囲を指定してSheets APIの「exceeds grid limits」エラーで失敗する
（2026-08-15発覚、CrowdWorksの自動チェックと手動でのworker_match_main.py実行が
重なった際に実際に29件が失敗した。書き込み前にAPIエラーで弾かれるだけなので
データ破損はなく、失敗した行は「未チェック」のまま残り次回再処理されるが、
Discord通知だけ二重に送られてしまう無駄が起きる）。両方から同じロックを取る
ことで、常にどちらか一方だけが実行される状態にする。
"""
import os
import time
from pathlib import Path

_LOCK_PATH = Path(__file__).parent.parent / "logs" / "sheet_write.lock"
_LOCK_STALE_SECONDS = 20 * 60  # このロックを持つ処理が20分以上かかることは通常ない


def acquire() -> bool:
    _LOCK_PATH.parent.mkdir(exist_ok=True)
    if _LOCK_PATH.exists():
        age = time.time() - _LOCK_PATH.stat().st_mtime
        if age < _LOCK_STALE_SECONDS:
            return False
        _LOCK_PATH.unlink(missing_ok=True)
    try:
        fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False


def release() -> None:
    _LOCK_PATH.unlink(missing_ok=True)
