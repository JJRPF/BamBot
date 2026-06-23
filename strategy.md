# Kaggriculture Autonomous Loop Strategy

This document outlines the design pattern and policy rules for our simulation agent participating in the Kaggriculture simulation challenge.

## Core Autonomous Agent Loop

The agent operates on a sense-plan-act loop:
1. **Observation (Sense)**: Retrieve current crop health, weather forecasts, water levels, and soil nutrient levels.
2. **Evaluation (Plan)**: 
   - Parse weather forecasting to predict water depreciation rates.
   - Run short-horizon lookahead simulation.
   - Weigh utility of watering vs. fertilizing vs. conserving resources.
3. **Execution (Act)**: Issue command to environment API.

## Control Rules & Policy Decisions

- **Watering Policy**: If water levels drop below 35% or drought is forecasted next day, prioritize `water`.
- **Nutrient Policy**: Maintain `soil_nutrients` above 50% using `fertilize`.
- **Health Preservation**: If `crop_health` is deteriorating rapidly (<70%), trigger emergency intervention strategies.

## Gemini Reasoning API Integration

We will use the Gemini API to dynamically adjust target thresholds based on contextual textual weather alerts (e.g. "heatwave warning issued for next 3 days").
