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
packages/audio-core   Python library with all pipelines and a CLI
assets/cues           spoken cue samples (es, en)
infra                 docker-compose and deployment
scripts               evaluation and smoke-test scripts
docs                  product brief and notes (Spanish)
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

## Development

Python projects (`packages/audio-core`, `apps/api`, `workers/cpu`) use uv:

```bash
cd packages/audio-core   # or apps/api, workers/cpu
uv sync
uv run ruff check .
uv run pytest
```

Web app (needs [pnpm](https://pnpm.io/)):

```bash
cd apps/web
pnpm install
pnpm dev          # next dev
pnpm lint
pnpm typecheck
pnpm test         # vitest
```

Full stack with Docker Compose:

```bash
cp infra/.env.example infra/.env   # replace every placeholder
docker compose -f infra/docker-compose.yml up --build
```

More detail: [infra/README.md](infra/README.md) (local stack),
[infra/prod/README.md](infra/prod/README.md) (VPS deployment),
[scripts/README.md](scripts/README.md), [MODELS.md](MODELS.md),
[DESIGN.md](DESIGN.md) and [PRODUCT.md](PRODUCT.md). The product brief (in Spanish) is at
[docs/brief.md](docs/brief.md).

## License

GNU Affero General Public License v3.0. See [LICENSE](LICENSE).

The Funke name and logos are trademarks of Funke and are not covered by the AGPL-3.0 license of
this repository.
