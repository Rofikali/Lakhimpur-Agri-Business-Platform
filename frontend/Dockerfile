# # frontend/Dockerfile — multi-stage
# frontend/Dockerfile

# FROM node:20-alpine AS base
FROM node:22-alpine AS base

WORKDIR /app

ENV NODE_ENV=development

# Enable pnpm (comes with Node via Corepack)
RUN corepack enable

# -----------------------------
# Development
# -----------------------------
FROM base AS development

COPY package.json pnpm-lock.yaml ./

RUN pnpm install --frozen-lockfile --ignore-scripts=false
# RUN pnpm install --frozen-lockfile

COPY . .

EXPOSE 3000

CMD ["pnpm", "dev"]

# -----------------------------
# Build
# -----------------------------
FROM base AS builder

ENV NODE_ENV=production

COPY package.json pnpm-lock.yaml ./

RUN pnpm install --frozen-lockfile

COPY . .

RUN pnpm build

# -----------------------------
# Production
# -----------------------------
FROM node:20-alpine AS production


WORKDIR /app

COPY --from=builder /app/.output ./

ENV HOST=0.0.0.0
ENV PORT=3000
ENV NODE_ENV=production

EXPOSE 3000

CMD ["node", "server/index.mjs"]

# FROM node:20-alpine AS base

# WORKDIR /app
# ENV NODE_ENV=development

# # Development stage
# FROM base AS development
# COPY package*.json ./
# RUN npm ci
# COPY . .
# EXPOSE 3000
# CMD ["npm", "run", "dev"]

# # Build stage
# FROM base AS builder
# ENV NODE_ENV=production
# COPY package*.json ./
# RUN npm ci --only=production
# COPY . .
# RUN npm run build

# # Production stage
# FROM node:20-alpine AS production
# WORKDIR /app
# COPY --from=builder /app/.output ./
# ENV HOST=0.0.0.0 PORT=3000 NODE_ENV=production
# EXPOSE 3000
# CMD ["node", "server/index.mjs"]