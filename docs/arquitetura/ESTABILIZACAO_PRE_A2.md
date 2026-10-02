# Estabilização pré-A2 — 07/09/2026

Esta entrega foi concluída e sucedida pelo primeiro recorte manual de A2. O estado corrente está em [Etapas do projeto](../planejamento/ETAPAS_PROJETO.md).

## Escopo desta entrega

Correções incrementais sobre o marco pré-A2. Nenhuma alteração em modelos, migrações, 2FA ou regras jurídicas. Nenhuma importação, exclusão de documento real, commit ou publicação.

## Correções efetivas

- Upload institucional passou a exigir ADMIN em todas as categorias; botão de cadastro acompanha a permissão.
- Entendimentos não publicados ficam invisíveis para os demais perfis tanto na área específica quanto na listagem, detalhe e download genéricos. Não altera a elegibilidade do RAG.
- Transições para PRONTO_PARA_ANALISE, ANALISE_DISPONIVEL e DECISAO_REGISTRADA ficam bloqueadas até existirem suas validações. Estados anteriormente gravados não foram migrados nem apagados. Preparação, aguardo de conferência e encerramento permanecem disponíveis.
- Reprocessamento manual de anexos privados em preparação/conferência, inclusive após reinício que deixe PROCESSANDO sem tarefa ativa. Bloqueia tarefa já reservada, caso inacessível, caso encerrado, arquivo ausente e documento com fatos vinculados. Mantém a classificação; substitui páginas extraídas sem duplicação e reinspeciona a segurança.
- Erros internos de extração de casos não são refletidos como mensagens públicas.
- Novos Entendimentos: paginação real de 20 itens, atualização periódica e cancelamento de respostas obsoletas ao mudar de página. Corrigido o efeito que impedia o lint.
- Teste de migrações usa ScriptDirectory do próprio Alembic, em vez de expressões regulares frágeis.
- Testes usam banco em memória e diretórios temporários para uploads. Sessões dos serviços de ingestão também são redirecionadas para o banco de testes.
- Novos testes de casos próprios/atribuídos/ADMIN, anexos privados, isolamento de corpus, transições, classificação contextual, reprocessamento e visibilidade/paginação dos entendimentos.

## Limite operacional importante

O piloto deve executar **um único processo/worker da API**. A reserva de tarefas é local ao processo; não coordena vários workers ou servidores. Após reinício, o operador solicita Reprocessar; não existe retomada automática. Se o processo continua ativo porém travado, não dispare outra tarefa: investigue a falha antes de reiniciar.

O reprocessamento não constitui aprovação jurídica, confirmação de fatos ou prova de completude. Diagnóstico e inspeção continuam separados do status PRONTO.

## Validação manual recomendada

### Verificações automatizadas executadas nesta entrega

- `python -m pytest`: **143 passaram**, nenhuma falha, um aviso de depreciação da integração Starlette/httpx (não suprimido).
- `npm run lint`: passou, sem erros ou avisos.
- `npm run build`: passou, incluindo TypeScript e geração das rotas.
- `alembic heads`: uma cabeça, `8d06fc8d27e7`.
- `alembic check`: nenhuma nova operação de migração necessária.
- `git diff --check`: sem erros de whitespace nos arquivos rastreados.

Não houve execução de upgrade/downgrade, teste integral de migrações em banco vazio, homologação visual no navegador ou teste com acervo real. O build gerou alterações em next-env.d.ts que foram revertidas isoladamente, preservando a versão pré-execução.

### Roteiro para o responsável

1. Entrar com ADMIN e um USUARIO de teste, mantendo 2FA habilitado.
2. ADMIN cria entendimento em rascunho: outro usuário não o lista nem obtém detalhe/download pelo UUID. Após publicação válida, passa a ser visível.
3. USUARIO não encontra Novo documento no corpus; tentativa direta de upload institucional retorna 403. Upload de anexo em seu próprio caso permanece permitido.
4. Criar caso sintético e anexar TXT/PDF de teste. Conferir texto, classificação e localização; verificar que o anexo não aparece em Documentos/Consulta.
5. Outra conta não atribuída não acessa caso, conteúdo ou download. ADMIN acessa todos.
6. Em caso de falha de extração, corrigir a causa e usar Reprocessar. Atualizar a lista e conferir que não há duplicação de páginas. Durante tarefa ativa, nova solicitação retorna 409.
7. Verificar paginação de Novos Entendimentos e o último registro após exclusão de uma página final.
8. Confirmar que estados de análise concluída/decisão não podem ser antecipados pela API.

## Continuidade — não implementado neste bloco

1. Homologar manualmente estas correções e amostras de OCR com documentos autorizados. A suíte determinística não mede qualidade real do Tesseract/Ollama nem qualidade jurídica.
2. Consolidar os contratos A1/A2/TAB/A3 e implementar A2 com origem verificável, fatos, divergências e conferência humana. A classificação continua sendo contexto, não prova.
3. Fluxo gerencial de atribuição/reatribuição de responsáveis: a filtragem por responsável já existe, mas a operação de atribuir pela interface ainda não.
4. Evoluir validação das citações do RAG e avaliação jurídica revisada por humanos. Heurísticas de sobreposição lexical não comprovam fundamentação.
5. Descarte durável de arquivos: hoje falha após exclusão no banco pode deixar arquivo órfão. Exige desenho transacional/retentivo; não trocar a ordem por exclusão antes do commit, que pode causar perda de dados.
6. Desempenho: contagens por caso, volume de páginas retornadas, limites de descompactação e consumo do OCR. Coordenação persistente de ingestão se houver múltiplos workers.
7. Resolver destino da cópia frontend-envio e retirada futura das rotas legadas de Minutas mediante autorização. Nada foi removido ou reativado nesta entrega.
8. Ata Notarial, transcrição local e política de retenção continuam etapas posteriores.

## Backup e restauração

Foi preservado um snapshot pré-alterações do código em `C:\Users\joaog\Projetos\tabeleao-backup-pre-estabilizacao-20260907-143637.zip`, com caminhos backend/frontend. Não contém banco, arquivos operacionais de uploads nem segredos .env; não é backup completo da instalação.

Para reverter, extraia primeiro em diretório separado e compare os arquivos com o projeto, preservando alterações posteriores. Os novos arquivos desta entrega não existirão no snapshot: identifique-os antes de qualquer remoção. Não restaure por cima do projeto indiscriminadamente.
