import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import medfilt
from numpy.polynomial import Polynomial
from sklearn.preprocessing import MinMaxScaler
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
    print("Usage: python preprocess.py <filename_in_spectra_raw>")
    sys.exit(1)

fileName = sys.argv[1]
input_file = RAW_DIR / fileName

if not input_file.exists():
    print(f"Error: File not found -> {input_file}")
    sys.exit(1)

########################################
# Load spectrum (two columns only)
# Left = WAVE, Right = INTENSITY
########################################
df = pd.read_csv(input_file, header=None, names=["WAVE", "INTENSITY"])

# Remove negatives and round
df = df[df["INTENSITY"] > 0]

df = df.sort_values("WAVE")

#df["INTENSITY"] = df["INTENSITY"].round()
#df["WAVE"] = df["WAVE"].round()

# Restrict to 200–3400 cm-1
df = df[(df["WAVE"] >= 200) & (df["WAVE"] <= 3400)]

########################################
# Interpolation to full 1 cm-1 grid
########################################
wave_min = int(np.ceil(df["WAVE"].min()))
wave_max = int(np.floor(df["WAVE"].max()))
wave_grid = np.arange(wave_min, wave_max + 1, 1)

interp_intensity = np.interp(wave_grid, df["WAVE"], df["INTENSITY"])

df_proc = pd.DataFrame({"WAVE": wave_grid, "INTENSITY_RAW": interp_intensity})

########################################
# Median filter
########################################
df_proc["INTENSITY_MED"] = medfilt(df_proc["INTENSITY_RAW"], kernel_size=15)

########################################
# Polynomial baseline correction
########################################
p = Polynomial.fit(df_proc["WAVE"], df_proc["INTENSITY_MED"], deg=7)
baseline = p(df_proc["WAVE"])
df_proc["INTENSITY_CORR"] = df_proc["INTENSITY_MED"] - baseline

########################################
# SNV normalization
########################################
snv = (
    df_proc["INTENSITY_CORR"] - df_proc["INTENSITY_CORR"].mean()
) / df_proc["INTENSITY_CORR"].std()

df_proc["INTENSITY_SNV"] = snv

########################################
# Min-Max scaling (0–1)
########################################
scaler = MinMaxScaler()
df_proc["INTENSITY_NORM"] = scaler.fit_transform(
    df_proc["INTENSITY_SNV"].values.reshape(-1, 1)
)

########################################
# Visualization
########################################
plt.figure(figsize=(10, 5))
#plt.plot(df["WAVE"], df["INTENSITY"], label="Raw", alpha=0.5)
#plt.plot(df_proc["WAVE"], df_proc["INTENSITY_MED"], label="Median filter", alpha=0.8)
#plt.plot(df_proc["WAVE"], baseline, label="7th poly baseline", color="red")
#plt.plot(df_proc["WAVE"], df_proc["INTENSITY_CORR"], label="Corrected", color="black")
plt.plot(df_proc["WAVE"], df_proc["INTENSITY_NORM"], label="Final normalized", color="green")
plt.legend()
plt.xlabel("Wavenumber (cm$^{-1}$)")
plt.ylabel("Intensity")
plt.title(f"Preprocessing Raman Spectrum\n{input_file.name}")
plt.show()

########################################
# Create processed folder + save output
########################################
processed_dir = Path("spectra/processed")
processed_dir.mkdir(exist_ok=True)

output_path = processed_dir / f"{input_file.stem}_processed.csv"
df_proc.to_csv(output_path, index=False)

print(f"\nProcessed file saved to: {output_path}")
