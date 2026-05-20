import numpy as np


def normalize_array(array):
    array = array.astype(np.float32)
    low = np.percentile(array, 1)
    high = np.percentile(array, 99)
    if high <= low:
        return np.zeros(array.shape, dtype=np.uint8)
    array = np.clip((array - low) / (high - low), 0, 1)
    return (array * 255).astype(np.uint8)
