import numpy as np
from scipy.optimize import brentq
from typing import Dict, Any, Tuple, List

class ThermodynamicSolver:
    """
    Thermodynamic energy balance solver for urban surfaces.
    Solves for Surface Temperature (Ts) using:
      Rn - H - LE - G = 0
    """
    
    # Constants
    SIGMA = 5.67e-8  # Stefan-Boltzmann constant (W/m^2/K^4)
    RHO_AIR = 1.2    # Air density (kg/m^3)
    CP_AIR = 1005.0  # Specific heat capacity of air (J/kg/K)
    
    def __init__(self):
        pass

    def compute_aerodynamic_resistance(self, wind_speed: float, building_density: float, building_height: float) -> float:
        """
        Calculates aerodynamic resistance (ra) in s/m.
        In dense urban environments, buildings create friction which reduces local wind speed,
        thereby increasing ra and slowing convective heat dissipation.
        """
        # Base aerodynamic roughness parameters
        z_disp = 0.6 * building_height * building_density       # Zero plane displacement height
        z_ref = max(10.0, z_disp + 10.0)                        # Reference height of wind measurements (m)
        z_zero = 0.1 + 0.1 * building_height * building_density  # Roughness length increases with height & density
        
        # Clip values to keep log functions stable
        z_zero = np.clip(z_zero, 0.01, z_ref * 0.4)
        z_disp = np.clip(z_disp, 0.0, z_ref * 0.8)
        
        # von Karman constant
        kappa = 0.4
        
        # Effective wind speed at displacement height
        u_eff = max(wind_speed, 0.1)  # Avoid division by zero
        
        # Aerodynamic resistance formula based on logarithmic wind profile
        log_term_m = np.log((z_ref - z_disp) / z_zero)
        log_term_h = np.log((z_ref - z_disp) / (0.1 * z_zero))  # Roughness length for heat is approx 0.1 * z_zero
        
        ra = (log_term_m * log_term_h) / (kappa**2 * u_eff)
        
        # Clamp to realistic bounds (10 s/m for open high wind, 500 s/m for stagnant street canyon)
        return float(np.clip(ra, 15.0, 450.0))

    def compute_energy_balance_components(
        self,
        Ts_C: float,            # Surface temperature in Celsius
        albedo: float,
        ndvi: float,
        building_density: float,
        building_height: float,
        sky_view_factor: float,
        air_temp: float,        # Air temperature in Celsius
        rel_humidity: float,
        wind_speed: float,
        solar_rad: float,       # Solar downwelling radiation (W/m^2)
        sky_temp: float,        # Sky temperature (C) for longwave downwelling
        land_use: str = "residential",
        hour: float = 12.0      # Hour of day (0-24)
    ) -> Dict[str, float]:
        """
        Computes all energy fluxes (W/m^2) for a given surface temperature (Ts).
        Positive values represent energy fluxes AWAY from the surface.
        """
        # Convert temperatures to Kelvin
        Ts_K = Ts_C + 273.15
        Ta_K = air_temp + 273.15
        Tsky_K = sky_temp + 273.15
        
        # 1. Net Shortwave Radiation (S_net)
        # S_net = (1 - albedo) * solar_radiation. Solar radiation is shaded by building canyons
        # Shading factor is modeled via sky_view_factor
        effective_solar = solar_rad * (sky_view_factor if land_use != 'water' else 1.0)
        S_net = (1.0 - albedo) * effective_solar
        
        # 2. Net Longwave Radiation (L_net)
        # Downward atmospheric longwave
        emissivity_atm = 0.70 + 5.95e-5 * (rel_humidity * 100)  # simple empirical humidity correlation
        L_down = emissivity_atm * self.SIGMA * Tsky_K**4
        # Upward surface longwave
        emissivity_surf = 0.98 if land_use == 'water' else (0.90 + 0.10 * max(0.0, ndvi))
        L_up = emissivity_surf * self.SIGMA * Ts_K**4
        
        Rn = S_net + L_down - L_up
        
        # 3. Sensible Heat Flux (H)
        ra = self.compute_aerodynamic_resistance(wind_speed, building_density, building_height)
        H = (self.RHO_AIR * self.CP_AIR * (Ts_C - air_temp)) / ra
        
        # 4. Latent Heat Flux (LE)
        # Potential Evapotranspiration (PET) under peak conditions
        PET_base = 350.0  # W/m^2 potential max at noon
        if land_use == 'water':
            LE = PET_base * (1.0 - rel_humidity)  # Open evaporation driven by dryness
        else:
            # Latent heat driven by active transpiration (NDVI) and relative humidity
            vegetation_transpiration = max(0.0, ndvi)
            LE = vegetation_transpiration * PET_base * (1.0 - rel_humidity)
            
        # 5. Ground Heat Flux (G)
        # During peak solar noon, concrete/built spaces store massive heat (high G)
        # We model this ground coefficient (mu) based on land use and density
        if land_use == 'water':
            mu = 0.15
        elif land_use == 'park':
            mu = 0.10
        elif land_use == 'industrial':
            mu = 0.35  # asphalt, factory roofs
        elif land_use == 'commercial':
            mu = 0.30  # dense concrete
        else:
            # residential scales with density
            mu = 0.15 + 0.15 * building_density
            
        # For diurnal transient simulation, G varies with hour:
        # Solar noon (12:00) is peak storage. Night has heat release (negative G)
        diurnal_factor = np.cos((hour - 12.0) * np.pi / 12.0)  # +1 at noon, -1 at midnight
        
        # G = mu * Rn (modified by diurnal phase)
        G = mu * Rn * max(0.1, diurnal_factor) if diurnal_factor > 0 else mu * Rn * 0.3 * diurnal_factor
        
        # Thermodynamic residual (should be 0 when Ts is fully solved)
        residual = Rn - H - LE - G
        
        return {
            "Rn": float(Rn),
            "H": float(H),
            "LE": float(LE),
            "G": float(G),
            "residual": float(residual),
            "ra": float(ra)
        }

    def solve_equilibrium_temperature(
        self,
        albedo: float,
        ndvi: float,
        building_density: float,
        building_height: float,
        sky_view_factor: float,
        air_temp: float,
        rel_humidity: float,
        wind_speed: float,
        solar_rad: float,
        sky_temp: float,
        land_use: str = "residential",
        hour: float = 12.0
    ) -> Tuple[float, Dict[str, float]]:
        """
        Solves for the Surface Temperature (Ts) that yields energy balance closure (residual = 0).
        Uses a highly optimized Newton-Raphson solver for instant convergence.
        """
        # Initial guess: air temperature + solar radiation scaling
        solar_offset = (solar_rad / 800.0) * 12.0 if solar_rad > 0 else -2.0
        Ts_solved = air_temp + solar_offset
        
        # 4 iterations of Newton-Raphson are enough to reach high precision (< 0.001 K error)
        for _ in range(4):
            fluxes = self.compute_energy_balance_components(
                Ts_solved, albedo, ndvi, building_density, building_height,
                sky_view_factor, air_temp, rel_humidity, wind_speed,
                solar_rad, sky_temp, land_use, hour
            )
            
            # Derivative df/dTs calculation
            Ts_K = Ts_solved + 273.15
            emissivity_surf = 0.98 if land_use == 'water' else (0.90 + 0.10 * max(0.0, ndvi))
            
            # Ground heat flux coefficient
            if land_use == 'water':
                mu = 0.15
            elif land_use == 'park':
                mu = 0.10
            elif land_use == 'industrial':
                mu = 0.35
            elif land_use == 'commercial':
                mu = 0.30
            else:
                mu = 0.15 + 0.15 * building_density
                
            diurnal_factor = np.cos((hour - 12.0) * np.pi / 12.0)
            mu_eff = mu * max(0.1, diurnal_factor) if diurnal_factor > 0 else mu * 0.3 * diurnal_factor
            
            # dRn/dTs = -4 * emissivity_surf * SIGMA * Ts^3
            dRn_dTs = -4.0 * emissivity_surf * self.SIGMA * Ts_K**3
            # dH/dTs = RHO_AIR * CP_AIR / ra
            ra = fluxes["ra"]
            dH_dTs = (self.RHO_AIR * self.CP_AIR) / ra
            
            # df/dTs = (1 - mu_eff) * dRn_dTs - dH/dTs
            df_dTs = (1.0 - mu_eff) * dRn_dTs - dH_dTs
            
            # Newton step
            f = fluxes["residual"]
            if abs(df_dTs) > 1e-4:
                Ts_solved -= f / df_dTs
            else:
                break
                
        # Final evaluation
        fluxes = self.compute_energy_balance_components(
            Ts_solved, albedo, ndvi, building_density, building_height,
            sky_view_factor, air_temp, rel_humidity, wind_speed,
            solar_rad, sky_temp, land_use, hour
        )
        return float(Ts_solved), fluxes

    def calculate_wbgt(self, air_temp: float, rel_humidity: float, surface_temp: float, solar_rad: float) -> float:
        """
        Calculates a simplified outdoor Wet Bulb Globe Temperature (WBGT) in Celsius.
        WBGT = 0.7 * T_nw (Natural Wet Bulb) + 0.2 * T_g (Globe Temperature) + 0.1 * T_d (Dry bulb air temp)
        This is a standard human heat stress metric.
        """
        # 1. Estimate Natural Wet Bulb Temperature (T_nw) using Stull's formula (empirical approximation)
        T_d = air_temp
        RH_pct = rel_humidity * 100.0
        T_nw = T_d * np.arctan(0.151977 * (RH_pct + 8.313659)**0.5) + np.arctan(T_d + RH_pct) - np.arctan(RH_pct - 1.676331) + 0.00391838 * (RH_pct)**1.5 * np.arctan(0.023101 * RH_pct) - 4.686035
        
        # 2. Globe Temperature (T_g) represents radiant heat.
        # It is driven by air temperature, solar radiation, and ground surface temperature.
        # Simple empirical approximation:
        T_g = 0.6 * air_temp + 0.3 * surface_temp + 0.1 * (solar_rad / 100.0)
        
        wbgt = 0.7 * T_nw + 0.2 * T_g + 0.1 * T_d
        return float(wbgt)

    def simulate_diurnal_cycle(
        self,
        albedo: float,
        ndvi: float,
        building_density: float,
        building_height: float,
        sky_view_factor: float,
        weather_base: Dict[str, float],
        land_use: str = "residential"
    ) -> Dict[str, List[float]]:
        """
        Simulates a 24-hour cycle of surface energy balance and temperature variation.
        Generates realistic ambient cycles for solar radiation, air temp, and sky temp.
        """
        hours = np.linspace(0, 23, 24)
        temps = []
        rn_fluxes = []
        h_fluxes = []
        le_fluxes = []
        g_fluxes = []
        
        air_temp_noon = weather_base["air_temp_noon"]
        rh_noon = weather_base["relative_humidity"]
        wind = weather_base["wind_speed"]
        solar_noon = weather_base["solar_radiation"]
        sky_temp_noon = weather_base["sky_temp"]
        
        for hour in hours:
            # Model air temperature variation (typical sinusoidal curve peaking at 15:00)
            air_t = air_temp_noon - 6.0 + 6.0 * np.sin((hour - 9.0) * np.pi / 12.0)
            
            # Solar radiation profile (positive only between 6:00 and 18:00)
            if 6.0 <= hour <= 18.0:
                solar = solar_noon * np.sin((hour - 6.0) * np.pi / 12.0)
            else:
                solar = 0.0
                
            # Relative humidity has inverse relation to temperature
            rh = min(0.95, max(0.1, rh_noon + 0.20 * (1.0 - np.sin((hour - 9.0) * np.pi / 12.0))))
            
            # Sky temp diurnal shift
            sky_t = sky_temp_noon - 3.0 + 3.0 * np.sin((hour - 9.0) * np.pi / 12.0)
            
            # Solve for Ts
            Ts, fluxes = self.solve_equilibrium_temperature(
                albedo, ndvi, building_density, building_height, sky_view_factor,
                air_t, rh, wind, solar, sky_t, land_use, hour
            )
            
            temps.append(Ts)
            rn_fluxes.append(fluxes["Rn"])
            h_fluxes.append(fluxes["H"])
            le_fluxes.append(fluxes["LE"])
            g_fluxes.append(fluxes["G"])
            
        return {
            "hours": hours.tolist(),
            "surface_temp": temps,
            "Rn": rn_fluxes,
            "H": h_fluxes,
            "LE": le_fluxes,
            "G": g_fluxes
        }
