import numpy as np
import pandas as pd

########################################
# Raman shift axis (1 cm^-1 spacing)
########################################
wave = np.arange(200, 3401, 1)

########################################
# Function to generate raw spectrum
########################################
def generate_raw_spectrum(peaks, baseline_slope, noise_level):
    intensity = np.zeros_like(wave, dtype=float)

    # Add Gaussian Raman peaks
    for center, width, height in peaks:
        intensity += height * np.exp(-0.5 * ((wave - center) / width) ** 2)

    # Add sloped fluorescence-like baseline
    baseline = baseline_slope * (wave - 200)
    intensity += baseline

    # Add Gaussian noise
    noise = np.random.normal(0, noise_level, len(wave))
    intensity += noise

    return intensity


########################################
# Define 3 materials (unscaled, raw)
########################################
materials = {
    "Polystyrene_raw.csv": {
        "peaks": [
            (620, 15, 900),
            (1000, 20, 1300),
            (1030, 12, 800),
            (1600, 25, 1700),
            (3050, 35, 600)
        ],
        "baseline": 0.004,
        "noise": 25
    },

    "PET_raw.csv": {
        "peaks": [
            (630, 20, 500),
            (860, 25, 1100),
            (1285, 30, 1500),
            (1615, 25, 700),
            (1725, 30, 1900)
        ],
        "baseline": 0.002,
        "noise": 40
    },

    "HDPE_raw.csv": {
        "peaks": [
            (1060, 25, 1800),
            (1130, 25, 1400),
            (1295, 35, 1000),
            (1440, 40, 2100),
            (2850, 50, 1700)
        ],
        "baseline": 0.006,
        "noise": 30
    }
}

########################################
# Generate and save spectra
########################################
for filename, params in materials.items():
    intensity = generate_raw_spectrum(
        params["peaks"],
        params["baseline"],
        params["noise"]
    )

    df = pd.DataFrame({
        "WAVE": wave,
        "INTENSITY": intensity
    })

    df.to_csv(filename, index=False)
    print(f"{filename} generated.")

print("\nThree raw Raman spectra created successfully.")
