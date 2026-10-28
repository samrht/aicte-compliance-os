import os
import sys
import tempfile
from pathlib import Path

# Isolated data dir and instant workflow steps, set before `app` is imported.
_tmp = Path(tempfile.mkdtemp(prefix="acos-test-"))
os.environ["ACOS_DATA"] = str(_tmp / "data")
os.environ["ACOS_DEMO_ASSETS"] = str(_tmp / "demo-assets")
os.environ["DAG_STEP_DELAY"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
