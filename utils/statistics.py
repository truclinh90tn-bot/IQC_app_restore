
import numpy as np
import pandas as pd

def mean_sd_cv(values):
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return np.nan, np.nan, np.nan
    mean = float(np.mean(arr))
    sd = float(np.std(arr, ddof=1)) if arr.size > 1 else np.nan
    cv = (sd/mean*100.0) if mean not in (0.0, np.nan) and not np.isnan(mean) and not np.isnan(sd) else np.nan
    return mean, sd, cv
