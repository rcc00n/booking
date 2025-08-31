from dal import autocomplete
from django.db.models import Q

from .models import Service

class ServiceAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        qs = Service.objects.all().order_by("name")

        q = (self.q or "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))

        # ключевой момент: фильтруем по выбранному мастеру из forward
        master_id = (self.forwarded.get("master") or "").strip()
        if master_id:
            qs = qs.filter(servicemaster__master_id=master_id)

        return qs

    def get_result_label(self, obj: Service):
        # видимый текст в выпадающем списке
        return f"{obj.name} — ${obj.base_price} · {obj.duration_min} min"

    # Чтобы в JS можно было вытащить цену напрямую из select2 data:
    def get_results(self, context):
        """В каждый элемент выдачи допишем base_price и duration_min для фронта."""
        results = super().get_results(context)
        ids = [r["id"] for r in results["results"]]
        # подкачиваем объекты одним запросом
        by_id = {str(s.pk): s for s in self.get_queryset().filter(pk__in=ids)}
        for r in results["results"]:
            s = by_id.get(str(r["id"]))
            if s:
                r["base_price"] = str(s.base_price)
                r["duration_min"] = s.duration_min
        return results

