# Build stage
FROM node:20-alpine AS build

WORKDIR /app

# Build argument for admin password hash (SHA-256)
# Default: "Ruckus123!" = 8f4179b458b4e4622c32089b025ff4e4b531137642dfdf5143b5f29af3c32e84
ARG VITE_ADMIN_PASSWORD_HASH=8f4179b458b4e4622c32089b025ff4e4b531137642dfdf5143b5f29af3c32e84

# Set as environment variable for Vite build
ENV VITE_ADMIN_PASSWORD_HASH=${VITE_ADMIN_PASSWORD_HASH}

# Copy package files
COPY package.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
