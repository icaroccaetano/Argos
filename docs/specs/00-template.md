# Spec 00: Template e Contrato de Especificação

> Esta é uma meta-spec: ela define **como escrever specs** no Argos, não uma
> funcionalidade. Toda spec de `docs/specs/` deve seguir a estrutura da Seção 3.

## 1. Contexto

O Argos adota **Spec-Driven Development (SDD)**: a especificação é a única fonte
da verdade e o código é consequência do que está documentado. Isso só funciona se
as specs forem **verificáveis** — uma spec que não pode ser provada como cumprida
é documentação, não especificação.

Este documento padroniza o formato para que specs escritas em momentos diferentes,
por pessoas ou agentes diferentes, permaneçam comparáveis e rastreáveis.

## 2. Convenções

### 2.1 Nomenclatura de arquivos

`NN-nome_em_snake_case.md`, com `NN` sequencial e sem reuso (ex: `03-data_model_embeddings.md`).
Números não são reciclados: se uma spec for descontinuada, seu número permanece
queimado e o arquivo ganha o status `Descontinuada`.

### 2.2 Identificadores rastreáveis

Todo requisito recebe um ID único e estável no formato `<TIPO>-<NN>-<seq>`:

| Prefixo | Significado | Exemplo |
|---|---|---|
| `RF` | Requisito Funcional — o que o sistema faz | `RF-04-01` |
| `RN` | Regra de Negócio — restrição ou cálculo do domínio | `RN-06-02` |
| `RT` | Requisito Técnico — imposição de arquitetura ou stack | `RT-01-03` |
| `CA` | Critério de Aceite — prova verificável | `CA-01-02` |

IDs **nunca são renumerados**. Se um requisito deixa de valer, marque-o como
`~~RF-04-03~~ (removido na v1.2)` em vez de apagá-lo — outros documentos, commits
e testes podem referenciá-lo.

### 2.3 Idioma

Prosa, requisitos e regras de negócio em **Português**. Nomes de arquivos,
diretórios, variáveis, classes, endpoints e trechos de código em **Inglês**.

### 2.4 Rastreabilidade spec ↔ código

- Módulos que implementam uma spec declaram no docstring do topo: `Implementa: RF-04-01, RF-04-02`.
- Testes de aceite nomeiam o critério: `def test_ca_01_02_health_returns_200(): ...`.
- Mensagens de commit referenciam a spec: `feat(curricula): add upload endpoint (spec 04)`.

### 2.5 Política de mudança

Quando a implementação revelar que a spec está errada ou incompleta:

1. **Pare a implementação.**
2. Atualize a spec e o seu `Histórico de Revisões`.
3. Só então retome o código.

É proibido ajustar o código de forma que contrarie a spec vigente. Uma spec que
mente sobre o sistema é pior do que nenhuma spec.

### 2.6 Status

Toda spec declara um status no cabeçalho:

- `Rascunho` — em discussão, não implementável.
- `Aprovada` — estável, pode ser implementada.
- `Implementada` — todos os critérios de aceite passam.
- `Descontinuada` — não vale mais; manter o arquivo para histórico.

---

## 3. Estrutura Obrigatória

Copie o bloco abaixo ao criar uma nova spec. Seções são obrigatórias; se uma não
se aplicar, escreva `N/A` com uma linha de justificativa — nunca a omita.

```markdown
# Spec NN: <Título>

**Status:** Rascunho | Aprovada | Implementada | Descontinuada
**Depende de:** spec NN, spec NN (ou `Nenhuma`)

## 1. Contexto
Por que esta spec existe. Qual problema de `docs/argos.md` ela endereça.
Máximo dois parágrafos.

## 2. Requisitos Funcionais
Lista numerada de `RF-NN-nn`. Cada item é uma afirmação testável sobre o
comportamento observável do sistema. Um requisito por linha.

## 3. Contratos
Interfaces expostas: endpoints (método, path, status codes), schemas Pydantic
de request/response, assinaturas de serviço, tabelas e colunas. Use blocos de
código. Se a spec não expõe interface, `N/A`.

## 4. Regras de Negócio
Lista numerada de `RN-NN-nn`. Cálculos, validações, precedências, casos de
borda. É aqui que mora o domínio — seja explícito sobre o que acontece quando
a entrada é inválida, vazia ou ambígua.

## 5. Requisitos Técnicos
Lista numerada de `RT-NN-nn`. Imposições de stack, arquitetura, performance,
segurança. Restrições, não sugestões.

## 6. Critérios de Aceite
Lista numerada de `CA-NN-nn`. Cada critério é uma **prova executável**: um
comando com saída esperada, ou um teste automatizado. Se não dá para rodar,
não é critério de aceite.

## 7. Fora de Escopo
O que esta spec deliberadamente NÃO cobre, e para qual spec o assunto foi
adiado. Esta seção previne escopo implícito.

## 8. Pendências
Divergências conhecidas entre esta spec e o estado atual do repositório, e
decisões ainda em aberto. Vazio quando o status é `Implementada`.

## 9. Histórico de Revisões
| Data | Versão | Alteração |
|---|---|---|
| AAAA-MM-DD | 1.0 | Criação. |
```

---

## 4. Critérios de Qualidade

Antes de marcar uma spec como `Aprovada`, verifique:

1. **Verificabilidade** — todo `RF` e `RN` tem pelo menos um `CA` que o prova.
2. **Ausência de ambiguidade** — nenhum "deve ser rápido", "adequado", "se
   necessário". Números e condições explícitas.
3. **Sem decisão implícita** — se a spec deixa uma escolha arquitetural para o
   momento da implementação, ela está incompleta. Decida na spec.
4. **Sem código de implementação** — a spec define contratos e comportamento
   esperado, não a solução. Blocos de código servem para assinaturas, schemas e
   exemplos de payload, não para lógica.
5. **Dependências declaradas** — se a spec pressupõe outra, o campo
   `Depende de` diz qual.

---

## 5. Fora de Escopo

- Padrões de código (tipagem, nomenclatura, tamanho de função): vivem em `CLAUDE.md`.
- Processo de revisão e aprovação de specs entre humanos: não formalizado.

## 6. Histórico de Revisões

| Data | Versão | Alteração |
|---|---|---|
| 2026-07-21 | 1.0 | Criação do template e do contrato de specs. |
