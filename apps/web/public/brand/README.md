# Brand assets

Provenance of the rasters in this folder.

| File | Source | Used for |
| --- | --- | --- |
| `funke-orange.webp` | Funke brand kit, Logo-01 (orange, transparent, 4000x2022) | Top bar mark |
| `funke-white.webp` | Funke brand kit, Logo-02 (white, transparent, 4000x2022) | Reserved for orange or paper-light surfaces |

Converted on 2026-10-26 to 640x323 with alpha preserved:

```sh
sips -Z 640 "Funke - Logo-01.png" --out funke-orange.png
cwebp -q 90 -alpha_q 100 -m 6 funke-orange.png -o funke-orange.webp
# same for Logo-02 -> funke-white.webp
```

The logo is the property of funke. Do not recolor or redraw it.

The Funke name and logos are trademarks of Funke and are not covered by the AGPL-3.0 license of this repository.
