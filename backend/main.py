import os
import shutil
from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

# Import local modules
from backend.data_manager import GeospatialDataManager
from backend.physics import ThermodynamicSolver
from backend.model import PhysicsInformedMLModel
from backend.roi_calculator import ROICalculator
from backend.optimizer import UrbanHeatOptimizer

app = FastAPI(title="Geospatial Urban Heat Mitigation & Cooling Engine")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize engines
data_manager = GeospatialDataManager()
solver = ThermodynamicSolver()
model = PhysicsInformedMLModel(solver)
roi_calculator = ROICalculator()
optimizer = UrbanHeatOptimizer(model, roi_calculator)

# Keep track of the currently loaded city state in memory to allow relative calculations
loaded_city_state: Dict[str, Any] = {}

class SimulationRequest(BaseModel):
    cells: List[Dict[str, Any]]
    weather: Dict[str, float]

class OptimizationRequest(BaseModel):
    cells: List[Dict[str, Any]]
    weather: Dict[str, float]
    budget: float
    strategy: str

class DiurnalRequest(BaseModel):
    cell: Dict[str, Any]
    weather: Dict[str, float]

@app.get("/api/city-data")
def get_city_data(profile: str = "dense_highrise", size: int = 40):
    global loaded_city_state
    
    # 1. Generate or load city grid
    city_data = data_manager.generate_synthetic_city(profile=profile, grid_size=size)
    weather = city_data["metadata"]["weather"]
    cells = city_data["cells"]
    
    # 2. Fit the microclimatic ML model on this city grid layout
    model.train(cells, weather)
    
    # 3. Calculate baseline temperatures and drivers for each cell
    baseline_cells = []
    for cell in cells:
        Ts, Ta, fluxes = model.predict_cell_temperatures(cell, weather, hour=12.0)
        drivers = model.compute_local_drivers(cell, weather)
        
        c_copy = cell.copy()
        c_copy["temp_surface"] = float(Ts)
        c_copy["temp_air"] = float(Ta)
        c_copy["fluxes"] = fluxes
        c_copy["drivers"] = drivers
        baseline_cells.append(c_copy)
        
    city_data["cells"] = baseline_cells
    loaded_city_state = city_data
    
    return city_data

@app.post("/api/simulate")
def simulate_scenario(req: SimulationRequest):
    weather = req.weather
    cells = req.cells
    
    simulated_cells = []
    for cell in cells:
        Ts, Ta, fluxes = model.predict_cell_temperatures(cell, weather, hour=12.0)
        drivers = model.compute_local_drivers(cell, weather)
        
        c_copy = cell.copy()
        c_copy["temp_surface"] = float(Ts)
        c_copy["temp_air"] = float(Ta)
        c_copy["fluxes"] = fluxes
        c_copy["drivers"] = drivers
        simulated_cells.append(c_copy)
        
    # Calculate savings compared to baseline loaded city state
    global loaded_city_state
    baseline_cells = loaded_city_state.get("cells", simulated_cells)
    
    roi_summary = roi_calculator.calculate_scenario_roi(baseline_cells, simulated_cells)
    
    return {
        "cells": simulated_cells,
        "roi": roi_summary
    }

@app.post("/api/optimize")
def optimize_interventions(req: OptimizationRequest):
    # Run the greedy knapsack optimizer
    opt_cells, roi_summary = optimizer.run_optimization(
        cells=req.cells,
        weather=req.weather,
        budget=req.budget,
        strategy=req.strategy
    )
    return {
        "cells": opt_cells,
        "roi": roi_summary
    }

@app.post("/api/pareto")
def get_pareto_frontier(req: OptimizationRequest):
    # Runs multiple optimizations at varying budgets to draw the trade-off curve
    frontier = optimizer.generate_pareto_frontier(
        cells=req.cells,
        weather=req.weather,
        max_budget=req.budget
    )
    return {"frontier": frontier}

@app.post("/api/diurnal")
def get_diurnal_profile(req: DiurnalRequest):
    cell = req.cell
    weather = req.weather
    
    # 1. Simulate diurnal cycle for original state
    baseline_cycle = solver.simulate_diurnal_cycle(
        albedo=cell.get("albedo_original", cell["albedo"]),
        ndvi=cell.get("ndvi_original", cell["ndvi"]),
        building_density=cell["building_density"],
        building_height=cell["building_height"],
        sky_view_factor=cell["sky_view_factor"],
        weather_base=weather,
        land_use=cell["land_use"]
    )
    
    # 2. Simulate diurnal cycle for modified state (if changed)
    modified_cycle = solver.simulate_diurnal_cycle(
        albedo=cell["albedo"],
        ndvi=cell["ndvi"],
        building_density=cell["building_density"],
        building_height=cell["building_height"],
        sky_view_factor=cell["sky_view_factor"],
        weather_base=weather,
        land_use=cell["land_use"]
    )
    
    return {
        "baseline": baseline_cycle,
        "modified": modified_cycle
    }

@app.post("/api/upload-gis")
async def upload_gis_file(file: UploadFile = File(...)):
    # Save the file locally
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, file.filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Parse the custom file
        custom_data = data_manager.load_custom_gis_data(file_path)
        if not custom_data:
            raise HTTPException(status_code=400, detail="Invalid GIS file format. Please upload a structured CSV or GeoJSON.")
            
        # Calibrate the ML model on this custom data
        global loaded_city_state
        weather = custom_data["metadata"]["weather"]
        cells = custom_data["cells"]
        
        model.train(cells, weather)
        
        baseline_cells = []
        for cell in cells:
            Ts, Ta, fluxes = model.predict_cell_temperatures(cell, weather, hour=12.0)
            drivers = model.compute_local_drivers(cell, weather)
            
            c_copy = cell.copy()
            c_copy["temp_surface"] = float(Ts)
            c_copy["temp_air"] = float(Ta)
            c_copy["fluxes"] = fluxes
            c_copy["drivers"] = drivers
            baseline_cells.append(c_copy)
            
        custom_data["cells"] = baseline_cells
        loaded_city_state = custom_data
        
        return custom_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process spatial data: {str(e)}")
    finally:
        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)

# Serve the static frontend files
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    print(f"Warning: Frontend directory not found at {frontend_dir}. Make sure to create it.")
