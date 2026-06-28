import numpy as np
import pandas as pd
import json
import os
from typing import Dict, Any, List, Optional

class GeospatialDataManager:
    def __init__(self, output_dir: str = "data"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
    def generate_synthetic_city(self, profile: str = "dense_highrise", grid_size: int = 40) -> Dict[str, Any]:
        """
        Generates a high-fidelity synthetic city grid representing different microclimatic and urban morphological archetypes.
        Profiles:
          - 'dense_highrise' (e.g., Singapore/Manhattan): High building density, low SVF, medium albedo, medium NDVI.
          - 'arid_inland' (e.g., Delhi/Phoenix): Low humidity, high solar radiation, low NDVI, high albedo variation.
          - 'tropical_coastal' (e.g., Mumbai/Chennai): High humidity, low diurnal range, sea-breeze correlation.
        """
        np.random.seed(42)  # For reproducibility
        
        # Grid dimensions
        rows, cols = grid_size, grid_size
        
        # Base coordinate reference system (mock Lat/Lon bounds for a city center)
        base_lat, base_lon = 19.0760, 72.8777  # Mumbai-like coordinates by default
        if profile == "arid_inland":
            base_lat, base_lon = 28.6139, 77.2090  # Delhi-like coordinates
        elif profile == "dense_highrise":
            base_lat, base_lon = 1.3521, 103.8198  # Singapore-like coordinates
            
        lat_step = 0.001  # approx 110 meters per grid cell
        lon_step = 0.001
        
        # Create grids
        x_coords, y_coords = np.meshgrid(np.arange(cols), np.arange(rows))
        latitudes = base_lat + y_coords * lat_step
        longitudes = base_lon + x_coords * lon_step
        
        # Create urban elements: rivers, parks, commercial cores, industrial hubs, residential zones
        land_use = np.empty((rows, cols), dtype=object)
        
        # Let's model a river/water body flowing through the city
        # River curve: x = cols/2 + amplitude * sin(y/wavelength)
        river_amplitude = cols * 0.15
        river_wavelength = rows * 0.4
        river_x = (cols / 2) + river_amplitude * np.sin(y_coords / river_wavelength)
        is_water = np.abs(x_coords - river_x) < (cols * 0.06)
        
        # Let's model a large central park
        park_center_y, park_center_x = rows // 2, cols // 3
        is_park = ((y_coords - park_center_y)**2 + (x_coords - park_center_x)**2) < (rows * 0.15)**2
        
        # Commercial high-density core
        cbd_center_y, cbd_center_x = rows // 3, 2 * cols // 3
        is_cbd = ((y_coords - cbd_center_y)**2 + (x_coords - cbd_center_x)**2) < (rows * 0.2)**2
        
        # Industrial zone (low albedo, high concrete, low vegetation, far edge)
        is_industrial = (y_coords > 4 * rows // 5) & (x_coords > 3 * cols // 5)
        
        # Default land use assignment
        land_use[:] = 'residential'
        land_use[is_cbd] = 'commercial'
        land_use[is_industrial] = 'industrial'
        land_use[is_park] = 'park'
        land_use[is_water] = 'water'
        
        # Primary physical attributes dependent on land use and profile
        ndvi = np.zeros((rows, cols))
        albedo = np.zeros((rows, cols))
        building_density = np.zeros((rows, cols))
        building_height = np.zeros((rows, cols))
        sky_view_factor = np.zeros((rows, cols))
        
        # Demographics
        pop_density = np.zeros((rows, cols))  # people/sq km
        elderly_ratio = np.zeros((rows, cols))  # fraction
        avg_income = np.zeros((rows, cols))  # USD/year (scaled)

        for r in range(rows):
            for c in range(cols):
                lu = land_use[r, c]
                # Noise component
                noise = np.random.normal(0, 0.05)
                
                if lu == 'water':
                    ndvi[r, c] = max(-0.15, -0.1 + noise * 0.2)
                    albedo[r, c] = max(0.03, 0.06 + noise * 0.01)
                    building_density[r, c] = 0.0
                    building_height[r, c] = 0.0
                    sky_view_factor[r, c] = 1.0
                    pop_density[r, c] = 0
                    elderly_ratio[r, c] = 0
                    avg_income[r, c] = 0
                elif lu == 'park':
                    ndvi[r, c] = min(0.85, 0.7 + noise * 0.1)
                    albedo[r, c] = max(0.12, 0.18 + noise * 0.02)
                    building_density[r, c] = 0.02
                    building_height[r, c] = 2.0
                    sky_view_factor[r, c] = max(0.9, 0.95 + noise * 0.05)
                    pop_density[r, c] = min(200, max(0, int(100 + noise * 50)))
                    elderly_ratio[r, c] = 0.12
                    avg_income[r, c] = 75000
                elif lu == 'commercial':
                    ndvi[r, c] = min(0.2, max(0.02, 0.1 + noise * 0.05))
                    albedo[r, c] = max(0.08, 0.13 + noise * 0.03)
                    building_density[r, c] = min(0.95, 0.8 + noise * 0.05)
                    building_height[r, c] = max(20.0, 60.0 + noise * 20.0) if profile == "dense_highrise" else max(10.0, 30.0 + noise * 10.0)
                    sky_view_factor[r, c] = max(0.1, 0.35 - (building_height[r, c]/150.0))
                    pop_density[r, c] = int(12000 + noise * 3000)
                    elderly_ratio[r, c] = 0.16 + noise * 0.02
                    avg_income[r, c] = 110000 + noise * 10000
                elif lu == 'industrial':
                    ndvi[r, c] = min(0.15, max(0.0, 0.05 + noise * 0.03))
                    albedo[r, c] = max(0.06, 0.10 + noise * 0.02)  # dark roofs, asphalt
                    building_density[r, c] = min(0.9, 0.65 + noise * 0.1)
                    building_height[r, c] = max(6.0, 12.0 + noise * 3.0)
                    sky_view_factor[r, c] = max(0.4, 0.6 + noise * 0.08)
                    pop_density[r, c] = int(1500 + noise * 400)
                    elderly_ratio[r, c] = 0.08 + noise * 0.01
                    avg_income[r, c] = 45000 + noise * 5000
                else:  # residential
                    ndvi[r, c] = min(0.5, max(0.05, 0.3 + noise * 0.1))
                    albedo[r, c] = max(0.08, 0.14 + noise * 0.02)
                    building_density[r, c] = min(0.7, 0.5 + noise * 0.1)
                    building_height[r, c] = max(4.0, 12.0 + noise * 5.0)
                    sky_view_factor[r, c] = max(0.5, 0.7 - (building_density[r, c]*0.3))
                    # Add demographic variance: poor dense area vs wealthy green suburbs
                    is_suburban = (x_coords[r, c] < cols * 0.3) or (y_coords[r, c] < rows * 0.3)
                    if is_suburban and not is_park[r, c] and not is_water[r, c]:
                        ndvi[r, c] = min(0.6, ndvi[r, c] + 0.15)
                        avg_income[r, c] = 85000 + noise * 8000
                        pop_density[r, c] = int(4000 + noise * 1000)
                        elderly_ratio[r, c] = 0.20 + noise * 0.03
                    else:
                        avg_income[r, c] = 48000 + noise * 6000
                        pop_density[r, c] = int(18000 + noise * 4000)
                        elderly_ratio[r, c] = 0.14 + noise * 0.02

        # Apply spatial smoothing (simulating geospatial auto-correlation)
        def smooth_grid(grid, iterations=1):
            smoothed = np.copy(grid)
            for _ in range(iterations):
                for r in range(1, rows-1):
                    for c in range(1, cols-1):
                        neighbors = grid[r-1:r+2, c-1:c+2]
                        smoothed[r, c] = np.mean(neighbors)
            return smoothed
            
        ndvi = smooth_grid(ndvi, 1)
        albedo = smooth_grid(albedo, 1)
        building_density = smooth_grid(building_density, 1)
        
        # Enforce physical bounds
        ndvi = np.clip(ndvi, -0.2, 0.9)
        albedo = np.clip(albedo, 0.02, 0.85)
        building_density = np.clip(building_density, 0.0, 1.0)
        sky_view_factor = np.clip(sky_view_factor, 0.05, 1.0)
        
        # Generate cell data
        cells = []
        for r in range(rows):
            for c in range(cols):
                # Calculate SVI (Socio-Economic Vulnerability Index)
                # SVI = 0.4 * (Elderly ratio) + 0.3 * (normalized low income) + 0.3 * (normalized pop density)
                # Norms based on maximum reasonable values
                norm_elderly = min(1.0, elderly_ratio[r, c] / 0.35)
                norm_income = max(0.0, 1.0 - (avg_income[r, c] / 150000.0))
                norm_pop = min(1.0, pop_density[r, c] / 25000.0)
                
                svi = 0.4 * norm_elderly + 0.3 * norm_income + 0.3 * norm_pop
                # Water has 0 vulnerability
                if land_use[r, c] == 'water':
                    svi = 0.0
                
                cells.append({
                    "id": int(r * cols + c),
                    "x": int(c),
                    "y": int(r),
                    "lat": float(latitudes[r, c]),
                    "lon": float(longitudes[r, c]),
                    "land_use": str(land_use[r, c]),
                    "albedo": float(albedo[r, c]),
                    "ndvi": float(ndvi[r, c]),
                    "building_density": float(building_density[r, c]),
                    "building_height": float(building_height[r, c]),
                    "sky_view_factor": float(sky_view_factor[r, c]),
                    "population_density": float(pop_density[r, c]),
                    "elderly_ratio": float(elderly_ratio[r, c]),
                    "avg_income": float(avg_income[r, c]),
                    "svi": float(svi)
                })
                
        # Profile metadata
        meta = {
            "profile": profile,
            "grid_size": grid_size,
            "base_lat": base_lat,
            "base_lon": base_lon,
            "weather": self.get_profile_weather(profile)
        }
        
        return {"metadata": meta, "cells": cells}
        
    def get_profile_weather(self, profile: str) -> Dict[str, float]:
        """
        Returns typical meteorological boundary conditions for the urban microclimate solver.
        Values represent peak solar noon conditions.
        """
        if profile == "arid_inland":
            return {
                "air_temp_noon": 42.0,      # Extreme inland summer heat
                "relative_humidity": 0.15,  # Dry air
                "wind_speed": 3.0,          # Low convective cooling
                "solar_radiation": 950.0,   # Clear sky intense solar radiation (W/m^2)
                "sky_temp": 12.0            # Clean low RH sky has low downward longwave emission
            }
        elif profile == "dense_highrise":
            return {
                "air_temp_noon": 33.0,
                "relative_humidity": 0.75,  # Humid
                "wind_speed": 1.5,          # Low wind due to street friction/canyons
                "solar_radiation": 800.0,   # Tropical solar radiation
                "sky_temp": 22.0
            }
        else:  # tropical_coastal
            return {
                "air_temp_noon": 35.0,
                "relative_humidity": 0.65,
                "wind_speed": 4.5,          # Strong sea breeze
                "solar_radiation": 850.0,
                "sky_temp": 20.0
            }

    def load_custom_gis_data(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Ingests custom CSV or JSON grid files.
        File format expectation: CSV with headers (lat, lon, ndvi, albedo, built_density, SVF/SVI, etc.)
        """
        if not os.path.exists(file_path):
            return None
            
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            elif file_path.endswith('.json') or file_path.endswith('.geojson'):
                with open(file_path, 'r') as f:
                    data = json.load(f)
                # If GeoJSON, flatten features
                if "features" in data:
                    flat_data = []
                    for feature in data["features"]:
                        props = feature.get("properties", {})
                        geom = feature.get("geometry", {})
                        if geom.get("type") == "Point":
                            coords = geom.get("coordinates", [0, 0])
                            props["lon"] = coords[0]
                            props["lat"] = coords[1]
                        flat_data.append(props)
                    df = pd.DataFrame(flat_data)
                else:
                    df = pd.DataFrame(data)
            else:
                return None
                
            # Verify columns or patch missing defaults
            required_cols = ['lat', 'lon']
            for col in required_cols:
                if col not in df.columns:
                    raise ValueError(f"Missing required column: {col}")
                    
            # Fill missing attributes with reasonable defaults
            defaults = {
                'ndvi': 0.25,
                'albedo': 0.15,
                'building_density': 0.4,
                'building_height': 15.0,
                'sky_view_factor': 0.6,
                'population_density': 5000.0,
                'elderly_ratio': 0.12,
                'avg_income': 50000.0,
                'land_use': 'residential'
            }
            for col, val in defaults.items():
                if col not in df.columns:
                    df[col] = val
                    
            # Reconstruct grid size
            num_cells = len(df)
            grid_size = int(np.sqrt(num_cells))
            
            # Map index
            df['id'] = range(num_cells)
            df['x'] = df['id'] % grid_size
            df['y'] = df['id'] // grid_size
            
            # Recalculate SVI
            norm_elderly = df['elderly_ratio'] / 0.35
            norm_income = 1.0 - (df['avg_income'] / 150000.0)
            norm_pop = df['population_density'] / 25000.0
            df['svi'] = 0.4 * norm_elderly.clip(0, 1) + 0.3 * norm_income.clip(0, 1) + 0.3 * norm_pop.clip(0, 1)
            df.loc[df['land_use'] == 'water', 'svi'] = 0.0
            
            cells = df.to_dict(orient='records')
            
            # Simple boundary analysis for metadata
            metadata = {
                "profile": "custom_upload",
                "grid_size": grid_size,
                "base_lat": float(df['lat'].mean()),
                "base_lon": float(df['lon'].mean()),
                "weather": self.get_profile_weather("tropical_coastal")  # Default weather
            }
            
            return {"metadata": metadata, "cells": cells}
            
        except Exception as e:
            print(f"Error reading custom GIS file: {e}")
            return None
