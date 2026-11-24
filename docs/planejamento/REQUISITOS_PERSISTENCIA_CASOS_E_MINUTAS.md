# Requisitos de persistência de casos, análises e minutas

Atualizado em 24/11/2026. Este documento registra as exigências do Tabelião para a evolução do sistema. Os itens classificados como pendentes não estão implementados apenas por constarem neste planejamento.

## Objetivo

Preservar os campos definidos no MVP para mapear os dados do ato, acompanhar os estados intermediários da análise, manter histórico uniforme e permitir retomar o trabalho depois de uma saída da página ou reinicialização do backend. A estrutura atual pode ser diferente da proposta original, desde que cada informação tenha destino identificado e não haja perda de histórico.

Também é requisito que minutas geradas fiquem persistidas e vinculadas ao caso, com versões recuperáveis.

## O que o código já representa

| Informação/necessidade | Representação atual no código | Situação |
|---|---|---|
| Identificação e ciclo de vida do caso | `casos`: título, identificação, tipo de ato, descrição, dados estruturados em `dados_ato`, estado desses dados, estado do caso, responsável, criador, encerramento e datas | Implementado; `dados_ato` é JSON e precisa ser cotejado com os campos do MVP |
| Documentos privados do caso | `caso_documentos`: nome, caminho, hash, tipo e vínculo com o ato, estados de processamento e segurança, erros, número de páginas e dados de extração | Implementado |
| Texto por página e origem da extração | `caso_documento_paginas`: página, conteúdo, localização, confiabilidade, método e estado da extração | Implementado |
| Fatos extraídos e conferidos | `caso_fatos`: campo, categoria, origem, valor original e atual, evidência, estado da conferência, trecho e localização da fonte, página e método | Implementado |
| Histórico de alterações humanas | `caso_conferencias`: confirmação, correção ou reabertura, valores anterior e novo, observação, usuário e data | Implementado como histórico append-only |
| Snapshot uniforme para análise | `caso_versoes`: número, hash, motivo e snapshots de fatos e documentos | Implementado |
| Análise A1 e decisão TAB | `caso_analises` referencia uma versão e guarda resumo, requisitos, impedimentos, pendências e fontes; `caso_decisoes` registra a decisão humana | Implementado no modelo atual |
| Conversa e tarefas do caso | `caso_mensagens` mantém mensagens; `caso_tarefas` mantém tipo, estado, tentativas, erro e horários | Persistência básica implementada; retomada automática ainda não |
| Minutas vinculadas e versionadas por caso | A geração devolve o texto na resposta e a exportação produz um DOCX. Modelos de minuta são documentos institucionais. Não há entidade/tabela própria para rascunhos gerados vinculados a um caso | **Pendente** |

O modelo cobre partes importantes do mapeamento, dos estados intermediários e do histórico. Ainda não é possível afirmar que **todos** os campos do MVP foram preservados: o arquivo original com a especificação campo a campo não foi localizado entre os documentos versionados neste repositório. A auditoria comparativa permanece pendente; não se deve tratar a tabela acima como certificação de equivalência integral.

## Exigências a implementar

### 1. Auditoria campo a campo do MVP

- Incorporar ou localizar no repositório a versão de referência do documento MVP usado pelo Tabelião.
- Criar uma matriz para cada campo e estado descrito no MVP, indicando: campo original, tabela/coluna ou caminho JSON correspondente, classificação (`preservado`, `adaptado`, `ausente` ou `não verificável`), transformação aplicada e eventual migração necessária.
- Validar a matriz com o responsável pelo MVP antes de declarar equivalência.
- Para campos em `dados_ato` ou outros JSON, documentar o caminho e o formato esperado; a presença de uma coluna JSON, por si só, não comprova que todos os campos estejam armazenados ou validados.

### 2. Histórico e retomada do caso

- Preservar valores extraídos/declarados e valores corrigidos separadamente, além da origem, trecho/página, responsável e datas.
- Manter os estados intermediários, erros, pendências e transições humanas em histórico auditável; uma nova extração não pode apagar correções humanas silenciosamente.
- Registrar snapshots versionados usados por A1/TAB e indicar quando nova evidência torna uma análise anterior desatualizada.
- Substituir a execução dependente apenas de `BackgroundTasks` por worker durável, com reivindicação atômica de tarefas, heartbeat/lease, progresso por etapa, tentativas, política de retentativa e retomada de tarefa abandonada após reinício.
- Adicionar chave de idempotência persistida por operação/versão para evitar duplicação em retentativas. No estado atual, `caso_tarefas` **não** possui essa coluna; hashes usados na extração factual não substituem idempotência da fila inteira.

### 3. Persistência e versões de minutas

- Criar entidade/tabela de minutas geradas, vinculada ao caso e ao modelo institucional utilizado.
- Persistir cada versão do texto e os dados estruturados que a originaram; preservar versões anteriores quando houver nova geração ou edição.
- Registrar estado (por exemplo, rascunho, em revisão, revisada), usuário responsável, datas, versão/hash do modelo e metadados necessários para reproduzir a geração.
- Armazenar o DOCX em armazenamento privado e controlado; manter no PostgreSQL a referência, formato, hash, tamanho e vínculo com a versão da minuta. Não guardar apenas o texto transitório devolvido pela API.
- Manter explícito que minuta gerada é rascunho e não equivale a aprovação ou decisão do Tabelião.

### 4. Migração, segurança e continuidade

- Projetar migrações Alembic com backup, validação de dados existentes e plano de retorno; não descartar `dados_ato`, snapshots, fatos ou histórico atuais.
- Restringir leitura e escrita de casos, documentos, fatos, análises e minutas às permissões do caso e do perfil do usuário.
- Definir retenção, exclusão e restauração dos arquivos privados sem quebrar referências históricas necessárias.
- Incluir verificações automatizadas para gravação, versionamento, autorização, retentativa idempotente, retomada após reinício e recuperação de uma minuta já gerada.

## Critérios para considerar concluído

1. A matriz campo a campo do MVP foi preenchida e revisada; nenhum campo está sem destino ou sem decisão explícita.
2. Uma falha/reinicialização permite retomar tarefas sem perder estado e sem duplicar efeitos, preservando correções humanas.
3. Um caso pode ser reaberto e recuperado com documentos, fatos, conferências, snapshots, análises, decisões e mensagens correspondentes.
4. Minutas geradas ficam vinculadas ao caso, podem ser reabertas e exportadas em versões específicas, com autoria e histórico.
5. Migrações e testes de autorização, continuidade e restauração foram executados antes de habilitar o fluxo operacional de Análise/Minuta.

## Estado da interface

A interface de Análise e Minuta permanece em prévia/desabilitada até o refatoramento e a homologação desses requisitos. Este documento é planejamento; não altera por si só o banco da VM nem declara as abas prontas para uso.
