# tool-multitrack

A free, open-source web tool that turns a song into stems, analysis, a Stage Pack and a
Producer Pack for live musicians and producers.

All audio processing lives in a standalone Python library with a CLI. The web app, the API and
the workers only call it.

## Layout

```
apps/web              Next.js mixer and editors
apps/api              FastAPI, jobs, signed links
workers/cpu           analysis, click, guide, packs, pitch and tempo
workers/gpu           separation
packages/audio-core   Python library with all pipelines and a CLI
assets/cues           spoken cue samples (es, en)
assets/clicks         click sounds
infra                 docker-compose and infrastructure
tests/fixtures        freely licensed test songs
MODELS.md             every model checkpoint with its license and origin
```

## Running the audio-core CLI

Requirements: [uv](https://docs.astral.sh/uv/) and `ffmpeg` on the PATH.

```bash
cd packages/audio-core
uv sync
uv run audio-core --help
uv run audio-core analyze song.wav --out out/
uv run audio-core separate song.wav --out out/ --model htdemucs_6s
```

## Local services

```bash
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d
```

## License

GNU Affero General Public License v3.0. See [LICENSE](LICENSE).

The product brief (in Spanish) is at the repository root; costs are tracked in
[docs/costos.md](docs/costos.md).
