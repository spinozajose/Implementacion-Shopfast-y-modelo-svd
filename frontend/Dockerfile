# Etapa 1: compilar con Vite
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY index.html vite.config.js ./
COPY src ./src
RUN npm run build

# Etapa 2: servir con nginx (plantilla con API_KEY inyectada al iniciar)
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 80
