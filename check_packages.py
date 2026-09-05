import importlib.util

packages = ["numpy", "pandas", "sklearn", "lightgbm", "joblib", "scipy",
            "shap", "cv2", "redis", "celery", "fastapi", "uvicorn",
            "pydantic", "supabase", "jwt", "slowapi"]

for pkg in packages:
    found = importlib.util.find_spec(pkg) is not None
    print(f"{'[OK]' if found else '[NO]'} {pkg}")