# Spec 07: Topologia e Estratégia de Testes

**Status:** Implementada
**Depende de:** spec 01, spec 02

## 1. Contexto

A suíte cresceu para 14 testes em quatro arquivos planos sob `tests/`, com custos de
execução radicalmente diferentes e nenhuma marca que os distinga: `test_config.py`
roda em memória, enquanto `test_models.py` exige um PostgreSQL migrado e commita de
verdade. Quem roda `pytest` no host sem o Compose de pé vê seis falhas de conexão que
não são falhas de lógica — e não tem como pedir "só o que roda sem infraestrutura".

O ganho é rodar sem *infraestrutura*, não sem configuração: a camada unitária continua
exigindo um `.env` na raiz, porque `tests/unit/test_config.py` importa a instância de
módulo `settings`, construída no import (RT-02-01). Um clone recém-feito, que só tem
`.env.example`, falha na coleta — pré-condição de ambiente, não de infraestrutura.

Esta spec define o eixo de separação, onde cada teste vive, o que cada camada pode
depender e — como consequência direta disso — o banco dedicado sobre o qual a camada
de integração opera, hoje inexistente: a suíte escreve no banco de desenvolvimento e
se protege apenas por um prefixo convencionado no `bucket_key`. Ela detalha a linha `tests/` da spec 01 §3.2, que enumera o diretório sem
expandir seu interior; nenhuma seção normativa da spec 01 é alterada. O número `07`
foi usado porque `04`, `05`, `06`, `08` e `10` estão reservados por nome na spec 01 §7.

## 2. Requisitos Funcionais

- **RF-07-01** — A suíte é organizada em duas camadas, `tests/unit/` e
  `tests/integration/`. Todo arquivo `test_*.py` pertence a exatamente uma delas;
  nenhum permanece na raiz de `tests/`.
- **RF-07-02** — `pytest tests/unit` executa com sucesso sem nenhuma infraestrutura
  externa no ar: sem Docker, sem PostgreSQL, sem Redis, sem rede.
- **RF-07-03** — `pytest` sem argumentos continua descobrindo e executando as duas
  camadas, preservando CA-01-08, CA-02-14 e CA-03-12 sem alteração no enunciado.
- **RF-07-04** — Construtores de dados de teste compartilhados vivem em
  `tests/factories.py`, importável por qualquer camada.
- **RF-07-05** — O `Makefile` expõe um alvo `test-unit` que executa apenas a camada
  unitária, ao lado do `test` existente, que continua executando a suíte inteira.
- **RF-07-06** — A camada `tests/integration/` opera sobre um banco de dados dedicado,
  distinto do banco da aplicação. Nenhum teste escreve no banco de desenvolvimento.
- **RF-07-07** — O banco de teste é criado e migrado automaticamente pela própria
  suíte quando ausente. Rodar `pytest` em uma instância PostgreSQL onde ele não existe
  não exige nenhum passo manual prévio.

## 3. Contratos

### 3.1 Topologia de `tests/`

```
tests/
├── __init__.py
├── factories.py            # Construtores de entidades. Sem asserções, sem fixtures.
├── unit/
│   ├── __init__.py
│   └── test_config.py      # CA-02-04 … CA-02-07
└── integration/
    ├── __init__.py
    ├── conftest.py         # Fixture `session`: banco real, com teardown.
    ├── test_health.py      # CA-01-02
    ├── test_database.py    # CA-02-10
    └── test_models.py      # CA-03-06 … CA-03-11
```

Não existe `tests/conftest.py`. Um conftest na raiz vale para as duas camadas, e é
o caminho pelo qual uma dependência de banco vaza para `unit/` sem ninguém notar.

### 3.2 Interface de `tests/factories.py`

```python
def make_curriculum(**overrides: object) -> Curriculum: ...
def make_evaluation(curriculum_id: uuid.UUID, **overrides: object) -> Evaluation: ...
```

Funções puras: constroem a instância e devolvem. Não recebem sessão, não persistem,
não commitam. Quem persiste é o teste.

### 3.3 Comandos por camada

Conforme spec 01 §3.5, o padrão é dentro do container:

```bash
docker compose exec api pytest                  # suíte completa
docker compose exec api pytest tests/unit       # só unitários
```

A camada unitária é a única que roda no host **sem** o override de ambiente da
spec 02 §3.4, porque não abre conexão — `POSTGRES_HOST` é irrelevante para ela:

```bash
pytest tests/unit                               # host, Compose parado
POSTGRES_HOST=localhost pytest                  # host, Compose no ar (spec 02 §3.4)
```

Ambos pressupõem o `.env` na raiz e as dependências instaladas no host (§1). O que a
camada unitária dispensa é o Compose, não a configuração.

### 3.4 Banco de teste

A camada de integração usa um banco dedicado **na mesma instância PostgreSQL** do
banco da aplicação. Não há segundo serviço no Compose: o custo de um contêiner extra
não se paga, e o isolamento pretendido é entre *bases*, não entre instâncias.

| Variável | Tipo | Obrigatória | Default |
|---|---|---|---|
| `POSTGRES_TEST_DB` | `str` | não | `argos_test` |

Estende a tabela da spec 01 §3.4 e a da spec 02 §3.1. Tem default porque um nome de
banco de teste não é decisão de operação; exigi-lo no `.env` seria ruído.

```python
# api/core/config.py — estende o contrato da spec 02 §3.3

class Settings(BaseSettings):
    POSTGRES_TEST_DB: str = "argos_test"

    @property
    def database_url_test_async(self) -> str: ...   # postgresql+asyncpg://...
    @property
    def database_url_test_sync(self) -> str: ...    # postgresql+psycopg2://...
```

As duas URLs derivam das mesmas `POSTGRES_*` das URLs da aplicação, trocando apenas o
nome do banco, e são construídas por `URL.create()` (RN-02-01).

**Ciclo de vida.** Uma fixture **síncrona** de escopo de sessão em
`tests/integration/conftest.py`, executada uma vez por invocação do `pytest`:

1. Verifica o destino e aborta se `POSTGRES_TEST_DB` for igual a `POSTGRES_DB`
   (RN-07-07). É o primeiro passo porque os dois seguintes já são destrutivos.
2. Conecta ao banco de manutenção `postgres` e emite `CREATE DATABASE` se
   `POSTGRES_TEST_DB` não constar de `pg_database` (RT-07-06).
3. Aplica `alembic upgrade head` sobre `database_url_test_sync` (RT-07-07).

Síncrona por decisão, não por preferência: RT-07-02 proíbe arquivo de configuração, e
uma fixture assíncrona de escopo de sessão exigiria `loop_scope="session"` do
`pytest-asyncio` — que só se declara em config. A fixture `session`, essa sim
assíncrona, permanece de escopo de função.

O banco **não** é destruído ao final: recriar e remigrar a cada execução custa segundos
por invocação, e um banco de teste persistente é inspecionável depois de uma falha.
A limpeza entre testes é responsabilidade do teardown por teste (RN-07-06).

## 4. Regras de Negócio

- **RN-07-01 — Critério de `unit/`.** Um teste pertence a `tests/unit/` se, e somente
  se, exercita um único componente sem instanciar aplicação ASGI, sem abrir conexão
  de rede ou de banco, e sem depender de processo externo. É a definição estrita:
  cruzar uma fronteira de camada já descaracteriza o teste unitário, mesmo que a
  execução seja rápida e local.
- **RN-07-02 — Critério de `integration/`.** Todo teste que não satisfaz RN-07-01
  pertence a `tests/integration/`. Isso inclui testes que sobem `TestClient` sem
  tocar o banco: eles atravessam roteamento, injeção de dependência e serialização.
- **RN-07-03 — Desempate.** Na dúvida sobre a camada, o teste vai para
  `integration/`. Os erros não são simétricos: classificar um teste de integração
  como unitário quebra RF-07-02 para todo mundo; o inverso apenas o faz rodar menos
  vezes.
- **RN-07-04 — Pré-condição de `integration/`.** A camada de integração pressupõe uma
  instância PostgreSQL acessível, com um papel que possua `CREATEDB` — RF-07-07 depende
  disso, e no Compose só é verdade porque `POSTGRES_USER` é o superusuário criado pela
  imagem. O banco de teste em si não é pré-condição: a suíte o cria (RF-07-07). Falha
  por instância indisponível ou privilégio insuficiente é erro de ambiente, não de
  código.
- **RN-07-05 — Localização de fixtures.** Fixtures que abrem sessão, conexão ou
  qualquer recurso externo residem em `tests/integration/conftest.py`. Fixtures de
  `unit/`, se existirem, vivem no próprio arquivo de teste.
- **RN-07-06 — Limpeza entre testes.** O teardown de cada teste emite
  `TRUNCATE evaluations, curricula`. Truncar as duas tabelas no mesmo comando dispensa
  a ordenação imposta pelo `ON DELETE RESTRICT` (RN-03-08), que hoje obriga o teardown
  a apagar avaliações antes de currículos. Sem `RESTART IDENTITY`, que é no-op sobre PK
  `UUID` (RT-03-05), e sem `CASCADE`, redundante com as duas tabelas já nomeadas e
  perigoso no dia em que uma terceira tabela referenciar `curricula`.
  O `TEST_BUCKET_PREFIX` deixa de existir: ele era o mecanismo de isolamento dentro de
  um banco compartilhado, e o banco dedicado o torna redundante. `bucket_key` continua
  gerado com `uuid4()` para satisfazer a unicidade de RN-03-09 dentro de uma execução.
- **RN-07-07 — Guarda de destino.** A suíte de integração aborta se `POSTGRES_TEST_DB`
  for igual a `POSTGRES_DB`. A verificação é o **primeiro** passo da fixture de sessão
  (§3.4), antes do `CREATE DATABASE` e do `alembic upgrade`: não adianta proteger o
  `TRUNCATE` se a migration já rodou no banco errado. Adicionalmente, antes de cada
  `TRUNCATE`, `SELECT current_database()` deve devolver `POSTGRES_TEST_DB` e um valor
  diferente de `POSTGRES_DB`.
  Comparar o banco conectado apenas com `POSTGRES_TEST_DB` não protegeria nada: com a
  variável apontada para o banco da aplicação, a igualdade se verifica e o `TRUNCATE`
  roda. O que se defende é o banco da aplicação, então é contra ele que se compara.
  Uma fixture com poder de truncar tabelas é indistinguível de um acidente quando
  apontada para o banco errado, e configuração errada é justamente o que ninguém
  percebe a tempo.
- **RN-07-08 — Origem da conexão.** `tests/integration/conftest.py` constrói o próprio
  `AsyncEngine` a partir de `settings.database_url_test_async`. É proibido importar
  `engine` ou `async_session_factory` de `api.core.database` na suíte: os dois apontam
  para o banco da aplicação, e usá-los reintroduz exatamente o acoplamento que RF-07-06
  elimina. `get_db` está **fora** da proibição: `tests/integration/test_database.py` o
  importa porque CA-02-10 existe para testá-lo, e a sessão que ele entrega nunca emite
  query — não chega a abrir conexão.

## 5. Requisitos Técnicos

- **RT-07-01 — Pacotes Python.** `tests/`, `tests/unit/` e `tests/integration/`
  contêm `__init__.py`. Sem isso, `from tests.factories import ...` falha e dois
  módulos homônimos em camadas diferentes colidem no `sys.modules`.
- **RT-07-02 — Separação por diretório, não por marker.** A camada é determinada
  exclusivamente pelo caminho do arquivo. É proibido introduzir markers de camada
  (`@pytest.mark.unit`, `@pytest.mark.integration`) ou seleção por `-m`. Consequência
  deliberada: nenhum `pytest.ini`, `pyproject.toml` ou `setup.cfg` é adicionado, e a
  enumeração de arquivos da raiz na spec 01 §3.2 permanece exata.
- **RT-07-03 — Pureza de `factories.py`.** O módulo não contém `assert`, decorador de
  fixture, nem import de `pytest`. Um factory que valida vira um teste sem nome que
  falha em todos os outros.
- **RT-07-04 — Preservação de histórico.** Os arquivos são movidos com `git mv`. O
  conteúdo dos testes não é alterado, salvo duas edições: a linha de import de
  `tests.conftest` para `tests.factories`, e a remoção das referências ao
  `TEST_BUCKET_PREFIX`, extinto por RN-07-06. São duas ocorrências em `test_models.py`
  — a do import e o `bucket_key` literal de `test_ca_03_06`; sem a segunda, CA-07-16 é
  inalcançável.
- **RT-07-05 — Contagem estável.** A reorganização não cria, remove nem renomeia
  nenhum teste. A suíte tem 14 testes antes e depois.
- **RT-07-06 — Criação do banco fora de transação.** `CREATE DATABASE` não pode rodar
  dentro de um bloco transacional no PostgreSQL. A conexão de manutenção é síncrona
  (`create_engine` sobre `psycopg2`, conforme §3.4) e usa
  `isolation_level="AUTOCOMMIT"`.
- **RT-07-07 — Migração programática.** O schema do banco de teste é aplicado por
  `alembic.command.upgrade` sobre um `alembic.config.Config` construído com o caminho
  de `alembic.ini` — o `%(here)s` de `script_location` torna a chamada independente do
  cwd —, definindo `sqlalchemy.url = settings.database_url_test_sync` com `%` escapado
  como `%%` (o configparser interpola `%`). Isso pressupõe que `migrations/env.py`
  respeite uma URL já configurada em vez de sobrescrevê-la, o que é emenda a RF-02-06
  registrada na spec 02 v1.8; sem ela, este requisito migra o banco da aplicação em
  silêncio. `Base.metadata.create_all()` permanece proibido também em testes
  (RT-01-04): um schema criado por caminho diferente do de produção testa um banco que
  não existe.

## 6. Critérios de Aceite

Executados conforme spec 01 §3.5, salvo onde indicado.

- **CA-07-01** — `pytest --collect-only -q` reporta **14** testes, e todo path
  coletado começa com `tests/unit/` ou `tests/integration/`.
- **CA-07-02** — Executado **no host, com o Compose parado** (`docker compose down`):
  `pytest tests/unit` termina com `5 passed` e código de saída `0`.
- **CA-07-03** — `pytest` executa a suíte completa sem falhas, mantendo CA-01-08,
  CA-02-14 e CA-03-12.
- **CA-07-04** — Executado na raiz do repositório:
  ```bash
  ls tests/*.py
  ```
  retorna exatamente `tests/__init__.py` e `tests/factories.py`.
- **CA-07-05** — `grep -rn "tests\.conftest" tests/` não retorna resultados.
- **CA-07-06** — Executado na raiz do repositório, provando RT-07-02:
  ```bash
  ls pytest.ini pyproject.toml setup.cfg 2>/dev/null
  grep -rn "pytest.mark.unit\|pytest.mark.integration" tests/
  ```
  nenhum dos dois comandos retorna resultados.
- **CA-07-07** — `test -f tests/unit/__init__.py && test -f tests/integration/__init__.py`
  retorna código de saída `0` (RT-07-01).
- **CA-07-08** — `grep -n "assert\|import pytest\|fixture" tests/factories.py` não
  retorna resultados (RT-07-03).
- **CA-07-09** — `make test-unit` executa `pytest tests/unit` dentro do container.
- **CA-07-10** — `ruff check .` termina sem erros.
- **CA-07-11** — Banco de teste criado do zero (RF-07-07):
  ```bash
  docker compose exec db  psql -U "$POSTGRES_USER" -d postgres -c 'DROP DATABASE IF EXISTS argos_test;'
  docker compose exec api pytest tests/integration
  docker compose exec db  psql -U "$POSTGRES_USER" -lqt | cut -d'|' -f1 | grep -w argos_test
  ```
  o `pytest` termina com `9 passed`, e a terceira linha — que não retornava nada antes
  da suíte — passa a retornar uma linha. O `psql` roda no serviço `db`: a imagem do
  `api` é `python:3.12-slim`, sem `postgresql-client`.
- **CA-07-12** — Isolamento do banco da aplicação (RF-07-06). A contagem
  ```bash
  docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc 'SELECT count(*) FROM curricula;'
  ```
  medida antes e depois de `docker compose exec api pytest` devolve o mesmo valor.
- **CA-07-13** — `grep -rn "api\.core\.database" tests/` retorna **exatamente uma
  linha**: o `import get_db` de `tests/integration/test_database.py`, exigido por
  CA-02-10. Nenhuma ocorrência de `engine` nem de `async_session_factory` (RN-07-08).
- **CA-07-14** — Guarda de destino (RN-07-07). Executado com o banco de teste
  apontando para o da aplicação:
  ```bash
  docker compose exec -e POSTGRES_TEST_DB="$POSTGRES_DB" api pytest tests/integration
  ```
  encerra com erro que nomeia o banco recusado e código de saída diferente de `0`, sem
  ter emitido `CREATE DATABASE` nem `alembic upgrade`; a contagem de CA-07-12 no banco
  da aplicação permanece inalterada.
- **CA-07-15** — `grep -c POSTGRES_TEST_DB .env.example` retorna `1`, mantendo
  CA-01-10.
- **CA-07-16** — `grep -rn "TEST_BUCKET_PREFIX" tests/` não retorna resultados
  (RN-07-06).

## 7. Fora de Escopo

| Assunto | Destino |
|---|---|
| Markers de pytest e seleção por `-m` | rejeitado por RT-07-02 |
| Medição de cobertura (`pytest-cov`) | não especificado |
| Camada `e2e` ou testes contra LLM/S3 reais | `04-ingestion_pdf` em diante |
| Fixtures de mock de LLM e de embeddings | `04-ingestion_pdf` |
| Execução em CI e matriz de ambientes | não especificado |
| Segunda instância PostgreSQL no Compose para testes | rejeitado em §3.4 — o isolamento é entre bases, na mesma instância |
| Execução paralela da suíte (`pytest-xdist`) | não especificado; o teardown por `TRUNCATE` de RN-07-06 pressupõe execução serial |

## 8. Pendências

Divergências entre esta spec e o estado do repositório, reverificadas em 2026-08-24,
depois da implementação:

| # | Divergência |
|---|---|
| 1 | CA-07-10 falha: `ruff check .` acusa 33 erros no container, nenhum originado em código desta implementação. 31 são `EXE002` (arquivo executável sem shebang) e atingem todo `.py` do repositório — `api/main.py`, `airflow/` e `workers/` inclusive: o Git Bash do Windows grava modo `755` na árvore de trabalho e o `COPY . .` do `Dockerfile` leva o modo para a imagem, embora o índice do git registre `100644`. Os 2 restantes são `B008` sobre `Depends(get_db)` em `tests/integration/test_database.py`. Ambas as regras entraram no conjunto padrão do `ruff` 0.16.4, que a reconstrução da imagem instalou sob o range `ruff>=0.6,<1.0` do `requirements.txt`. Fechar exige decisão de dependência (fixar a versão) ou arquivo de configuração de lint na raiz — nenhuma das duas cabe em escrituração. Pela mesma causa caem CA-01-07, CA-02-14 e CA-03-12, e com eles a cláusula "mantendo CA-02-14" de CA-07-03 — cuja metade de `pytest` passa. |

As pendências 1 a 8 da revisão anterior foram fechadas pela implementação.

Executados e aprovados em 2026-08-24, dentro do container `api` salvo onde indicado:
CA-07-01 (14 testes coletados, todo path sob `tests/unit/` ou `tests/integration/`),
CA-07-02 (**no host**, com `docker compose down`: `5 passed`, saída `0`), CA-07-03
(`14 passed`), CA-07-04, CA-07-05, CA-07-06, CA-07-07, CA-07-08, CA-07-09, CA-07-11
(`argos_test` derrubado antes, recriado pela suíte e migrado até
`0002_curricula_evaluations`; `9 passed`), CA-07-12 (contagem em `argos` inalterada, e
uma linha sentinela inserida antes da suíte sobreviveu ao `TRUNCATE`), CA-07-13,
CA-07-14 (recusa nomeando `argos`, saída `1`, sem `CREATE DATABASE` nem
`alembic upgrade`) e CA-07-16.

CA-07-15 foi executado **no host**, e não no container como manda o preâmbulo da §6:
`.env.example` consta do `.dockerignore` e não existe na imagem, de modo que o critério,
como escrito, não é executável em `docker compose exec api`. Vale o mesmo para CA-01-10,
que lê o mesmo arquivo. O critério passa no host (`1`); a imprecisão está no contexto de
execução, não no repositório, e corrigi-la é decisão do usuário.

## 9. Histórico de Revisões

| Data | Versão | Alteração |
|---|---|---|
| 2026-08-24 | 1.3 | Implementação. `tests/` reorganizado em `unit/` e `integration/` com `git mv`; `tests/factories.py` criado; `tests/integration/conftest.py` reescrito com a preparação síncrona do banco dedicado (guarda de destino, `CREATE DATABASE` em AUTOCOMMIT, `alembic upgrade head` programático) e teardown por `TRUNCATE`; `POSTGRES_TEST_DB` e as URLs `database_url_test_*` em `api/core/config.py`; `POSTGRES_TEST_DB` em `.env.example`; alvo `test-unit` no `Makefile`; `migrations/env.py` passa a respeitar a URL já presente no `Config` (RF-02-06). Pendências 1 a 8 fechadas. 15 dos 16 `CA-07-*` verificados; CA-07-10 permanece aberto por causa externa à spec. Removida da §8 a afirmação de que a spec estava em `Rascunho`, que contradizia o campo Status. |
| 2026-08-17 | 1.2 | Auditoria da spec contra o repositório, a pedido do usuário, antes de implementar. Quatro contradições corrigidas: RT-07-07 supunha um `env.py` que respeitasse o `Config` (resolvido pela emenda a RF-02-06, spec 02 v1.8, escolhida pelo usuário entre duas saídas); RN-07-07 comparava o banco conectado com `POSTGRES_TEST_DB`, comparação tautológica que tornava CA-07-14 impossível de passar; CA-07-13 proibia todo `api.core.database` em `tests/` e alcançava o `import get_db` que CA-02-10 exige; RT-07-04 permitia uma única edição nos testes e inviabilizava CA-07-16, já que `TEST_BUCKET_PREFIX` aparece também no corpo de `test_ca_03_06`. Corrigidos ainda: CA-07-11, CA-07-12 e CA-07-14 invocavam `psql` no container `api`, que não o tem; RN-07-04 omitia o privilégio `CREATEDB`; §3.4 não dizia se a fixture de sessão é síncrona, o que colide com a proibição de arquivo de config (RT-07-02); RN-07-06 trazia `RESTART IDENTITY CASCADE` inócuo e arriscado. §1 recua no exemplo do clone recém-feito, que não roda sem `.env`. Nenhum `RF-07-*` alterado. |
| 2026-08-04 | 1.1 | Banco dedicado de teste trazido para o escopo por decisão do usuário: novos RF-07-06, RF-07-07, §3.4, RN-07-06 (reescrito — `TRUNCATE` substitui a limpeza por prefixo), RN-07-07, RN-07-08, RT-07-06, RT-07-07 e CA-07-11 … CA-07-16. Specs 01 e 02 emendadas em consequência. |
| 2026-08-04 | 1.0 | Criação. Eixo de separação definido como unit/integration em sentido estrito (RN-07-01), escolhido pelo usuário entre três taxonomias. Separação por diretório, com markers rejeitados em RT-07-02. |
