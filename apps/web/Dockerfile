# syntax=docker/dockerfile:1
# Build from the repository root:
#   docker build -f apps/web/Dockerfile \
#     --build-arg NEXT_PUBLIC_API_URL=https://<host>/api -t multitrack-web .
#
# NEXT_PUBLIC_* values are inlined into the browser bundle at build time, so they are build args,
# not runtime env. Two deployment shapes (the value is just the API base the browser will call):
#   single host, API under /api (Caddy strips the prefix):  https://tool.example.com/api
#   separate API host:                                      https://api.example.com
# NEXT_PUBLIC_MAX_UPLOAD_MB (optional) must match the API's MAX_UPLOAD_MB.
FROM node:22-alpine AS deps
RUN corepack enable
WORKDIR /repo/apps/web
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile

FROM node:22-alpine AS build
RUN corepack enable
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_MAX_UPLOAD_MB=100
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_MAX_UPLOAD_MB=$NEXT_PUBLIC_MAX_UPLOAD_MB \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /repo
# The prebuild script (scripts/copy-cues.mjs) copies assets/cues into public/cues.
COPY assets/cues assets/cues
WORKDIR /repo/apps/web
COPY --from=deps /repo/apps/web/node_modules node_modules
COPY apps/web ./
RUN pnpm build

FROM node:22-alpine AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /app
RUN addgroup -S -g 10001 app && adduser -S -u 10001 -G app app
COPY --from=build --chown=app:app /repo/apps/web/.next/standalone ./
COPY --from=build --chown=app:app /repo/apps/web/.next/static ./.next/static
COPY --from=build --chown=app:app /repo/apps/web/public ./public
USER app
EXPOSE 3000
CMD ["node", "server.js"]
