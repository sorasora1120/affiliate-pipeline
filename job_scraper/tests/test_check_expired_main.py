import check_expired_main as m


def test_hired_and_ordered_are_protected_from_deletion():
    assert m._is_protected_from_deletion({"進捗ステージ": "hired"}) is True
    assert m._is_protected_from_deletion({"進捗ステージ": "ordered"}) is True


def test_applied_is_protected_from_deletion():
    # 募集終了だけでは「落選」と「採用されたがまだ②を押していない」を
    # 区別できないため、応募済み段階も自動削除の対象から外す（2026-08-13）。
    assert m._is_protected_from_deletion({"進捗ステージ": "applied"}) is True


def test_new_and_rejected_are_not_protected_from_deletion():
    assert m._is_protected_from_deletion({"進捗ステージ": ""}) is False
    assert m._is_protected_from_deletion({"進捗ステージ": "rejected"}) is False
    assert m._is_protected_from_deletion({}) is False


def test_only_hired_and_ordered_are_protected_from_stale_tagging():
    assert m._is_won_deal({"進捗ステージ": "hired"}) is True
    assert m._is_won_deal({"進捗ステージ": "ordered"}) is True
    assert m._is_won_deal({"進捗ステージ": "applied"}) is False
    assert m._is_won_deal({"進捗ステージ": ""}) is False
