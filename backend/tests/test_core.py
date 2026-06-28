import numpy as np
from backend.data_manager import GeospatialDataManager
from backend.physics import ThermodynamicSolver
from backend.model import PhysicsInformedMLModel
from backend.roi_calculator import ROICalculator
from backend.optimizer import UrbanHeatOptimizer

def test_data_manager():
    dm = GeospatialDataManager()
    data = dm.generate_synthetic_city(profile="dense_highrise", grid_size=10)
    
    assert "metadata" in data
    assert "cells" in data
    assert len(data["cells"]) == 100
    assert data["metadata"]["grid_size"] == 10
    
    cell = data["cells"][0]
    assert "albedo" in cell
    assert "ndvi" in cell
    assert "svi" in cell
    assert "land_use" in cell

def test_physics_solver():
    solver = ThermodynamicSolver()
    
    # Run a test calculation
    Ts, fluxes = solver.solve_equilibrium_temperature(
        albedo=0.15,
        ndvi=0.2,
        building_density=0.6,
        building_height=15.0,
        sky_view_factor=0.6,
        air_temp=30.0,
        rel_humidity=0.5,
        wind_speed=2.0,
        solar_rad=800.0,
        sky_temp=15.0,
        land_use="residential",
        hour=12.0
    )
    
    assert isinstance(Ts, float)
    assert Ts > 30.0  # Under solar noon, surface temp should exceed air temp
    # Conservation of Energy: Net radiation should balance H + LE + G (residual should be close to 0)
    assert abs(fluxes["residual"]) < 1e-2

def test_pinn_model():
    solver = ThermodynamicSolver()
    model = PhysicsInformedMLModel(solver)
    dm = GeospatialDataManager()
    
    data = dm.generate_synthetic_city(profile="dense_highrise", grid_size=10)
    weather = data["metadata"]["weather"]
    cells = data["cells"]
    
    # Test model training
    model.train(cells, weather)
    assert model.is_trained
    
    # Test prediction
    cell = cells[0]
    Ts, Ta, fluxes = model.predict_cell_temperatures(cell, weather)
    assert isinstance(Ts, float)
    assert isinstance(Ta, float)
    assert "Rn" in fluxes
    
    # Test explainability
    drivers = model.compute_local_drivers(cell, weather)
    assert "albedo_attribution_celsius" in drivers
    assert "ndvi_attribution_celsius" in drivers

def test_optimizer():
    solver = ThermodynamicSolver()
    model = PhysicsInformedMLModel(solver)
    roi_calc = ROICalculator()
    opt = UrbanHeatOptimizer(model, roi_calc)
    dm = GeospatialDataManager()
    
    data = dm.generate_synthetic_city(profile="dense_highrise", grid_size=10)
    weather = data["metadata"]["weather"]
    cells = data["cells"]
    
    model.train(cells, weather)
    
    # Pre-calculate temperatures
    for c in cells:
        Ts, Ta, _ = model.predict_cell_temperatures(c, weather)
        c["temp_surface"] = Ts
        c["temp_air"] = Ta
        
    budget = 100000.0  # $100k
    opt_cells, summary = opt.run_optimization(cells, weather, budget=budget, strategy="balanced")
    
    assert len(opt_cells) == len(cells)
    assert summary["actual_cost_allocated"] <= budget
    
    # Verify we achieved cooling or albedo/NDVI increases
    albedo_deltas = [c["albedo_delta"] for c in opt_cells]
    ndvi_deltas = [c["ndvi_delta"] for c in opt_cells]
    
    assert any(d > 0 for d in albedo_deltas) or any(d > 0 for d in ndvi_deltas)
