# Spec 03: Modelo de Dados — Currículos e Avaliações

**Status:** Implementada
**Depende de:** spec 01, spec 02

## 1. Contexto

O Argos recebe currículos em PDF, os processa em um pipeline assíncrono e depois
avalia cada currículo contra uma descrição de vaga (`docs/argos.md` §4). Nada
disso sobrevive a um restart hoje: `api/models/` contém apenas a `Base`
declarativa e a única migration existente habilita o `pgvector`. Não há tabela
de domínio alguma.

Esta spec define a fundação relacional desse fluxo: a tabela `curricula`, que
guarda o arquivo e o estágio da ingestão, e a tabela `evaluations`, que guarda o
resultado estruturado da avaliação — nota, pontos fortes, lacunas e
justificativa. A spec 01 §7 adiou o modelo de dados para este documento.

## 2. Requisitos Funcionais

- **RF-03-01** — A tabela `curricula` persiste o arquivo enviado (nome original e
  chave no bucket) e o estágio atual do pipeline de ingestão.
- **RF-03-02** — A tabela `evaluations` persiste uma avaliação de um currículo
  contra uma descrição de vaga, incluindo o resultado estruturado produzido pelo
  LLM.
- **RF-03-03** — Toda `evaluation` referencia exatamente um `curriculum`
  existente; o banco rejeita uma avaliação órfã.
- **RF-03-04** — Ambas as tabelas suportam remoção lógica: o registro é marcado
  como removido, não apagado.
- **RF-03-05** — Toda linha registra quando foi criada e quando foi alterada pela
  última vez, sem que a aplicação precise informar esses valores.

## 3. Contratos

### 3.1 DDL alvo

```sql
CREATE TYPE curriculum_status AS ENUM ('pending','parsing','embedding','ready','error');
CREATE TYPE evaluation_status AS ENUM ('pending','processing','done','error');

CREATE TABLE curricula (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename    VARCHAR(255) NOT NULL,
    bucket_key      VARCHAR(512) NOT NULL UNIQUE,
    status      curriculum_status NOT NULL DEFAULT 'pending',
    error_msg   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ
);
CREATE INDEX ix_curricula_status ON curricula (status);

CREATE TABLE evaluations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    curriculum_id   UUID NOT NULL REFERENCES curricula(id) ON DELETE RESTRICT,
    job_description TEXT NOT NULL,
    status          evaluation_status NOT NULL DEFAULT 'pending',
    score           DOUBLE PRECISION,
    strengths       JSONB,
    weaknesses      JSONB,
    justification   TEXT,
    model_version   VARCHAR(100) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,
    CONSTRAINT ck_evaluations_score_range CHECK (score >= 0 AND score <= 100)
);
CREATE INDEX ix_evaluations_curriculum_id ON evaluations (curriculum_id);
CREATE INDEX ix_evaluations_status ON evaluations (status);
```

### 3.2 Mapeamento coluna → tipo Python

Módulo `api/models/curriculum.py`, classe `Curriculum`, tabela `curricula`:

| Coluna | Tipo Python | Observação |
|---|---|---|
| `id` | `Mapped[uuid.UUID]` | PK; ver RT-03-05 |
| `filename` | `Mapped[str]` | nome original do arquivo enviado |
| `bucket_key` | `Mapped[str]` | chave do objeto no bucket; único (RN-03-09) |
| `status` | `Mapped[CurriculumStatus]` | ENUM nativo (RT-03-04) |
| `error_msg` | `Mapped[str \| None]` | preenchido só em `error` (RN-03-03) |
| `created_at` | `Mapped[datetime]` | `TIMESTAMPTZ`, default do banco |
| `updated_at` | `Mapped[datetime]` | `TIMESTAMPTZ`, default do banco + `onupdate` |
| `deleted_at` | `Mapped[datetime \| None]` | `NULL` = registro vivo (RN-03-08) |

Módulo `api/models/evaluation.py`, classe `Evaluation`, tabela `evaluations`:

| Coluna | Tipo Python | Observação |
|---|---|---|
| `id` | `Mapped[uuid.UUID]` | PK |
| `curriculum_id` | `Mapped[uuid.UUID]` | FK → `curricula.id`, `RESTRICT` |
| `job_description` | `Mapped[str]` | texto da vaga avaliada |
| `status` | `Mapped[EvaluationStatus]` | ENUM nativo |
| `score` | `Mapped[float \| None]` | `[0, 100]` (RN-03-06) |
| `strengths` | `Mapped[list[str] \| None]` | `JSONB` (RN-03-07) |
| `weaknesses` | `Mapped[list[str] \| None]` | `JSONB` (RN-03-07) |
| `justification` | `Mapped[str \| None]` | texto livre do LLM |
| `model_version` | `Mapped[str]` | obrigatório na criação (RN-03-05) |
| `created_at` | `Mapped[datetime]` | — |
| `updated_at` | `Mapped[datetime]` | — |
| `deleted_at` | `Mapped[datetime \| None]` | — |

### 3.3 Enumerações

Módulo `api/models/enums.py`. Ambas herdam de `StrEnum`; o banco armazena o
**valor**, não o nome do membro.

`StrEnum` (Python 3.11+) é escolhida sobre `(str, Enum)` porque as duas divergem
em `str(member)`: `(str, Enum)` devolve `"CurriculumStatus.PENDING"`, `StrEnum`
devolve `"pending"`. A primeira forma vaza o nome do membro em qualquer
interpolação — `f"status={status}"` num log, por exemplo — contrariando a regra
desta própria seção de que é o valor que trafega. `.value`, a serialização do
Pydantic e o `values_callable` do `sa.Enum` (RT-03-04) são idênticos nas duas
formas, de modo que o DDL e as linhas já gravadas não mudam.

```python
class CurriculumStatus(StrEnum):
    PENDING = "pending"
    PARSING = "parsing"
    EMBEDDING = "embedding"
    READY = "ready"
    ERROR = "error"


class EvaluationStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"
```

### 3.4 Relacionamento

`Curriculum.evaluations` ↔ `Evaluation.curriculum`, one-to-many, carregamento
**lazy explícito** (`lazy="raise"`): em contexto assíncrono, o lazy loading
implícito levanta `MissingGreenlet` em runtime. Quem precisar da coleção carrega
com `selectinload()`.

## 4. Regras de Negócio

- **RN-03-01** — `curriculum_status` admite exatamente `pending`, `parsing`,
  `embedding`, `ready` e `error`. Um currículo nasce em `pending`.
- **RN-03-02** — `evaluation_status` admite exatamente `pending`, `processing`,
  `done` e `error`. Uma avaliação nasce em `pending`.
- **RN-03-03** — `error_msg` é preenchido somente quando `status = 'error'`. Nos
  demais estados é `NULL`. Transição para um estado de sucesso limpa o campo.
- **RN-03-04** — `score`, `strengths`, `weaknesses` e `justification` permanecem
  `NULL` enquanto `status ≠ 'done'`. São gravados em uma única transação, junto
  com a mudança para `done`.
- **RN-03-05** — `model_version` é obrigatório desde a criação da avaliação: o
  serviço resolve qual modelo será usado **antes** de enfileirar o trabalho. Isso
  torna a avaliação reprodutível mesmo se ela nunca chegar a `done`.
- **RN-03-06** — `score` é um número real no intervalo fechado `[0, 100]`
  (`docs/argos.md` §4.2), garantido por `CheckConstraint` no banco. `NULL` é
  aceito — a checagem só se aplica a valores presentes.
- **RN-03-07** — `strengths` e `weaknesses` são listas de strings serializadas em
  `JSONB`. Lista vazia (`[]`) significa "avaliado, nada encontrado"; `NULL`
  significa "ainda não avaliado". Os dois casos não são intercambiáveis.
- **RN-03-08** — Remoção é lógica: `deleted_at IS NULL` identifica o registro
  vivo. Toda leitura de domínio filtra por essa condição. Um `DELETE` físico de
  um currículo que possua avaliações é bloqueado pelo banco (`ON DELETE
  RESTRICT`) — o histórico de avaliação não pode ser perdido por remoção em
  cascata.
- **RN-03-09** — `bucket_key` é único: dois currículos nunca apontam para o mesmo
  objeto do bucket. A unicidade vale inclusive para registros com `deleted_at`
  preenchido — reenviar um arquivo removido logicamente exige uma nova chave.
- **RN-03-10** — Um mesmo currículo pode ter várias avaliações, inclusive contra
  a mesma vaga. Não há restrição de unicidade sobre
  `(curriculum_id, job_description)`: reavaliar é uma operação legítima, e o
  histórico é preservado.

## 5. Requisitos Técnicos

- **RT-03-01** — Modelos escritos em SQLAlchemy 2.0 (`Mapped[]`,
  `mapped_column()`), herdando de `api/models/base.py::Base` (RT-01-05).
- **RT-03-02** — Toda coluna de tempo é `TIMESTAMP WITH TIME ZONE`
  (`DateTime(timezone=True)`). Timestamps ingênuos são proibidos: o Argos é
  consumido por sistemas internos que não compartilham fuso garantido.
- **RT-03-03** — `created_at` e `updated_at` têm `server_default=func.now()`;
  `updated_at` tem também `onupdate=func.now()`. O default é do **banco**, não da
  aplicação, para valer também em inserts feitos fora do ORM (migrations, scripts
  de manutenção).
- **RT-03-04** — Os `status` usam tipos ENUM **nativos** do PostgreSQL, nomeados
  `curriculum_status` e `evaluation_status`, com `values_callable` para que o
  banco guarde o valor do membro. A migration cria e remove os tipos
  explicitamente: o autogenerate do Alembic não emite `DROP TYPE` no
  `downgrade`, e sem isso o ciclo `downgrade` → `upgrade` falha com
  `type already exists`.
- **RT-03-05** — A PK é `UUID` com `server_default=text("gen_random_uuid()")`
  (nativo no PostgreSQL 16, sem extensão) e `default=uuid.uuid4` no lado Python,
  para que o ORM conheça o id antes do flush.
- **RT-03-06** — Todo modelo é importado em `api/models/__init__.py`. Sem isso
  `Base.metadata` fica vazio no momento em que `migrations/env.py` o lê, e o
  `alembic revision --autogenerate` produz uma migration vazia em silêncio
  (RT-01-09).
- **RT-03-07** — O schema é criado e alterado exclusivamente por migration do
  Alembic (RT-01-04). A migration desta spec é `0002`, com
  `down_revision = "0001_enable_pgvector"`.
- **RT-03-08** — As colunas de tempo repetidas nas duas tabelas vivem em mixins
  (`TimestampMixin`, `SoftDeleteMixin`) em `api/models/mixins.py`, não são
  duplicadas por classe.
- **RT-03-09** — Nomes de constraint são explícitos e estáveis
  (`ck_evaluations_score_range`, `uq_curricula_bucket_key`,
  `fk_evaluations_curriculum_id_curricula`). Constraints com nome gerado pelo
  banco são impossíveis de alterar em migrations futuras de forma portável.

## 6. Critérios de Aceite

Executados dentro do container `api`, conforme spec 01 §3.5.

- **CA-03-01** — `alembic upgrade head` roda sem erro em banco vazio e
  `alembic current` reporta a revisão `0002`.
- **CA-03-02** — Após `upgrade head`, um `alembic downgrade 0001_enable_pgvector`
  seguido de novo `alembic upgrade head` roda sem erro — prova que os `DROP TYPE`
  do downgrade existem (RT-03-04).
- **CA-03-03** — `psql -c '\d curricula'` e `psql -c '\d evaluations'` exibem
  exatamente as colunas, tipos, defaults e índices declarados na §3.1.
- **CA-03-04** — A consulta abaixo retorna os 5 valores de `curriculum_status` e
  os 4 de `evaluation_status`, na ordem declarada:
  ```sql
  SELECT t.typname, e.enumlabel
  FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid
  WHERE t.typname IN ('curriculum_status','evaluation_status')
  ORDER BY t.typname, e.enumsortorder;
  ```
- **CA-03-05** — Com o banco em `head`, `alembic revision --autogenerate` produz
  uma migration com `upgrade()` e `downgrade()` vazios — prova que os modelos e o
  schema não divergem (RT-03-06). O arquivo gerado é descartado.
- **CA-03-06** — Teste automatizado: `INSERT` em `curricula` com
  `status = 'invalid'` levanta erro do banco (`DataError` /
  `InvalidTextRepresentation`).
- **CA-03-07** — Teste automatizado: `DELETE` físico de um `curriculum` que possui
  `evaluation` levanta `IntegrityError` (RN-03-08).
- **CA-03-08** — Teste automatizado: gravar `strengths=["a","b"]` e reler devolve
  `["a", "b"]` como `list[str]`; `created_at` e `updated_at` vêm preenchidos sem
  terem sido informados, e `updated_at` avança após um `UPDATE` (RF-03-05).
- **CA-03-09** — Teste automatizado: `INSERT` em `evaluations` com `score = 101`
  levanta `IntegrityError` pela constraint `ck_evaluations_score_range`
  (RN-03-06).
- **CA-03-10** — Teste automatizado: `INSERT` de dois `curricula` com o mesmo
  `bucket_key` levanta `IntegrityError` (RN-03-09).
- **CA-03-11** — Teste automatizado: dois `evaluations` do mesmo
  `curriculum_id` com o mesmo `job_description` são gravados sem erro
  (RN-03-10).
- **CA-03-12** — `ruff check .` e `pytest` terminam sem falhas, mantendo
  CA-01-07 e CA-01-08 verdes.

## 7. Fora de Escopo

| Assunto | Destino |
|---|---|
| Tabela de chunks/embeddings, dimensão do vetor, índice HNSW/IVFFlat | revisão v2.0 **desta** spec |
| Parser de PDF, chunking, provedor de embeddings | spec `04-ingestion_pdf` |
| Contratos de endpoint de currículos e avaliações; schemas Pydantic | spec `05-api_contracts` |
| Motor de pesos dinâmicos e cálculo do `score` | spec `06-scoring_weights` |
| Exceções de domínio para "currículo não encontrado" etc. | spec `08-errors_observability` |
| Funções de repositório, queries de leitura e paginação | não especificado |
| Política de retenção e expurgo de dados (LGPD) | não especificado |

O nome do arquivo (`03-data_model_embeddings`) foi fixado pela spec 01 §7 antes
do recorte de escopo. As tabelas de embeddings pertencem a esta spec e entram na
revisão v2.0; o número não é reciclado (template §2.1).

## 8. Pendências

Nenhuma.

A pendência anterior — a metade de `ruff` de CA-03-12 — foi fechada pela criação
do `ruff.toml` na raiz (spec 01 §8), que declara o conjunto de regras e o desacopla
da versão instalada. CA-03-12 foi reexecutado por inteiro no container em
2026-08-24: `pytest` em `14 passed` e `ruff check .` em `All checks passed!`.

Os `CA-03-01` … `CA-03-11` foram executados e aprovados em 2026-08-04, dentro do
container `api`. Os testes que verificam `CA-03-06` … `CA-03-11` mudaram de caminho para
`tests/integration/test_models.py` com a implementação da spec 07 e foram reexecutados
em 2026-08-24 — `6 passed` —, agora contra o banco de teste dedicado.

## 9. Histórico de Revisões

| Data | Versão | Alteração |
|---|---|---|
| 2026-08-24 | 1.4 | Escrituração após a revisão 1.3 e a criação do `ruff.toml` na raiz (spec 01 §8). Pendência 1 fechada: CA-03-12 reexecutado por inteiro no container — `pytest` em `14 passed`, `ruff check .` em `All checks passed!`. As enumerações em `StrEnum` não alteraram o DDL nem os dados: `CA-03-06` … `CA-03-11` passam sem migration nova. §8 zerada. Nenhuma seção normativa alterada. |
| 2026-08-24 | 1.3 | §3.3 revisada a pedido do usuário: as enumerações passam de `(str, Enum)` para `StrEnum`. Motivo: `(str, Enum)` devolve `"CurriculumStatus.PENDING"` em `str(member)`, vazando o nome do membro em interpolações e contrariando a regra da própria §3.3. `.value`, o `values_callable` de RT-03-04 e a serialização do Pydantic não mudam — DDL e dados gravados ficam intactos. Nenhum `RN-` ou `CA-` alterado. |
| 2026-08-24 | 1.2 | Escrituração após a implementação da spec 07, sem alteração de seção normativa. Os testes de CA-03-06 … CA-03-11 mudaram de `tests/test_models.py` para `tests/integration/test_models.py` e passaram a rodar contra o banco dedicado; o `TEST_BUCKET_PREFIX` deixou de existir (spec 07 RN-07-06) e os construtores saíram de `tests/conftest.py` para `tests/factories.py`. Reexecutados e aprovados. Nova pendência 1: a metade de `ruff` de CA-03-12 falha por causa externa a esta spec. |
| 2026-08-04 | 1.1 | Implementação. Criados `api/models/enums.py`, `mixins.py`, `curriculum.py`, `evaluation.py`, o `__init__.py` do pacote e a migration `0002_create_curricula_and_evaluations.py`; testes em `tests/test_models.py`, sobre uma fixture de sessão assíncrona nova em `tests/conftest.py`. Todos os `CA-03-*` executados e aprovados; §8 zerada e Status para `Implementada`. Dois fatos descobertos na execução: (a) o id da revisão é `0002_curricula_evaluations`, mais curto que o nome do arquivo, porque `alembic_version.version_num` é `VARCHAR(32)` e o nome completo tem 38 caracteres; (b) CA-03-06 foi verificado pelo ramo `InvalidTextRepresentation` do critério — SQLSTATE `22P02` — porque o asyncpg não traduz esse erro para `DataError`. |
| 2026-07-22 | 1.0 | Criação. Escopo restrito a `curricula` e `evaluations` por decisão do usuário; embeddings adiados para a v2.0. Decisões firmadas: ENUM nativo do PostgreSQL, `model_version` NOT NULL desde a criação, `deleted_at` nas duas tabelas e FK `ON DELETE RESTRICT`. |
  