import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import medfilt
from numpy.polynomial import Polynomial
from sklearn.preprocessing import MinMaxScaler
from scipy.stats import pearsonr
from pathlib import Path

########################################
# Base directories
########################################
RAW_DIR = Path("spectra/raw")
PROCESSED_DIR = Path("spectra/processed")

########################################
# Check command-line argument
########################################
if len(sys.argv) != 2:
    print("Usage: python fullPipeline.py <filename_in_spectra_raw>")
    sys.exit(1)

fileName = sys.argv[1]
input_name = f"{fileName}_raw.csv"
input_path = RAW_DIR / input_name

if not input_path.exists():
    print(f"Error: File not found -> {input_path}")
    sys.exit(1)

########################################
# Load spectrum (two columns only)
# Left = WAVE, Right = INTENSITY
########################################
df = pd.read_csv(input_path, header=None, names=["WAVE", "INTENSITY"])

# Remove negatives and round
df = df[df["INTENSITY"] > 0]
df["INTENSITY"] = df["INTENSITY"].round()
df["WAVE"] = df["WAVE"].round()

# Restrict to 200–3400 cm-1
df = df[(df["WAVE"] >= 200) & (df["WAVE"] <= 3400)]

########################################
# Interpolation to full 1 cm-1 grid
########################################
wave_grid = np.arange(200, 3401, 1)
interp_intensity = np.interp(wave_grid, df["WAVE"], df["INTENSITY"])

df_proc = pd.DataFrame({
    "WAVE": wave_grid,
    "INTENSITY_RAW": interp_intensity
})

########################################
# Median filter (remove spikes)
########################################
df_proc["INTENSITY_MED"] = medfilt(df_proc["INTENSITY_RAW"], kernel_size=15)

########################################
# Polynomial baseline correction (7th order)
########################################
p = Polynomial.fit(df_proc["WAVE"], df_proc["INTENSITY_MED"], deg=7)
baseline = p(df_proc["WAVE"])
df_proc["INTENSITY_CORR"] = df_proc["INTENSITY_MED"] - baseline

########################################
# SNV normalization
########################################
snv = (df_proc["INTENSITY_CORR"] - df_proc["INTENSITY_CORR"].mean()) / df_proc["INTENSITY_CORR"].std()
df_proc["INTENSITY_SNV"] = snv

########################################
# Min-Max scaling (0–1)
########################################
scaler = MinMaxScaler()
df_proc["INTENSITY_NORM"] = scaler.fit_transform(
    df_proc["INTENSITY_SNV"].values.reshape(-1, 1)
)

########################################
# Quick visualization
########################################
plt.figure(figsize=(10, 5))
plt.plot(df["WAVE"], df["INTENSITY"], label="Raw", alpha=0.5)
plt.plot(df_proc["WAVE"], df_proc["INTENSITY_MED"], label="Median filter", alpha=0.8)
plt.plot(df_proc["WAVE"], baseline, label="7th poly baseline", color="red")
plt.plot(df_proc["WAVE"], df_proc["INTENSITY_CORR"], label="Corrected", color="black")
plt.plot(df_proc["WAVE"], df_proc["INTENSITY_NORM"], label="Final normalized", color="green")
plt.legend()
plt.xlabel("Wavenumber (cm$^{-1}$)")
plt.ylabel("Intensity")
plt.title("Preprocessing Raman Spectrum (Python)")
plt.show()


########################################
# Build processed output filename
########################################

# Remove extension safely
base_name = Path(input_path).stem

# Replace _raw with _processed
base_name = base_name.replace("_raw", "_processed")

output_name = f"{base_name}.csv"
output_path = PROCESSED_DIR / output_name

########################################
# Save processed unknown spectrum
########################################
df_proc.to_csv(output_path, index=False)

########################################
# Load PRE-PROCESSED LIBRARY
########################################
# Format:
# Row 0: material names in WAVE columns
# Col pairs: [WAVE, INTENSITY_NORM]
########################################
library_df = pd.read_csv(PROCESSED_DIR / "lib.csv", header=None)

unknown_intensity = df_proc["INTENSITY_NORM"].values

best_match = None
best_r = -np.inf
scores = {}

########################################
# Pearson correlation matching
########################################
for col in range(0, library_df.shape[1], 2):
    material_name = library_df.iloc[0, col]

    lib_intensity = library_df.iloc[1:, col + 1].astype(float).values

    if len(lib_intensity) != len(unknown_intensity):
        raise ValueError(f"Length mismatch for {material_name}")

    r, _ = pearsonr(unknown_intensity, lib_intensity)
    scores[material_name] = r

    if r > best_r:
        best_r = r
        best_match = material_name

########################################
# Results
########################################
print("\n=== Spectral Match Results ===")
print(f"Best match: {best_match}")
print(f"Pearson r: {best_r:.4f}")

print("\nTop 5 matches:")
for name, r in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:5]:
    print(f"{name:25s}  r = {r:.4f}")
