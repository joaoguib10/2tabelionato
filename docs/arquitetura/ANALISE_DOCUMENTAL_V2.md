# Análise documental por caso

Este documento define a evolução da aba **Análise** sem descartar o fluxo A2/A1/TAB já implementado.

## Decisão arquitetural

O `Caso` é o espaço de trabalho persistente do processo e a conversa é a interface
principal da Análise. A pessoa pode enviar um documento, explicar o que ele é e a
quem se refere, e orientar o que deseja conferir. A resposta e as mensagens
subsequentes ficam vinculadas ao mesmo caso, permitindo retomá-lo após sair da
página ou concluir uma etapa. Anexos continuam privados e fora do RAG institucional.

Fluxo conversacional atualmente conectado:

1. a pessoa abre ou cria um caso e informa o ato;
2. anexa um documento no próprio chat, informa seu tipo, vínculo e orientação;
3. a API registra a mensagem e agenda extração documental, inspeção de segurança,
   propostas factuais A2 e resposta da IA como etapas rastreáveis;
4. a IA só recebe o documento se estiver extraído, integralmente processado e
   liberado na inspeção; fatos do A2 permanecem propostas até conferência humana;
5. novos documentos e mensagens acrescentam contexto ao mesmo caso; o chat usa um
   limite de histórico/contexto e oferece paginação para consultar mensagens antigas;
6. a pessoa pode concluir o caso preservando anexos e conversa, reabri-lo depois,
   ou usar separadamente a ação explícita de conclusão com remoção dos arquivos e
   textos privados extraídos. A limpeza não apaga o histórico do chat.

O chat não substitui nem confirma A2, A1 ou TAB. A2 organiza fatos com trecho e
localização verificáveis; A1 só pode fundamentar conclusão jurídica com fontes
institucionais elegíveis; TAB continua sendo decisão humana. Se uma etapa de
extração ou segurança falhar, a aplicação informa a falha e não apresenta a
resposta como análise concluída. O resumo A1 salvo só entra no contexto do chat
quando o caso permanece em `ANALISE_DISPONIVEL`; ao voltar à preparação/conferência,
o resultado anterior não é apresentado como análise atual.

## Mensagens do caso (implementado)

A tabela `caso_mensagens` e os endpoints de leitura/registro já estão disponíveis. O registro pode solicitar uma resposta local assíncrona (`gerar=true`), vinculada a uma tarefa `CHAT_CASO`; ela contém:

- caso;
- autor;
- papel (`USUARIO`, `ASSISTENTE`, `SISTEMA`);
- texto;
- tipo (`PERGUNTA`, `RESPOSTA`, `AVISO`, `DECISAO`);
- referências aos fatos/documentos usados;
- versão factual/A1 considerada;
- data e hora.

As mensagens devem ser somente acrescentadas. A recuperação de uma pergunta posterior usa o histórico recente com limite de contexto e fatos extraídos apenas de documentos elegíveis. Uma mensagem não pode confirmar fato, alterar governança ou registrar decisão automaticamente. O histórico longo é carregado por páginas, sem solicitar todas as mensagens em uma única chamada.

## Fila de processamento (implementada para o piloto)

O `BackgroundTasks` continua executando no processo local, mas a tabela `caso_tarefas` persiste o estado das etapas para acompanhamento. Ela contém:

- caso e documento relacionados;
- tipo (`EXTRACAO_DOCUMENTAL`, `OCR`, `ANALISE_MATRICULA`, `ANALISE_REPRESENTACAO`, `RESUMO_A1`);
- status (`PENDENTE`, `PROCESSANDO`, `CONCLUIDA`, `ERRO`, `CANCELADA`);
- tentativas, erro público e timestamps;
- chave de idempotência por hash do documento/versão.

O estado persistido torna a execução visível, mas o executor atual não retoma automaticamente trabalho interrompido por uma queda/reinicialização do backend; antes de operação multiworker é necessária uma fila/worker durável. Falhas devem permitir reprocessamento explícito, sem duplicar fatos ou substituir correções humanas.

## Regras de conteúdo

- Matrícula: ler todas as páginas, preservar R./Av. em ordem, registrar trechos e destacar alienação, indisponibilidade, ônus, averbações de divórcio/óbito, divergências ou qualquer fato que exija conferência.
- Representação: contratos sociais, procurações, alvarás, atas, estatutos e regimentos devem indicar a fonte literal dos poderes. Cargo ou classificação isolada não prova competência.
- Resumo: separar fatos encontrados, documentos faltantes/desatualizados, pendências e possíveis impedimentos. A IA não decide validade.
- A1: somente após a conferência humana, com snapshot da versão factual e fontes institucionais elegíveis.
- TAB: decisão exclusivamente humana, identificada e vinculada ao caso.

## Retenção e privacidade

O caso e seus anexos permanecem privados. O usuário pode anexar documentos adicionais no mesmo caso até o encerramento. Ao concluir ou arquivar, a política de retenção deve permitir apagar os binários temporários, preservando somente os snapshots e registros necessários à auditoria autorizada.

## Próximas evoluções

1. Homologar o ciclo upload → extração → A2 → resposta conversacional com documentos
   sintéticos ou autorizados, inclusive falha, PDF sem texto, OCR e inspeção que
   exija liberação humana.
2. Completar análise especializada de matrícula e poderes de representação para
   procuração, alvará, contrato social, ata, estatuto e regimento, sempre com fonte
   literal e confirmação humana.
3. Fazer com que o chat identifique explicitamente documento novo, pendências,
   fatos alterados e eventual necessidade de regenerar A1; uma análise A1 antiga
   não pode ser tratada como atual após mudança material do caso.
4. Substituir `BackgroundTasks` por worker durável antes de depender de recuperação
   após reinício ou de múltiplas instâncias da API.
5. Homologar reabertura, conclusão preservando histórico e limpeza explícita dos
   anexos; medir concorrência, tempo do Ollama e espaço em disco na VM.
