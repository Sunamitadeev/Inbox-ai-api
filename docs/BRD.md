# Business Requirements Document (BRD)
## Projeto: `inbox-ai-api` — Triagem Inteligente de Mensagens de Atendimento

---

### 1. Visão Geral & Dor de Negócio

#### O Problema
Operações de atendimento e suporte ao cliente enfrentam filas desorganizadas com alto volume de mensagens não estruturadas que chegam via canais como chat, e-mail e formulários web. Mensagens críticas (ex: pedidos de cancelamento com risco iminente de churn, ou falhas financeiras de cobrança duplicada) competem na mesma fila por ordem estrita de chegada (FIFO) com dúvidas simples e repetitivas.

Isso gera:
- **Perda de clientes (churn):** clientes insatisfeitos pedindo cancelamento demoram horas para receber primeiro contato de retenção.
- **Sobrecarga de atendentes:** equipes seniores gastam tempo lendo mensagens irrelevantes ou simples em vez de focar em suporte técnico crítico.
- **Falta de visibilidade métrica:** gestores não têm visão em tempo real do volume de demandas por categoria e severidade de urgência.

#### A Solução
O `inbox-ai-api` é um microsserviço REST leve e resiliente que atua como middleware de triagem automática:
1. Recebe a mensagem do cliente via API.
2. Analisa e categoriza a mensagem de forma semântica com Large Language Model (Google Gemini).
3. Determina o nível de urgência (`alta`, `media`, `baixa`) e sugere uma ação recomendada para o operador humano.
4. Possui garantia de **alta disponibilidade por fallback local determinístico**: se a API do LLM estiver indisponível ou sem chave configurada, um motor determinístico baseado em padrões semânticos assume imediatamente a classificação sem derrubar o fluxo operacional.
5. Persiste o histórico em banco de dados e expõe métricas consolidadas em tempo real.

---

### 2. Personas Envolvidas

- **Operador de Atendimento (N1/N2):** necessita que as mensagens mais urgentes e com risco apareçam no topo de sua fila já com uma orientação de ação sugerida.
- **Gestor de Suporte / CX Lead:** necessita acompanhar métricas agregadas (total de tickets, distribuição por categorias e urgências) para alocação eficiente da equipe.
- **Sistemas de Terceiros (CRM/Helpdesk/Frontends):** sistemas emissores que consomem a API enviando mensagens brutas e recebendo respostas estruturadas de triagem.

---

### 3. Requisitos Funcionais (RF)

| ID | Requisito | Descrição |
|:---|:---|:---|
| **RF-01** | Triagem de Mensagem | O sistema deve receber um payload JSON contendo a mensagem de texto (`content`) e retornar categoria, urgência, ação recomendada e flag indicando se houve fallback. |
| **RF-02** | Taxonomia de Categorias | As categorias de classificação devem ser restritas a: `financeiro`, `suporte_tecnico`, `cancelamento` e `duvida_geral`. |
| **RF-03** | Níveis de Urgência | Os níveis de urgência devem ser restritos a: `alta`, `media` e `baixa`. Pedidos de cancelamento devem ser classificados com urgência `alta`. |
| **RF-04** | Fallback Determinístico Local | Caso a chamada ao Google Gemini falhe (timeout, rate limit, rede) ou `GEMINI_API_KEY` não esteja presente, o sistema deve acionar o classificador heurístico local garantindo SLA 100% sem retornar erro 500 para o cliente. |
| **RF-05** | Persistência de Tickets | Cada mensagem triada deve ser armazenada com: ID gerado, conteúdo original, categoria, urgência, ação recomendada, indicador de fallback e timestamp ISO 8601. |
| **RF-06** | Consulta de Tickets com Filtro | O sistema deve disponibilizar endpoint para listar os tickets armazenados, suportando filtro opcional pelo parâmetro `urgency`. |
| **RF-07** | Agregação de Métricas | O sistema deve disponibilizar endpoint consolidando métricas: total de tickets, contagem por categoria, contagem por urgência e total de tickets classificados via fallback. |

---

### 4. Requisitos Não Funcionais (RNF)

| ID | Requisito | Meta / Padrão |
|:---|:---|:---|
| **RNF-01** | Validação Estrita de Entrada | Utilizar Pydantic v2 para validação de dados em runtime; textos vazios ou contendo apenas espaços devem ser rejeitados com HTTP 422. |
| **RNF-02** | Segurança & SQL Injection | Acesso a dados via SQLite com SQL puro estritamente parametrizado (`?`); queries concatenadas são proibidas. |
| **RNF-03** | Resiliência e Graceful Degradation | Degradação graciosa da IA para fallback local em caso de qualquer exceção externa, mantendo resposta rápida. |
| **RNF-04** | Arquitetura Limpa e Modular | Separação de responsabilidades em camadas simples (`main`, `schemas`, `services`, `repositories`, `database`), facilitando testes unitários isolados. |
| **RNF-05** | Testabilidade | Cobertura de testes automatizados com Pytest e FastAPI `TestClient`, garantindo isolamento total por meio de banco temporário em memória ou arquivo descartável. |
| **RNF-06** | Gerenciamento Seguro de Configuração | Zero credenciais no código; uso exclusivo de variáveis de ambiente (`.env` via `python-dotenv`). |
