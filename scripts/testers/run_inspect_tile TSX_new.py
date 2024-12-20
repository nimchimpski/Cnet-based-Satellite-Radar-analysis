

from pathlib import Path
import rasterio
import numpy as np
from tqdm import tqdm
import shutil  # For safely replacing files


def main():
    '''
    checks tile size and pads if necessarys
    '''
    print('+++++++++++++RUNNING+++++++++++++X')
    tiles_path = Path(r"C:\Users\floodai\UNOSAT_FloodAI_v2\1data\2interim\TSX_all_processing\TSX_TILES\NORM_TILES_FOR_SELECT_AND_SPLIT_###\695958835_1.nc_normalized_tiles_logclipmm_g_pcnf100")
    padded = 0
    problems = 0

    for folder in tiles_path.iterdir():
        if folder.is_dir():
            for tile in tqdm(folder.iterdir(), total=len(list(folder.iterdir()))):
                if tile.suffix == '.tif':
                    try:
                        with rasterio.open(tile) as src:
                                print('---tile:', tile.name)
                                # Read all datasdsdfsdfsdvsdvs
                                data = src.read()

                                # LOOP THRU BANDS
                                for band in range(1, src.count + 1):
                                    band_data= data[band - 1]
                                    band_name = src.descriptions[band - 1].lower() if src.descriptions[band - 1] else None
                                    print('---band:', band_name)

                                    # IF BAND IS UNIFORM 0.5 IT PASSES
                                    if (np.min(band_data) == np.max(band_data) == 0.5):
                                        print(f'---band: {band_name} is uniform and set to 0.5')
                                    else:
                                        # IF UNIQUE VALS NOT 0 OR 1 - FLAG IT
                                        if ((np.min(band_data) not in [0,  1]) or (np.max(band_data) not in [0, 1])):
                                            print(f"---Band {band} in {tile.name} has values outside [0, 1]: min={np.min(band_data)}, max={np.max(band_data)}")
                                            problems += 1

                                        # Normalize uniform DEM bands to 0.5
                                        if band_name == 'dem':
                                            if (np.min(band_data) == np.max(band_data)) and (np.min(band_data) < 0 or np.max(band_data) > 1):
                                                print('---out of range')
                                                print(f"Normalizing uniform DEM band in {tile.name} with value {np.min(band_data)}")
                                                data[band - 1] = np.full_like(band_data, 0.5)

                                    # ENSURE MASK IS 0 OR 1
                                    if band_name in ['mask', 'valid']:
                                        unique_values = np.unique(band_data)
                                        if not set(unique_values).issubset({0, 1}):
                                            print(f"---Invalid mask in {tile.name} band {band}: min={np.min(band_data)}, max={np.max(band_data)}")

                                    # Write the band back to the destination file
                                    # dst.write(data[band - 1], band)

                                    # Retain band descriptions
                                    # if band_name:
                                        # dst.set_band_description(band, band_name)

                            # Replace original file with modified temporary file
                            # shutil.move(temp_tile, tile)

                    except Exception as e:
                        print(f"---Error processing {tile.name}: {e}")
                        # Remove temporary file in case of error

            # print(f"Processing complete. problems: {problems} padded: {padded}.")





if __name__ == "__main__":
    main()
