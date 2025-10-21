from pathlib import Path
path = Path("core/autocomplete.py")
text = path.read_text(encoding="utf-8")
old = "        results = super().get_results(context)\n        ids = [r[\"id\"] for r in results[\"results\"]]\n        # D?D_D'D?D???D,D?D?D?D? D_D?SD?D??,?< D_D'D?D,D? D?D?D???D_??D_D?\n        by_id = {str(s.pk): s for s in self.get_queryset().filter(pk__in=ids)}\n        for r in results[\"results\"]:\n            s = by_id.get(str(r[\"id\"]))\n            if s:\n                r[\"base_price\"] = str(s.base_price)\n                r[\"duration_min\"] = s.duration_min\n        return results\n"
new = "        results = super().get_results(context)\n        result_list = results[\"results\"] if isinstance(results, dict) else results\n        ids = [r[\"id\"] for r in result_list]\n        # D?D_D'D?D???D,D?D?D?D? D_D?SD?D??,?< D_D'D?D,D? D?D?D???D_??D_D?\n        by_id = {str(s.pk): s for s in self.get_queryset().filter(pk__in=ids)}\n        for r in result_list:\n            s = by_id.get(str(r[\"id\"]))\n            if s:\n                r[\"base_price\"] = str(s.base_price)\n                r[\"duration_min\"] = s.duration_min\n        return results\n"
if old not in text:
    raise SystemExit('pattern not found')
path.write_text(text.replace(old, new, 1), encoding="utf-8")
