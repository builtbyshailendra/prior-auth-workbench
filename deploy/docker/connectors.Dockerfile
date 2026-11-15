# syntax=docker/dockerfile:1
# The connector service. Node runs the TypeScript directly; it has no runtime dependencies.
#   docker build -f deploy/docker/connectors.Dockerfile -t priorauth-connectors connectors
#   docker run --rm -e CONNECTOR_TOKEN=... -e WORKFLOW_URL=... -v ./inbox:/inbox priorauth-connectors ingest /inbox

FROM node:26.13.1-alpine
WORKDIR /srv
ENV NODE_ENV=production \
    OUTBOX_DIR=/tmp/outbox

COPY package.json ./
COPY src ./src
COPY fixtures ./fixtures

USER 1000
ENTRYPOINT ["node", "src/cli.ts"]
CMD ["ingest", "fixtures"]
