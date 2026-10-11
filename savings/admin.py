from django.contrib import admin

from .models import Contribution, DebtObligation, Goal, SavingsPlan, SavingsPlanRevision

admin.site.register(Goal)
admin.site.register(Contribution)
admin.site.register(DebtObligation)
admin.site.register(SavingsPlan)
admin.site.register(SavingsPlanRevision)
