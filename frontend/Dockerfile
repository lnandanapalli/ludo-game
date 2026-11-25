# Ludo web client: a Vite build served as static files by nginx on port 80.
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# The API origin is compiled into the bundle, e.g. https://ludoapi.example.com
ARG VITE_API_URL
RUN test -n "$VITE_API_URL" || { echo "Pass --build-arg VITE_API_URL=https://<api host>"; exit 1; }
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
