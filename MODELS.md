# Models

| Model | Task | Source | License | Notes |
| --- | --- | --- | --- | --- |
| `htdemucs_ft` | Source separation, 4 stems (drums, bass, other, vocals) | Demucs, Meta: https://github.com/facebookresearch/demucs | MIT | Fine-tuned Hybrid Transformer Demucs. |
| `htdemucs_6s` | Source separation, 6 stems (drums, bass, other, vocals, guitar, piano) | Demucs, Meta: https://github.com/facebookresearch/demucs | MIT | Default model. Guitar and piano stems are lower quality than the other four. |
| `beat_this` `final0` | Beat and downbeat tracking | CPJKU beat_this: https://github.com/CPJKU/beat_this (PyPI `beat_this`) | MIT | Default checkpoint, run on CPU without the madmom DBN post-processor. |

## Checkpoint download and caching

Demucs weights are not vendored. `demucs.pretrained.get_model` downloads them on first use from the
Meta release URLs (`https://dl.fbaipublicfiles.com/demucs/...`, referenced by the Demucs package
configuration) and caches them in the torch hub cache (`$TORCH_HOME/hub/checkpoints`, by default
`~/.cache/torch/hub/checkpoints`). `htdemucs_ft` is a bag of four fine-tuned models, so its first
download is about four times the size of a single checkpoint. Only the names in this file are
accepted by `audio_core.separation.ALLOWED_MODELS`.

## Rule

No checkpoint is used before its license is recorded in this file. Non-commercial or unlicensed
weights are not allowed, because the tool is agency-branded and therefore used commercially.
