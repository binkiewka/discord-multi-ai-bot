FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source files
COPY . .

# Build argument for client ID
ARG VITE_DISCORD_CLIENT_ID
ENV VITE_DISCORD_CLIENT_ID=$VITE_DISCORD_CLIENT_ID

# Build the application
RUN npm run build

# Production stage - serve with nginx
FROM nginx:alpine

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built files
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
