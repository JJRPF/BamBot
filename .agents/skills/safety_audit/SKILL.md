---
name: safety_audit
description: Guide the agent on verifying safety bounds, temperature guardrails, and door status before starting a print.
---

# Skill: Safety Audit

## Overview
Provides guidelines for the Safety/Critic agents to audit print jobs and ensure thermal and mechanical safety.

## Guardrail Rules
1. **Nozzle Limit**: Max temperature 300°C. If a print job requests higher, reject it.
2. **Bed Limit**: Max temperature 120°C. If a print job requests higher, reject it.
3. **Bed Clearance**: Ensure the user confirms the bed is clear of any previous prints. Do not bypass this.
4. **Door State for ABS/ASA**: Warn or require closed door/chamber if printing ABS, ASA, PC, or PA to prevent warping and fumes.
5. **Filament Low warning (Optional)**: If Spoolman details exist, warn if remaining filament is less than requested print weight.
