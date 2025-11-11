from dal import autocomplete
from django.db.models import Q

from .models import Service, UserProfile


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


class MasterUserProfileAutocomplete(autocomplete.Select2QuerySetView):
    """Autocomplete view returning only user profiles that have a master profile attached."""  # // CHANGED

    def get_queryset(self):
        if not (self.request.user and self.request.user.is_staff):  # // CHANGED
            return UserProfile.objects.none()  # // CHANGED

        qs = (
            UserProfile.objects.select_related("user", "master_profile")  # // CHANGED
            .filter(master_profile__isnull=False)  # // CHANGED
            .order_by("user__first_name", "user__last_name", "user__username")  # // CHANGED
        )  # // CHANGED

        query = (self.q or "").strip()  # // CHANGED
        if query:  # // CHANGED
            qs = qs.filter(  # // CHANGED
                Q(user__first_name__icontains=query)  # // CHANGED
                | Q(user__last_name__icontains=query)  # // CHANGED
                | Q(user__username__icontains=query)  # // CHANGED
            )  # // CHANGED

        return qs  # // CHANGED

    def get_result_label(self, obj):  # // CHANGED
        user = getattr(obj, "user", None)  # // CHANGED
        full_name = (user.get_full_name() if user else "") or str(obj)  # // CHANGED
        username = getattr(user, "username", "") if user else ""  # // CHANGED
        if username and username not in full_name:  # // CHANGED
            return f"{full_name} ({username})"  # // CHANGED
        return full_name or username or str(obj)  # // CHANGED

    def get_selected_result_label(self, obj):  # // CHANGED
        return self.get_result_label(obj)  # // CHANGED
