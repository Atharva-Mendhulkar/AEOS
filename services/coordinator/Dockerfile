FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build
RUN npm prune --production

EXPOSE 8001

CMD ["node", "dist/index.js"]
