# Replanejamento da IA: VM, privacidade e atendimento de 5–6 funcionários

**Atualizado:** 20/10/2026, após inspeção somente de leitura da VM e comparação do código implantado com o GitHub.  
**Estado:** planejamento; nenhuma integração externa ou alteração de configuração foi executada.  
**Código:** GitHub `master` em `ee04871`; VM em `eb91e14`, um commit atrás. A diferença contém apenas documentação e teste de segurança, sem mudança no código da aplicação.

## Decisão executiva

Não é correto concluir que a única saída é enviar tudo a uma IA externa. A inferência local continua possível, mas a VM atual não oferece uma experiência rápida e previsível para 5–6 pessoas ao mesmo tempo: o modelo local mediu aproximadamente 0,9 token de saída por segundo, e o Ollama está limitado a uma inferência paralela. Uma API externa tende a aliviar esse gargalo de CPU, mas a gratuidade, as cotas e as regras de tratamento de dados impedem assumir que ela possa processar todos os documentos reais do cartório.

A arquitetura recomendada é **híbrida e local-first**: arquivos, OCR, banco, embeddings, recuperação de fontes, classificação, histórico, trilha de auditoria e decisões continuam na VM. Um provedor externo poderá ajudar a redigir/sintetizar somente o contexto mínimo que passar por uma política de dados explícita. O sistema nunca enviará a base inteira, arquivos completos ou todos os documentos de um processo “por padrão”.

Há um conflito que precisa permanecer visível no plano: o requisito de custo zero não garante capacidade para seis usuários nem autoriza o envio de conteúdo confidencial. Nos termos vigentes consultados, os serviços não pagos do Gemini podem usar prompts e respostas para aprimorar produtos e permitir revisão humana; o Google orienta não enviar conteúdo pessoal, confidencial ou sensível. Remover CPF e nomes não torna automaticamente um processo anônimo ou deixa de torná-lo confidencial. Assim, **Gemini gratuito fica restrito a conteúdo público ou sintético aprovado**. Para documentos privados reais, não haverá envio externo até que o conteúdo seja considerado efetivamente anônimo e autorizado, ou que exista um provedor/contrato aprovado para esse tratamento. [Termos Gemini](https://ai.google.dev/gemini-api/terms?hl=pt-br) · [Níveis e preços Gemini](https://ai.google.dev/gemini-api/docs/pricing)

O DeepSeek API não deve ser considerado uma opção permanentemente gratuita: a tabela oficial consultada cobra por tokens. A escolha de provedor ficará para depois da conferência de termos, preços, cotas por projeto, retenção e aprovação institucional. [Preços oficiais do DeepSeek API](https://api-docs.deepseek.com/quick_start/pricing/)

## Evidências da auditoria de desempenho

O registro detalhado do sistema convidado está em [Ambiente da VM](../operacao/AMBIENTE_VM.md). O retrato relevante para esta decisão é:

| Medida observada | Resultado |
| --- | --- |
| SO e máquina | Rocky Linux 9.8; 6 vCPUs, Intel Xeon E5-2609 v3 a 1,90 GHz |
| RAM e swap | 11 GiB de RAM; cerca de 8,3 GiB disponíveis no instante ocioso da inspeção; swap de 2 GiB sem uso |
| Acelerador | Ollama identificou backend `cpu`; `/api/ps` mostrou 0 bytes em VRAM. `nvidia-smi` não está instalado |
| Disco | `/dev/sda` ainda tem 20 GB; raiz XFS de 17 GB com 95% de uso e cerca de 1,1 GB livre. A ampliação para 50 GB ainda não aparece no Linux |
| Serviço de consulta | `qwen3:1.7b`, contexto 8.192, máximo de 900 tokens, timeout de 900 s e `keep_alive=30m` por chamada |
| Concorrência local | Inicialização do Ollama registrou `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1` e fila máxima 512; seis consultas locais simultâneas podem esperar em fila |
| Modelo de embeddings | `nomic-embed-text-v2-moe`; modelo de geração geral `qwen3:8b`; visão `qwen3-vl:2b` |
| Incidente | Journal do backend registra timeout de 900 s em 20/10/2026 às 10:53:29 |
| Saúde | Nginx, frontend, backend, Ollama e Docker ativos; backend `/health` `ok` e `/ready` `ready`, banco online |

Foi feita uma prova sintética curta diretamente na Ollama, sem documentos do cartório e sem gravação de consulta. Com 22 tokens de entrada e resposta de 2 tokens, o primeiro uso levou 18,12 s no total (11,08 s de carga, 3,39 s de leitura do prompt e 3,65 s de geração). Repetido com o modelo aquecido, levou 4,26 s (2,00 s de leitura do prompt e 2,24 s de geração para os mesmos 2 tokens). A chamada de produção também usa `think=false` e `stream=false`, como a prova.

Na taxa aquecida medida, gerar 900 tokens levaria aproximadamente 16 min e 48 s, antes da recuperação de trechos e da avaliação de um contexto maior; é uma extrapolação aproximada, não uma garantia de tempo. Isso explica por que uma resposta que se aproxime do limite pode exceder os 15 minutos configurados. O contexto real contém instruções e trechos recuperados, portanto a prova curta representa uma condição favorável.

O disco cheio é um risco operacional e deve ser corrigido, mas a amostra não mostrou swap nem espera de I/O. Ampliar o disco para 50 GB dará espaço para dados, logs e modelos; não aumentará CPU, RAM, VRAM ou tokens por segundo. Depois que o host apresentar o novo tamanho, será preciso expandir partição/LVM e XFS, com backup e validação.

## Requisitos de capacidade para 5–6 pessoas

- Tratar 5–6 funcionários como concorrência simultânea de projeto, não apenas usuários cadastrados. A Consulta deve suportar perguntas em paralelo sem recarregar a página; análises com vários documentos devem ser tarefas persistentes, com estado, progresso, cancelamento e retomada.
- O modo local deve ter fila observável, limites de concorrência e mensagem clara de espera. Não iniciar várias gerações pesadas simultaneamente na VM atual.
- O provedor externo deve ser submetido a teste real com seis sessões simultâneas. No Gemini, limites de RPM, TPM e RPD variam por modelo e projeto; são aplicados por projeto, não por chave. A cota disponível precisa ser confirmada no AI Studio e pode não atender a rotina do cartório. Não rotacionar contas/chaves para contornar limites. [Limites oficiais do Gemini](https://ai.google.dev/gemini-api/docs/rate-limits)
- O modo gratuito não poderá fazer fallback automático para cobrança. Cota esgotada, `429`, indisponibilidade ou erro de privacidade devem interromper a chamada externa, informar o usuário e oferecer fila local ou tentativa posterior.
- O alvo a validar é resposta simples da Consulta em até 30 s no percentil 95 com seis sessões de teste. Análises longas podem ser assíncronas, mas precisam mostrar progresso e resultado persistido. Se um provedor gratuito não cumprir cota e latência, o sistema deve declarar que esse requisito não foi atendido, sem ocultar fila ou custo.

## Arquitetura e fronteira de dados

1. A aplicação recebe pergunta e arquivos na VM. Banco, OCR, extração, hash, chunking, embeddings, histórico e busca semântica ficam locais.
2. O RAG local seleciona apenas as fontes e passagens pertinentes. A chamada externa, se permitida, leva a pergunta minimizada e os trechos necessários; nunca o banco, os embeddings privados, o OCR integral ou o arquivo inteiro.
3. Antes do gateway externo, uma política no backend classifica fonte, finalidade e sensibilidade. Regras determinísticas devem detectar CPF/CNPJ, telefone, e-mail, CEP, matrícula, número de processo e identificadores. Reconhecimento local de nomes, endereços, imóveis e relações complementa essas regras. Ollama local pode sugerir entidades, mas não será a única barreira.
4. Entidades aprovadas para pseudonimização recebem marcadores estáveis por requisição, como `<PESSOA_1>` e `<IMOVEL_1>`. A chave de reversão fica somente em memória/local, não segue ao provedor nem aparece em logs. Uma varredura posterior ao prompt bloqueia o envio se encontrar identificador não tratado ou se a classificação for incerta.
5. **Mascaramento não é autorização automática.** Informações indiretas, contexto processual, fatos patrimoniais e minutas ainda podem identificar as partes ou continuar confidenciais. Conteúdo privado real é bloqueado no modo gratuito até análise de privacidade e autorização formal. Se não for possível demonstrar anonimização adequada, não sai da VM.
6. O modelo externo só redige/sintetiza. A API local valida formato, referências e consistência; as citações exibidas vêm dos IDs, páginas e trechos recuperados no banco local, nunca de uma citação inventada pelo modelo. A resposta volta ao usuário e é armazenada localmente.
7. Não enviar prompt, resposta integral, arquivo ou mapa de pseudônimos a telemetria. Guardar somente ID opaco, modelo, classe de dados permitida, tempos, tokens, cota, resultado e erro sanitizado. A chave do provedor fica em secret do backend, fora do Git e do navegador.

## Escopo por área

| Área | Comportamento planejado |
| --- | --- |
| **Consulta** | Manter retrieval local e a prioridade vigente de entendimentos, respostas humanas elegíveis e documentos institucionais. Depois da busca, sintetizar a resposta em linguagem clara com fontes locais, sem respostas prontas que ignorem a base. No Gemini gratuito, só pergunta/contexto público ou sintético autorizado. Perguntas com dados de cliente também passam por triagem local. |
| **Documentos** | Upload, OCR, classificação, governança, extração e persistência continuam locais. Não enviar arquivos completos. Uma pergunta sobre documento pode usar passagens mínimas e anonimizadas somente se a política do provedor permitir. |
| **Análise de processo — vários documentos** | Permitir análise conjunta e persistente do conjunto do processo. Extração e associação documento/página/fato ocorrem localmente; a IA compara apenas fatos/passagens elegíveis e devolve referência verificável a documento, página e trecho. Progresso continua visível mesmo se demorar ou após reconexão. Documentos privados reais não seguem a uma API gratuita só por terem CPF/nome ocultados. |
| **A2** | Propor fatos com origem, localização, grau de certeza e conflitos. A confirmação permanece humana; nunca converter proposta externa em fato confirmado automaticamente. |
| **A1** | Produzir síntese/análise assistiva usando fatos A2 confirmados e fontes institucionais elegíveis, com versão/hash e lacunas explícitas. A IA não substitui revisão profissional nem cria fundamento sem fonte. |
| **TAB** | Permanecer exclusivamente humano para decisão, aprovação, recusa, qualificação final e assinatura. Nenhum provedor altera status ou executa decisão. |
| **Novos Entendimentos e Revisões** | Autoria e aprovação humanas. Rascunhos e respostas internas não são enviados ao nível gratuito. Publicação não ocorre automaticamente; só material formalmente público e liberado pode virar trecho recuperável externo. |
| **Histórico e Configurações** | Histórico, anexos, credenciais, papéis e configuração permanecem na VM. ADMIN pode desligar o provedor e ver cota/estado sem revelar a chave. Não reaproveitar histórico como contexto externo automaticamente. |
| **Ata Notarial** | Preservar o funcionamento atual. A única alteração de IA prevista nesta aba é avaliar e atualizar o modelo local de transcrição de áudio. Áudio, anexos e transcrições não serão enviados a provedor externo. Homologar o modelo em português considerando CPU/RAM e fila, pois a VM tem 11 GiB e não tem aceleração de inferência observada. |

## Modos operacionais e opções

| Opção | Benefício | Limite / decisão |
| --- | --- | --- |
| **Local otimizado** | Mantém dados na VM e custo de API zero. | Continua sujeito a CPU e fila; testar modelo compacto Qwen3 0.6B Q4 como comparação, sem trocar o 1.7B até avaliação de A1/A2/TAB. O modelo 0.6B publicado pela Ollama ocupa cerca de 523 MB; tamanho menor não prova precisão jurídica suficiente. |
| **Gemini gratuito** | Pode reduzir a inferência na VM para teste com conteúdo público/sintético. | Termos de uso de dados e revisão humana são incompatíveis com enviar conteúdo pessoal, confidencial ou sensível. As cotas gratuitas são variáveis por modelo/projeto e não garantem seis funcionários. Sem cobrança ou fallback pago. |
| **DeepSeek API** | Candidato técnico para comparação futura de qualidade/latência. | A API oficial é cobrada por tokens; não satisfaz a premissa de gratuidade permanente. Não integrar sem autorização expressa de custo. |
| **API privada/contratada** | Pode oferecer termos, controles e capacidade mais adequados a dados de trabalho. | Pode envolver custo e precisa de análise/contrato; fora da condição atual de custo zero, portanto apenas contingência futura. |

Sob as restrições atuais, não foi identificada uma opção comprovada que seja simultaneamente gratuita, apropriada para conteúdo confidencial real e capaz de garantir baixa latência para seis usuários. Se esses três requisitos forem inegociáveis, o próximo passo depende de uma decisão institucional sobre a fronteira de dados, orçamento ou infraestrutura; mascarar campos isolados não resolve sozinho esse conflito.

## Fases de trabalho

1. **Consolidar baseline:** preservar métricas da VM, comparar consulta curta/média/checklist em teste sintético, medir recuperação, embeddings, carga, prefill, geração e fila; testar 1, 3 e 6 usuários. Não registrar conteúdo de perguntas ou documentos.
2. **Reduzir espera local:** adicionar métricas por etapa também em timeout; retirar buscas complementares redundantes quando não forem necessárias; aproveitar cache e batching de embeddings; considerar manter embeddings e geração aquecidos se a RAM permitir; limitar fila e concorrência. Streaming real de tokens deve substituir a resposta única após `stream=false`; isso melhora percepção/progresso, mas não acelera o modelo.
3. **Provar qualidade/capacidade:** comparar Qwen3 1.7B com alternativa menor e parâmetros de contexto/saída, usando casos aprovados de Consulta e testes A1/A2/TAB. Não reduzir contexto ou limite de saída sem verificar citações e completude dos checklists.
4. **Definir política externa:** confirmar termos atuais, elegibilidade dos dados, disponibilidade regional, cotas por projeto e responsável pela chave. Gemini gratuito começa somente com dados públicos/sintéticos. Se o serviço não atender seis sessões sem custo, registrar o limite; não contornar com contas múltiplas nem ativar cobrança.
5. **Construir gateway e privacidade:** implementar classificação, mascaramento local, bloqueio por padrão, scanner de payload, allowlist do host/modelo, secret do backend, limite de tamanho/tokens, cancelamento, cota, modo desligado e logs sem conteúdo. Começar com chamadas externas desabilitadas.
6. **Integrar por área:** primeiro Consulta pública; depois Documentos e Análise com corpus sintético e múltiplos arquivos; por último qualquer categoria adicional formalmente autorizada. Novos Entendimentos/Revisões seguem aprovação humana. A1/A2/TAB mantêm os limites desta proposta. Ata segue local, com trilha separada para homologação do transcritor.
7. **Piloto e rollback:** seis funcionários em cenários simultâneos, medir p50/p95, erro de cota, qualidade, referências e fila; ADMIN pode desligar o provedor sem publicar segredos. Reverter ao modo local se houver falha de privacidade ou integridade.

## Critérios de aceite

- Seis sessões simultâneas testadas; Consulta simples atende ao alvo de p95 de 30 s no provedor escolhido, ou o limite e a fila são claramente apresentados e o piloto não é declarado aprovado.
- Análise de vários documentos sobrevive a navegação/reconexão, mostra estado por etapa e mantém links a documento/página/trecho. Nenhum arquivo completo é enviado automaticamente.
- Testes com CPF/CNPJ, nome, telefone/e-mail, endereço, matrícula, número de processo, imóvel e combinações contextuais confirmam que o scanner bloqueia identificadores residuais. Payload e logs são inspecionados em ambiente sintético.
- Cota `429`, indisponibilidade, timeout, cancelamento, retry e erro de mascaramento não enviam dados por caminho alternativo nem incorrem em custo. Nenhuma rotação de contas para contornar limite.
- Em modo Gemini gratuito, só passam fontes públicas ou dados sintéticos formalmente aprovados; conteúdo privado ou confidencial bloqueia por padrão. Uma revisão jurídica/privacidade registra a autorização antes de ampliar a classe de dados.
- A Consulta continua baseada na base local e apresenta as fontes efetivamente recuperadas. A1 expõe evidência e lacunas; A2 não confirma fatos; TAB permanece humano.
- Ata Notarial permanece local; só o modelo de áudio muda após teste documentado de precisão em português, tempo, memória, disco e coexistência com 5–6 usuários.
- Expansão de disco confirma capacidade nova no Linux, extensão segura de LVM/XFS e espaço livre; não é contabilizada como ganho de velocidade de IA.

## Auditoria de segurança anterior

Os achados, comandos, resultados de SQL injection em banco de teste, análise Bandit/dependências e recomendações de correção permanecem registrados em [plano anterior e auditoria de segurança](PLANO_GEMINI_PRIVACIDADE_E_AUDITORIA_SEGURANCA.md). Esse documento é referência histórica da revisão de segurança; o desenho de integração externa daquele texto foi substituído por este replanejamento, especialmente quanto a dados privados, concorrência e uso gratuito.

