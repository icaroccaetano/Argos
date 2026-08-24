# Spec 01: Estrutura do Projeto e Setup Inicial

**Status:** Implementada
**Depende de:** Nenhuma

## 1. Contexto

Este documento define a fundação estrutural do Argos: stack tecnológica, topologia
de diretórios e as regras de separação de responsabilidades. Todas as demais specs
pressupõem esta.

O objetivo é garantir que o desenvolvimento — humano ou gerado por IA — parta de um
esqueleto previsível, onde cada tipo de código tem um endereço único e óbvio.

## 2. Requisitos Funcionais

- **RF-01-01** — A aplicação expõe um endpoint `GET /health` que responde `200` com
  `{"status": "ok"}`, sem depender de banco de dados ou serviços externos.
- **RF-01-02** — A aplicação sobe integralmente via `docker compose up`, provisionando
  os serviços `api`, `db` e `redis`.
- **RF-01-03** — O schema do banco é criado e evoluído exclusivamente por
  `alembic upgrade head`.
- **RF-01-04** — Toda configuração é lida de variáveis de ambiente através de um único
  objeto `Settings` tipado, exposto em `api/core/config.py`.

## 3. Contratos

### 3.1 Stack tecnológica

| Camada | Tecnologia | Restrição |
|---|---|---|
| Linguagem | Python 3.12 | imagem base `python:3.12-slim` |
| Framework HTTP | FastAPI | — |
| Banco relacional | PostgreSQL 16 **com extensão `pgvector`** | imagem `pgvector/pgvector:pg16` |
| Cache / broker | Redis 7 | provisionado; uso definido em spec futura |
| ORM | SQLAlchemy 2.x | obrigatório o estilo 2.0 (`select()`, `Mapped[]`, `mapped_column()`) |
| Driver — aplicação | `asyncpg` | acesso assíncrono em runtime |
| Driver — migrations | `psycopg2-binary` | Alembic roda de forma síncrona |
| Migrations | Alembic | — |
| Validação | Pydantic v2 | — |
| Configuração | `pydantic-settings` | única fonte de env vars |
| Containerização | Docker + Docker Compose | — |
| Testes | `pytest` + `pytest-asyncio` | — |
| Lint / format | `ruff` | Regras declaradas em `ruff.toml` na raiz |

O uso de `pgvector` é decisão firmada nesta spec: o armazenamento e a busca de
embeddings acontecem no próprio PostgreSQL, sem banco vetorial dedicado. O schema
das colunas vetoriais é definido na spec `03-data_model_embeddings`.

**Estratégia de dois drivers.** A aplicação acessa o banco de forma assíncrona
(`postgresql+asyncpg://`), enquanto o Alembic executa migrations de forma síncrona
(`postgresql+psycopg2://`). O objeto `Settings` é responsável por expor as duas URLs;
nenhum outro módulo faz conversão de string de conexão.

### 3.2 Topologia de diretórios

```
ARGOS/
├── airflow/                # DAGs e orquestração de dados.
├── api/                    # Aplicação FastAPI (backend principal).
│   ├── core/               # Infraestrutura transversal.
│   │   ├── config.py       # Settings(BaseSettings) — única fonte de env vars.
│   │   └── database.py     # engine, async_session_factory, get_db().
│   ├── routers/            # Controladores HTTP (curricula.py, evaluations.py).
│   ├── schemas/            # Modelos Pydantic de request/response.
│   ├── models/             # Modelos ORM (SQLAlchemy 2.x).
│   ├── services/           # Lógica de negócio isolada (core da aplicação).
│   └── main.py             # Entrypoint FastAPI.
├── docs/
│   ├── argos.md            # Visão de domínio do produto.
│   └── specs/              # Especificações (SDD).
├── migrations/             # Migrações geradas e gerenciadas pelo Alembic.
├── tests/                  # Testes. Topologia interna definida na spec 07.
├── workers/                # Processamento em background.
├── .env                    # Variáveis de ambiente locais (não versionado).
├── .env.example            # Template seguro de variáveis de ambiente.
├── .gitignore              # `.env` e artefatos fora do versionamento.
├── alembic.ini             # Configuração raiz do Alembic.
├── docker-compose.yml      # Serviços: api, db (pgvector), redis.
├── Dockerfile              # Imagem da aplicação FastAPI.
├── requirements.txt        # Dependências Python.
├── ruff.toml               # Regras de lint — `select` explícito.
├── Makefile                # Automação (dev, test, lint, migrate).
└── CLAUDE.md               # Instruções de sistema do agente.
```

### 3.3 Versionamento da API

Rotas de negócio são montadas sob o prefixo `/v1`. Endpoints operacionais ficam
fora do versionamento.

```
GET  /health           # operacional, sem versão
POST /v1/curricula
POST /v1/evaluations
```

```python
app.include_router(curricula.router, prefix="/v1/curricula", tags=["curricula"])
app.include_router(evaluations.router, prefix="/v1/evaluations", tags=["evaluations"])
```

### 3.4 Variáveis de ambiente

`.env.example` é o contrato: toda variável lida por `Settings` aparece nele, com
valor vazio ou exemplo não sensível.

| Variável | Autoritativa | Observação |
|---|---|---|
| `APP_ENV` | sim | — |
| `SECRET_KEY` | sim | nunca versionada |
| `POSTGRES_USER` | sim | consumida também pela imagem do Postgres |
| `POSTGRES_PASSWORD` | sim | idem |
| `POSTGRES_DB` | sim | idem |
| `POSTGRES_HOST` | sim | `db` no Compose |
| `POSTGRES_PORT` | sim | opcional; default `5432` |
| `POSTGRES_TEST_DB` | sim | opcional; default `argos_test`. Banco dedicado da suíte de integração; adicionada pela spec 07 §3.4 |
| `REDIS_URL` | sim | — |

**Sem duplicação de URL.** As URLs de conexão **não** são variáveis de ambiente: são
derivadas pelo `Settings` a partir das variáveis `POSTGRES_*`, que são a única fonte
autoritativa. Manter um `DATABASE_URL` literal ao lado de `POSTGRES_USER/PASSWORD/DB`
cria duas verdades que divergem silenciosamente.

```python
settings.database_url_async   # postgresql+asyncpg://...
settings.database_url_sync    # postgresql+psycopg2://...
```

A implementação do `Settings` e a estratégia por ambiente pertencem à spec `02-config_settings`.

### 3.5 Contexto de execução dos critérios

Salvo indicação em contrário, todo comando dos Critérios de Aceite roda **dentro do
container `api`**:

```bash
docker compose exec api <comando>
```

Isso é normativo, não conveniência: `POSTGRES_HOST=db` só resolve dentro da rede do
Compose, então os mesmos comandos dão resultados diferentes no host. Habilitar a
execução no host exige um override de ambiente, definido na spec `02-config_settings`.

## 4. Regras de Negócio

N/A — esta spec trata exclusivamente de estrutura. Regras de domínio vivem nas
specs de funcionalidade (`04` em diante).

## 5. Requisitos Técnicos

- **RT-01-01 — Configuração.** É proibido `os.getenv`, `os.environ`, `python-decouple`
  ou `load_dotenv()`. Todo acesso a ambiente passa pelo `Settings` de `api/core/config.py`.
  **Escopo:** aplica-se a `api/`, `workers/`, `airflow/` **e `migrations/`** — inclusive
  `migrations/env.py`, que deve importar `settings` em vez de ler o ambiente por conta
  própria. Não há exceções de ferramental.
- **RT-01-02 — Camada de roteamento.** `api/routers/` não contém lógica de negócio.
  A responsabilidade do router é receber a requisição já validada, chamar um serviço
  e devolver a resposta HTTP com o status apropriado.
- **RT-01-03 — Camada de serviços.** `api/services/` concentra 100% da lógica de
  negócio. Funções de serviço desconhecem o contexto HTTP: não recebem `Request`,
  `Response` nem levantam `HTTPException`.
- **RT-01-04 — Camada de dados.** Alterações de schema acontecem exclusivamente via
  migrations do Alembic. `Base.metadata.create_all()` é proibido em código de
  aplicação e de produção.
- **RT-01-05 — SQLAlchemy 2.0.** Uso obrigatório da sintaxe moderna: `Mapped[]`,
  `mapped_column()`, `select()`. A Query API legada (`session.query()`) é proibida.
- **RT-01-06 — Tipagem.** Toda função tem type hints completos, incluindo o retorno.
- **RT-01-07 — Sessão de banco.** O acesso ao banco é injetado via dependência
  `get_db()` de `api/core/database.py`. Serviços recebem a sessão como parâmetro;
  não a criam nem a importam globalmente.
- **RT-01-08 — Versões de dependência.** Toda entrada do `requirements.txt` declara
  um range de compatibilidade com limite superior de major (ex:
  `sqlalchemy[asyncio]>=2.0,<3.0`). Dependência sem limite superior é proibida: sem
  ele, um `pip install` futuro pode violar RT-01-05 sem nenhum sinal.
- **RT-01-09 — Autogenerate do Alembic.** `migrations/env.py` define
  `target_metadata = Base.metadata`. Com `target_metadata = None`, o
  `alembic revision --autogenerate` produz migrations vazias em silêncio.
- **RT-01-10 — Extensão pgvector.** A primeira migration executa
  `CREATE EXTENSION IF NOT EXISTS vector;`. A imagem `pgvector/pgvector` fornece o
  binário, mas a extensão precisa ser habilitada por banco — provisionar a imagem
  não basta.

## 6. Critérios de Aceite

Executados conforme §3.5.

- **CA-01-01** — `docker compose up -d` sobe os três serviços e `docker compose ps`
  reporta `api`, `db` e `redis` como `healthy` ou `running`.
- **CA-01-02** — `curl -s localhost:8000/health` retorna `200` e o corpo
  `{"status":"ok"}`. Coberto por teste automatizado.
- **CA-01-03** — `alembic upgrade head` executa sem erro em banco vazio, e
  `alembic current` reporta a revisão de topo.
- **CA-01-04** — `SELECT extversion FROM pg_extension WHERE extname = 'vector';`
  retorna uma linha **após** `alembic upgrade head` em banco vazio.
- **CA-01-05** — `python -c "from api.core.config import settings; print(settings.APP_ENV)"`
  imprime o valor sem erro de validação.
- **CA-01-06** — Executado **na raiz do repositório**, cobrindo todo o código versionado:
  ```bash
  grep -rn --include='*.py' --exclude-dir=.venv \
    "os\.getenv\|os\.environ\|load_dotenv\|create_all()\|session\.query(" .
  ```
  não retorna resultados. `.venv/` é a única exclusão: é dependência de terceiros
  instalada localmente, não versionada, e RT-01-01 vale para o código do projeto.
- **CA-01-07** — `ruff check .` termina sem erros.
- **CA-01-08** — `pytest` executa a suíte sem falhas, **dentro do container** — o que
  exige que `tests/` não esteja excluído do `.dockerignore`.
- **CA-01-09** — `make dev`, `make test`, `make lint` e `make migrate` executam os
  comandos correspondentes.
- **CA-01-10** — Toda variável referenciada em `api/core/config.py` está presente em
  `.env.example`.
- **CA-01-11** — `grep -cE '>=.+,<' requirements.txt` retorna um número igual ao total
  de linhas de dependência do arquivo (RT-01-08).

## 7. Fora de Escopo

Decisões deliberadamente adiadas para specs futuras:

| Assunto | Spec destino |
|---|---|
| Implementação do `Settings`, derivação das URLs, override para execução no host | `02-config_settings` |
| Modelo de dados, dimensão dos vetores, índice `pgvector` | `03-data_model_embeddings` |
| Provedor de LLM e de embeddings; parser de PDF; chunking | `04-ingestion_pdf` |
| Contratos de endpoint de currículos e avaliações | `05-api_contracts` |
| Motor de pesos dinâmicos e cálculo de score | `06-scoring_weights` |
| Tratamento de erros, exceções de domínio, logging | `08-errors_observability` |
| Escolha da tecnologia de workers e uso concreto do Redis | `10-workers` |
| Autenticação e autorização | não especificado |
| Lock de dependências transitivas (`pip-compile`) | não especificado |
| Hot-reload e volume mount para desenvolvimento | não especificado |

## 8. Pendências

Nenhuma. Todos os `CA-01-*` foram executados e passam.

A pendência de lint — CA-01-07 acusando 33 erros no container — foi fechada pela
criação do `ruff.toml` na raiz. O arquivo declara o `select` explicitamente, o que
desacopla o conjunto de regras da versão de `ruff` que cada ambiente resolve sob o
range de RT-01-08 — a causa real da falha, e não o `EXE002` em si. Fixar a versão
foi descartado por violar RT-01-08 e CA-01-11. O fechamento exigiu 8 edições de
código: 7 `W292` (newline final ausente) e um `# noqa: S105` sobre
`FORBIDDEN_PRODUCTION_SECRET`, que é sentinela e não segredo. Um achado
remanescente, `UP042`, contradizia o contrato da §3.3 da spec 03 e foi resolvido
pela revisão daquela spec (v1.3), não por configuração de lint. CA-01-07 foi
reexecutado no container em 2026-08-24 — `All checks passed!` —, com host
(`ruff` 0.15.22) e container (0.16.4) convergindo no mesmo resultado.

A pendência anterior — `POSTGRES_TEST_DB` ausente de `api/core/config.py` e de
`.env.example` — foi fechada pela implementação da spec 07. CA-01-10 foi reexecutado em
2026-08-24 e passa, agora sem vacuidade: as nove variáveis do `Settings`, incluindo
`POSTGRES_TEST_DB`, constam do `.env.example`. Ele roda **no host**, não no container:
`.env.example` está no `.dockerignore` e não existe na imagem.

CA-01-06 e CA-01-08 foram reexecutados na mesma data e passam. Os demais `CA-01-*` foram
executados e aprovados em 2026-07-22.

Os routers `curricula` e `evaluations` são stubs sem rotas, e `/openapi.json` expõe
apenas `/health`. Isso **não** é pendência: §3.3 exige que rotas de negócio sejam
montadas sob `/v1` — e estão (`api/main.py`) — não que existam. Os contratos de
endpoint são escopo da spec `05-api_contracts` por §7.

## 9. Histórico de Revisões

| Data | Versão | Alteração |
|---|---|---|
| 2026-08-24 | 2.13 | Emenda à §2 solicitada pelo usuário: a tabela de stack passa a registrar que as regras de `ruff` são declaradas em `ruff.toml` na raiz. Fecha a pendência 1; §8 zerada. Status permanece `Implementada`. |
| 2026-08-24 | 2.12 | Emenda à §3.2 solicitada pelo usuário: `ruff.toml` incorporado à árvore de diretórios, entre `requirements.txt` e `Makefile`. Registra na topologia o arquivo criado na v2.11. Pendência 1 reduzida à §2, que segue registrando `ruff` sem menção ao arquivo de configuração. |
| 2026-08-24 | 2.11 | Escrituração. Pendência 1 fechada: `ruff.toml` criado na raiz, declarando `target-version`, `select`, `extend-immutable-calls` para o `Depends()` do FastAPI e `per-file-ignores` para `tests/**`. CA-01-07 reexecutado no container — `All checks passed!` — e CA-01-08 em `14 passed`. Nova pendência 1: §2 e §3.2 não citam o `ruff.toml` e são normativas. Nenhuma seção normativa alterada. |
| 2026-08-24 | 2.10 | Escrituração após a implementação da spec 07. Pendência 1 fechada: `POSTGRES_TEST_DB` existe em `api/core/config.py` e em `.env.example`, com CA-01-10 reexecutado. Nova pendência 1: CA-01-07 falha por causa externa a esta spec — regras que entraram no conjunto padrão do `ruff` 0.16.4. Nenhuma seção normativa alterada. |
| 2026-08-04 | 2.9 | Emenda solicitada pelo usuário em consequência da spec 07: §3.2 delega a topologia interna de `tests/` à spec 07; §3.4 recebe `POSTGRES_TEST_DB`. Status permanece `Implementada` — todos os `CA-01-*` seguem passando —, com a divergência registrada na §8. |
| 2026-07-22 | 2.8 | Pendência 3 removida: não era divergência com o repositório. §3.3 exige o prefixo `/v1` montado, não a existência de rotas; os contratos de endpoint são escopo da spec `05` por §7. Suíte completa de `CA-01-*` reexecutada e aprovada; Status passa a `Implementada`. |
| 2026-07-22 | 2.7 | CA-01-06 alterado a pedido do usuário: `--exclude-dir=.venv`, com a justificativa da exclusão anexada ao critério. Reexecutado e aprovado. |
| 2026-07-22 | 2.6 | Pendência 2 fechada: GNU Make 4.4.1 instalado no host (`winget install ezwinports.make`) e CA-01-09 executado — `make dev`, `make test`, `make lint` e `make migrate` rodam os comandos correspondentes. |
| 2026-07-22 | 2.5 | Fechadas as pendências 1, 5, 6, 9 e 10 pela implementação da spec 02: `api/core/config.py` e `api/core/database.py` criados, `migrations/env.py` reescrito sobre o `settings` com `target_metadata = Base.metadata`, `DATABASE_URL` removido e `python-dotenv` retirado do `requirements.txt`. CA-01-02, CA-01-04, CA-01-05, CA-01-06, CA-01-07, CA-01-08, CA-01-10 e CA-01-11 verificados. |
| 2026-07-22 | 2.4 | Emenda à §3.4 solicitada pelo usuário: `POSTGRES_PORT` incorporado ao conjunto autoritativo de variáveis, com default `5432`. Elimina a divergência com a spec 02 §3.1 (pendência 1 daquela spec). |
| 2026-07-21 | 1.0 | Criação. |
| 2026-07-21 | 2.0 | Adequação ao template `00`. Registrada a decisão por `pgvector`; adicionada camada `api/core/`; definido versionamento `/v1`; adicionados requisitos numerados, critérios de aceite executáveis, fora de escopo e pendências. |
| 2026-07-22 | 2.3 | Fechadas as pendências 12, 13 e 14. Adicionado `httpx2>=2.7,<3.0` (aprovado pelo usuário): `starlette` 1.3.1 exige esse pacote — não `httpx` — para o `TestClient`. `Dockerfile` cria o `appuser` antes do `COPY`, com home, e dá posse de `/app` ao usuário. CA-01-02, CA-01-07, CA-01-08 e CA-01-11 verificados. |
| 2026-07-22 | 2.2 | Implementação parcial (bloco sem dependência do `Settings`). Fechadas as pendências 4, 7, 8 e 11 — `Base` declarativa, migration `0001_enable_pgvector`, ranges de versão no `requirements.txt` e `tests/` de volta na imagem; CA-01-03, CA-01-04 e CA-01-11 verificados. Prefixo `/v1` montado em `api/main.py`; `Makefile` criado; `POSTGRES_HOST` adicionado ao `.env`/`.env.example`. Novas pendências 13 (`httpx2` ausente) e 14 (permissão de escrita em `/app` no container) descobertas na execução dos critérios. |
| 2026-07-21 | 2.1 | Auditoria contra o código existente. Corrigido CA-01-06 (escopo era só `api/` e não cobria `os.environ`/`load_dotenv` — falso negativo). Definido o contexto de execução dos critérios (§3.5). RT-01-01 passa a valer explicitamente para `migrations/`. Registradas decisões que existiam só no código: Python 3.12, estratégia de dois drivers. Novos RT-01-08 (ranges de versão), RT-01-09 (`target_metadata`), RT-01-10 (extensão `vector` via migration). §3.4 elimina a duplicação `DATABASE_URL` × `POSTGRES_*`. Pendências: 6 → 12. |
