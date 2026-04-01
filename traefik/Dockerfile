FROM traefik:v3.0
RUN apk add --no-cache gettext
COPY traefik.yml /etc/traefik/traefik.yml
COPY routes.yml.tmpl /etc/traefik/routes.yml.tmpl
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
