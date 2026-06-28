import numpy as np
from typing import Dict, Any, List

class ROICalculator:
    """
    Computes economic cost-benefit analysis and ROI for urban heat mitigation strategies.
    Covers greening (canopy/parks/green roofs) and albedo improvements (cool roofs/pavements).
    """
    
    # Financial and physical constants (default USD-based, configurable)
    COST_GREEN_M2 = 65.0      # USD per m2 of green roof or canopy installation
    COST_ALBEDO_M2 = 18.0     # USD per m2 of cool reflective coating application
    
    ENERGY_COST_KWH = 0.15    # USD per kWh of electricity
    CARBON_VAL_TON = 45.0     # USD value per metric ton of CO2 offset
    STORMWATER_VAL_M3 = 2.20  # USD saved in municipal stormwater treatment per m3 retained
    
    # Grid parameters
    CELL_LENGTH = 100.0       # 100m grid cell length
    CELL_AREA = 10000.0       # 10,000 m2 total cell area
    
    # Savings coefficients
    # Cool roofs save energy: ~12.5 kWh/year per m2 of roof for each 0.1 albedo increase
    ALBEDO_AC_SAVING_FACTOR = 12.5
    # Vegetative shading saves energy: ~8.0 kWh/year per m2 for each 0.1 NDVI increase (shading + air cooling)
    VEG_AC_SAVING_FACTOR = 8.0
    # Carbon absorption: ~1.5 kg CO2 per m2 per year for each 0.1 NDVI increase
    VEG_CARBON_COEF = 1.5
    # Stormwater absorption: ~0.45 m3 per m2 per year retained for each 0.1 NDVI increase
    VEG_STORMWATER_COEF = 0.45

    def __init__(self, energy_rate: float = ENERGY_COST_KWH, currency_symbol: str = "$"):
        self.energy_cost = energy_rate
        self.currency_symbol = currency_symbol

    def calculate_cell_roi(
        self,
        building_density: float,
        delta_albedo: float,     # Increase in albedo (0.0 to 0.7)
        delta_ndvi: float,       # Increase in NDVI (0.0 to 0.8)
    ) -> Dict[str, float]:
        """
        Calculates construction costs and annual operational savings for a single grid cell.
        """
        # 1. Calculate affected area
        # We assume albedo changes apply primarily to rooftops (commercial/residential buildings)
        # rooftop area = building density * total grid area
        rooftop_area = building_density * self.CELL_AREA
        # Greening changes apply to available open ground space AND roof space (green roofs)
        # Max greenable area = (1.0 - building density + building_density * 0.4) * CELL_AREA
        # Let's simplify: area greened = delta_ndvi * self.CELL_AREA
        greened_area = max(0.0, delta_ndvi) * self.CELL_AREA
        
        # 2. Capital Costs
        cost_albedo = rooftop_area * max(0.0, delta_albedo) * self.COST_ALBEDO_M2
        cost_green = greened_area * self.COST_GREEN_M2
        total_cost = cost_albedo + cost_green
        
        # 3. Annual Benefits / Savings
        # AC Energy Savings
        # Albedo effect: 10 * delta_albedo gives albedo shift in units of 0.1
        albedo_energy_savings = rooftop_area * (delta_albedo * 10) * self.ALBEDO_AC_SAVING_FACTOR
        # Greening effect:
        veg_energy_savings = greened_area * (delta_ndvi * 10) * self.VEG_AC_SAVING_FACTOR
        total_energy_saved_kwh = albedo_energy_savings + veg_energy_savings
        energy_savings_usd = total_energy_saved_kwh * self.energy_cost
        
        # Carbon Sequestration
        carbon_saved_kg = greened_area * (delta_ndvi * 10) * self.VEG_CARBON_COEF
        carbon_saved_tons = carbon_saved_kg / 1000.0
        carbon_savings_usd = carbon_saved_tons * self.CARBON_VAL_TON
        
        # Stormwater Retention
        stormwater_retained_m3 = greened_area * (delta_ndvi * 10) * self.VEG_STORMWATER_COEF
        stormwater_savings_usd = stormwater_retained_m3 * self.STORMWATER_VAL_M3
        
        # Total annual financial benefits
        annual_savings = energy_savings_usd + carbon_savings_usd + stormwater_savings_usd
        
        # Payback period calculation
        payback = total_cost / annual_savings if annual_savings > 0 else 999.0
        payback = min(99.0, payback)
        
        return {
            "capital_cost": float(total_cost),
            "annual_energy_saved_kwh": float(total_energy_saved_kwh),
            "annual_energy_savings": float(energy_savings_usd),
            "annual_carbon_saved_tons": float(carbon_saved_tons),
            "annual_carbon_savings": float(carbon_savings_usd),
            "annual_stormwater_retained_m3": float(stormwater_retained_m3),
            "annual_stormwater_savings": float(stormwater_savings_usd),
            "total_annual_savings": float(annual_savings),
            "payback_years": float(round(payback, 1))
        }

    def calculate_scenario_roi(self, baseline_cells: List[Dict[str, Any]], modified_cells: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregates costs and benefits across all modified cells in a scenario.
        """
        total_cost = 0.0
        total_energy_kwh = 0.0
        total_energy_usd = 0.0
        total_carbon_tons = 0.0
        total_carbon_usd = 0.0
        total_stormwater_m3 = 0.0
        total_stormwater_usd = 0.0
        total_savings = 0.0
        
        # Create map of baseline for fast lookup
        baseline_map = {c["id"]: c for c in baseline_cells}
        
        for m_cell in modified_cells:
            cell_id = m_cell["id"]
            if cell_id not in baseline_map:
                continue
                
            b_cell = baseline_map[cell_id]
            
            # Detect changes
            delta_albedo = max(0.0, m_cell["albedo"] - b_cell["albedo"])
            delta_ndvi = max(0.0, m_cell["ndvi"] - b_cell["ndvi"])
            
            if delta_albedo > 1e-4 or delta_ndvi > 1e-4:
                cell_results = self.calculate_cell_roi(
                    building_density=b_cell.get("building_density", 0.4),
                    delta_albedo=delta_albedo,
                    delta_ndvi=delta_ndvi
                )
                
                total_cost += cell_results["capital_cost"]
                total_energy_kwh += cell_results["annual_energy_saved_kwh"]
                total_energy_usd += cell_results["annual_energy_savings"]
                total_carbon_tons += cell_results["annual_carbon_saved_tons"]
                total_carbon_usd += cell_results["annual_carbon_savings"]
                total_stormwater_m3 += cell_results["annual_stormwater_retained_m3"]
                total_stormwater_usd += cell_results["annual_stormwater_savings"]
                total_savings += cell_results["total_annual_savings"]
                
        payback = total_cost / total_savings if total_savings > 0 else 0.0
        roi_pct = (total_savings / total_cost) * 100.0 if total_cost > 0 else 0.0
        
        return {
            "currency_symbol": self.currency_symbol,
            "total_capital_cost": float(total_cost),
            "annual_energy_saved_kwh": float(total_energy_kwh),
            "annual_energy_savings": float(total_energy_usd),
            "annual_carbon_saved_tons": float(total_carbon_tons),
            "annual_carbon_savings": float(total_carbon_usd),
            "annual_stormwater_retained_m3": float(total_stormwater_m3),
            "annual_stormwater_savings": float(total_stormwater_usd),
            "total_annual_savings": float(total_savings),
            "payback_years": float(round(payback, 1)),
            "roi_percentage": float(round(roi_pct, 1))
        }
