from osgeo import gdal
import numpy as np
import rasterio
from pathlib import Path
import shutil
from tqdm import tqdm
import shutil

def custom_normalize(array, lower_percentile=2, upper_percentile=98, clip_range=(0, 1)):
    """
    Normalizes a given array by scaling values between the given percentiles
    and clipping to the specified range.

    Args:
    - array: Input data (xarray.DataArray or NumPy array)
    - lower_percentile: The lower bound for normalization (default 2)
    - upper_percentile: The upper bound for normalization (default 98)
    - clip_range: Tuple specifying the range to clip the normalized data (default (0, 1))

    Returns:
    - normalized_array: The normalized data array (same type as input)
    """
    print('+++in custom_normalize fn')
    print('---array type',type(array))
    
    # Check if the input is an xarray.DataArray
    if isinstance(array, xr.DataArray):
        print('---array is xarray.DataArray')

        # Rechunk 'y' dimension into a single chunk, leave other dimensions unchanged
        array = array.chunk({'y': -1})  

        # Apply normalization while preserving metadata
        min_val = array.quantile(lower_percentile / 100.0)
        max_val = array.quantile(upper_percentile / 100.0)

        # Normalize the array
        normalized_array = (array - min_val) / (max_val - min_val)

        # Clip values to the specified range
        normalized_array = normalized_array.clip(min=clip_range[0], max=clip_range[1])
        normalized_array = normalized_array.astype('float32')
        return normalized_array

    else:
        print('---array is not xarray.DataArray')
        # Handle as a NumPy array if not xarray.DataArray
        min_val = np.nanpercentile(array, lower_percentile)
        max_val = np.nanpercentile(array, upper_percentile)
        
        # Normalize the array
        normalized_array = (array - min_val) / (max_val - min_val)
        
        # Clip values to the specified range
        normalized_array = np.clip(normalized_array, clip_range[0], clip_range[1])

        return normalized_array

def normalise_a_tile(file_path, output_path):
    # print('++++IN NORMALIZE A TILE')
    output_path = output_path / file_path.name
    if file_path.suffix.lower() not in ['.tif', '.tiff']:
        return
    # print(f"---Normalizing {file_path.name}")
    with rasterio.open(file_path) as src:
        meta = src.meta.copy()
        meta.update(dtype='float32')  # Ensure dtype can store normalized values

        with rasterio.open(output_path, 'w', **meta) as dst:
            for band in range(1, src.count + 1):
                # print(f"---normalizing band {band}")
                try:
                    band_name = src.descriptions[band - 1].lower()
                    data = src.read(band)

                    if band_name in ['vv','vh','grd','dem','slope' ] and np.min(data) != np.max(data) :
                        normalized_data = (data - np.min(data)) / (np.max(data) - np.min(data))
                        dst.write(normalized_data.astype('float32'), band)
                    else:
                        dst.write(data, band)
                    dst.set_band_description(band, band_name)
                except Exception as e:
                    print(f"---Error normalizing band {band}: {e}")
                    dst.write(data, band)

    # print(f"Normalized tile saved to {output_path}")

def process_tiles_newdir(tile_path, normalized_tiles_path):
    print('++++IN PROCESS TILES NEW DIR')   

    # if normalized_tiles_path.exists():
    #     shutil.rmtree(normalized_tiles_path)
    # Ensure the main parent folder for normalized data exists
    normalized_tiles_path.mkdir(parents=True, exist_ok=True)

    num_events = sum(1 for i in tile_path.rglob('tiles') if i.is_dir())
    print(f"---Found {num_events} event directories")

    done = 0

    for event in tile_path.iterdir():  # Iterate over event directories
        if event.is_dir():
            print(f"---Processing event: {event.name}")

            # Find 'tiles' folders at any level within each event directory

            for tiles_folder in event.rglob('tiles'):
                if tiles_folder.is_dir():
                    # Construct the path for the mirrored 'normalized_tiles' directory
                    relative_path = tiles_folder.relative_to(tile_path)
                    normalized_tiles_folder = normalized_tiles_path / relative_path.parent / 'normalized_minmax_tiles'
                    normalized_tiles_folder.mkdir(parents=True, exist_ok=True)

                    # Normalize each tile in the 'tiles' folder
                    j = 0
                    for tile in tiles_folder.iterdir():
                        if tile.is_file():
                            print(f"---Normalizing tile {j}")
                            normalise_a_tile(tile, normalized_tiles_folder)
                            print(f"---tile: {j}. Finished {done} of {num_events} events")
                            j += 1
                    

                    done += 1
                print(f"---Processed {done} of {num_events} events")
          
