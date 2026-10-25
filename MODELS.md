# Models

| Model | Task | Source | License | Notes |
| --- | --- | --- | --- | --- |
| `htdemucs_ft` | Source separation, 4 stems (drums, bass, other, vocals) | Demucs, Meta: https://github.com/facebookresearch/demucs | MIT | Fine-tuned Hybrid Transformer Demucs. |
| `htdemucs_6s` | Source separation, 6 stems (drums, bass, other, vocals, guitar, piano) | Demucs, Meta: https://github.com/facebookresearch/demucs | MIT | Default model. Guitar and piano stems are lower quality than the other four. |

## Rule

No checkpoint is used before its license is recorded in this file. Non-commercial or unlicensed
weights are not allowed, because the tool is agency-branded and therefore used commercially.
