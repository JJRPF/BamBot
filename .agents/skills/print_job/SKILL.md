---
name: print_job
description: Guide the agent on how to manage, validate, and monitor 3D print jobs on the Bambu Lab X1C.
---

# Skill: Print Job Management

## Overview
This skill provides instructions for the agent when preparing, starting, and monitoring 3D print jobs.

## Workflow
1. **File Retrieval**: Retrieve the list of sliced G-code files from BamBuddy.
2. **Pre-Print Safety Checks**:
   - Check hotend/nozzle temperature targets.
   - Check bed temperature targets.
   - Check chamber door requirement (closed for ABS/ASA, open/ventilated for PLA).
3. **AMS / Material Verification**:
   - Query AMS slots to identify loaded material types and colors.
   - Verify if Spoolman has weight/filament remaining.
   - Present checklist to user via chat card.
4. **Initiation**: Heat nozzle, heat bed, home axis, and start printing.
5. **Monitoring Loop**: Periodically query nozzle temperature, bed temperature, layer height, and completion percentage.
