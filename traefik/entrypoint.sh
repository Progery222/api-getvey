#!/bin/sh
set -e
envsubst < /etc/traefik/routes.yml.tmpl > /etc/traefik/routes.yml
exec traefik "$@"
