import sys
from backend.tests.test_core import (
    test_data_manager,
    test_physics_solver,
    test_pinn_model,
    test_optimizer
)

if __name__ == "__main__":
    print("Running Urban Heat Mitigation AI Engine Tests...")
    
    try:
        print("1. Testing Data Manager... ", end="")
        test_data_manager()
        print("PASSED")
        
        print("2. Testing Physics thermodynamic Solver... ", end="")
        test_physics_solver()
        print("PASSED")
        
        print("3. Testing Physics-Informed ML Model & SHAP... ", end="")
        test_pinn_model()
        print("PASSED")
        
        print("4. Testing AI Optimization Engine... ", end="")
        test_optimizer()
        print("PASSED")
        
        print("\nAll 4 Core Unit Tests Passed Successfully!")
        sys.exit(0)
    except Exception as e:
        print("FAILED")
        import traceback
        traceback.print_exc()
        sys.exit(1)
