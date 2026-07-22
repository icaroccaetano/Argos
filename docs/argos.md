# Projeto Argos

## 1. Visão Geral
O **Argos** é uma API corporativa interna de inteligência artificial especializada no ranqueamento e análise semântica de currículos, com foco inicial em vagas do ecossistema de Tecnologia (Engenharia de Software, Dados, Infraestrutura, etc.). 

Utilizando técnicas avançadas de RAG (Retrieval-Augmented Generation) e LLMs, o sistema atua como um motor de *scoring* inteligente para o processo seletivo da empresa. O grande diferencial do Argos é a sua flexibilidade: ele não impõe uma fórmula única de avaliação, permitindo que a equipe de recrutamento ou gestão técnica tenha controle total sobre os pesos de cada critério para cada vaga específica.

## 2. O Problema que Resolve
* **Triagem Manual Lenta:** Recrutadores perdem horas lendo dezenas de currículos técnicos complexos.
* **Filtros Baseados em Palavras-Chave:** Sistemas tradicionais descartam bons candidatos de TI apenas porque usaram sinônimos, invés da sigla exata (ex: "K8s" vs "Kubernetes").
* **Falta de Padronização e Flexibilidade:** Avaliações humanas estão sujeitas a vieses, e ferramentas de mercado muitas vezes possuem critérios engessados que não refletem a necessidade momentânea de um time específico (ex: um time pode precisar de alguém com mais *soft skills* agora, enquanto outro exige apenas conhecimento técnico profundo).

## 3. O Diferencial Core: Motor de Pesos Dinâmicos
Ao contrário de soluções de mercado de "caixa preta", o Argos permite que o cliente da API (o time interno) defina a relevância de cada aspecto da avaliação no momento da requisição. Os critérios base incluem:
* **Aderência técnica** (ferramentas, linguagens, arquitetura).
* **Experiência relevante** (anos de atuação, setor, senioridade).
* **Formação e certificações**.
* **Soft skills e liderança**.

O sistema garante a liberdade total para alterar esses pesos (ex: 80% Técnico e 20% Soft Skills para um dev especialista; ou 50/50 para uma vaga de liderança), retornando um score perfeitamente ajustado à demanda daquela vaga específica.

## 4. Como o Argos Funciona (Fluxo Principal)
O Argos atua como um serviço de backend com duas responsabilidades principais:

1. **Ingestão e Compreensão (Currículos):**
   * Recebe um arquivo PDF do candidato.
   * O texto é extraído, compreendido em seções lógicas e dividido em fragmentos (*chunks*).
   * Esses fragmentos são convertidos em vetores matemáticos (*embeddings*) e armazenados no banco de dados.

2. **Avaliação sob Demanda (Match com a Vaga):**
   * A API recebe a descrição da vaga e o *curriculum_id*.
   * O motor de busca vetorial resgata os trechos mais relevantes daquele currículo.
   * O LLM avalia o contexto contra a vaga, obedecendo rigidamente à distribuição de pesos configurada na requisição.
   * A resposta é um JSON estruturado com a nota final (0-100), pontos fortes, lacunas mapeadas e uma justificativa detalhada.

## 5. Limites do Sistema (O que o Argos NÃO é)
* **Não é um SaaS Multi-tenant:** Foi desenhado como uma ferramenta interna para uma empresa específica. Não possui isolamento complexo de dados por cliente (B2B externo).
* **Não é um Frontend:** O Argos não possui interface gráfica. É uma API *headless* desenhada para ser consumida por outros sistemas internos, *workers* ou painéis da empresa.
* **Não é um Banco de Talentos Genérico:** Não foi feito para responder a perguntas amplas sobre a base de dados, mas sim avaliar um indivíduo específico contra uma necessidade específica.