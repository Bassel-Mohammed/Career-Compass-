FROM node:22-alpine

WORKDIR /app

# WORKDIR is created as root. Give the development user ownership before
# `npm ci` creates node_modules in this directory.
RUN chown node:node /app

# Install from the lockfile first so dependency layers survive source changes.
COPY --chown=node:node package.json package-lock.json ./

USER node

RUN npm ci

COPY --chown=node:node . .

EXPOSE 5173

# This image is intentionally a development image: Vite serves the source and
# receives the browser-facing Spring URL through VITE_API_BASE_URL at runtime.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173", "--strictPort"]
