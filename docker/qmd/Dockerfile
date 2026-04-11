FROM node:22-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @tobilu/qmd

RUN groupadd -r qmd && useradd -r -g qmd -m -d /home/qmd qmd

RUN mkdir -p /vault /home/qmd/.cache/qmd \
    && chown -R qmd:qmd /home/qmd/.cache

COPY --chown=qmd:qmd server.mjs /opt/qmd/server.mjs

USER qmd

ENV VAULT_PATH=/vault
ENV QMD_PORT=3100
ENV NODE_ENV=production
ENV XDG_CONFIG_HOME=/home/qmd/.cache

EXPOSE 3100

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD node -e "fetch('http://localhost:3100/health').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"

ENTRYPOINT ["tini", "--"]
CMD ["node", "/opt/qmd/server.mjs"]
