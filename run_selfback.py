from src.selfback_applier import SelfbackApplier
from src.notifier import notify_discord

applier = SelfbackApplier()
results = applier.run(max_apply=10)
applied = [r for r in results if r.status == "applied"]
notify_discord(
    f"=== セルフバック申込完了 ===\n"
    f"成功: {len(applied)}件 / 見込報酬: {sum(r.reward for r in applied):,}円"
)
