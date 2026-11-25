"""Pydantic v2 data models and schemas for request validation and response serialization.

Este módulo centraliza todos os contratos de dados (DTOs) da aplicação,
garantindo validação estrita em tempo de execução e serialização segura.
"""

from typing import Dict, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Tipos Literais: garantem em tempo de compilação/execução que apenas os
# valores previstos no documento de requisitos (BRD) sejam aceitos.
# ---------------------------------------------------------------------------
CategoryType = Literal["financeiro", "suporte_tecnico", "cancelamento", "duvida_geral"]
UrgencyType = Literal["alta", "media", "baixa"]


class MessageInput(BaseModel):
    """Schema de entrada para a mensagem enviada pelo cliente.
    
    Aplica validações para impedir payloads vazios ou abusivos.
    """

    content: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Conteúdo em texto da mensagem de atendimento enviada pelo cliente.",
        examples=["Quero cancelar minha assinatura agora mesmo!"],
    )

    @field_validator("content")
    @classmethod
    def validate_content_not_empty_or_whitespace(cls, value: str) -> str:
        """Regra de negócio: impede strings compostas apenas por espaços em branco.
        
        Caso o cliente envie '   ', strip() resultará em vazio e disparará
        ValueError, fazendo o FastAPI retornar HTTP 422 Unprocessable Entity.
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("O conteúdo da mensagem não pode ser vazio ou conter apenas espaços.")
        return stripped


class TriageResult(BaseModel):
    """Resultado da classificação gerado pelo LLM ou pelo fallback heurístico.
    
    Este schema é passado tanto para a API do Gemini gerar o JSON estruturado
    quanto como contrato de saída do serviço de triagem.
    """

    category: CategoryType = Field(
        ...,
        description="Categoria de negócio identificada para o chamado.",
        examples=["cancelamento"],
    )
    urgency: UrgencyType = Field(
        ...,
        description="Nível de urgência da solicitação ('alta', 'media', 'baixa').",
        examples=["alta"],
    )
    suggested_action: str = Field(
        ...,
        min_length=3,
        description="Próxima ação recomendada para orientar o atendente de suporte.",
        examples=["Acionar time de retenção imediatamente para contato telefônico."],
    )
    used_fallback: bool = Field(
        default=False,
        description="Flag booleana indicando se o resultado veio do fallback local determinístico.",
    )


class TicketResponse(BaseModel):
    """Schema de resposta representando um ticket já persistido no banco de dados.
    
    Habilita 'from_attributes=True' para permitir conversão direta a partir
    de dicionários ou objetos mapeados pelo SQLite/ORM.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Identificador único numérico do ticket.")
    content: str = Field(..., description="Mensagem original enviada pelo cliente.")
    category: CategoryType = Field(..., description="Categoria classificada.")
    urgency: UrgencyType = Field(..., description="Nível de urgência classificado.")
    suggested_action: str = Field(..., description="Ação recomendada para o operador.")
    used_fallback: bool = Field(..., description="Indica se a triagem usou fallback heurístico.")
    created_at: str = Field(..., description="Data e hora de criação do ticket no banco.")


class MetricsResponse(BaseModel):
    """Schema para o endpoint de métricas e observabilidade em tempo real.
    
    Consolida o volume total de atendimentos e distribuições estatísticas.
    """

    total_tickets: int = Field(..., description="Total acumulado de tickets registrados.")
    by_category: Dict[str, int] = Field(
        default_factory=dict,
        description="Distribuição quantitativa de tickets agrupados por categoria.",
    )
    by_urgency: Dict[str, int] = Field(
        default_factory=dict,
        description="Distribuição quantitativa de tickets agrupados por nível de urgência.",
    )
    fallback_count: int = Field(
        ...,
        description="Quantidade total de tickets que precisaram do fallback determinístico.",
    )
