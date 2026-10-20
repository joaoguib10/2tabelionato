# Plano de IA externa, privacidade e segurança

**Estado:** planejamento para implementação futura; as integrações com Gemini descritas aqui ainda não foram implementadas.  
**Revisão do repositório:** 20/10/2026, branch `master`, revisão local do commit `eb91e14`.  
**Objetivo:** preparar uma opção de IA externa sem custo para testes, preservando o processamento local de dados sensíveis, as fontes citadas e os limites de A1, A2 e TAB.

## Diretriz de produto

O sistema pode usar o nível gratuito do Gemini como apoio de síntese somente quando o conteúdo enviado estiver classificado como público ou sintético e aprovado para saída da máquina. O nível gratuito pode usar solicitações e respostas para melhoria dos produtos do Google e permitir revisão humana; os termos orientam a não enviar informações pessoais, confidenciais ou sensíveis. Portanto, mascarar nomes e números não transforma automaticamente um processo ou documento em dado anônimo, nem autoriza seu envio. Consulte os [termos da Gemini API](https://ai.google.dev/gemini-api/terms?hl=pt-br) e a [página de preços e níveis](https://ai.google.dev/gemini-api/docs/pricing).

O alvo é permanecer no nível gratuito. A aplicação não deve fazer fallback pago: deve impor limites de cota, mostrar indisponibilidade e voltar ao fluxo local quando a cota gratuita acabar. A gratuidade e os limites do provedor podem mudar; revisar termos e limites antes de ativar e periodicamente. A chave fica apenas no backend, nunca no navegador, no Git, nos prompts de log ou em mensagens de erro.

### Classes de dados e roteamento

1. **Público:** legislação e fontes institucionais publicadas. Pode ser enviado em pequenos trechos necessários, desde que a política vigente do cartório autorize o uso externo.
2. **Interno:** entendimentos, respostas de Revisões, minutas e notas ainda não publicados. Permanecem locais por padrão; só podem sair após aprovação humana explícita, saneamento e classificação como publicáveis.
3. **Privado/restrito:** documentos, fatos e conversas de processos, dados pessoais, documentos de identidade, dados patrimoniais, valores, endereços e informações de clientes. Nunca enviar ao Gemini gratuito. A2 e a triagem desses documentos permanecem locais.
4. **Sintético:** dados fabricados para testes, sem vínculo com pessoa ou processo real. Pode ser enviado após verificação de que não contém cópia ou identificador real.

O roteador deve negar por padrão quando a classe for desconhecida. Uma detecção ou máscara inconclusiva cancela a chamada externa; não deve haver envio parcial automático, silencioso ou baseado apenas em configuração de prompt.

## Proteção de dados antes de qualquer chamada externa autorizada

- Fazer a classificação e a recuperação de fontes no backend local; selecionar somente os trechos estritamente necessários, nunca enviar o documento inteiro por conveniência.
- Aplicar detecção local em camadas: padrões determinísticos para CPF/CNPJ, telefone, e-mail, CEP, matrícula, número de processo e identificadores; reconhecimento local de nomes, endereços e dados de imóvel; revisão adicional de contexto e uma varredura final de saída. O Ollama pode ajudar a identificar candidatos, mas não deve ser o único controle de privacidade.
- Substituir entidades por marcadores estáveis no contexto, como `<PESSOA_1>` e `<IMOVEL_1>`. Manter o mapa de reversão somente em memória/local, protegido e vinculado à requisição. Nunca enviá-lo ao provedor nem registrá-lo em log. Avaliar máscara de valores, datas, cartório e relações familiares conforme o risco e a pergunta.
- Fazer uma varredura de prevenção de perda de dados no payload final, depois de montar o prompt. Se restar identificador ou dado fora da classe aprovada, bloquear a chamada.
- Reassociar nomes apenas localmente quando a resposta precisar deles e quando a política permitir. A saída externa não pode introduzir fatos nem substituir as fontes do banco.
- Não registrar payload, resposta integral, chave, mapa de pseudônimos, CPF, nome ou conteúdo de documento em logs, métricas, tracing ou eventos de erro. Registrar apenas provedor, modelo, classe autorizada, quantidade de tokens/cota, duração, resultado e identificador opaco.
- Expor um botão de desligamento imediato para Gemini, com modo local como padrão e sem fallback pago.

## Escopo por aba

| Área | Plano e limites |
| --- | --- |
| **Consulta** | Recuperar entendimentos publicados, respostas humanas de Revisões elegíveis e documentos institucionais aprovados localmente. Manter prioridade e citações do banco; só enviar ao Gemini trechos públicos/sintéticos aprovados e minimizados. O modelo sintetiza, não escolhe fonte sem evidência, não cria fundamentação e não substitui os critérios de suficiência. Sem dados privados de casos. |
| **Documentos** | Upload, OCR, extração, governança, classificação e armazenamento continuam locais. O Gemini não recebe arquivo, OCR completo, embeddings que codifiquem conteúdo privado nem lote de páginas. Para documento público, liberar somente trecho mínimo aprovado e preservar referência local de página/trecho. Revisão humana continua necessária antes de aprovar/publicar. |
| **Novos Entendimentos** | Rascunhos e textos internos ficam locais. Após publicação e classificação como fonte pública, pequenos trechos podem ser elegíveis para síntese na Consulta. Nenhuma resposta do Gemini é publicada automaticamente como entendimento. |
| **Análise de processo (A2/A1/TAB)** | Anexos e conversa do caso permanecem segregados e locais. **A2** sugere fatos com evidência e estado pendente de conferência; não toma decisão. **A1** combina fatos confirmados pelo humano com fontes institucionais aprovadas, registra referências/snapshot e expõe lacunas; conteúdo privado do caso não segue ao Gemini gratuito. **TAB** continua exclusivamente humano: aprovação, recusa, qualificação final ou decisão não é automatizada. Nenhuma chamada externa pode alterar fato confirmado, estado, decisão ou publicação. |
| **Revisões** | Revisão/resposta do ADMIN é conhecimento humano, não treinamento automático. Conteúdo ligado a uma pessoa ou caso fica local. Só entendimento generalizado, revisto, sem identificadores e publicado pode tornar-se fonte elegível, ainda sujeito à classe de dados. |
| **Histórico** | Consultas, autoria, feedback e fontes continuam no banco local com controle de acesso. Histórico não é enviado como contexto externo automaticamente. Minimizar retenção e não expor perguntas potencialmente pessoais em telemetria. |
| **Configurações** | ADMIN configura chave no servidor, provedor/modelo permitido, limite de uso, modo local, classificação e desligamento. Chave jamais é retornada à interface ou exibida após gravação. Registrar auditoria administrativa sem valores secretos ou dados de clientes. |
| **Ata Notarial** | Preservar o fluxo atual de exportação, organização, privacidade e transcrição local. Não enviar áudio, mensagens, anexos ou transcrições ao Gemini. Fazer somente avaliação e possível atualização do modelo local de transcrição, comparando qualidade, velocidade, RAM, disco e execução na VM antes de trocar o padrão. |

## Invariantes de A1, A2 e TAB

- A2 continua uma camada factual: cada sugestão precisa apontar ao documento/trecho de origem, manter incertezas e conflitos e aguardar conferência humana.
- A1 continua uma análise assistiva fundamentada nas fontes institucionais aprovadas, sem substituir a revisão profissional; guardar versão/hash das fontes e identificar o que está confirmado ou pendente.
- TAB continua fora do ciclo decisório da IA. Gemini, Ollama ou outro modelo não aprova ato, não dá a palavra final e não promove automaticamente informação para fonte institucional.
- A resposta deve manter proveniência local: fonte, página/trecho, versão e política de dados usada. Citação externa, por si só, não prova que a fonte existe no acervo aprovado.
- Anexos privados de Análise não migram para a base institucional nem para Consulta sem processo explícito de generalização e aprovação humana.

## Arquitetura sugerida

1. Criar um gateway único de provedores no backend com interface comum, timeout, cancelamento, limite de tokens, cota, tratamento de indisponibilidade e trilha de auditoria mínima.
2. Colocar classificação, minimização, pseudonimização e scanner de saída antes do gateway. A autorização deve depender da classe da fonte e do propósito, não só da aba ou do prompt.
3. Manter retrieval, OCR, embeddings, histórico e decisão de elegibilidade no ambiente local. O provedor externo recebe apenas a pergunta saneada e o contexto público mínimo.
4. Aplicar allowlist de modelos e hosts, TLS, limite de chamadas/tamanho, controle de custo igual a zero, proteção contra repetição e chave em secret do servidor.
5. Tornar toda chamada externa identificável por um ID opaco e permitir auditoria sem conteúdo sensível; incluir configuração para desligar o provedor sem reiniciar o sistema, se a arquitetura permitir.
6. Tratar texto recuperado e anexos como dados não confiáveis e potencialmente contendo prompt injection. O modelo não deve obedecer a instruções de documentos, ter acesso a ferramentas, credenciais, banco ou rede, nem alterar política do sistema.

## Etapas de implementação

1. Corrigir e fixar o baseline de dependências e testes descrito na auditoria abaixo.
2. Definir política de dados, conjunto de dados sintético e contratos de A1/A2/TAB; obter decisão administrativa sobre quais fontes são publicáveis.
3. Implementar e testar mascaramento local, reversão local, scanner de payload e bloqueio por padrão. Começar sem chamadas Gemini.
4. Implementar o gateway com cota gratuita, kill switch, telemetria sem conteúdo e testes de indisponibilidade/limites; validar apenas com dados públicos/sintéticos.
5. Habilitar primeiro uma experiência limitada em Consulta com fontes públicas; depois avaliar Documentos e Novos Entendimentos apenas para conteúdo autorizado. Manter Análise privada local e Ata isolada.
6. Fazer piloto monitorado, revisão humana das respostas, avaliação de citações/privacidade e procedimento de rollback. Expandir apenas após os critérios de aceite.

## Critérios de aceite

- Testes comprovam que CPF/CNPJ, nome, telefone/e-mail, endereço, matrícula e identificadores de processo de dados sintéticos não aparecem no payload externo nem nos logs; scanner inconclusivo bloqueia o envio.
- Testes comprovam que conteúdo privado de Análise e Ata, áudio e transcrições nunca são enviados ao Gemini gratuito, inclusive em erro, retry, fallback e geração de resumo.
- Apenas fonte institucional pública aprovada/sintética e contexto mínimo podem cruzar a fronteira; chamadas externas preservam o ID e as citações locais sem alegar evidência ausente.
- A2 continua pendente de confirmação, A1 mantém suas fontes/limitações e TAB não pode ser acionado ou alterado por modelo.
- Desligar Gemini ou esgotar a cota gratuita mantém o sistema utilizável no modo local e não aciona custo pago.
- Chaves não aparecem no bundle frontend, Git, histórico, resposta de API ou telemetria. Há teste de autorização por perfil e segregação por caso.
- Avaliação do modelo de áudio da Ata documenta qualidade, tempo, memória, disco e resultado em português antes de alterar o modelo padrão.

## Revisão de segurança realizada

### Escopo e limites

Foi revisada a estrutura do checkout em `eb91e14`: frontend Next.js/React, backend FastAPI/SQLAlchemy, modelos e rotas, serviços de IA/OCR/ingestão, migrações, dependências, Compose, documentação e suíte backend. Foram executados Bandit, `pip-audit`, `npm audit`, a suíte backend e testes de regressão SQLi em banco SQLite em memória. Nenhum payload foi enviado à VM, ao GitHub como endpoint, ou ao banco/serviço de produção. Esta revisão não equivale a pentest independente, análise dinâmica completa, teste de rede, nem certificação de segurança.

### Resultado dos testes

- **SQL injection:** as consultas de persistência examinadas usam ORM/SQLAlchemy com valores vinculados; o SQL textual encontrado é constante ou parametrizado. Foram adicionados dois testes: tentativa de autenticação por entrada SQL e entrada maliciosa na Consulta verificando que a tabela de usuários permanece intacta. O conjunto direcionado de autenticação, permissões, Ollama, diagnóstico e SQLi: **15 aprovados**.
- **Suíte backend completa:** após incluir os dois testes SQLi, **276 aprovados e 1 falha**, em 63,19 s. A falha em `test_consulta_salva_fontes_e_feedback` espera `num_ctx=8192`, mas a configuração atual usa `12288`; alinhar a expectativa ao contrato/configuração atual ou centralizar o valor usado no teste. Não mudar o contexto de produção só para satisfazer o teste sem decisão técnica. O pytest também emitiu um aviso de depreciação do `TestClient`/`httpx`.
- **Bandit:** 16.366 linhas examinadas; nenhum achado de severidade alta, 11 médios e 9 baixos. Revisar os achados médios no ciclo de correção; o relatório não apontou vulnerabilidade de alta confiança.
- **Dependências Python:** 13 avisos/advisories em 4 pacotes fixados: `python-jose 3.5.0` (PYSEC-2026-4298), `pypdf 6.16.2` (PYSEC-2026-4153 a 4160), `pytest 8.4.1` (PYSEC-2026-1845, dependência de desenvolvimento) e `ecdsa 0.19.2` (PYSEC-2026-1325, transitivo). O código de JWT fixa `HS256` explicitamente, mitigando a condição específica citada no advisory de `python-jose`; ainda assim, atualizar ou substituir a biblioteca e manter a allowlist de algoritmo. Para `pypdf`, testar versão corrigida (mínimo indicado pelos advisories: 6.19.0). Confirmar compatibilidade do pytest 9 antes de atualizar; verificar se `ecdsa` é necessário e remover/reduzir a dependência se possível.
- **Dependências JavaScript:** `npm audit --omit=dev` reportou uma vulnerabilidade alta transitiva em `sharp` (<0.35.5), com correção disponível. Auditoria completa reportou seis ocorrências altas na árvore incluindo dependências de lint/glob. Não aplicar o `npm audit fix` sugerido cegamente: a sugestão envolvendo `eslint-config-next` rebaixa a linha principal; atualizar versões compatíveis com Next 16 e validar build/lint.
- **Segredos:** inventário de arquivos rastreados encontrou `.env.example`, não `.env`; manter validação periódica para evitar que credenciais ou uploads sejam adicionados ao Git.

### Achados e correções sugeridas

| Prioridade | Achado | Correção recomendada |
| --- | --- | --- |
| **P1 — antes de habilitar IA externa** | `minute_service.py` faz requisições diretas a `OLLAMA_BASE_URL` sem usar `garantir_ollama_permitido` nem verificar loopback, embora o padrão `OLLAMA_LOCAL_ONLY=true` exista. Minutas podem conter dados pessoais. | Centralizar todas as chamadas de modelo no gateway Ollama e fazer a política local-only ser obrigatória para conteúdo privado; testar todos os serviços e caminhos de retry. Incluir minutas e serviços legados no inventário de egress. |
| **P1 — antes de acesso por rede** | `docker-compose.yml` publica PostgreSQL em `5432:5432` sem limitar interface. `compose.vm.yaml` já troca para loopback. | Aplicar loopback também como padrão seguro no Compose base; expor DB somente quando intencional e filtrado por firewall. Trocar credenciais de exemplo e exigir segredos aleatórios por instalação. |
| **P1 — antes de HTTPS/uso externo** | `AUTH_COOKIE_SECURE` tem padrão `false`; adequado ao exemplo HTTP local, mas inadequado sob acesso HTTPS se não configurado. | Validar configuração de produção na inicialização/deploy; exigir HTTPS e `AUTH_COOKIE_SECURE=true`, HSTS apenas após TLS, e não permitir publicar autenticação por HTTP aberto. |
| **P1 — antes de ampliar ingestão externa** | Atualizações de dependências auditadas: avisos em `python-jose`, `pypdf`, `sharp` e dependências de desenvolvimento. | Criar PR de atualização controlada, manter `algorithms=["HS256"]`, testar parsing de PDFs reais sintéticos, build Next e suíte completa; repetir auditorias e registrar versões resolvidas. |
| **P2 — endurecimento de contas** | Política atual aceita senha a partir de 5 caracteres; há bloqueio por conta, mas não foi identificado rate limit geral por IP/endpoint. Bloqueio por conta isolado também pode permitir negação de serviço contra usuário conhecido. | Elevar mínimo para passphrase (por exemplo, 12 caracteres), suportar senhas longas, bloquear senhas comuns/vazadas e combinar limitação progressiva por conta/IP com mensagens uniformes e proteção contra lockout malicioso. |
| **P2 — endurecimento de navegador** | Backend emite `nosniff`, `X-Frame-Options`, `Referrer-Policy` e `Permissions-Policy`, mas não foi encontrado CSP. | Definir CSP compatível com Next, retirar permissões desnecessárias e testar recursos embutidos; acrescentar HSTS somente em implantação HTTPS correta. |
| **P2 — prompt injection e arquivos** | A detecção de instruções hostis em documentos é heurística e não cobre instruções indiretas/obfuscadas. A Ata já limita tamanho, entradas, razão de compressão e caminhos; OCR/ingestão pode consumir CPU/memória. | Manter documentos como dados não confiáveis, sem ferramentas/segredos; criar corpus adversarial de prompt injection. Executar parsing/OCR em worker isolado com limites de CPU, RAM, tempo, páginas e fila durável; considerar antivírus quando adequado. |
| **P2 — sessão e operação** | Sessão deslizante configurada em 480 minutos e tarefas de OCR/embedding/análise dependem parcialmente de execução em background. | Considerar limite absoluto de sessão, rotação/revogação e reautenticação para ações sensíveis. Migrar jobs para fila persistente, idempotente, recuperável e com estado observável. |
| **P2 — correção de qualidade do repositório** | Um teste completo mantém expectativa `num_ctx` antiga (`8192` contra configuração atual `12288`). | Alinhar teste e configuração a uma fonte única de verdade; evitar regressão na configuração de consulta. |

### SQL injection: evidência e limite

Os dois testes novos são regressões de defesa em profundidade no banco de teste em memória, não tentativas contra a VM. Um teste verifica que uma string com sintaxe de SQL não autentica um usuário; o outro verifica que a pergunta maliciosa continua sendo dado e que a tabela `usuarios` permanece disponível. A análise estática não encontrou concatenação óbvia de entrada do usuário em SQL nas rotas examinadas. Repetir testes específicos quando houver nova query, migração, filtro dinâmico ou mudança de driver; considerar também autorização por objeto (IDOR/BOLA), CSRF, XSS, path traversal e carga de upload no próximo ciclo.

## Referências internas e externas

- [Base funcional e limites de A1/A2/TAB](../arquitetura/BASE_FUNCIONAL.md)
- [Análise documental V2](../arquitetura/ANALISE_DOCUMENTAL_V2.md)
- [Endurecimento existente](../arquitetura/ENDURECIMENTO.md)
- [Termos Gemini API](https://ai.google.dev/gemini-api/terms?hl=pt-br)
- [Preços e níveis Gemini API](https://ai.google.dev/gemini-api/docs/pricing)
- [Advisory python-jose PYSEC-2026-4298](https://osv.dev/vulnerability/PYSEC-2026-4298)
- [Advisory ecdsa PYSEC-2026-1325](https://osv.dev/vulnerability/PYSEC-2026-1325)
