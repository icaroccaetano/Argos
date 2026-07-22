# Spec 02: Configuração, Settings e Sessão de Banco

**Status:** Implementada
**Depende de:** spec 01

## 1. Contexto

A spec `01-project_structure` estabeleceu que toda configuração vem de um único objeto
`Settings` tipado (RF-01-04) e que nenhum módulo lê o ambiente por conta própria
(RT-01-01) — mas delegou a esta spec a implementação, a derivação das URLs de conexão
e o override para execução fora do Compose. Enquanto isso não existe, sete pendências
da spec 01 permanecem abertas e `migrations/env.py` continua violando RT-01-01.

Esta spec fecha esse buraco. Ela cobre o módulo `api/core/config.py`, seu consumidor
imediato `api/core/database.py` (a sessão injetável exigida por RT-01-07) e a adequação
de `migrations/env.py`. O Argos manipula PII de candidatos e credenciais de banco: a
disciplina de configuração aqui é um requisito de segurança, não de estilo.

## 2. Requisitos Funcionais

- **RF-02-01** — `api/core/config.py` expõe a classe `Settings`, derivada de
  `BaseSettings` do `pydantic-settings`, e uma instância única de módulo chamada
  `settings`.
- **RF-02-02** — `Settings` lê as variáveis de ambiente do processo e, se presente, do
  arquivo `.env` na raiz do repositório. Variáveis do processo têm precedência sobre o
  arquivo.
- **RF-02-03** — `Settings` expõe `database_url_async` e `database_url_sync`, ambas
  derivadas das variáveis `POSTGRES_*`. Nenhuma das duas é lida do ambiente.
- **RF-02-04** — A ausência de uma variável obrigatória, ou um valor de tipo inválido,
  impede a inicialização da aplicação com um erro de validação que nomeia a variável
  faltante.
- **RF-02-05** — `api/core/database.py` expõe o `engine` assíncrono, a fábrica
  `async_session_factory` e a dependência `get_db()`, que entrega uma `AsyncSession` por
  requisição e a encerra ao final, inclusive quando a requisição levanta exceção.
- **RF-02-06** — `migrations/env.py` obtém sua URL de conexão de
  `settings.database_url_sync` e define `target_metadata = Base.metadata`.
- **RF-02-07** — Os comandos do projeto podem ser executados no host, fora da rede do
  Compose, sobrescrevendo `POSTGRES_HOST` no ambiente do processo — sem editar `.env`
  e sem nenhum arquivo de configuração adicional.

## 3. Contratos

### 3.1 Variáveis de ambiente

Estende a tabela da spec 01 §3.4. Toda variável aparece em `.env.example` (CA-01-10).

| Variável | Tipo | Obrigatória | Default |
|---|---|---|---|
| `APP_ENV` | `Environment` (enum) | sim | — |
| `SECRET_KEY` | `SecretStr` | sim | — |
| `POSTGRES_USER` | `str` | sim | — |
| `POSTGRES_PASSWORD` | `SecretStr` | sim | — |
| `POSTGRES_DB` | `str` | sim | — |
| `POSTGRES_HOST` | `str` | sim | — |
| `POSTGRES_PORT` | `int` | não | `5432` |
| `REDIS_URL` | `str` | sim | — |

`POSTGRES_PORT` é a única adição desta spec ao conjunto autoritativo da spec 01 §3.4.
Ela existe para eliminar o `5432` literal da derivação das URLs; tem default porque a
porta padrão do Postgres é estável e exigi-la no `.env` seria ruído. A tabela §3.4 da
spec 01 foi emendada para incluí-la (spec 01 v2.4); as duas specs estão alinhadas.

`DATABASE_URL` **não é variável de ambiente** e deve ser removida de `.env` e
`.env.example` (spec 01 §3.4, pendência 10).

### 3.2 Enum de ambiente

```python
class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"
```

### 3.3 Assinaturas

```python
# api/core/config.py

class Settings(BaseSettings):
    model_config: SettingsConfigDict

    APP_ENV: Environment
    SECRET_KEY: SecretStr
    POSTGRES_USER: str
    POSTGRES_PASSWORD: SecretStr
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    REDIS_URL: str

    @property
    def database_url_async(self) -> str: ...   # postgresql+asyncpg://...

    @property
    def database_url_sync(self) -> str: ...    # postgresql+psycopg2://...


settings: Settings = Settings()
```

```python
# api/core/database.py

engine: AsyncEngine
async_session_factory: async_sessionmaker[AsyncSession]

async def get_db() -> AsyncGenerator[AsyncSession, None]: ...
```

### 3.4 Execução no host

O contrato da spec 01 §3.5 (comandos rodam dentro do container) permanece o padrão.
Para rodar no host, sobrescreva o host do banco no ambiente do processo:

```bash
POSTGRES_HOST=localhost pytest
POSTGRES_HOST=localhost alembic upgrade head
```

Isso funciona por RF-02-02: a variável do processo vence a do `.env`. Não há
`.env.local`, `.env.test` nem perfil por ambiente — um único `.env` e overrides
pontuais na chamada.

## 4. Regras de Negócio

- **RN-02-01** — As URLs são construídas com `sqlalchemy.URL.create()`, nunca por
  concatenação ou f-string. Senha com `@`, `:`, `/` ou `#` quebra silenciosamente uma
  URL montada à mão, e a falha aparece como erro de autenticação, não de sintaxe.
- **RN-02-02** — `SECRET_KEY` e `POSTGRES_PASSWORD` são `SecretStr`. O `repr` de
  `Settings` e qualquer log que o inclua exibem `**********` em vez do valor.
- **RN-02-03** — Quando `APP_ENV` é `production`, `SECRET_KEY` não pode ser vazia nem
  igual a `changeme`. A violação é um erro de validação na inicialização.
- **RN-02-04** — Um valor de `APP_ENV` fora do enum é erro de validação. Não há
  fallback silencioso para `development`: um ambiente digitado errado que roda como
  desenvolvimento é pior do que um que não sobe.
- **RN-02-05** — Variáveis presentes no ambiente e desconhecidas por `Settings` são
  ignoradas (`extra="ignore"`). O ambiente do container carrega variáveis alheias à
  aplicação (`PATH`, `LANG`, injeções do orquestrador), e falhar por causa delas
  tornaria a aplicação impossível de subir.

## 5. Requisitos Técnicos

- **RT-02-01** — `Settings` é instanciado uma única vez, no import de
  `api/core/config.py`. Nenhum outro módulo instancia `Settings()`; todos importam
  `settings`.
- **RT-02-02** — `api/core/config.py` não importa nada de `api/` além de tipos. É a
  base da árvore de dependências: nenhum ciclo pode alcançá-lo.
- **RT-02-03** — `get_db()` é um gerador assíncrono com `async with`. Não faz `commit()`
  implícito: a transação é responsabilidade do serviço.
- **RT-02-04** — `python-dotenv` é removido do `requirements.txt`. O carregamento do
  `.env` passa a ser feito exclusivamente pelo `pydantic-settings` (fecha a pendência 9
  da spec 01).
- **RT-02-05** — O `engine` é criado no import do módulo, com `pool_pre_ping=True`.
  Conexões ociosas derrubadas pelo Postgres devem falhar no `ping`, não na query do
  usuário.
- **RT-02-06** — Nenhum default é definido para variáveis obrigatórias. Um default de
  conveniência (`POSTGRES_HOST = "localhost"`) transforma erro de configuração em
  conexão ao banco errado.

## 6. Critérios de Aceite

Executados conforme spec 01 §3.5, dentro do container `api`, salvo indicação contrária.

- **CA-02-01** — `python -c "from api.core.config import settings; print(settings.APP_ENV)"`
  imprime `development` sem erro (equivale a CA-01-05). A saída é o valor, não o
  nome do membro, porque `Environment` é um `StrEnum` (§3.2).
- **CA-02-02** — `python -c "from api.core.config import settings; print(settings.database_url_async)"`
  imprime uma URL iniciada por `postgresql+asyncpg://` e terminada pelo valor de
  `POSTGRES_DB`.
- **CA-02-03** — O mesmo para `database_url_sync`, iniciada por `postgresql+psycopg2://`.
- **CA-02-04** — Teste automatizado: com `POSTGRES_PASSWORD="p@ss:w/rd#1"`, o host
  derivado da URL é `POSTGRES_HOST` — e não um fragmento da senha (RN-02-01).
- **CA-02-05** — Teste automatizado: instanciar `Settings` sem `POSTGRES_DB` levanta
  `ValidationError` cuja mensagem contém `POSTGRES_DB` (RF-02-04).
- **CA-02-06** — Teste automatizado: `APP_ENV=staging` levanta `ValidationError`
  (RN-02-04); e `APP_ENV=production` com `SECRET_KEY=changeme` levanta `ValidationError`
  (RN-02-03).
- **CA-02-07** — Teste automatizado: `repr(settings)` não contém o valor de
  `SECRET_KEY` nem o de `POSTGRES_PASSWORD` (RN-02-02).
- **CA-02-08** — Com `DATABASE_URL` ausente de `.env`, `alembic upgrade head` executa
  sem erro em banco vazio e `alembic current` reporta a revisão de topo (RF-02-06).
- **CA-02-09** — `alembic revision --autogenerate -m "probe"` sobre um banco já
  migrado gera uma revisão com `upgrade()` vazio — prova de que `target_metadata` está
  ligado (RT-01-09). O arquivo gerado é descartado.
- **CA-02-10** — Teste automatizado: uma rota de teste que depende de `get_db()`
  recebe uma instância de `AsyncSession`, e a sessão está fechada após a resposta
  (RF-02-05).
- **CA-02-11** — Executado **no host**, com o Compose no ar:
  `POSTGRES_HOST=localhost python -c "from api.core.config import settings; print(settings.database_url_sync)"`
  imprime a URL com `localhost`, sem alteração de nenhum arquivo (RF-02-07).
- **CA-02-12** — Na raiz do repositório: `grep -rn "python-dotenv" requirements.txt` e
  `grep -rn --include='*.py' --exclude-dir=.venv "dotenv" .` não retornam resultados
  (RT-02-04). A exclusão do `.venv/` segue CA-01-06: `python-dotenv` permanece instalado
  como dependência transitiva do `pydantic-settings`, o que RT-02-04 não proíbe — o que
  ele exige é que o projeto não o declare nem o importe.
- **CA-02-13** — O comando de CA-01-06 continua sem resultados, agora incluindo
  `migrations/env.py`.
- **CA-02-14** — `pytest` e `ruff check .` passam.

## 7. Fora de Escopo

| Assunto | Spec destino |
|---|---|
| Modelos ORM concretos e migrations de tabela | `03-data_model_embeddings` |
| Cliente Redis e uso concreto do cache/broker | `10-workers` |
| Chaves de API de provedores de LLM e embeddings | `04-ingestion_pdf` |
| Tratamento e formato de erro das exceções de configuração | `08-errors_observability` |
| Gestão de segredos em produção (vault, secret manager) | não especificado |
| Perfis de configuração por ambiente (`.env.production` etc.) | deliberadamente rejeitado — ver §3.4 |
| Pool de conexões (tamanho, overflow, timeout) | não especificado; usa-se o default do SQLAlchemy |

## 8. Pendências

Nenhuma. Todos os `CA-02-*` foram executados e aprovados em 2026-07-22.

## 9. Histórico de Revisões

| Data | Versão | Alteração |
|---|---|---|
| 2026-07-22 | 1.6 | CA-02-12 alterado a pedido do usuário: exclui `.venv/` da varredura, alinhado a CA-01-06 (spec 01 v2.7). Pendência 5 fechada. Com a §8 vazia e todos os `CA-02-*` aprovados, o Status passa a `Implementada`. |
| 2026-07-22 | 1.5 | Pendência 4 fechada: virtualenv criado em `./.venv` com as dependências do projeto e CA-02-11 executado no host — `POSTGRES_HOST=localhost` produz a URL com `localhost`, sem alteração de arquivo. Nova pendência 5: o `.venv` no repositório quebra os critérios de `grep` da raiz. |
| 2026-07-22 | 1.4 | CA-02-01 corrigido a pedido do usuário: passa a esperar `development`, a saída real de um `StrEnum` (§3.2 inalterada). Critério reexecutado e aprovado; pendência 3 fechada. |
| 2026-07-22 | 1.3 | Implementação. `api/core/config.py` e `api/core/database.py` criados; `migrations/env.py` adequado a RT-01-01 e RT-01-09; `DATABASE_URL` removido de `.env`/`.env.example` e `POSTGRES_PORT` adicionado; `python-dotenv` removido do `requirements.txt`. Pendência 2 fechada. Verificados CA-02-02 a CA-02-10 e CA-02-12 a CA-02-14. Novas pendências 3 (CA-02-01 contradiz §3.2) e 4 (CA-02-11 não executável neste host). |
| 2026-07-22 | 1.2 | Pendência 1 fechada: a §3.4 da spec 01 foi emendada para incluir `POSTGRES_PORT` (spec 01 v2.4). §3.1 atualizada a pedido do usuário — não afirma mais que as specs divergem. |
| 2026-07-22 | 1.1 | Correção da §8: a pendência 2 afirmava que a spec estava em `Rascunho`, contradizendo o campo Status (`Aprovada`). A pendência passa a registrar apenas o que de fato falta — a implementação. |
| 2026-07-22 | 1.0 | Criação. Contrato do `Settings`, derivação das duas URLs via `URL.create()`, enum `Environment`, estratégia de override no host por variável de processo, sessão `get_db()` e adequação de `migrations/env.py`. |
