# Ambiente da VM do Tabeleão

## Retrato atual — 20/10/2026

Inspeção somente de leitura para investigar lentidão e confirmar as especificações visíveis no sistema convidado. Este registro não representa a configuração do host KVM. Nenhum serviço foi reiniciado, nenhuma configuração foi alterada, nenhum modelo foi baixado e nenhum documento foi removido durante a inspeção.

### Recursos detectados

- Sistema: Rocky Linux 9.8; arquitetura x86_64.
- CPU: **6 vCPUs**, Intel Xeon E5-2609 v3 a 1,90 GHz. O retrato anterior de 06/10 indicava 4 vCPUs; a contagem atual é a observada em 20/10.
- Memória: 11 GiB de RAM; cerca de 8,3 GiB disponíveis no instante ocioso consultado. Swap de 2 GiB, sem uso durante a verificação.
- Disco: `/dev/sda` continua com **20 GB**. A raiz XFS tem 17 GB, aproximadamente 16 GB usados e cerca de 1,1 GB livres (95%). A ampliação esperada para 50 GB ainda não está visível no Rocky Linux.
- Não foi detectada inferência por GPU: o Ollama identificou o backend `cpu` e `/api/ps` informou `size_vram=0`. `nvidia-smi` não está instalado.

### Modelos e parâmetros observados

- Modelos presentes: `qwen3:1.7b` (consulta), `qwen3:8b` (geração geral), `qwen3-vl:2b` (visão) e `nomic-embed-text-v2-moe` (embeddings).
- Configuração efetiva do backend para consulta: contexto de 8.192 tokens, saída máxima de 900 tokens, timeout de 900 segundos e `keep_alive=30m` por chamada.
- Ambiente registrado na inicialização do Ollama: `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1` e `OLLAMA_MAX_QUEUE=512`. A fila grande não representa capacidade de processamento paralelo: a inferência local está limitada a uma geração paralela.
- O backend usa `stream=false` na chamada de geração, portanto a resposta chega ao usuário após a conclusão, sem tokens incrementais da inferência.

### Verificação sintética de desempenho

Foi enviada diretamente ao Ollama uma solicitação sintética curta (“Responda apenas: OK”), sem documento, dado de usuário ou gravação de consulta. A entrada tinha 22 tokens e a saída, 2 tokens:

| Estado do modelo | Tempo total | Carga do modelo | Avaliação do prompt | Geração |
| --- | ---: | ---: | ---: | ---: |
| Primeira chamada | 18,12 s | 11,08 s | 3,39 s | 3,65 s |
| Chamada aquecida | 4,26 s | 0,01 s | 2,00 s | 2,24 s |

A geração aquecida observada foi de aproximadamente 0,89 token/s. Extrapolar linearmente essa medição para 900 tokens dá cerca de 16 min e 48 s, antes do custo de avaliar um prompt real e os trechos recuperados. É uma indicação aproximada baseada em uma prova muito curta, não uma previsão garantida; ainda assim, ajuda a explicar o timeout. O journal do backend registra timeout da Ollama após 900 segundos em 20/10/2026 às 10:53:29.

Esses números não são um teste de carga de 5–6 usuários. O serviço do Ollama estava configurado para uma inferência paralela, então consultas simultâneas podem esperar em fila. O planejamento de capacidade e privacidade para esse grupo está em [Replanejamento da IA híbrida](../planejamento/PLANO_IA_HIBRIDA_VM_PRIVACIDADE_CAPACIDADE_2026-10-20.md).

### Serviços e versão do código

- Nginx, `tabeleao-backend`, `tabeleao-frontend`, Ollama e Docker estavam ativos.
- Backend local respondeu `{"status":"ok"}` em `/health`; `/ready` respondeu `ready`, com o banco online.
- A VM estava no commit `eb91e14`; o `master` do GitHub estava em `ee04871`, um commit à frente. A diferença observada continha apenas documentação e um teste de segurança, sem alterações na aplicação.
- O sistema respondeu na rede local em `http://192.168.1.18`. Essa verificação não comprova acesso público pela internet.

### Impacto e próximos passos

O disco quase cheio é um risco operacional e pode dificultar atualizações e armazenamento, mas a inspeção não mostrou uso de swap ou espera significativa de I/O. Expandir o disco pode dar espaço para dados, logs e modelos, mas não acrescenta CPU, RAM, VRAM nem velocidade de geração. Antes de crescer partições, confirme que o host apresenta o novo tamanho em `lsblk`, faça backup/snapshot e só então expanda a partição, o volume físico, o volume lógico e o XFS.

O relatório abaixo é o retrato histórico de 06/10/2026; diferenças para a medição mais recente devem ser interpretadas conforme as datas.

## Retrato histórico — 06/10/2026

Registro de diagnóstico feito em 06/10/2026 para apoiar a revisão das especificações da VM. Este documento descreve o que o sistema convidado detectou; não representa uma configuração do host KVM.

## Sistema operacional e virtualização

- Sistema: Rocky Linux 9.8 (Blue Onyx), família Enterprise Linux 9.
- Arquitetura: x86_64.
- Kernel: `5.14.0-687.10.1.el9_8.0.1.x86_64`.
- Virtualização detectada: QEMU/KVM.

## Recursos detectados pelo Rocky Linux

- CPU: 4 vCPUs; `possible`, `present` e `online` são `0-3`. Topologia vista pelo sistema: 1 socket, 4 cores e 1 thread por core.
- Memória: 11 GiB de RAM e 2 GiB de swap.
- Disco: `/dev/sda` com 20 GiB no total.
  - `/dev/sda1`: 1 GiB, XFS, montado em `/boot`.
  - `/dev/sda2`: aproximadamente 19 GiB, usado como volume físico LVM.
  - Volume lógico `rlm-root`: 17 GiB, XFS, montado em `/`.
  - Volume lógico `rlm-swap`: 2 GiB.
- Na verificação, `/` estava com 95% de uso, aproximadamente 1 GiB livre. O grupo LVM não tinha extents livres.
- A nova varredura de dispositivos não mostrou outro disco nem capacidade além dos 20 GiB de `/dev/sda`.

## Divergência a verificar no host

O administrador informou que foram incluídos 8 núcleos e mais 4 GB de disco. No diagnóstico do Rocky Linux, porém, continuam visíveis apenas 4 vCPUs e um disco de 20 GiB. As CPUs adicionais não aparecem nem como CPUs offline. O aumento de disco também não aparece no dispositivo virtual.

A alteração precisa ser conferida na configuração da VM no host/painel QEMU/KVM. Se os valores já foram alterados enquanto a VM estava ligada, faça um desligamento completo e uma nova inicialização pelo hipervisor; reiniciar somente o Rocky Linux pode manter a configuração de hardware apresentada pelo processo QEMU em execução. Depois, confira novamente `nproc`, `/sys/devices/system/cpu/{possible,present,online}` e `lsblk`.

Quando o host apresentar um disco maior, ainda será necessário ampliar a partição LVM, o volume físico, o volume lógico raiz e o sistema de arquivos XFS. Faça backup/snapshot antes dessa operação. Não execute a expansão até a capacidade nova ser visível em `lsblk`.

## Serviços observados

Após o reboot de 06/10/2026, estavam ativos `docker`, `nginx`, `ollama`, `tabeleao-backend` e `tabeleao-frontend`. O container `cartorio-ai-postgres` também estava em execução. O checkout do sistema fica em `/opt/tabeleao`.

O arquivo local `whisper/base.pt` (cerca de 139 MiB) não é versionado no Git e foi preservado na VM. Não armazene credenciais, conteúdo de `.env`, documentos do cartório ou dados pessoais neste registro.
