FROM nginx:alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy AEOS nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Validate configuration at build time


EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
