import pandas as pd
import numpy as np
from scipy.signal import savgol_filter
from numpy.polynomial import Polynomial
from pathlib import Path

########################################
# Directories
########################################
RAW_DIR = Path("spectra/raw")
OUTPUT_FILE = Path("spectra/processed/lib.csv")
OUTPUT_FILE.parent.mkdir(exist_ok=True)

########################################
# GLOBAL FIXED GRID
########################################
GLOBAL_WAVE_MIN = 200
GLOBAL_WAVE_MAX = 3400
GLOBAL_GRID = np.arange(GLOBAL_WAVE_MIN, GLOBAL_WAVE_MAX + 1, 1)

########################################
# Function: Process Single Spectrum
########################################
def process_spectrum(file_path):
    # Load CSV
    df = pd.read_csv(file_path, header=None, names=["WAVE", "INTENSITY"])
    df = df.sort_values("WAVE")
    df = df[(df["WAVE"] >= GLOBAL_WAVE_MIN) & (df["WAVE"] <= GLOBAL_WAVE_MAX)]

    # Interpolate to GLOBAL grid
    interp_intensity = np.interp(GLOBAL_GRID, df["WAVE"], df["INTENSITY"])

    # Savitzky-Golay smoothing
    intensity_smooth = savgol_filter(interp_intensity, window_length=15, polyorder=3)

    # Polynomial baseline correction (10th degree)
    p = Polynomial.fit(GLOBAL_GRID, intensity_smooth, deg=10)
    baseline = p(GLOBAL_GRID)
    intensity_corr = intensity_smooth - baseline

    # Standard Normal Variate (SNV)
    snv = (intensity_corr - np.mean(intensity_corr)) / np.std(intensity_corr)

    return snv

########################################
# Process All Files in RAW_DIR
########################################
library_df = pd.DataFrame({"WAVE": GLOBAL_GRID})

for file in sorted(RAW_DIR.glob("*.csv")):
    print(f"Processing: {file.name}")
    material_name = file.stem
    processed = process_spectrum(file)
    library_df[material_name] = processed

########################################
# Save Library CSV
########################################
library_df.to_csv(OUTPUT_FILE, index=False)
print(f"\nLibrary saved to: {OUTPUT_FILE}")
