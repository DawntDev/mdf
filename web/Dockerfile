# syntax=docker/dockerfile:1.7
# -----------------------------------------------------------------------------
# MDF Dictionary Extractor — Web image (multi-stage)
# -----------------------------------------------------------------------------
# Stage 1 builds the production bundle with pnpm.
# Stage 2 serves the static bundle through Nginx and reverse-proxies /api/
# calls to the backend service on the compose network.
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Stage 1 — build
# -----------------------------------------------------------------------------
FROM node:20-alpine AS builder

# VITE_API_BASE_URL is baked into the bundle at build time. In the compose
# setup we leave it empty so the browser calls same-origin URLs (e.g.
# /api/v1/models) and Nginx proxies them to the api service.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN corepack enable

WORKDIR /app

# Install dependencies first to maximize Docker layer caching.
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Build the SPA.
COPY . .
RUN pnpm build

# -----------------------------------------------------------------------------
# Stage 2 — serve
# -----------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Replace the default server block with our SPA + proxy configuration.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Ship only the built assets.
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
