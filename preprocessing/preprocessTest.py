import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import medfilt
from numpy.polynomial import Polynomial
from sklearn.preprocessing import MinMaxScaler

########################################
# Load spectrum (two columns only)
# Left = WAVE, Right = INTENSITY
########################################
df = pd.read_csv("Styro10sTest.csv", header=None, names=["INTENSITY", "WAVE"])

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
df_proc["INTENSITY_NORM"] = scaler.fit_transform(df_proc["INTENSITY_SNV"].values.reshape(-1, 1))

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
# Save processed spectrum
########################################
df_proc.to_csv("processed_one_spectrum.csv", index=False)
