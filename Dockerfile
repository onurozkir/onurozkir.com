FROM ghcr.io/gohugoio/hugo:v0.166.0 AS builder

USER root
WORKDIR /src
RUN chown hugo:hugo /src
USER hugo:hugo
COPY --chown=hugo:hugo . .

RUN hugo --minify --gc --baseURL "https://onurozkir.com/"

FROM nginx:alpine

COPY --from=builder /src/public /usr/share/nginx/html
COPY deploy/nginx-default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
