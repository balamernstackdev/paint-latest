import requests
import os

url = "https://github.com/ChaoningZhang/MobileSAM/raw/master/weights/mobile_sam.pt"
output_path = "weights/mobile_sam.pt"

if not os.path.exists("weights"):
    os.makedirs("weights")

print(f"Downloading {url}...")
response = requests.get(url, stream=True)
response.raise_for_status()

with open(output_path, "wb") as f:
    for chunk in response.iter_content(chunk_size=8192):
        f.write(chunk)

print(f"Downloaded to {output_path}")
