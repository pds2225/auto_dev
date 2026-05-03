import sys
import importlib.util
from pathlib import Path

# Add dashboard directory to Python path so all dashboard imports work
dashboard_dir = Path(__file__).parent / "dashboard"
sys.path.insert(0, str(dashboard_dir))

# Execute the actual dashboard Streamlit app while preserving __file__ semantics
spec = importlib.util.spec_from_file_location("dashboard_streamlit", dashboard_dir / "streamlit_app.py")
module = importlib.util.module_from_spec(spec)
sys.modules["dashboard_streamlit"] = module
spec.loader.exec_module(module)
