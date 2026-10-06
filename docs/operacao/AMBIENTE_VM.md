# Ambiente da VM do Tabeleão

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
