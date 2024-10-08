import rasterio
from pyproj import Transformer
from geopy.geocoders import Nominatim
import os
from pathlib import Path
import json
import time
'''
iterates through a folder and subfolders to find a tiff file and rename the folder based on the country name.
(some json reading functionality remains commented out.)
'''

# Initialize the geolocator for reverse geocoding
geolocator = Nominatim(user_agent="floodai")

def get_crs_from_tiff(tiff_path):
    with rasterio.open(tiff_path) as dataset:
        if not dataset.crs:
            raise ValueError("---CRS not found in the TIFF file")
        print(f"---CRS: {dataset.crs}")
        return dataset.crs      

# Function to get the central coordinates from a TIFF file
def get_central_coordinate_from_tiff(tiff_path):
    with rasterio.open(tiff_path) as dataset:
        # Get the bounding box of the dataset
        bbox = dataset.bounds
        # Calculate the central coordinate in the native CRS
        central_x = (bbox.left + bbox.right) / 2
        central_y = (bbox.bottom + bbox.top) / 2
        # Get the dataset CRS (e.g., UTM)
        src_crs = dataset.crs
        
        # Transform to WGS84 (EPSG:4326) for reverse geocoding (lat/lon)
        transformer = Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)
        central_lon, central_lat = transformer.transform(central_x, central_y)
        
        return central_lat, central_lon

# Function to get the country name using reverse geocoding
def get_country_name(lat, lon):
    try:
        # print(f"---Reverse geocoding lat: {lat}, lon: {lon}")  # Debug: Print coordinates being geocoded
        time.sleep(1)  # Add a delay between requests
        location = geolocator.reverse((lat, lon), language='en')
        if location and 'country' in location.raw['address']:
            return location.raw['address']['country']
        return "Unknown"
    except Exception as e:
        print(f"---Error during reverse geocoding: {e}")
        return "Unknown"

# Function to rename the folder based on the country name
def rename_folder_based_on_country(folder_path, tiff_path):
    # Get the CRS from the TIFF file
    tiff_crs = get_crs_from_tiff(tiff_path)

    # Get the central coordinate of the tiff file using the CRS from the TIFF
    central_lat, central_lon = get_central_coordinate_from_tiff(tiff_path)
    
    # Get the country name from the central coordinates
    country = get_country_name(central_lat, central_lon)
    print(f"---Country: {country} for folder: {folder_path}")
    
    # Define the new folder name
    new_folder_name = f"{country}_{folder_path.name}"
    new_folder_path = folder_path.parent / new_folder_name
    
    # Rename the folder
    try:
        os.rename(folder_path, new_folder_path)
        # print(f"Renamed folder from {folder_path} to {new_folder_path}")
        return new_folder_path
    except Exception as e:
        print(f"---Error renaming folder: {e}")
        return None
    
# Function to iterate through dataset folders and rename them
def process_dataset_folders(base_path):
    base_folder = Path(base_path)
    for folder_path in base_folder.iterdir():
        if folder_path.is_dir():
            '''
            use this if you want to extract jason info.
            '''
            # Look for the JSON file in the folder
            # json_files = list(folder_path.glob("*.json"))
            # if json_files:
            #     # Process the first JSON file found
            #     json_path = json_files[0]
            # else:
            #     print(f"---No JSON file found in {folder_path}")

            # Search for a Sentinel-1 or Sentinel-2 img TIFF file (you can adjust the pattern as needed)
            tiff_files = list(folder_path.glob("*img.tif"))  # Looks for any file ending with img.tif
                
            if tiff_files:
                # Use the first TIFF file found
                tiff_path = tiff_files[0]
                # Proceed with renaming using the JSON and the TIFF file to get the CRS
                rename_folder_based_on_country(folder_path, tiff_path)
            else:
                    print(f"---No suitable TIFF file found in {folder_path}")


# Example usage
base_path_root = r"X:\1NEW_DATA\1data\2interim"
base_path = Path(base_path_root) / "dataset_rename_test"
# print("---Processing dataset folders in:", base_path)
# print(f"----Checking path: {base_path}")
if base_path.exists():
    # print("---Path exists.")
else:
    print("---Path does not exist:", base_path)
process_dataset_folders(base_path)

