# Savings plan refresh

1. User opens `/savings/plan/` or triggers refresh
2. `analyze_finances` → `choose_scenario` → `build_recommendation`
3. If fingerprint/material change: write `SavingsPlan` + `SavingsPlanRevision`
4. Else: keep existing recommendation
5. User may pause/disable/override percents (100% constraint)
