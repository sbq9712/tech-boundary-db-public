FROM nginx:1.27-alpine

# The web image is an explicit public-file whitelist. Never serve the repository root.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY *.html *.js *.css /usr/share/nginx/html/
COPY lib/extractor.js /usr/share/nginx/html/lib/extractor.js
COPY assets /usr/share/nginx/html/assets
COPY data/*.json data/*.csv /usr/share/nginx/html/data/
COPY breadth/index.html breadth/app.js breadth/qa.js breadth/styles.css /usr/share/nginx/html/breadth/
COPY breadth/data/category-order-data.js breadth/data/category-order.json /usr/share/nginx/html/breadth/data/
COPY breadth/version.txt /usr/share/nginx/html/breadth/version.txt
COPY breadth/data/processed /usr/share/nginx/html/breadth/data/processed

# A rebuilt web image must never silently ship without the pinned breadth runtime.
# Shard count is dynamic (data volume decides); the invariant is that all three
# prefix families agree and are non-zero.
RUN set -eu; \
    runtime=/usr/share/nginx/html/breadth/data/processed; \
    for file in manifest-data.js manifest.json alert-records.json category-counts.json; do \
      test -s "$runtime/$file" || { echo "Missing breadth runtime file: $file" >&2; exit 1; }; \
    done; \
    lite="$(find "$runtime" -type f -name 'lite-part-*.js' | wc -l | tr -d ' ')"; \
    meta="$(find "$runtime" -type f -name 'meta-part-*.js' | wc -l | tr -d ' ')"; \
    summary="$(find "$runtime" -type f -name 'summary-part-*.js' | wc -l | tr -d ' ')"; \
    test "$lite" -gt 0 -a "$lite" -eq "$meta" -a "$meta" -eq "$summary" || \
      { echo "Shard families disagree: lite=$lite meta=$meta summary=$summary" >&2; exit 1; }

# Regression guard (2nd incident): a stray </div> in breadth/index.html once closed
# aside.sidebar + div.layout early, pushing main.content below the fold — the whole
# right side looked blank. Fail the build on div imbalance.
RUN set -eu; \
    page=/usr/share/nginx/html/breadth/index.html; \
    opens="$(grep -o '<div\b' "$page" | wc -l | tr -d ' ')"; \
    closes="$(grep -o '</div>' "$page" | wc -l | tr -d ' ')"; \
    test "$opens" -eq "$closes" || \
      { echo "breadth/index.html div imbalance: <div>=$opens </div>=$closes — layout would break" >&2; exit 1; }
