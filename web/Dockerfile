FROM nginx:1.27-alpine

# The web image is an explicit public-file whitelist. Never serve the repository root.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY *.html *.js *.css /usr/share/nginx/html/
COPY lib/extractor.js /usr/share/nginx/html/lib/extractor.js
COPY assets /usr/share/nginx/html/assets
COPY data/*.json data/*.csv /usr/share/nginx/html/data/
COPY breadth/index.html breadth/app.js breadth/styles.css /usr/share/nginx/html/breadth/
COPY breadth/data/category-order-data.js breadth/data/category-order.json /usr/share/nginx/html/breadth/data/
COPY breadth/data/processed /usr/share/nginx/html/breadth/data/processed

# A rebuilt web image must never silently ship without the pinned breadth runtime.
RUN set -eu; \
    runtime=/usr/share/nginx/html/breadth/data/processed; \
    for file in manifest-data.js manifest.json alert-records.json category-counts.json; do \
      test -s "$runtime/$file" || { echo "Missing breadth runtime file: $file" >&2; exit 1; }; \
    done; \
    for prefix in lite-part meta-part summary-part; do \
      count="$(find "$runtime" -type f -name "$prefix-*.js" | wc -l | tr -d ' ')"; \
      test "$count" -eq 30 || { echo "Expected 30 $prefix shards, found $count" >&2; exit 1; }; \
    done
