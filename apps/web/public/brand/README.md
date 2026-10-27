# Brand assets

Provenance of the rasters in this folder.

| File | Source | Used for |
| --- | --- | --- |
| `funke-orange.webp` | `the Funke brand kit/Funke - Logo-01.png` (orange, transparent, 4000x2022) | Top bar mark |
| `funke-white.webp` | `the Funke brand kit/Funke - Logo-02.png` (white, transparent, 4000x2022) | Reserved for orange or paper-light surfaces |

Converted on 2026-10-26 to 640x323 with alpha preserved:

```sh
sips -Z 640 "Funke - Logo-01.png" --out funke-orange.png
cwebp -q 90 -alpha_q 100 -m 6 funke-orange.png -o funke-orange.webp
# same for Logo-02 -> funke-white.webp
```

The logo is the property of funke. Do not recolor or redraw it.
