# Build tahap 1: compile React (Vite) jadi static assets
FROM node:20-alpine AS build
WORKDIR /app

# VITE_API_URL di-bake ke bundle saat build — set lewat build arg jika backend
# tidak berada di http://localhost:5000 (default untuk dev lokal).
ARG VITE_API_URL=http://localhost:5000
ENV VITE_API_URL=$VITE_API_URL

COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Build tahap 2: serve hasil build dengan nginx ringan
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
