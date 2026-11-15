# syntax=docker/dockerfile:1
# The reviewer screen.
#   docker build -f deploy/docker/web.Dockerfile -t priorauth-web web

FROM node:26.13.1-alpine AS build
WORKDIR /src
ENV NEXT_TELEMETRY_DISABLED=1

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# Next.js writes the API address into the build output, so it's a build argument.
# "workflow" is the service name in both compose and Kubernetes.
ARG API_URL=http://workflow:8000
RUN API_URL="$API_URL" BUILD_STANDALONE=1 npm run build


FROM node:26.13.1-alpine
WORKDIR /srv
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

# Only the standalone server and its static files: no source, no build-stage node_modules.
COPY --from=build --chown=1000:1000 /src/.next/standalone ./
COPY --from=build --chown=1000:1000 /src/.next/static ./.next/static

USER 1000
EXPOSE 3000
CMD ["node", "server.js"]
