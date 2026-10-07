FROM golang:1.27.1 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/servidor ./cmd/servidor && CGO_ENABLED=0 go build -o /out/migrar ./cmd/migrar

FROM gcr.io/distroless/static-debian12
WORKDIR /app
COPY --from=build /out/ /app/
COPY migrations /app/migrations
EXPOSE 8080
ENTRYPOINT ["/app/servidor"]
