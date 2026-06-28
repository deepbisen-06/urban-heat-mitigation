import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from typing import Dict, Any, List, Tuple
from backend.physics import ThermodynamicSolver

class PhysicsInformedMLModel:
    """
    A Hybrid Physics-Informed Geospatial ML Model.
    Uses Machine Learning to predict local air microclimate adjustments (Ta_local) 
    based on urban density features, then applies the thermodynamic solver to solve 
    for the exact Surface Temperature (Ts) ensuring energy conservation.
    """
    def __init__(self, solver: ThermodynamicSolver):
        self.solver = solver
        # ML model to predict local air temperature deviation from ambient regional temperature
        self.air_temp_model = RandomForestRegressor(n_estimators=30, random_state=42)
        self.is_trained = False
        
    def prepare_training_data(self, cells: List[Dict[str, Any]], weather: Dict[str, float]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Creates features and targets for training.
        Features: albedo, ndvi, building_density, building_height, sky_view_factor
        Target: local air temperature (simulated with physical microclimatic offsets)
        """
        X = []
        y = []
        
        ambient_ta = weather["air_temp_noon"]
        
        for cell in cells:
            albedo = cell["albedo"]
            ndvi = cell["ndvi"]
            bd = cell["building_density"]
            bh = cell["building_height"]
            svf = cell["sky_view_factor"]
            
            # Formulate features
            X.append([albedo, ndvi, bd, bh, svf])
            
            # Real-world microclimate physics:
            # - High building density and low SVF trap longwave radiation, heating the local air.
            # - High vegetation (NDVI) cools the local air via evapotranspiration.
            # - Low albedo (dark roads/roofs) heats the surrounding air.
            microclimate_offset = (5.0 * bd) - (3.5 * ndvi) - (2.0 * albedo) + (1.5 * (1.0 - svf))
            # Add some thermal noise
            offset_noise = np.random.normal(0, 0.2)
            
            y.append(ambient_ta + microclimate_offset + offset_noise)
            
        return np.array(X), np.array(y)
        
    def train(self, cells: List[Dict[str, Any]], weather: Dict[str, float]):
        """
        Trains the microclimatic ML regressor.
        """
        X, y = self.prepare_training_data(cells, weather)
        self.air_temp_model.fit(X, y)
        self.is_trained = True
        
    def predict_cell_temperatures(
        self,
        cell: Dict[str, Any],
        weather: Dict[str, float],
        hour: float = 12.0
    ) -> Tuple[float, float, Dict[str, float]]:
        """
        Predicts local Air Temperature (Ta) via ML, then solves for Surface Temperature (Ts) 
        using the Thermodynamic Solver.
        Returns: Ts (Surface), Ta (Air), and Energy Fluxes.
        """
        albedo = cell["albedo"]
        ndvi = cell["ndvi"]
        bd = cell["building_density"]
        bh = cell["building_height"]
        svf = cell["sky_view_factor"]
        land_use = cell["land_use"]
        
        # 1. Predict microclimatic air temperature adjustment using ML if trained
        if self.is_trained:
            features = np.array([[albedo, ndvi, bd, bh, svf]])
            Ta_local = float(self.air_temp_model.predict(features)[0])
        else:
            # Fallback mathematical model if not trained
            ambient_ta = weather["air_temp_noon"]
            microclimate_offset = (5.0 * bd) - (3.5 * ndvi) - (2.0 * albedo) + (1.5 * (1.0 - svf))
            Ta_local = ambient_ta + microclimate_offset
            
        # Adjust air temperature dynamically for diurnal simulation if hour is not noon
        if hour != 12.0:
            # Apply diurnal sine curve shift relative to noon air temperature
            Ta_local = Ta_local - 6.0 + 6.0 * np.sin((hour - 9.0) * np.pi / 12.0)

        # 2. Get diurnal solar, humidity, sky temperature conditions
        solar_noon = weather["solar_radiation"]
        if 6.0 <= hour <= 18.0:
            solar = solar_noon * np.sin((hour - 6.0) * np.pi / 12.0)
        else:
            solar = 0.0
            
        rh_noon = weather["relative_humidity"]
        rh = min(0.95, max(0.1, rh_noon + 0.20 * (1.0 - np.sin((hour - 9.0) * np.pi / 12.0))))
        
        sky_t_noon = weather["sky_temp"]
        sky_t = sky_t_noon - 3.0 + 3.0 * np.sin((hour - 9.0) * np.pi / 12.0)
        
        # 3. Solve for surface equilibrium temperature (Thermodynamic Physics Core)
        Ts, fluxes = self.solver.solve_equilibrium_temperature(
            albedo=albedo,
            ndvi=ndvi,
            building_density=bd,
            building_height=bh,
            sky_view_factor=svf,
            air_temp=Ta_local,
            rel_humidity=rh,
            wind_speed=weather["wind_speed"],
            solar_rad=solar,
            sky_temp=sky_t,
            land_use=land_use,
            hour=hour
        )
        # Add Wet Bulb Globe Temperature to fluxes
        fluxes["wbgt"] = float(self.solver.calculate_wbgt(Ta_local, rh, Ts, solar))
        
        return Ts, Ta_local, fluxes

    def compute_local_drivers(
        self,
        cell: Dict[str, Any],
        weather: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Explainable AI: Computes local driver attribution (similar to SHAP/LIME) 
        using local numerical perturbation.
        Measures how much each parameter (albedo, ndvi, building density) drives the surface 
        temperature above a "cool climate baseline" (e.g. albedo=0.45, ndvi=0.7, bd=0.05).
        """
        # Baseline reference parameters for a "fully cooled/mitigated" ideal cell
        ref_albedo = 0.45
        ref_ndvi = 0.60
        ref_bd = 0.05
        
        # Get baseline prediction for the current state
        Ts_current, _, _ = self.predict_cell_temperatures(cell, weather, hour=12.0)
        
        # Compute marginal impact by perturbing towards reference
        # Driver 1: Albedo contribution
        cell_alt_albedo = cell.copy()
        cell_alt_albedo["albedo"] = ref_albedo
        Ts_alt_albedo, _, _ = self.predict_cell_temperatures(cell_alt_albedo, weather, hour=12.0)
        albedo_contribution = Ts_current - Ts_alt_albedo  # Positive means low albedo caused warming
        
        # Driver 2: NDVI (vegetation) contribution
        cell_alt_ndvi = cell.copy()
        cell_alt_ndvi["ndvi"] = ref_ndvi
        Ts_alt_ndvi, _, _ = self.predict_cell_temperatures(cell_alt_ndvi, weather, hour=12.0)
        ndvi_contribution = Ts_current - Ts_alt_ndvi      # Positive means lack of vegetation caused warming
        
        # Driver 3: Building Density contribution
        cell_alt_bd = cell.copy()
        cell_alt_bd["building_density"] = ref_bd
        cell_alt_bd["sky_view_factor"] = 0.90            # SVF improves as BD drops
        Ts_alt_bd, _, _ = self.predict_cell_temperatures(cell_alt_bd, weather, hour=12.0)
        bd_contribution = Ts_current - Ts_alt_bd          # Positive means high concrete density caused warming
        
        # Normalize contributions to sum to total temperature difference above reference
        ref_cell = cell.copy()
        ref_cell["albedo"] = ref_albedo
        ref_cell["ndvi"] = ref_ndvi
        ref_cell["building_density"] = ref_bd
        ref_cell["sky_view_factor"] = 0.90
        Ts_ref, _, _ = self.predict_cell_temperatures(ref_cell, weather, hour=12.0)
        
        total_excess_heat = max(0.1, Ts_current - Ts_ref)
        
        # Relative weights
        contribs = np.array([albedo_contribution, ndvi_contribution, bd_contribution])
        # Force positive weights since we are explaining "excess" heat
        contribs = np.clip(contribs, 0.0, None)
        total_contrib = np.sum(contribs)
        
        if total_contrib > 0:
            contrib_shares = contribs / total_contrib
            albedo_attr = contrib_shares[0] * total_excess_heat
            ndvi_attr = contrib_shares[1] * total_excess_heat
            bd_attr = contrib_shares[2] * total_excess_heat
        else:
            albedo_attr, ndvi_attr, bd_attr = 0.0, 0.0, 0.0
            
        return {
            "albedo_attribution_celsius": float(round(albedo_attr, 2)),
            "ndvi_attribution_celsius": float(round(ndvi_attr, 2)),
            "density_attribution_celsius": float(round(bd_attr, 2)),
            "total_excess_heat": float(round(total_excess_heat, 2))
        }
