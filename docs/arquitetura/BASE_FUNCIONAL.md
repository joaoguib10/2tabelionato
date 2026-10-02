# Base funcional consolidada — etapas 1 e 2

Referência: orientações do responsável até 07/09/2026. Este documento consolida o escopo autorizado; não declara implementados os módulos futuros nem substitui homologação do tabelião.

**Atualização de 08/09/2026:** existem somente os perfis ADMIN e USUARIO. Todos podem criar e trabalhar em casos próprios ou atribuídos; o ADMIN vê e edita todos e atribui responsáveis. Gestão do corpus, contas, Revisões e Novos Entendimentos continua exclusiva do ADMIN. A2 assistido, A1 versionado e TAB humano estão disponíveis para o piloto.

## Precedência e fontes

- A1-CORE v2, A1-FONTES v1.0, A1-M v0.8 e A1-O v0.4: análise, governança de fontes e incerteza.
- A2-M MHT-H v1.0 e A2-O v0.2: organização factual; A2-O é protótipo, não tratar todos os estados históricos como especificação definitiva.
- TAB-M v0.6 e TAB-O v0.2: decisão humana, alcance e reutilização controlada. CNR histórico não é módulo paralelo novo.
- A3/S0 nos documentos arquiteturais e parecer do DPO: minimização, segregação, pseudonimização, recomposição controlada e retenção.
- Pareceres técnicos da pasta 05_PARECER_TECNICO: extrair requisitos de privacidade e validação; não migrar a interface para Open WebUI.
- Mudanças expressas: Tesseract local autorizado; Análise substitui evolução de Minutas; Ata Notarial entra no escopo futuro; gestão somente ADMIN; recuperação local auditada.

A comparação integral de todas as versões históricas ainda precisa ser concluída antes de congelar os contratos jurídicos de Análise. Não há alegação de leitura integral de todo o acervo histórico nesta entrega. Conflitos não resolvidos serão submetidos ao responsável, sem preenchimento por suposição.

## Matriz de responsabilidades

| Ação | ADMIN | USUARIO |
|---|---|---|
| Consulta e feedback próprios | Sim | Sim |
| Ler documentos institucionais disponíveis | Sim | Sim |
| Cadastrar, editar, aprovar, reprocessar ou excluir documentos | Sim | Não |
| Gerenciar contas e recuperar contas não ADMIN | Sim, após 2FA | Não |
| Recuperar acesso ADMIN | Procedimento local no servidor | Não |
| Ver histórico de outras contas, excluir histórico | Sim | Não |
| Gerenciar revisões e publicar entendimentos | Sim | Não |
| Confirmar leitura de novos casos publicados | Futuro | Futuro, apenas própria confirmação |
| Criar e trabalhar em casos da Análise | Todos os casos; atribui responsáveis | Casos próprios ou atribuídos |
| Ata Notarial | Futuro | Futuro |

Competência notarial continua sendo uma responsabilidade humana; o perfil ADMIN não torna uma conclusão juridicamente válida por si só.

## Contratos funcionais por camada

| Camada | Entrada | Saída | Validação / responsável | Reaproveitamento / pendência |
|---|---|---|---|---|
| A3 | Documento ou mídia do caso | Conteúdo mínimo autorizado, acesso e retenção definidos | Responsável pelo caso e política institucional; bloquear entrada inadequada | Autenticação, minimização e isolamento por caso existentes |
| A2 | Evidências extraídas | Fatos, relações, divergências e pendências com origem | Usuário responsável confere valor, trecho, método e incerteza | Extração estruturada disponível; versionamento/delta futuro |
| A1 | Fatos conferidos e base aprovada | Regras, requisitos, exceções, fundamentos contrários, alertas e fontes | Não concluir além da evidência; ADMIN confere | Versão do caso, busca híbrida e snapshots implementados; homologação jurídica pendente |
| TAB | Análise e decisão do responsável | Decisão identificada, datada, fundamentada, com escopo e versão | Somente ADMIN decide; IA não aprova | Registro append-only por caso implementado; generalização continua manual |
| Histórico | Versões e alterações | Evolução conferível e impacto das mudanças | Não sobrescrever silenciosamente | Histórico de consultas existente; continuidade de caso futura |

Documentos particulares não entram automaticamente no RAG institucional. Documentos A1/A2/TAB/A3 não serão anexados como se fossem normas: seus requisitos viram validações, contratos, permissões e testes.

Fatos: separar ENCONTRADO/AUSENTE/INCERTO/CONFLITANTE de conferência PENDENTE/CONFIRMADO/CORRIGIDO. Conservar o valor identificado antes da correção humana.
Caso proposto: preparação → conferência → análise → decisão; novos documentos geram nova versão e apontam conclusões afetadas. Estes estados aguardam consolidação específica, não criam tabelas nesta entrega.

## Ata Notarial — primeira versão

- ZIP/RAR de 1 GB ou mais: streaming para área temporária restrita, limite por tamanho descompactado e quantidade de entradas, prevenção de traversal e bomba de descompactação. Não carregar tudo em memória.
- Texto justificado e mensagens em sequência contínua, preservando ordem da exportação, horários, remetentes e ambiguidades.
- Áudio transcrito localmente com duração; passagens inaudíveis explícitas; não corrigir silenciosamente fala ou mensagens.
- Sem inclusão de imagens no primeiro resultado. Detectar anexos e ausência deles sem inventar conteúdo. A extensão sozinha não valida o tipo real do arquivo.
- Conclusão humana e entrega verificada antecedem descarte dos temporários. Falhas não apagam material ainda necessário ao trabalho.
- O resultado e os arquivos são temporários e são apagados quando o usuário confirma **Concluir e apagar**. Trabalhos abandonados ainda exigem uma política automática de expiração futura.
- Hash verifica integridade desde o recebimento, não autentica a conversa ou seus participantes.

## Entendimentos e avaliação

ADMIN insere/revisa/publica; demais usuários consultam, avaliam e futuramente confirmam leitura. Fontes predefinidas passam pela mesma revisão manual; nada é importado ou aprovado automaticamente.
Feedback não treina o modelo: casos úteis e não úteis podem ser selecionados, anonimizados e revisados para avaliação estável. Decisão específica não vira entendimento geral sem ação e aprovação explícitas.

## Próximas prioridades

1. Validar primeiro acesso e recuperação do ADMIN (senha + TOTP).
2. Pequena amostra documental revisada, diagnóstico e OCR local.
3. Homologar casos/Análise com A2, conferência, A1, TAB e A3 transversal.
4. Instalar e homologar o suporte local de RAR, Whisper e FFprobe para a Ata Notarial.
5. Homologar fontes, qualidade jurídica, segurança contra instruções adversárias, ausência de egress, retenção, restauração e desempenho.

Não criar decisão automática, não promover casos particulares a entendimentos gerais e não migrar framework ou banco sem novo recorte aprovado.
