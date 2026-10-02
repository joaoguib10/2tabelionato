# Checkpoint — especialização da Análise em Compra e Venda

Atualizado em 09/09/2026. Este arquivo registra o ponto exato de continuidade. Não declara concluído o fluxo ainda em desenvolvimento e não substitui validação jurídica humana.

## Regras preservadas

- A2 organiza dados e propõe fatos com origem verificável; nenhuma sugestão da IA é confirmada automaticamente.
- A1 cruza o estado factual conferido com fontes institucionais elegíveis; classificação documental é contexto, não prova.
- TAB continua sendo decisão exclusivamente humana, registrada pelo ADMIN.
- Documentos do caso permanecem privados e não entram no corpus jurídico.
- A Consulta usa documentos e entendimentos processados, ativos, aprovados e publicados. Resposta administrativa de uma Revisão somente entra nessa base quando o ADMIN a generaliza e publica como Novo Entendimento; isso não treina os pesos do modelo.

## Escopo funcional aprovado

- Nesta etapa, novos casos de Análise aceitam somente `COMPRA_VENDA`.
- Documentos devem poder ser identificados como RG/CNH, certidão de casamento, certidão de nascimento, matrícula, contrato social, procuração ou outro tipo já suportado.
- A extração deve sugerir, com fonte e conferência: partes, CPF, estado civil, união estável, endereço, profissão, dados do casamento, empresa, procuração e representação por alvará judicial.
- Endereço e profissão podem permanecer pendentes e ser preenchidos manualmente; a pendência deve ficar visível, mas não impedir a análise.
- Deve haver várias partes e inclusão manual, distinguindo principal, cônjuge, anuente, representante e procurador.
- A qualificação deve contemplar indivíduo, união estável, casal assinando, cônjuge anuente, somente um cônjuge assinando, empresa representada e procuração.
- Os papéis estruturais são outorgante/outorgado. Procuração e alvará podem registrar poderes e limites mínimo/máximo; o sistema apenas compara esses limites com o valor informado e mantém a decisão no TAB humano.
- O negócio registra valor e forma de pagamento para conferência.
- A matrícula deve apresentar R./Av. em ordem e gerar a descrição pelo endereço resumido somente quando logradouro, número, bairro e cidade estiverem todos presentes; faltando qualquer item, usar a descrição completa da especialidade objetiva.

## Concluído neste recorte

- Causa do erro de login identificada: Docker Desktop/PostgreSQL estavam indisponíveis. Docker e o contêiner PostgreSQL foram iniciados; banco, API e único usuário ADMIN foram validados sem expor credenciais.
- Login passou a tratar respostas não JSON e indisponibilidade do banco com mensagem pública compreensível.
- Backend ganhou tratamento JSON genérico para indisponibilidade do PostgreSQL, sem expor exceção interna.
- Categorias específicas de documentos de compra e venda foram adicionadas aos schemas.
- Schemas iniciais de partes, casamento, empresa, procuração, averbações e imóvel foram preparados.
- O prompt A2 especializado de Compra e Venda foi criado, versionado e conectado ao serviço local.
- Campos JSON de estado estruturado foram adicionados ao modelo `Caso`.
- Migração `e64b1c3f9a20` foi criada e aplicada ao banco local.
- Serviço estruturado percorre somente documentos privados processados e liberados, em lotes controlados e idempotentes por hash.
- Sugestões sem trecho literal verificável são descartadas; nenhum dado do caso é incluído em `Documento` ou `DocumentoChunk`.
- A mesclagem preenche lacunas e não substitui uma parte ou imóvel já confirmado pelo usuário.
- APIs de leitura, salvamento e extração foram adicionadas com as mesmas regras de acesso do caso e validação de que fontes pertencem ao próprio caso.
- O estado estruturado integra o snapshot versionado do A1 sem incluir diagnósticos técnicos; pendências permanecem explícitas e não equivalem a decisão.
- A interface agora permite várias partes, associação à parte principal, qualificação, casamento, empresa, procuração, imóvel, R./Av., inclusão manual e conferência.
- Profissão, endereço e outras lacunas são destacadas como pendências sem impedir a continuidade do fluxo.
- O gate aceita o estado estruturado como base factual quando partes e imóvel foram explicitamente confirmados; campos ausentes continuam registrados como pendências e não bloqueiam o A1.
- A descrição resumida do imóvel só é formada quando logradouro, número, bairro e cidade estão completos; caso contrário, usa a descrição integral.
- Novos casos exibem somente o ato Compra e Venda e a classificação documental ganhou as opções específicas previstas.
- A área de documentos passou a ser o primeiro bloco do caso aberto; PDFs suspeitos podem receber OCR integral por solicitação explícita.
- A nomenclatura interna e visível usa outorgante/outorgado, preservando compatibilidade de leitura com registros antigos.

## Ainda não implementado / depende de homologação

- Homologação jurídica dos textos de qualificação para todos os arranjos conjugais, representação societária e procuração.
- Validação com certidões e matrículas sintéticas ou expressamente autorizadas, incluindo documentos extensos e OCR.
- Critérios documentados para capacidade, anuência, comunhão de bens, validade documental e averbações; A1/A2/TAB não devem inventá-los.
- Calibração da extração local para separar corretamente várias partes e associar cônjuges quando a ordem do documento for ambígua.
- Ampliação para Doação e demais atos somente após a homologação de Compra e Venda.

## Ponto exato para retomar

1. Homologar manualmente o painel com um caso sintético completo e corrigir somente divergências comprovadas.
2. Revisar juridicamente cada texto de qualificação e fornecer a redação aprovada para os casos ambíguos.
3. Reprocessar uma amostra autorizada com OCR e medir campos corretos, ausentes e incorretos.
4. Validar A1 contra fontes institucionais aprovadas e registrar a decisão exclusivamente humana no TAB.
5. Só então congelar o contrato de Compra e Venda e planejar Doação.

Verificação deste recorte: suíte integral do backend aprovada; lint e build do frontend aprovados. Nenhum backup ou commit foi criado.
