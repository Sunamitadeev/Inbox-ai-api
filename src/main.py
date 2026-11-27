"""FastAPI application initialization, lifespan, and REST API endpoints.

Este módulo orquestra a aplicação:
- Inicializa o banco de dados SQLite no ciclo de vida (lifespan) da aplicação;
- Expõe endpoints REST para triagem inteligente, listagem de tickets e métricas consolidadas.
"""

from contextlib import asynccontextmanager
import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from dotenv import load_dotenv

from src.database import get_db_connection, init_db
from src.repositories import ticket_repo
from src.schemas import (
    MessageInput,
    MetricsResponse,
    TicketResponse,
    UrgencyType,
)
from src.services.ai_classifier import classify_message

# Carrega variáveis de ambiente do arquivo .env (caso exista)
load_dotenv()

# Configuração básica de logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciador do ciclo de vida da aplicação (Lifespan).
    
    Executa a inicialização do esquema do banco de dados na subida da aplicação
    e lida com eventuais limpezas ou finalizações no shutdown.
    """
    logger.info("Inicializando banco de dados no lifespan da aplicação...")
    init_db()
    logger.info("Banco de dados pronto para receber requisições.")
    yield
    logger.info("Encerrando aplicação.")


# Inicialização da instância FastAPI com metadados para documentação automática (/docs)
app = FastAPI(
    title="Inbox AI API",
    description="API REST de triagem inteligente e resiliente para atendimento ao cliente.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/", tags=["Health"])
def health_check():
    """Endpoint simples para verificação de status e saúde do serviço."""
    return {"status": "healthy", "service": "inbox-ai-api", "version": "1.0.0"}


@app.post(
    "/triage",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Triar mensagem de atendimento",
    description="Recebe a mensagem do cliente, classifica via IA (ou fallback) e persiste o ticket.",
    tags=["Triage"],
)
def triage_message(payload: MessageInput) -> TicketResponse:
    """Endpoint principal de triagem de mensagens.
    
    1. Recebe e valida o payload com Pydantic v2 (MessageInput).
    2. Envia para o serviço de inteligência artificial (Gemini ou fallback).
    3. Persiste o ticket no banco de dados usando conexão segura via context manager.
    4. Retorna os dados completos do ticket criado com status HTTP 201 Created.
    """
    # Classificação inteligente (LLM Gemini com fallback determinístico local)
    triage_result = classify_message(payload.content)

    # Persistência no banco via Repository Pattern e context manager
    with get_db_connection() as conn:
        saved_ticket = ticket_repo.save_ticket(
            conn=conn,
            content=payload.content,
            category=triage_result.category,
            urgency=triage_result.urgency,
            suggested_action=triage_result.suggested_action,
            used_fallback=triage_result.used_fallback,
        )

    logger.info(
        f"Ticket #{saved_ticket['id']} criado | Categoria: {saved_ticket['category']} | "
        f"Urgência: {saved_ticket['urgency']} | Fallback: {saved_ticket['used_fallback']}"
    )
    return TicketResponse(**saved_ticket)


@app.get(
    "/tickets",
    response_model=List[TicketResponse],
    summary="Listar tickets registrados",
    description="Retorna a lista de tickets persistidos, suportando filtro opcional por urgência.",
    tags=["Tickets"],
)
def list_tickets(
    urgency: Optional[UrgencyType] = Query(
        None,
        description="Filtro opcional por nível de urgência ('alta', 'media', 'baixa')",
        examples=["alta"],
    ),
) -> List[TicketResponse]:
    """Lista tickets cadastrados com filtro opcional por urgência."""
    with get_db_connection() as conn:
        tickets = ticket_repo.list_tickets(conn=conn, urgency=urgency)

    return [TicketResponse(**ticket) for ticket in tickets]


@app.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Métricas consolidadas de atendimento",
    description="Retorna o total de tickets, distribuição por categoria, urgência e volume de fallback.",
    tags=["Metrics"],
)
def get_metrics() -> MetricsResponse:
    """Retorna métricas agregadas e estatísticas em tempo real da operação."""
    with get_db_connection() as conn:
        metrics = ticket_repo.get_ticket_metrics(conn=conn)

    return MetricsResponse(**metrics)
