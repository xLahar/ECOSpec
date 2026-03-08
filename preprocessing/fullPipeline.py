import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from scipy.signal import medfilt
from scipy.stats import pearsonr
from numpy.polynomial import Polynomial
from sklearn.preprocessing import MinMaxScaler


############################################################
# Directories
############################################################

RAW_DIR = Path("spectra/raw")
PROCESSED_DIR = Path("spectra/processed")
LIB_PATH = PROCESSED_DIR / "lib.csv"


############################################################
# Parameters
############################################################

WAVE_MIN = 200
WAVE_MAX = 3400
INTERP_STEP = 1

MEDIAN_KERNEL = 15
POLY_ORDER = 7


############################################################
# Utility Functions
############################################################

def load_raw_spectrum(path: Path) -> pd.DataFrame:
    """Load and clean raw spectrum."""
    
    df = pd.read_csv(path, header=None, names=["WAVE", "INTENSITY"])

    df = df[df["INTENSITY"] > 0]

    df["WAVE"] = df["WAVE"].round()
    df["INTENSITY"] = df["INTENSITY"].round()

    df = df[(df["WAVE"] >= WAVE_MIN) & (df["WAVE"] <= WAVE_MAX)]

    return df


def interpolate_spectrum(df: pd.DataFrame) -> pd.DataFrame:
    """Interpolate spectrum to uniform 1 cm⁻¹ grid."""

    wave_grid = np.arange(WAVE_MIN, WAVE_MAX + 1, INTERP_STEP)

    interp_intensity = np.interp(
        wave_grid,
        df["WAVE"],
        df["INTENSITY"]
    )

    return pd.DataFrame({
        "WAVE": wave_grid,
        "INTENSITY_RAW": interp_intensity
    })


def preprocess_spectrum(df_proc: pd.DataFrame):
    """Apply filtering, baseline correction, normalization."""

    # Median filter
    df_proc["INTENSITY_MED"] = medfilt(
        df_proc["INTENSITY_RAW"],
        kernel_size=MEDIAN_KERNEL
    )

    # Polynomial baseline
    poly = Polynomial.fit(
        df_proc["WAVE"],
        df_proc["INTENSITY_MED"],
        deg=POLY_ORDER
    )

    baseline = poly(df_proc["WAVE"])

    df_proc["INTENSITY_CORR"] = df_proc["INTENSITY_MED"] - baseline

    # SNV normalization
    corr = df_proc["INTENSITY_CORR"]

    snv = (corr - corr.mean()) / corr.std()

    df_proc["INTENSITY_SNV"] = snv

    # Min-max scaling
    scaler = MinMaxScaler()

    df_proc["INTENSITY_NORM"] = scaler.fit_transform(
        snv.values.reshape(-1, 1)
    )

    return df_proc, baseline


def visualize(df_raw, df_proc, baseline):
    """Plot preprocessing stages."""

    plt.figure(figsize=(10, 5))

    plt.plot(df_raw["WAVE"], df_raw["INTENSITY"],
             label="Raw", alpha=0.5)

    plt.plot(df_proc["WAVE"], df_proc["INTENSITY_MED"],
             label="Median filter")

    plt.plot(df_proc["WAVE"], baseline,
             label="Polynomial baseline", color="red")

    plt.plot(df_proc["WAVE"], df_proc["INTENSITY_CORR"],
             label="Corrected", color="black")

    plt.plot(df_proc["WAVE"], df_proc["INTENSITY_NORM"],
             label="Final normalized", color="green")

    plt.xlabel("Wavenumber (cm$^{-1}$)")
    plt.ylabel("Intensity")

    plt.title("Raman Spectrum Preprocessing")

    plt.legend()
    plt.tight_layout()
    plt.show()


def save_processed(df_proc: pd.DataFrame, input_path: Path) -> Path:
    """Save processed spectrum."""

    base = input_path.stem.replace("_raw", "_processed")

    output = PROCESSED_DIR / f"{base}.csv"

    df_proc.to_csv(output, index=False)

    return output


############################################################
# Library Matching
############################################################

def load_library() -> pd.DataFrame:

    if not LIB_PATH.exists():
        raise FileNotFoundError(f"Library not found: {LIB_PATH}")

    return pd.read_csv(LIB_PATH, header=None)


def match_spectrum(unknown: np.ndarray, library_df: pd.DataFrame):

    scores = {}

    # Skip first wave column
    for col in range(1, library_df.shape[1], 2):

        material = library_df.iloc[0, col]

        lib_intensity = library_df.iloc[1:, col].astype(float).values

        if len(lib_intensity) != len(unknown):
            raise ValueError(f"Length mismatch for {material}")

        r, _ = pearsonr(unknown, lib_intensity)

        scores[material] = r

    return scores


def print_results(scores: dict):

    sorted_scores = sorted(
        scores.items(),
        key=lambda x: x[1],
        reverse=True
    )

    best_name, best_r = sorted_scores[0]

    print("\n=== Spectral Match Results ===")
    print(f"Best match: {best_name}")
    print(f"Pearson r: {best_r:.4f}")

    print("\nTop 3 matches:")

    for name, r in sorted_scores[:3]:
        print(f"{name:25s} r = {r:.4f}")


############################################################
# Main
############################################################

def main():

    if len(sys.argv) != 2:
        print("Usage: python fullPipeline.py <filename>")
        sys.exit(1)

    file_name = sys.argv[1]

    input_path = RAW_DIR / f"{file_name}_raw.csv"

    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    print(f"Processing: {input_path}")

    # Load
    df_raw = load_raw_spectrum(input_path)

    # Interpolate
    df_proc = interpolate_spectrum(df_raw)

    # Preprocess
    df_proc, baseline = preprocess_spectrum(df_proc)

    # Plot
    visualize(df_raw, df_proc, baseline)

    # Save
    output_path = save_processed(df_proc, input_path)

    print(f"Saved processed spectrum: {output_path}")

    # Library matching
    library_df = load_library()

    unknown = df_proc["INTENSITY_NORM"].values

    scores = match_spectrum(unknown, library_df)

    print_results(scores)


############################################################

if __name__ == "__main__":
    main()