import sys
import exifread

with open(sys.argv[1], "rb") as fh:
    tags = exifread.process_file(fh, details=True)

for key in sorted(tags):
    if "Thumbnail" in key or "JPEGInterchange" in key:
        continue
    value = str(tags[key])
    if len(value) > 60:
        value = value[:60] + "..."
    print(f"  {key} = {value}")
