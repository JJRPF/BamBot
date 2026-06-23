import os
import random

class KaggricultureAgent:
    def __init__(self, farm_id: str):
        self.farm_id = farm_id
        self.crop_health = 100
        self.water_level = 50
        self.soil_nutrients = 75
        self.day = 1

    def get_state(self):
        return {
            "day": self.day,
            "crop_health": self.crop_health,
            "water_level": self.water_level,
            "soil_nutrients": self.soil_nutrients
        }

    def act(self, action: str):
        """
        Executes action for the day: 'water', 'fertilize', or 'wait'
        """
        print(f"Day {self.day} Action: {action.upper()}")
        
        # Simulate environment changes
        weather = random.choice(["sunny", "rainy", "drought"])
        print(f"Weather today: {weather.upper()}")
        
        if weather == "sunny":
            self.water_level -= 15
        elif weather == "rainy":
            self.water_level += 20
        elif weather == "drought":
            self.water_level -= 30
            self.crop_health -= 10
            
        if action == "water":
            self.water_level = min(100, self.water_level + 25)
        elif action == "fertilize":
            self.soil_nutrients = min(100, self.soil_nutrients + 20)
            self.water_level -= 5
        elif action == "wait":
            pass
            
        # Crop health check based on conditions
        if self.water_level < 20 or self.water_level > 90:
            self.crop_health -= 15
        if self.soil_nutrients < 30:
            self.crop_health -= 10
            
        self.crop_health = max(0, min(100, self.crop_health))
        self.day += 1
        return self.get_state()

if __name__ == "__main__":
    print("=== Starting Kaggriculture Simulation ===")
    agent = KaggricultureAgent(farm_id="farm_sector_7")
    
    # 5-day mock run
    for i in range(5):
        state = agent.get_state()
        print(f"Current State: {state}")
        # Simple threshold policy
        if state["water_level"] < 40:
            action = "water"
        elif state["soil_nutrients"] < 50:
            action = "fertilize"
        else:
            action = "wait"
        new_state = agent.act(action)
        print(f"New State: {new_state}\n" + "-"*30)
