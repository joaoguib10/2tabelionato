# Etapas do projeto Tabeleão

Atualizado em 01/10/2026. Este documento registra o estado do código, não substitui homologação humana nem declara validade jurídica das respostas.

## Marco atual

O desenho técnico especializado de Compra e Venda foi integrado ao A2 e ao snapshot do A1. A próxima fase é a homologação funcional e jurídica com amostras sintéticas ou autorizadas. O ponto exato e as regras aprovadas estão registrados em [CHECKPOINT_COMPRA_VENDA.md](CHECKPOINT_COMPRA_VENDA.md).

O projeto concluiu o fluxo técnico do piloto desde o estado factual A2 até a decisão humana TAB. A primeira versão da Ata Notarial também está disponível, com processamento textual de ZIP/RAR e integração preparada para transcrição local.

Nesta atualização, a Análise foi reorganizada para colocar a conversa persistente do caso em primeiro plano: anexos podem ser enviados com tipo, vínculo e orientação; a resposta é encadeada à ingestão e às propostas A2. Concluir preservando dados e reabrir são ações distintas da limpeza explícita dos anexos. A Consulta ganhou telemetria por etapa para distinguir recuperação, carga do Ollama, prefill e geração, e sua ordenação vetorial agora pode aproveitar o índice HNSW existente. O ganho e a cobertura de fontes precisam ser confirmados com plano SQL e casos avaliados; nenhum limiar jurídico ou limite de resposta foi reduzido.

Em 17/09/2026, a homologação técnica repetiu o fluxo sintético completo A2 → A1 → TAB. A interface denomina essas camadas A2, A1 e TAB; não existem módulos independentes chamados S1 ou S2. O MVP está apto a implantação interna controlada, mas a liberação operacional continua condicionada à validação jurídica humana, aos testes de carga na VM e à amostra documental autorizada.

Fluxo disponível na Análise:

`USUARIO ou ADMIN cria o caso → anexa documentos privados → confere extração e fatos A2 → conclui conferência → cria versão → solicita A1 → ADMIN registra decisão TAB`

A classificação continua sendo contexto, não prova. A análise A1 não decide, e a decisão TAB continua exclusivamente humana e identificada.

## Ato 1 — Base local, privacidade e governança

**Estado: implementado; homologação operacional pendente.**

- FastAPI, Next.js, PostgreSQL/pgvector, Ollama local e Alembic.
- Ollama vinculado a `127.0.0.1`, com nuvem e histórico de prompts desativados na máquina de desenvolvimento.
- Política mínima de senha com letras e números, TOTP, recuperação local e bloqueio de tentativas; a proteção forte para uso em rede ainda depende de HTTPS e política de credenciais adequada.
- Sessão da interface em cookie `HttpOnly` com `SameSite=Lax`; Bearer permanece disponível para compatibilidade e Swagger.
- Perfis unificados em ADMIN e USUARIO; o antigo MASTER passa a ADMIN e o antigo ADMIN perde privilégios gerenciais.
- Sessão deslizante de oito horas: atividade autenticada renova o token; inatividade exige novo login.
- Gestão de contas, corpus, revisões, entendimentos e casos exclusiva do ADMIN.
- Anexos de casos separados das tabelas Documento/DocumentoPagina/DocumentoChunk e do RAG.
- Usuários criam e trabalham em casos próprios ou atribuídos; ADMIN vê e edita todos e atribui responsáveis.

Continuidade: testar instalação em máquina limpa, restauração de backup, ausência de egress e operação com um único worker. Na VM definitiva, repetir as variáveis persistentes descritas em `docs/operacao/DESEMPENHO_CONSULTA.md` e validar a regra de firewall.

## Ato 2 — Corpus documental, ingestão e OCR

**Estado: funcional; qualidade real pendente de homologação.**

- Upload, extração, chunks, embeddings, governança, segurança, filtros, paginação e reprocessamento.
- PDF, DOCX e TXT; diagnóstico de camada de texto e OCR local configurável com Poppler e Tesseract.
- PDFs podem ser reprocessados com OCR integral por ação explícita, inclusive quando uma camada de texto ruim tiver gerado poucos trechos.
- Contagem preserva páginas sem texto; DOCX/TXT extensos usam blocos lógicos, sem referências físicas falsas.
- Limites de páginas, tempo e resolução do OCR podem ser ajustados por ambiente.
- Apenas documentos aprovados, ativos, integralmente processados e liberados entram na Consulta.

Continuidade: selecionar pequena amostra sem dados pessoais, validar OCR por página, documentos longos, tabelas, artigos continuados e diagnóstico de extração parcial. Corrigir perdas comprovadas antes de ampliar o acervo.

Dependência local atual: Poppler e Tesseract estão disponíveis na máquina de desenvolvimento, com os idiomas `por+eng`, e passaram por teste sintético. Ainda é necessário reprocessar uma amostra autorizada e repetir a instalação/configuração na VM definitiva.

## Ato 3 — Consulta, fontes, histórico e Revisões

**Estado: implementado para piloto; calibração jurídica pendente.**

- Busca híbrida, histórico conversacional, snapshots das fontes e feedback.
- Resposta negativa abre Revisão; ADMIN responde e pode generalizar manualmente como entendimento em rascunho.
- Fontes não são atribuídas automaticamente quando o modelo não as cita.
- Consultas sem corpus elegível retornam sem carregar desnecessariamente o modelo de embeddings.
- Modelos recebem `keep_alive`, a saída possui limite configurável e embeddings de perguntas repetidas usam cache efêmero por hash, sem conservar o texto nesse cache.

Medições históricas: ausência de corpus caiu de 22,63 s para 0,075 s; uma consulta sintética repetida caiu de 30,45 s para 13,09 s. Após manter embeddings na CPU e o gerador na GPU/CPU, duas perguntas sintéticas diferentes terminaram em 23,78 s e 22,92 s. A comparação anterior de `qwen3:4b` (modo thinking) registrou 18–29 s contra 64–98 s para `qwen3:8b`, mas a resposta do modelo menor foi inadequada para a Consulta. Em 01/10/2026, foi mantido `qwen3:4b-instruct` para Consulta, separado do `qwen3:8b` de Análise. Na mesma pergunta sobre o art. 1.277, o modelo atual levou 16,1 s após troca/carga e 10,2 s aquecido, com citação validada. O candidato oficial mais novo `qwen3.5:4b` levou 50,8 s frio e 11,3 s aquecido; não foi adotado pois falha o alvo de até 30 s no primeiro uso sem demonstrar benefício suficiente. Perguntas amplas sem respaldo foram recusadas; recuperação ficou em torno de 4,8 s. São poucas medições sintéticas, não garantia operacional. Continuidade: o usuário testar a interface agora aberta; depois repetir cold/warm start na VM de 24 GB, executar casos jurídicos revisados por humanos e melhorar a recuperação de perguntas amplas. A validação de citação é heurística lexical, não prova semântica; não reduzir contexto ou resposta só por velocidade, pois pode remover exceções jurídicas.

## Ato 4 — Análise A2, A1 e TAB

**Estado: caso persistente e chat-first integrado ao pipeline local; homologação com documentos e recuperação durável pendentes.**

Implementado:

- Todos os usuários criam e trabalham em casos próprios ou atribuídos; ADMIN vê e edita todos e atribui responsáveis.
- Documentos privados com localização, método de extração e inspeção de segurança.
- Fatos com locus `A–F` ou `CORINGA`, proveniência `DECLARADA`, `DOCUMENTAL`, `OBSERVADA` ou `INFERIDA` e condição `ENCONTRADO`, `AUSENTE`, `INCERTO` ou `CONFLITANTE`.
- Valor original preservado; correções alteram somente o valor corrente.
- Conferências `CONFIRMAR`, `CORRIGIR` e `REABRIR` geram histórico append-only identificado pelo usuário.
- Gate para `PRONTO_PARA_ANALISE`: fatos ativos conferidos e documentos integralmente processados/liberados.
- Reabertura de fato devolve o caso pronto para `AGUARDANDO_CONFERENCIA`.
- Propostas factuais pelo Ollama local disponíveis ao usuário do caso e sempre criadas como `PENDENTE`.
- O prompt factual exige varredura integral do bloco e fatos separados; no ensaio sintético local, nome, CPF, data e regime de bens foram propostos separadamente, sem confirmação automática.
- Verificação literal do trecho de origem: propostas sem fragmento encontrável são descartadas.
- Bloqueio de Ollama remoto para anexos privados; somente endereço loopback é aceito.
- Processamento em lotes com estado `PRONTO_PARCIAL`, permitindo continuar documentos longos sem ultrapassar o contexto.
- Comparação lado a lado do texto extraído e dos fatos vinculados por página/bloco.
- Reexecução idempotente por hash do bloco/campo; uma correção humana não é sobrescrita.
- Alertas da inspeção permanecem bloqueados até liberação humana explícita no caso, com registro de usuário e data.
- Versão imutável criada a partir do estado factual e documental conferido; estado idêntico reaproveita a mesma versão e alterações geram versão seguinte.
- A1 usa fatos conferidos e somente o corpus institucional elegível, preservando snapshots das fontes empregadas.
- Sem fonte válida, a análise registra base insuficiente em vez de fabricar fundamentação.
- Somente o ADMIN registra a decisão TAB, vinculada à análise e à versão do caso, com decisão, texto, fundamentação e escopo.
- Alterações de evidência são bloqueadas após a análise até que o caso siga o fluxo explícito de reabertura.
- Compra e Venda possui estado estruturado próprio, extração local em lotes com evidência literal, mesclagem sem sobrescrever dados humanos, partes múltiplas e painel editável.
- Ao abrir o caso, os documentos privados aparecem antes dos campos de conferência, respeitando a sequência upload → extração → correção humana.
- As partes usam os papéis neutros outorgante/outorgado e podem ser relacionadas como principal, cônjuge, anuente, representante ou procurador, com dados específicos de casamento, empresa, procuração e alvará judicial.
- Procuração e alvará registram poderes e limites de valor; o valor e a forma de pagamento do negócio ficam estruturados. A comparação numérica produz alerta, nunca decisão de validade.
- A matrícula preserva R./Av. em ordem e usa a descrição curta apenas quando todos os elementos mínimos do endereço estão presentes.
- O estado estruturado e suas pendências integram a versão factual do A1; diagnósticos técnicos ficam fora do snapshot.
- A confirmação humana das partes e do imóvel libera o A1 mesmo com campos ausentes, que permanecem destacados como pendências; sugestões não confirmadas continuam bloqueadas.
- A interface operacional foi simplificada sem retirar os dados jurídicos: textos repetidos, o `locus` técnico e o campo de moeda redundante deixaram de ser exibidos no fluxo comum; os valores internos e os alertas de segurança foram preservados.
- A conversa do caso é a primeira área apresentada. O upload é feito no chat com tipo, vínculo e orientação livre, e a mensagem fica registrada no mesmo caso.
- Upload agenda extração/inspeção, processamento factual A2 em lotes e retorno do assistente local, com tarefas persistidas para exibição de progresso.
- O chat carrega a conversa recente e permite buscar mensagens anteriores por páginas; o contexto enviado ao modelo tem limite de tamanho.
- A IA só responde após extração integral e liberação de segurança; falha de extração factual é apresentada como falha, não como análise concluída.
- “Concluir caso” preserva documentos e histórico; o caso pode ser reaberto. “Concluir e apagar arquivos” permanece uma ação separada e explícita que remove os documentos e texto extraído, mas conserva o chat.

Próximo recorte recomendado:

1. Homologar manualmente upload → extração → A2 → resposta do chat, incluindo documentos incompletos, OCR, inspeção de segurança e tentativas de reprocessamento.
2. Confirmar que nova evidência invalida claramente a atualidade de análises A1 anteriores antes que o chat possa reutilizá-las.
3. Congelar o contrato mínimo dos blocos A–F e os critérios jurídicos esperados.
4. Medir falsos positivos, fontes insuficientes, divergências humanas e recuperação após reiniciar o backend.
5. Antes de múltiplas instâncias, substituir `BackgroundTasks` por um worker durável que retome tarefas pendentes/abandonadas.

Não implementar no próximo recorte: decisão automática, inferência promovida a fato, checklist MHT-H visível, repositório geral dentro do caso ou reaproveitamento automático de decisão específica.

## Ato 5 — Novos Entendimentos

**Estado: primeira versão implementada.**

- Todos os usuários autenticados leem entendimentos publicados.
- ADMIN cria, edita, publica e exclui.
- Rascunhos e itens não elegíveis não ficam acessíveis por rotas genéricas.
- Paginação de 20 registros.

Continuidade: confirmação de leitura por usuário e organização editorial, sem transformar feedback bruto ou caso particular em regra geral automaticamente.

## Ato 6 — Ata Notarial

**Estado: primeira versão técnica implementada; carga real pendente.**

- Upload em fluxo de ZIP/RAR com limite configurável, hash e área temporária privada.
- Proteção contra caminhos maliciosos, excesso de entradas, expansão excessiva e taxa de compressão insegura.
- Leitura de exportações usuais do WhatsApp, união de continuações e saída cronológica em parágrafo contínuo.
- As referências textuais a imagens, vídeos, PDFs e stickers são preservadas na sequência; os binários não são alterados nem transcritos nesta versão.
- Áudios recebem duração quando FFprobe está disponível e transcrição quando Whisper e modelo local estão configurados.
- Quando uma transcrição local falha, o resultado fica `PRONTO_PARCIAL`, identifica a pendência e permite nova tentativa.
- Cada usuário vê somente seus trabalhos. **Concluir e apagar** remove arquivos e registro temporário; nada entra no histórico ou no RAG.

Na máquina de desenvolvimento, 7-Zip, FFmpeg/FFprobe, Whisper e o modelo multilíngue `small` foram instalados e validados localmente. Em 09/09/2026, um trabalho real de teste que estava parcial foi reprocessado localmente e terminou `PRONTO`, com um áudio transcrito e nenhuma pendência, sem exposição do conteúdo. Continuidade: repetir a instalação na VM definitiva; validar RAR real e arquivos progressivamente maiores, espaço em disco, duração, precisão da transcrição e recuperação de falhas; definir expiração automática para trabalhos abandonados.

## Ato 7 — Homologação controlada

**Estado: homologação técnica automatizada concluída; MVP apto ao piloto controlado; homologação humana pendente.**

- Testes com perfis ADMIN e USUARIO.
- Amostra documental autorizada e casos jurídicos esperados.
- Segurança, privacidade, restauração, desempenho, OCR/Ollama local e ausência de internet.
- Roteiro de aceite e registro de limitações conhecidas.

## Ato 8 — Endurecimento arquitetural

**Estado: primeira camada aplicada; evolução operacional pendente.**

- Pool e timeout do PostgreSQL configuráveis, com endpoint `/ready` separado do
  healthcheck do processo.
- Headers básicos de segurança, `X-Request-ID` e logs de duração sem conteúdo
  documental ou credenciais.
- Ollama local obrigatório por padrão, com bloqueio explícito de destinos
  remotos.
- Primeiro repositório administrativo isolando o acesso persistente de usuários.
- Backup de código criado antes deste recorte, sem `.env`, uploads ou ambientes.

Continuidade: extrair os demais agregados para services/repositories, criar
coordenação persistente para OCR/embeddings/Ata, testar PostgreSQL/pgvector e
Ollama reais sob carga, revisar CSRF para publicação em rede e validar
restauração completa.

## Verificações automatizadas do marco atual

Os resultados abaixo são o registro da última execução anterior a esta atualização; não foram repetidos neste recorte.

- Backend: 190 testes aprovados, incluindo o cenário encadeado A2 → A1 → TAB e os testes de sessão, Ollama local e hardening; permanece uma advertência de depreciação do `TestClient`, sem falha funcional.
- Frontend: Prettier, ESLint, TypeScript e build de produção aprovados nas 16 rotas.
- Execução local: API, banco, Swagger e páginas operacionais responderam com HTTP 200; rotas privadas testadas sem token responderam HTTP 401.
- Dependências: `pip check`, Ruff, Black e `npm audit` aprovados; auditoria npm sem vulnerabilidades conhecidas.
- Ollama real: extração especializada recuperou os campos sintéticos esperados; A1 retornou requisitos, pendência e somente a fonte fornecida. Na máquina atual, a extração estruturada levou cerca de 100 segundos e o A1 cerca de 32 segundos, exigindo nova medição na VM.
- OCR e Ata: Tesseract, Poppler, FFmpeg/FFprobe, Whisper, modelo local e ferramenta RAR foram encontrados pelos caminhos privados configurados, sem exposição desses caminhos na interface.
- Alembic: `d53a9b2e8f74` adiciona versões, análises A1, decisões TAB e trabalhos temporários de Ata; `e64b1c3f9a20` adiciona o estado estruturado de Compra e Venda ao caso.
- Nenhum documento real foi excluído e nenhum commit ou publicação foi realizado.
- Backend padronizado por Black e Ruff; frontend padronizado por Prettier e ESLint, com comandos reproduzíveis no repositório.

## Dependências do responsável pelo projeto

- Homologar a terminologia e a granularidade do registro factual.
- Fornecer casos e documentos sintéticos ou autorizados para OCR e extração factual.
- Definir quando um fato conflitante, mas reconhecido, permite seguir para A1 e validar o comportamento já conservador do gate.
- Validar critérios jurídicos e respostas esperadas; a equipe técnica não deve inventá-los.
- Repetir na VM definitiva a instalação documentada de Tesseract, 7-Zip, FFmpeg/FFprobe e Whisper/modelo exclusivamente locais.
- Validar o descarte da Ata e decidir prazo automático para trabalhos que o usuário não concluir.

## Dependências de desenvolvimento

- Corrigir defeitos encontrados na homologação sem ampliar silenciosamente as regras.
- Homologar e calibrar as propostas automáticas de fatos com proveniência e conferência obrigatória.
- Calibrar A1 e TAB com casos esperados revisados por humanos, sem transformar classificação em prova.
- Melhorar descarte automático, desempenho e coordenação persistente antes de múltiplos workers.

## Backup desta transição

O código imediatamente anterior ao A2 manual foi preservado em `C:\Users\joaog\Projetos\tabeleao-backup-pre-a2-inicial-20260907-210459.zip`. O arquivo não inclui banco, uploads operacionais nem segredos.

Antes do endurecimento arquitetural de 29/09/2026 foi criado o snapshot
`C:\Users\joaog\Projetos\cartorio-ai-backups\cartorio-ai-20260929-004647.zip`.
Como complemento, o estado do PostgreSQL foi exportado para
`C:\Users\joaog\Projetos\cartorio-ai-backups\cartorio-ai-db-20260929-010025.dump`.
Os dois arquivos ficam fora do repositório; o snapshot de código não contém
`.env`, uploads ou ambientes virtuais.
