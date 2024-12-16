import torch
from pathlib import Path
import shutil
import rasterio
import numpy as np
from tqdm import tqdm
import time
import os
import xarray as xr
import json
import matplotlib.pyplot as plt
from rasterio.plot import show
from rasterio.windows import Window
from rasterio.warp import calculate_default_transform, reproject, Resampling
from scripts.train_modules.train_classes import UnetModel
from scripts.process_modules.process_tiffs_module import match_dem_to_mask, clip_image_to_mask_gdal
from scripts.process_modules.process_tiffs_module import calculate_and_normalize_slope, create_event_datacube_TSX_inf,         reproject_layers_to_4326_TSX, nan_check, remove_mask_3_vals, reproject_to_4326_gdal, make_float32_inf, make_float32_inmem, create_extent_from_mask
from scripts.process_modules.process_dataarrays_module import tile_datacube_rxr, calculate_global_min_max_nc, get_global_min_max
from scripts.process_modules.process_helpers import  print_tiff_info_TSX
from collections import OrderedDict

start=time.time()

def make_prediction_tiles(tile_folder, metadata, model, device, threshold=0.5):
    predictions_folder = Path(tile_folder).parent / f'{tile_folder.stem}_predictions'
    if predictions_folder.exists():
        print(f"--- Deleting existing predictions folder: {predictions_folder}")
        # delete the folder and create a new one
        shutil.rmtree(predictions_folder)
    predictions_folder.mkdir(exist_ok=True)

    for tile_info in metadata:
        tile_path = tile_folder /  tile_info["tile_name"]
        pred_path = predictions_folder / tile_info["tile_name"]

        with rasterio.open(tile_path) as src:
            tile = src.read(1).astype(np.float32)  # Read the first band
            profile = src.profile   

        # Prepare tile for model
        tile_tensor = torch.tensor(tile).unsqueeze(0).unsqueeze(0).to(device)  # Add batch and channel dims

        # Perform inference
        with torch.no_grad():
            pred = model(tile_tensor)
            pred = torch.sigmoid(pred).squeeze().cpu().numpy()  # Convert logits to probabilities
            pred = (pred > threshold).astype(np.float32)  # Convert probabilities to binary mask

        # Save prediction as GeoTIFF
        profile.update(dtype=rasterio.float32)
        with rasterio.open(pred_path, "w", **profile) as dst:
            dst.write(pred.astype(np.float32), 1)

    return predictions_folder



def stitch_tiles(metadata, prediction_tiles, save_path, image):
    ''''
    metadata =list
    '''
    # GET CRS AND TRANSFORM
    with rasterio.open(image) as src:
        crs = src.crs
        transform = src.transform
        height, width = src.shape
        print('>>>src shape:',src.shape)
    
    # INITIALIZE THE STITCHED IMAGE AND COUNT
    stitched_image = np.zeros(src.shape)
    # print(">>>stitched_image dtype:", stitched_image.dtype)
    print(">>>stitched_image shape:", stitched_image.shape)

    count = np.zeros(src.shape)
    pred_tiles_paths_list = sorted(prediction_tiles.glob("*.tif"))

    for tile_info in metadata:
        tile_name = tile_info["tile_name"]
        # Extract position info from metadata
        x_start, x_end = tile_info["x_start"], tile_info["x_end"]
        y_start, y_end = tile_info["y_start"], tile_info["y_end"]

        # Find the corresponding prediction tile
        tile = prediction_tiles / tile_name

        # Load the tile
        with rasterio.open(tile) as src:
            tile = src.read(1)
            # Debugging: Print tile info and shapes
            # print(f">>>Tile shape: {tile.shape}")
        # print(f">>> Tile info: {tile_info}")

        # Extract the relevant slice from the stitched image
        stitched_slice = stitched_image[y_start:y_end, x_start:x_end]
        if (stitched_slice.shape[0] == 0) or (stitched_slice.shape[0] == 1):
            continue
        
        # Validate dimensions
        if stitched_slice.shape != tile.shape:
            print(f"---Mismatch: Stitched slice shape: {stitched_slice.shape}, ---Tile shape: {tile.shape}")
            slice_height, slice_width = stitched_slice.shape
            tile = tile[:slice_height, :slice_width]  # Crop tile to match slice
            # Debugging: Print the new tile shape
            print(f">>>New tile shape: {tile.shape}")


        # Add the tile to the corresponding position in the stitched image
        stitched_image[y_start:y_end, x_start:x_end] += tile
        # PRINT STITCHED IMAGE SIZE
        # print(f">>>Stitched image shape: {stitched_image.shape}")

    # Save the stitched image as tif, as save_path
    with rasterio.open(
        save_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=stitched_image.dtype,
        crs=crs,
        transform=transform,
    ) as dst:
        dst.write(stitched_image, 1)
        
    return stitched_image


def clean_checkpoint_keys(state_dict):
    """Fix the keys in the checkpoint by removing extra prefixes."""
    cleaned_state_dict = OrderedDict()
    for key, value in state_dict.items():
        if key.startswith("model.model."):
            new_key = key.replace("model.model.", "model.")
        elif key.startswith("model."):
            new_key = key.replace("model.", "")
        else:
            new_key = key
        cleaned_state_dict[new_key] = value
    return cleaned_state_dict
############################################################################
img_src =  Path(r"C:\Users\floodai\UNOSAT_FloodAI_v2\predictions\predict_input")
min_max_file = img_src / 'TSX_process1_stats.csv'
norm_func = 'logclipmm_g' # 'mm' or 'logclipmm'
stats = None
ckpt = Path(r"C:\Users\floodai\UNOSAT_FloodAI_v2\4results\checkpoints\all_TSX_logclipmm_g_nomask1__BS16__EP10_weighted_bce.ckpt")
save_path = img_src / 'prediction.tif'
threshold = 0.5
############################################################################

def main():
    # FIND THE SAR IMAGE
    input_list = list(i for i in img_src.iterdir() if i.is_file())
    if len(input_list) == 0:
        print(f"---No image with '*image* found in {img_src}")
    elif len(input_list) > 1:
        print(f"---Multiple images found in {img_src}. Using the first one.{input_list[0]}")
        return
    image = input_list[0]
    print(f'>>>image.name = ',image.name)
    with rasterio.open(image) as src:
        print(f'>>>src shape= ',src.shape)

    # # GET REGION CODE FROM MASK
    image_code = "_".join(image.name.split('_')[:2])
    print(f'>>>image_code= ',image_code)

    # # CREATE THE EXTRACTED FOLDER
    extracted = img_src / f'{image_code}_extracted'
    if extracted.exists():
        print(f"--- Deleting existing extracted folder: {extracted}")
        # delete the folder and create a new one
        shutil.rmtree(extracted)
    extracted.mkdir(exist_ok=True)

    # ex_extent = extracted / f'{image_code}_extent.tif'
    # create_extent_from_mask(image, ex_extent)

    reproj_image = extracted / f'{image_code}_4326.tif'
    reproject_to_4326_gdal(image, reproj_image)

    # reproj_extent = extracted / f'{image_code}_4326_extent.tif'
    # reproject_to_4326_gdal(ex_extent, reproj_extent)

    final_image = extracted / f'{reproj_image.stem}_32_final_image.tif'
    make_float32_inf(reproj_image, final_image)

    # final_extent = extracted / f'{image_code}_32_final_extent.tif'
    # make_float32_inf(reproj_extent, final_extent)

    # print_tiff_info_TSX(image=final_image) 
# 
    create_event_datacube_TSX_inf(img_src, image_code)

    cube = next(img_src.rglob("*.nc"), None)  
    save_tiles_path = img_src /  f'{image_code}_tiles'
    if save_tiles_path.exists():
        print(f">>> Deleting existing tiles folder: {save_tiles_path}")
        # delete the folder and create a new one
        shutil.rmtree(save_tiles_path)
        save_tiles_path.mkdir(exist_ok=True, parents=True)
        # CALCULATE THE STATISTICS
    min_max_file = img_src.parent / f'min_max.csv'
    stats = get_global_min_max(cube, 'hh', min_max_file= min_max_file)
    # DO THE TILING AND GET THE STATISTICS
    tiles, metadata = tile_datacube_rxr(cube, save_tiles_path, tile_size=256, stride=256, norm_func=norm_func, stats=stats, inference=True) 
    print(f">>>{len(tiles)} tiles saved to {save_tiles_path}")
    print(f">>>{len(metadata)} metadata saved to {save_tiles_path}")
    # metadata = Path(save_tiles_path) / 'tile_metadata.json'


    # INITIALIZE THE MODEL
    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = UnetModel( encoder_name="resnet34", in_channels=1, classes=1, pretrained=False 
    )   
    model.to(device)
    # LOAD THE CHECKPOINT
    ckpt_path = Path(ckpt)
    checkpoint = torch.load(ckpt_path)

    cleaned_state_dict = clean_checkpoint_keys(checkpoint["state_dict"])


    # EXTRACT THE MODEL STATE DICT
    # state_dict = checkpoint["state_dict"]

    # LOAD THE MODEL STATE DICT
    model.load_state_dict(cleaned_state_dict)

    # SET THE MODEL TO EVALUATION MODE
    model.eval()

    prediction_tiles = make_prediction_tiles(save_tiles_path, metadata, model, device, threshold)

    # STITCH PREDICTION TILES
    prediction_img = stitch_tiles(metadata, prediction_tiles, save_path, image)
    # print prediction_img size
    print(f'>>>prediction_img shape:',prediction_img.shape)
    # display the prediction mask
    plt.imshow(prediction_img, cmap='gray')



    end = time.time()
    # time taken in minutes to 2 decimal places
    print(f"Time taken: {((end - start) / 60):.2f} minutes")

if __name__ == "__main__":
    main()