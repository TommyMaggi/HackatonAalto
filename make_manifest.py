import json
import os
import glob
import re

runs = []
for sim_dir in sorted(glob.glob("data/features/simulationRun=*")):
    sim_match = re.search(r"simulationRun=([\d.]+)", sim_dir)
    if sim_match:
        sim = int(float(sim_match.group(1)))
        runs.append(f"sim{sim}_run00")

manifest = {
    "fit": runs[:10],
    "calibration": runs[10:15]
}

os.makedirs("contracts", exist_ok=True)
with open("contracts/reference_manifest.json", "w") as f:
    json.dump(manifest, f, indent=2)
print("Manifest created!")
