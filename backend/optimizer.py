import numpy as np
from typing import Dict, Any, List, Tuple
from backend.model import PhysicsInformedMLModel
from backend.roi_calculator import ROICalculator

class UrbanHeatOptimizer:
    """
    Solves multi-objective urban heat mitigation optimization.
    Uses a Greedy Marginal Utility Knapsack Solver to allocate budget to interventions
    that maximize either raw physical cooling, socio-economic heat equity, or a balanced index.
    Generates a Pareto Frontier of solutions.
    """
    def __init__(self, model: PhysicsInformedMLModel, roi_calc: ROICalculator):
        self.model = model
        self.roi_calc = roi_calc
        
    def run_optimization(
        self,
        cells: List[Dict[str, Any]],
        weather: Dict[str, float],
        budget: float,
        strategy: str = "balanced"  # "efficiency_focused", "equity_focused", "balanced"
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Optimizes albedo and NDVI values across all cells within a budget constraint.
        Returns the modified cells list and aggregate ROI metrics.
        """
        # Copy cells to avoid inplace edits to baseline
        optimized_cells = [c.copy() for c in cells]
        
        # Track total cost allocated
        current_allocated_cost = 0.0
        
        # Define step increments for greedy optimization
        # We perform continuous optimization by adding small chunks of greening or albedo
        # until budget is exhausted.
        albedo_step = 0.10
        ndvi_step = 0.10
        
        # Max limits
        MAX_ALBEDO = 0.65
        MAX_NDVI = 0.80
        
        # First, precompute current temperatures for all cells
        for cell in optimized_cells:
            Ts, Ta, _ = self.model.predict_cell_temperatures(cell, weather, hour=12.0)
            cell["temp_surface_current"] = Ts
            cell["temp_air_current"] = Ta
            cell["albedo_original"] = cell["albedo"]
            cell["ndvi_original"] = cell["ndvi"]
            
        # We loop and greedily apply the single next-best step increment
        iteration = 0
        max_iterations = 2000  # safeguard
        
        while current_allocated_cost < budget and iteration < max_iterations:
            iteration += 1
            best_utility = -1.0
            best_cell_idx = -1
            best_action = None
            best_step_cost = 0.0
            best_temp_reduction = 0.0
            
            for idx, cell in enumerate(optimized_cells):
                # Ignore water bodies
                if cell["land_use"] == 'water':
                    continue
                    
                bd = cell["building_density"]
                svi = cell["svi"]
                
                # Option A: Increase Albedo (only if there are buildings/roofs to paint)
                if cell["albedo"] + albedo_step <= MAX_ALBEDO and bd > 0.05:
                    # Calculate cost of this specific step in this cell
                    step_cost = bd * self.roi_calc.CELL_AREA * albedo_step * self.roi_calc.COST_ALBEDO_M2
                    
                    if current_allocated_cost + step_cost <= budget:
                        # Simulate the temperature reduction
                        temp_cell = cell.copy()
                        temp_cell["albedo"] += albedo_step
                        Ts_new, _, _ = self.model.predict_cell_temperatures(temp_cell, weather, hour=12.0)
                        temp_reduction = cell["temp_surface_current"] - Ts_new
                        
                        # Calculate utility based on strategy
                        if strategy == "efficiency_focused":
                            utility = temp_reduction / step_cost
                        elif strategy == "equity_focused":
                            # Prioritize high demographic vulnerability areas
                            utility = (temp_reduction * (svi + 0.1)) / step_cost
                        else:  # balanced
                            utility = (temp_reduction * (0.5 + 0.5 * svi)) / step_cost
                            
                        if utility > best_utility and temp_reduction > 0:
                            best_utility = utility
                            best_cell_idx = idx
                            best_action = "albedo"
                            best_step_cost = step_cost
                            best_temp_reduction = temp_reduction
                            
                # Option B: Increase NDVI (greening)
                if cell["ndvi"] + ndvi_step <= MAX_NDVI:
                    # Greening applies to open area
                    step_cost = self.roi_calc.CELL_AREA * ndvi_step * self.roi_calc.COST_GREEN_M2
                    
                    if current_allocated_cost + step_cost <= budget:
                        # Simulate temperature reduction
                        temp_cell = cell.copy()
                        temp_cell["ndvi"] += ndvi_step
                        Ts_new, _, _ = self.model.predict_cell_temperatures(temp_cell, weather, hour=12.0)
                        temp_reduction = cell["temp_surface_current"] - Ts_new
                        
                        # Calculate utility based on strategy
                        if strategy == "efficiency_focused":
                            utility = temp_reduction / step_cost
                        elif strategy == "equity_focused":
                            utility = (temp_reduction * (svi + 0.1)) / step_cost
                        else:  # balanced
                            utility = (temp_reduction * (0.5 + 0.5 * svi)) / step_cost
                            
                        if utility > best_utility and temp_reduction > 0:
                            best_utility = utility
                            best_cell_idx = idx
                            best_action = "ndvi"
                            best_step_cost = step_cost
                            best_temp_reduction = temp_reduction
            
            # If we found an action that fits budget and improves temperature, apply it
            if best_cell_idx != -1 and best_utility > 0:
                cell_to_modify = optimized_cells[best_cell_idx]
                if best_action == "albedo":
                    cell_to_modify["albedo"] += albedo_step
                elif best_action == "ndvi":
                    cell_to_modify["ndvi"] += ndvi_step
                    
                # Update current temperature of this cell in our tracking
                cell_to_modify["temp_surface_current"] -= best_temp_reduction
                current_allocated_cost += best_step_cost
            else:
                # No more viable improvements under budget
                break
                
        # Run a final full simulation across all cells to capture smooth spatial microclimate adjustments
        final_cells = []
        for cell in optimized_cells:
            # Re-predict using the model to get exact corrected temperatures and energy fluxes
            Ts, Ta, fluxes = self.model.predict_cell_temperatures(cell, weather, hour=12.0)
            
            # Calculate driver attributions for the final state
            drivers = self.model.compute_local_drivers(cell, weather)
            
            final_cell = cell.copy()
            final_cell["albedo_delta"] = float(cell["albedo"] - cell["albedo_original"])
            final_cell["ndvi_delta"] = float(cell["ndvi"] - cell["ndvi_original"])
            final_cell["temp_surface"] = float(Ts)
            final_cell["temp_air"] = float(Ta)
            final_cell["fluxes"] = fluxes
            final_cell["drivers"] = drivers
            final_cells.append(final_cell)
            
        # Calculate full ROI details
        roi_summary = self.roi_calc.calculate_scenario_roi(cells, final_cells)
        roi_summary["strategy_selected"] = strategy
        roi_summary["actual_cost_allocated"] = float(current_allocated_cost)
        
        return final_cells, roi_summary

    def generate_pareto_frontier(
        self,
        cells: List[Dict[str, Any]],
        weather: Dict[str, float],
        max_budget: float
    ) -> List[Dict[str, Any]]:
        """
        Generates different optimal runs (low/med/high budget combined with different strategies)
        to construct a Pareto Frontier demonstrating cost vs. heat risk mitigation trade-offs.
        """
        frontier = []
        
        # Test 3 strategies: equitable, efficient, balanced
        strategies = ["efficiency_focused", "equity_focused", "balanced"]
        # Test 4 budget steps: 15%, 40%, 70%, 100% of max budget
        budget_fractions = [0.15, 0.40, 0.70, 1.0]
        
        # Add baseline (0 budget)
        baseline_temp = np.mean([c.get("temp_surface", 35.0) for c in cells])
        
        for strat in strategies:
            for frac in budget_fractions:
                b_val = float(max_budget * frac)
                # Solve optimization
                _, summary = self.run_optimization(cells, weather, b_val, strategy=strat)
                
                # Calculate mean surface temperature reduction across the entire city
                cost = summary["actual_cost_allocated"]
                total_savings = summary["total_annual_savings"]
                payback = summary["payback_years"]
                
                frontier.append({
                    "strategy": strat,
                    "budget_limit": b_val,
                    "cost_allocated": cost,
                    "total_annual_savings": total_savings,
                    "payback_years": payback,
                    "carbon_offset_tons": summary["annual_carbon_saved_tons"],
                    "stormwater_m3": summary["annual_stormwater_retained_m3"],
                    "energy_saved_kwh": summary["annual_energy_saved_kwh"]
                })
                
        return frontier
