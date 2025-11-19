# 2. nginx.Dockerfile (at the project root)

# --- Stage 1: Build the React App ---
    FROM node:18-alpine AS builder

    # Set working directory
    WORKDIR /app
    
    # Copy the package.json and install dependencies
    COPY frontend/package.json .
    COPY frontend/package-lock.json .
    RUN npm install
    
    # Copy the rest of the frontend source code
    COPY frontend/ .
    
    # Get the VITE_API_URL from the docker-compose build command
    ARG VITE_API_URL
    # Build the production app
    RUN VITE_API_URL=$VITE_API_URL npm run build
    
    # --- Stage 2: Create the final Nginx server ---
    FROM nginx:1.25-alpine
    
    # Copy the built static files from the 'builder' stage
    COPY --from=builder /app/dist /usr/share/nginx/html
    
    # Copy your new Nginx configuration file
    COPY nginx.conf /etc/nginx/conf.d/default.conf
    
    # Expose port 80
    EXPOSE 80