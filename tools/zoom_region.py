"""Powieksza fragment zrzutu ekranu - do ogladania drobnych elementow."""

import sys

import cv2

source, target = sys.argv[1], sys.argv[2]
x, y, w, h = (int(v) for v in sys.argv[3:7])
factor = int(sys.argv[7]) if len(sys.argv) > 7 else 6

image = cv2.imread(source)
patch = image[y : y + h, x : x + w]
big = cv2.resize(patch, (w * factor, h * factor), interpolation=cv2.INTER_NEAREST)
cv2.imwrite(target, big)
print(f"{patch.shape[1]}x{patch.shape[0]} -> {big.shape[1]}x{big.shape[0]}, zapisano {target}")
