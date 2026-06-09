FROM klakegg/hugo:ext-alpine AS builder

WORKDIR /src
COPY . .

RUN hugo --minify --gc --baseURL "https://onurozkir.com/"

FROM nginx:alpine

COPY --from=builder /src/public /usr/share/nginx/html

EXPOSE 80
