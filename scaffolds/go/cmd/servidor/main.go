// Servidor HTTP da aplicação. Contrato com o harness: escuta em $PORT e responde GET /saude.
package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"escola/internal/infra/banco"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	pool, err := banco.Conectar(ctx)
	if err != nil {
		logger.Error("banco indisponível", "erro", err)
		os.Exit(1)
	}
	defer pool.Close()

	servidor := &http.Server{
		Addr:              ":" + porta(),
		Handler:           rotas(),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       60 * time.Second,
		MaxHeaderBytes:    1 << 20,
	}
	go func() {
		<-ctx.Done()
		desligar, cancelar := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancelar()
		_ = servidor.Shutdown(desligar)
	}()
	logger.Info("servidor no ar", "endereco", servidor.Addr)
	if err := servidor.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		logger.Error("servidor parou", "erro", err)
		os.Exit(1)
	}
}

func rotas() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /saude", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})
	return mux
}

func porta() string {
	if valor := os.Getenv("PORT"); valor != "" {
		return valor
	}
	return "8080"
}
