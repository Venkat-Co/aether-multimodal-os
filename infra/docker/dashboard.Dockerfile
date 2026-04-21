FROM node:20-alpine AS builder

WORKDIR /app
COPY dashboard/package.json ./
RUN npm install
COPY dashboard ./
RUN npm run build

FROM node:20-alpine

WORKDIR /app
COPY --from=builder /app ./
EXPOSE 3000
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "3000", "--strictPort"]
