import check_expired_main as m


def test_applied_hired_ordered_are_actively_pursued():
    # 募集終了だけでは「落選」と「採用されたがまだ②を押していない」を区別できず、
    # 鮮度切れも「検出から3日超」だけでは応募済み・返信待ちの案件と区別できない
    # ため、応募済み以降は自動削除・鮮度切れタグ付けの対象から外す
    # （2026-08-13/2026-08-14）。
    assert m._is_actively_pursued({"進捗ステージ": "applied"}) is True
    assert m._is_actively_pursued({"進捗ステージ": "hired"}) is True
    assert m._is_actively_pursued({"進捗ステージ": "ordered"}) is True


def test_new_and_rejected_are_not_actively_pursued():
    assert m._is_actively_pursued({"進捗ステージ": ""}) is False
    assert m._is_actively_pursued({"進捗ステージ": "rejected"}) is False
    assert m._is_actively_pursued({}) is False
