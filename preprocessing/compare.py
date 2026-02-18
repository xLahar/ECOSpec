import sys
import pandas as pd
import numpy as np
from scipy.signal import savgol_filter
from numpy.polynomial import Polynomial
from pathlib import Path

########################################
# Paths
########################################
RAW_DIR = Path("spectra/raw")
LIB_PATH = Path("spectra/processed/lib.csv")  # prebuilt masked library
if not LIB_PATH.exists():
    print("Library CSV not found:", LIB_PATH)
    sys.exit(1)

########################################
# Global wavelength grid
########################################
GLOBAL_WAVE_MIN = 200
GLOBAL_WAVE_MAX = 3400
GLOBAL_GRID = np.arange(GLOBAL_WAVE_MIN, GLOBAL_WAVE_MAX + 1, 1)

# Water absorption ranges to mask (broad)
MASK_RANGES = [(1400, 1800), (2800, 3400)]

########################################
# Check CLI argument
########################################
if len(sys.argv) != 2:
    print("Usage: python compare.py <query_file>")
    sys.exit(1)

query_file = RAW_DIR / sys.argv[1]
if not query_file.exists():
    print("Query file not found:", query_file)
    sys.exit(1)

########################################
# Masking function
########################################
def mask_water(wave, spectrum):
    mask = np.ones_like(wave, dtype=bool)
    for start, end in MASK_RANGES:
        mask &= ~((wave >= start) & (wave <= end))
    return spectrum[mask]

########################################
# Preprocess spectrum (SG + baseline + SNV)
########################################
def process_spectrum(file_path):
    df = pd.read_csv(file_path, header=None, names=["WAVE", "INTENSITY"])
    df = df.sort_values("WAVE")
    df = df[(df["WAVE"] >= GLOBAL_WAVE_MIN) & (df["WAVE"] <= GLOBAL_WAVE_MAX)]

    # Interpolate to global grid
    intensity = np.interp(GLOBAL_GRID, df["WAVE"], df["INTENSITY"])

    # Savitzky-Golay smoothing
    smooth = savgol_filter(intensity, window_length=15, polyorder=3)

    # Polynomial baseline correction (10th degree)
    p = Polynomial.fit(GLOBAL_GRID, smooth, deg=10)
    baseline = p(GLOBAL_GRID)
    corr = smooth - baseline

    # SNV
    snv = (corr - np.mean(corr)) / np.std(corr)

    # Mask water regions
    snv_masked = mask_water(GLOBAL_GRID, snv)

    return snv_masked

########################################
# Load masked library
########################################
library_df = pd.read_csv(LIB_PATH)
library_waves = library_df["WAVE"].values
material_names = library_df.columns[1:]
library_matrix = library_df.iloc[:, 1:].values.T

# Mask library spectra
def mask_library(lib_matrix, waves):
    masked_lib = []
    for spectrum in lib_matrix:
        masked_lib.append(mask_water(waves, spectrum))
    return np.array(masked_lib)

library_matrix_masked = mask_library(library_matrix, library_waves)

########################################
# Process query
########################################
query_vector = process_spectrum(query_file)

# Check length match
if query_vector.shape[0] != library_matrix_masked.shape[1]:
    print("Query vector length:", query_vector.shape[0])
    print("Library spectra length:", library_matrix_masked.shape[1])
    print("Mismatch! Exiting.")
    sys.exit(1)

########################################
# Compute Pearson correlation
########################################
def pearson_r(x, y):
    return np.corrcoef(x, y)[0, 1]

similarities = [pearson_r(query_vector, lib_vec) for lib_vec in library_matrix_masked]

########################################
# Rank top matches
########################################
results = list(zip(material_names, similarities))
results.sort(key=lambda x: x[1], reverse=True)

print("\nTop 3 Matches:")
for name, score in results[:3]:
    print(f"{name}  |  Pearson r: {score:.4f}")
