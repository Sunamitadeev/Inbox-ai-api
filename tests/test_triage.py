"""Automated test suite covering unit rules, AI fallback, schema validation, and API endpoints.

Este módulo implementa testes automatizados utilizando Pytest e FastAPI TestClient.
Todos os testes são herméticos e rodam contra um banco SQLite temporário isolado,
garantindo que o banco de dados de desenvolvimento não seja afetado.
"""

import os
import tempfile
from typing import Generator
import pytest
from fastapi.testclient import TestClient

from src.database import init_db
from src.schemas import MessageInput, TriageResult
from src.services.ai_classifier import classify_message


# ---------------------------------------------------------------------------
# Fixture: Banco de dados temporário e isolado para testes
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolated_test_database() -> Generator[str, None, None]:
    """Cria um arquivo SQLite temporário exclusivo para cada execução de teste."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    os.environ["DATABASE_PATH"] = db_path
    init_db(db_path)

    yield db_path

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def client(isolated_test_database: str) -> Generator[TestClient, None, None]:
    """Inicializa o TestClient do FastAPI garantindo o disparo do lifespan."""
    from src.main import app

    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# 1. Testes Unitários: Classificador e Fallback Determinístico Local
# ---------------------------------------------------------------------------
class TestAiClassifierUnit:
    """Testes unitários para validar a lógica heurística de fallback do classificador."""

    def test_cancellation_fallback_classifies_as_high_urgency(self) -> None:
        """RF-03 e RF-04: Cancelamento deve sempre ser classificado com urgência 'alta'."""
        result = classify_message("Gostaria de cancelar meu plano imediatamente!", api_key=None)

        assert isinstance(result, TriageResult)
        assert result.category == "cancelamento"
        assert result.urgency == "alta"
        assert result.used_fallback is True
        assert "retenção" in result.suggested_action.lower()

    def test_financial_fallback_classification(self) -> None:
        """RF-02: Perguntas sobre fatura/boleto devem ser mapeadas para 'financeiro'."""
        result = classify_message("Preciso da segunda via do meu boleto bancário.", api_key=None)

        assert result.category == "financeiro"
        assert result.urgency in ["media", "alta"]
        assert result.used_fallback is True

    def test_technical_support_fallback_classification(self) -> None:
        """RF-02: Erros de sistema devem ser mapeados para 'suporte_tecnico'."""
        result = classify_message("O aplicativo está travando com erro 500 no login.", api_key=None)

        assert result.category == "suporte_tecnico"
        assert result.used_fallback is True

    def test_general_inquiry_fallback_classification(self) -> None:
        """RF-02: Dúvidas informativas gerais devem ser mapeadas para 'duvida_geral' com urgência baixa."""
        result = classify_message("Qual o horário de atendimento presencial de vocês?", api_key=None)

        assert result.category == "duvida_geral"
        assert result.urgency == "baixa"
        assert result.used_fallback is True


# ---------------------------------------------------------------------------
# 2. Testes Unitários de Schemas Pydantic v2
# ---------------------------------------------------------------------------
class TestSchemasValidation:
    """Testes de validação dos contratos de dados (DTOs)."""

    def test_empty_or_whitespace_message_raises_validation_error(self) -> None:
        """RNF-01: Mensagens vazias ou contendo apenas espaços devem falhar na validação."""
        with pytest.raises(ValueError):
            MessageInput(content="    ")

    def test_valid_message_strips_leading_trailing_spaces(self) -> None:
        """Mensagens com espaços excedentes nas extremidades devem ser sanitizadas."""
        model = MessageInput(content="  Preciso de ajuda urgente  ")
        assert model.content == "Preciso de ajuda urgente"


# ---------------------------------------------------------------------------
# 3. Testes de Integração de API Endpoints (FastAPI + TestClient)
# ---------------------------------------------------------------------------
class TestApiEndpoints:
    """Testes de ponta a ponta dos endpoints HTTP."""

    def test_health_check_endpoint(self, client: TestClient) -> None:
        """Verifica o status saudável do serviço."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "inbox-ai-api"

    def test_triage_rejects_empty_content_with_http_422(self, client: TestClient) -> None:
        """RNF-01: Envio de string composta apenas por espaços deve retornar HTTP 422."""
        response = client.post("/triage", json={"content": "     "})
        assert response.status_code == 422

    def test_triage_flow_and_metrics_accumulation(self, client: TestClient) -> None:
        """Fluxo completo: POST /triage (múltiplas mensagens) -> GET /tickets -> GET /metrics."""
        # 1. Enviar mensagem de cancelamento (urgência alta)
        res_cancel = client.post(
            "/triage",
            json={"content": "Quero cancelar minha assinatura agora!"},
        )
        assert res_cancel.status_code == 201
        data_cancel = res_cancel.json()
        assert data_cancel["id"] == 1
        assert data_cancel["category"] == "cancelamento"
        assert data_cancel["urgency"] == "alta"
        assert data_cancel["used_fallback"] is True

        # 2. Enviar mensagem de suporte técnico
        res_tech = client.post(
            "/triage",
            json={"content": "Estou com erro 500 ao tentar entrar no painel."},
        )
        assert res_tech.status_code == 201
        data_tech = res_tech.json()
        assert data_tech["id"] == 2
        assert data_tech["category"] == "suporte_tecnico"

        # 3. Listar todos os tickets
        res_all = client.get("/tickets")
        assert res_all.status_code == 200
        tickets = res_all.json()
        assert len(tickets) == 2

        # 4. Listar filtrando por urgência alta
        res_high = client.get("/tickets?urgency=alta")
        assert res_high.status_code == 200
        high_tickets = res_high.json()
        assert len(high_tickets) >= 1
        assert all(t["urgency"] == "alta" for t in high_tickets)

        # 5. Consultar métricas agregadas
        res_metrics = client.get("/metrics")
        assert res_metrics.status_code == 200
        metrics = res_metrics.json()

        assert metrics["total_tickets"] == 2
        assert metrics["fallback_count"] == 2
        assert metrics["by_category"]["cancelamento"] == 1
        assert metrics["by_category"]["suporte_tecnico"] == 1
        assert "alta" in metrics["by_urgency"]
