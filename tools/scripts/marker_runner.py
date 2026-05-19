# Timestamp: 2026-04-20 16:40:01

import os
import sys
import subprocess
from datetime import datetime

from project_paths import MARKER_PROJECT_DIR

def run_marker(pdf_path, output_dir):
    """
    Runner for Marker with optimized environment for Low VRAM GPUs.
    """
    venv_python = MARKER_PROJECT_DIR / ".venv" / "bin" / "python"
    
    if not venv_python.exists():
        print(f"Error: Marker VENV not found at {venv_python}")
        return

    # Optimized Environment Variables
    env = os.environ.copy()
    env["DETECTOR_BATCH_SIZE"] = "1"
    env["RECOGNITION_BATCH_SIZE"] = "1"
    env["LAYOUT_BATCH_SIZE"] = "1"
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    
    # Optional: Force CPU if needed, but let our auto-fallback handle it first
    # env["TORCH_DEVICE"] = "cpu" 

    cmd = [
        str(venv_python),
        "-m", "marker.scripts.convert_single", 
        pdf_path, 
        "--output_dir", output_dir
    ]

    print(f"--- Starting Marker Conversion ---")
    print(f"File: {pdf_path}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Config: BatchSize=1, ExpandableSegments=True")
    
    try:
        process = subprocess.Popen(
            cmd, 
            env=env, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        for line in process.stdout:
            print(line, end="")
            
        process.wait()
        
        if process.returncode == 0:
            print(f"\n--- Conversion Successful ---")
        else:
            print(f"\n--- Conversion Failed (Code: {process.returncode}) ---")
            
    except Exception as e:
        print(f"Error during execution: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python marker_runner.py <pdf_path> <output_dir>")
        sys.exit(1)
    
    target_pdf = sys.argv[1]
    target_out = sys.argv[2]
    run_marker(target_pdf, target_out)
