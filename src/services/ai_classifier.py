"""AI Classifier service integrating Google Gemini with deterministic local fallback.

Este módulo implementa a inteligência de triagem do sistema.
Utiliza o Google Gemini (SDK google-genai) para classificação semântica estruturada
e possui fallback local determinístico por regras semânticas, garantindo resiliência total.
"""

import json
import logging
import os
import re
from typing import Optional
from google import genai
from google.genai import types

from src.schemas import CategoryType, TriageResult, UrgencyType

logger = logging.getLogger(__name__)

# Instrução de sistema detalhada com as regras de negócio de triagem
TRIAGE_SYSTEM_INSTRUCTION = """
Você é um especialista em triagem inteligente de mensagens de suporte e atendimento ao cliente.
Sua missão é classificar a mensagem do cliente com precisão de acordo com as seguintes regras de negócio:

1. Categorias permitidas:
   - "financeiro": questões sobre faturamento, boletos, cartão de crédito, cobrança duplicada, reembolso, estorno ou pagamento.
   - "suporte_tecnico": erros de sistema, bugs, problemas de login, site/app fora do ar, falhas de integração ou lentidão.
   - "cancelamento": intenção explícita ou implícita de cancelamento de assinatura, encerramento de conta, descontinuação de serviço ou churn.
   - "duvida_geral": dúvidas sobre funcionamento do produto, horário de atendimento, preços públicos ou elogios.

2. Níveis de urgência:
   - "alta": pedidos de cancelamento, ameaças de processo/reclamação pública (ex: Reclame Aqui/Procon), cobrança indevida ou sistema indisponível/fora do ar.
   - "media": problemas que atrapalham o uso mas não impedem totalmente, dúvidas de fatura sem cobrança errada.
   - "baixa": dúvidas gerais, pedidos de informação ou sugestões simples.

3. Sugestão de ação ("suggested_action"):
   - Forneça uma frase curta, direta e imperativa orientando o atendente humano sobre o próximo passo prático.
"""

# Schema JSON estrito passado para a API do Gemini gerar respostas válidas
GEMINI_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "category": {
            "type": "STRING",
            "enum": ["financeiro", "suporte_tecnico", "cancelamento", "duvida_geral"],
        },
        "urgency": {
            "type": "STRING",
            "enum": ["alta", "media", "baixa"],
        },
        "suggested_action": {
            "type": "STRING",
        },
    },
    "required": ["category", "urgency", "suggested_action"],
}


def _classify_with_local_fallback(content: str) -> TriageResult:
    """Classificador heurístico local determinístico baseado em padrões semânticos.

    Acionado quando a GEMINI_API_KEY não estiver configurada ou a API remota falhar,
    garantindo disponibilidade 100% (High Availability / Graceful Degradation).
    """
    normalized = content.lower()

    # 1. Cancelamento: Prioridade máxima de retenção de clientes
    cancel_patterns = [
        r"\bcancel",
        r"\bdesistir\b",
        r"\bencerrar (conta|plano|assinatura)\b",
        r"\breincid",
        r"\bdevolu",
        r"\bnao quero mais\b",
        r"\bnão quero mais\b",
        r"\bestorno\b",
    ]
    for pattern in cancel_patterns:
        if re.search(pattern, normalized):
            return TriageResult(
                category="cancelamento",
                urgency="alta",
                suggested_action="Acionar time de retenção imediatamente para contato com o cliente.",
                used_fallback=True,
            )

    # 2. Financeiro: Faturas, boletos e cobranças
    financial_patterns = [
        r"\b(boleto|fatura|cartao|cartão|pagamento|cobranca|cobrança|pix|segunda via|2a via|valor cobrado)\b"
    ]
    for pattern in financial_patterns:
        if re.search(pattern, normalized):
            urgency: UrgencyType = (
                "alta"
                if any(w in normalized for w in ["duplicad", "errad", "indevid", "procon"])
                else "media"
            )
            return TriageResult(
                category="financeiro",
                urgency=urgency,
                suggested_action="Verificar extrato financeiro no gateway de pagamentos e orientar cliente.",
                used_fallback=True,
            )

    # 3. Suporte Técnico: Erros de sistema, indisponibilidade e bugs
    tech_patterns = [
        r"\b(erro|bug|falha|travou|quebrou|nao funciona|não funciona|fora do ar|offline|login|senha|acesso|500|404|lentid)\b"
    ]
    for pattern in tech_patterns:
        if re.search(pattern, normalized):
            urgency: UrgencyType = (
                "alta"
                if any(w in normalized for w in ["fora do ar", "offline", "urgente", "bloquead"])
                else "media"
            )
            return TriageResult(
                category="suporte_tecnico",
                urgency=urgency,
                suggested_action="Coletar logs de erro e direcionar para o time de engenharia/suporte N2.",
                used_fallback=True,
            )

    # 4. Dúvida Geral: Fallback padrão para dúvidas informativas
    return TriageResult(
        category="duvida_geral",
        urgency="baixa",
        suggested_action="Consultar base de conhecimento (FAQ) e responder dúvida do cliente.",
        used_fallback=True,
    )


def classify_message(
    content: str,
    api_key: Optional[str] = None,
) -> TriageResult:
    """Classifica a mensagem utilizando Google Gemini ou fallback determinístico.

    Args:
        content: Mensagem em texto enviada pelo cliente.
        api_key: Chave opcional da API Gemini. Se None, lê de GEMINI_API_KEY no ambiente.

    Returns:
        TriageResult: Modelo validado com category, urgency, suggested_action e used_fallback.
    """
    resolved_key = api_key or os.getenv("GEMINI_API_KEY")

    # Se a chave não existir ou for o placeholder do .env.example, aciona o fallback local
    if not resolved_key or resolved_key == "your_gemini_api_key_here":
        logger.info("Chave Gemini não configurada. Utilizando fallback determinístico local.")
        return _classify_with_local_fallback(content)

    try:
        # Inicializa o cliente do SDK oficial google-genai
        client = genai.Client(api_key=resolved_key)

        prompt = f"Analise a seguinte mensagem de cliente e faça a triagem:\n\nMensagem: \"{content}\""

        # Solicita ao modelo estruturação JSON garantida via response_schema do SDK
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=TRIAGE_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=GEMINI_RESPONSE_SCHEMA,
                temperature=0.1,  # Temperatura baixa para garantir determinismo e reprodutibilidade
            ),
        )

        response_text = response.text
        if not response_text:
            raise ValueError("Resposta vazia retornada pelo modelo Gemini.")

        parsed_data = json.loads(response_text)
        return TriageResult(
            category=parsed_data["category"],
            urgency=parsed_data["urgency"],
            suggested_action=parsed_data["suggested_action"],
            used_fallback=False,
        )

    except Exception as exc:
        # Degradação graciosa (Graceful Degradation): qualquer falha na API ou rede
        # ativa imediatamente o fallback local, garantindo SLA 100% para o cliente
        logger.warning(
            f"Falha na comunicação com a API do Gemini ({exc}). Acionando fallback determinístico local."
        )
        return _classify_with_local_fallback(content)
