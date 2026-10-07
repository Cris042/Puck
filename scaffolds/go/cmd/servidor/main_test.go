package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSaudeRespondeOk(t *testing.T) {
	resposta := httptest.NewRecorder()
	rotas().ServeHTTP(resposta, httptest.NewRequest(http.MethodGet, "/saude", nil))

	if resposta.Code != http.StatusOK {
		t.Fatalf("status = %d, esperado 200", resposta.Code)
	}
	if corpo := resposta.Body.String(); corpo != "{\"status\":\"ok\"}\n" {
		t.Fatalf("corpo = %q", corpo)
	}
}
