"""Tnie wysoki arkusz na czesci, zeby dalo sie go obejrzec."""

import sys

import cv2

source = sys.argv[1]
parts = int(sys.argv[2]) if len(sys.argv) > 2 else 3
image = cv2.imread(source)
step = image.shape[0] // parts
for index in range(parts):
    end = image.shape[0] if index == parts - 1 else (index + 1) * step
    name = source.replace(".jpg", f"_{index + 1}.jpg")
    cv2.imwrite(name, image[index * step:end], [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(name)
