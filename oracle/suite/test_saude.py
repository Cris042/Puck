def test_saude_responde_ok(anonimo):
    resposta = anonimo.get("/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}
