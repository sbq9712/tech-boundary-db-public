FROM nginx:1.27-alpine

# The web image is an explicit public-file whitelist. Never serve the repository root.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY *.html *.js *.css /usr/share/nginx/html/
COPY lib/extractor.js /usr/share/nginx/html/lib/extractor.js
COPY data/*.json data/*.csv /usr/share/nginx/html/data/
COPY breadth/index.html breadth/app.js breadth/styles.css /usr/share/nginx/html/breadth/
COPY breadth/data/category-order-data.js breadth/data/category-order.json /usr/share/nginx/html/breadth/data/
COPY breadth/data/processed /usr/share/nginx/html/breadth/data/processed
