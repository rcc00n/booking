from dal import autocomplete
from django.db.models import Q

from .models import Service


class ServiceAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        qs = Service.objects.filter(is_active=True).order_by("name")

        q = (self.q or "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))

        master_id = (self.forwarded.get("master") or "").strip()
        if master_id:
            qs = qs.filter(servicemaster__master_id=master_id)

        return qs

    def get_result_label(self, obj: Service):
        return f"{obj.name} (${obj.base_price}) {obj.duration_min} min"

    def get_results(self, context):
        results = super().get_results(context)
        result_list = results["results"] if isinstance(results, dict) else results
        ids = [r["id"] for r in result_list]

        queryset = self.get_queryset().filter(pk__in=ids)
        by_id = {str(service.pk): service for service in queryset}

        for entry in result_list:
            service_obj = by_id.get(str(entry["id"]))
            if service_obj:
                entry["base_price"] = str(service_obj.base_price)
                entry["duration_min"] = service_obj.duration_min

        return results
