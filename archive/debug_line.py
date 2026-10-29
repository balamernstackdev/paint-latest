import sys
import numpy as np

try:
    with open('core/segmentation.py', 'r') as f:
        lines = f.readlines()
        print(f"Line 172: {lines[171].strip()}")
except Exception as e:
    print(e)
