

import torch
import numpy as np
import xarray as xr
from pathlib import Path
import tifffile as tiff
from model_definition import UnetModel  # Adjust the import to your model definition
from scripts.process_modules.process_dataarrays_module import log_clip_minmaxnorm  # Adjust the import to your preprocessing function


input_file_name = ''
input_path = Path(f'C:\Users\floodai\UNOSAT_FloodAI_v2\prediction' / input_file_name)
checkpoint = xxxxx
checkpoint_path = Path(r"C:\Users\floodai\UNOSAT_FloodAI_v2\4results\checkpoints" / checkpoint)
output_path =  input_path / 'predictions'


def load_model(checkpoint_path, device='cuda'):
    model = UnetModel(encoder_name='resnet34', in_channels=2, classes=1)  # Update based on your architecture
    model.load_state_dict(torch.load(checkpoint_path, map_location=device))
    model.to(device)
    model.eval()
    return model

def preprocess_tile(tile, device):
    preprocessed_tile, _ = log_clip_minmaxnorm(tile)
    tile_data = preprocessed_tile.values
    tensor = torch.tensor(tile_data, dtype=torch.float32).unsqueeze(0)  # Add batch dimension
    return tensor.to(device)

def postprocess_predictions(predictions, threshold=0.5):
    binary_mask = (predictions > threshold).float().cpu().numpy()
    return binary_mask

def split_into_tiles(image, tile_size, overlap):
    """Split a large image into overlapping tiles."""
    _, height, width = image.shape
    stride = tile_size - overlap
    tiles = []
    positions = []

    for y in range(0, height - tile_size + 1, stride):
        for x in range(0, width - tile_size + 1, stride):
            tile = image[:, y:y + tile_size, x:x + tile_size]
            tiles.append(tile)
            positions.append((y, x))
    return tiles, positions

def stitch_tiles(tiles, positions, image_shape, tile_size, overlap):
    """Stitch tiles back together into a single image."""
    _, height, width = image_shape
    full_mask = np.zeros((1, height, width))
    count = np.zeros((1, height, width))

    stride = tile_size - overlap
    for tile, (y, x) in zip(tiles, positions):
        full_mask[:, y:y + tile_size, x:x + tile_size] += tile
        count[:, y:y + tile_size, x:x + tile_size] += 1

    return (full_mask / count).squeeze(0)  # Normalize and return

def run_inference_on_image(model, image, tile_size, overlap, device='cuda'):
    """Run inference on a full image."""
    tiles, positions = split_into_tiles(image, tile_size, overlap)
    predictions = []

    for tile in tiles:
        tile_tensor = preprocess_tile(xr.DataArray(tile), device)
        with torch.no_grad():
            prediction = model(tile_tensor).squeeze(0).cpu().numpy()
        predictions.append(prediction)

    full_mask = stitch_tiles(predictions, positions, image.shape, tile_size, overlap)
    return postprocess_predictions(full_mask)



def main(input_path, checkpoint_path, output_path, tile_size=256, overlap=32, device='cuda'):
    # Load the trained model
    model = load_model(checkpoint_path, device)

    # Load the input SAR image
    input_image = xr.open_dataset(input_path)['tile'].values  # Adjust based on dataset format
    input_image = np.expand_dims(input_image, axis=0)  # Add channel dimension if needed

    # Run inference on the full image
    predictions = run_inference_on_image(model, input_image, tile_size, overlap, device)

    # Save the output prediction
    output_file = Path(output_path) / f"{Path(input_path).stem}_prediction.tif"
    tiff.imwrite(output_file, (predictions * 255).astype(np.uint8))  # Save as binary mask
    print(f"Predictions saved to {output_file}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run inference on a full image using a trained U-Net model.")
    parser.add_argument("--input", type=str, required=True, help="Path to input SAR image (GeoTIFF or NetCDF).")
    parser.add_argument("--checkpoint", type=str, required=True, help="Path to model checkpoint.")
    parser.add_argument("--output", type=str, required=True, help="Directory to save the output prediction.")
    parser.add_argument("--tile_size", type=int, default=256, help="Size of the tiles for inference.")
    parser.add_argument("--overlap", type=int, default=32, help="Overlap between tiles.")
    parser.add_argument("--device", type=str, default="cuda", help="Device to run inference on ('cuda' or 'cpu').")
    args = parser.parse_args()

    main(args.input, args.checkpoint, args.output, args.tile_size, args.overlap, args.device)