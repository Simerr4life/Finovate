from django.contrib import admin

from .models import Budget, BudgetPeriod, IncomeSource, RecurringExpense

admin.site.register(IncomeSource)
admin.site.register(RecurringExpense)
admin.site.register(BudgetPeriod)
admin.site.register(Budget)
