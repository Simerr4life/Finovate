from django.contrib import admin

from .models import (
    DemoInvestmentSuggestion,
    MarketPrice,
    PortfolioSnapshot,
    RoundUpLedgerEntry,
    RoundUpSettings,
    SimulatedOrder,
)

admin.site.register(RoundUpSettings)
admin.site.register(RoundUpLedgerEntry)
admin.site.register(PortfolioSnapshot)
admin.site.register(SimulatedOrder)
admin.site.register(MarketPrice)
admin.site.register(DemoInvestmentSuggestion)
