# Referência de capacidade da Consulta com Gemini — 18/11/2026

## Ambiente e método

- Máquina de desenvolvimento: Windows 11, Intel Core i7-12700H (20 processadores lógicos), 16 GiB de RAM. Banco PostgreSQL no Docker Desktop; backend Python executado no Windows.
- VM do cartório, conforme [última inspeção documentada em 20/10/2026](AMBIENTE_VM.md): Rocky Linux 9.8, 6 vCPUs de Xeon E5-2609 v3 a 1,90 GHz, 11 GiB de RAM e disco de 20 GB quase cheio. Essas especificações não foram verificadas novamente nesta medição.
- Uma pergunta geral sintética, sem dados pessoais, enviada à camada `ENTENDIMENTO` do Gemini File Search. Havia uma fonte aprovada e indexada. O teste chamou o serviço diretamente, sem interface, autenticação HTTP ou gravação no histórico de consultas.
- Comando executado dentro de `backend`: `python -m scripts.benchmark_consulta_gemini --concurrency N`, com `N=1` e depois `N=5`. O script registra apenas tempo, erro técnico e presença de citação; não imprime perguntas, respostas nem conteúdo da fonte.

## Resultado local

| Chamadas simultâneas | Duração total | Mediana por chamada | Maior duração | Resultado |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6,23 s | 6,22 s | 6,22 s | 1 com citação |
| 5 | 9,05 s | 7,58 s | 9,03 s | 4 com citação, 1 sem citação |

Não ocorreu erro de API no lote medido. A resposta sem citação não atende à exigência de evidência do produto; a causa não foi isolada neste ensaio. Esta amostra pequena não permite estimar percentil 95, disponibilidade contínua ou consumo diário.

## Interpretação e validação restante

Limitar Docker ou o processo a seis CPUs e 11 GiB de RAM pode aproximar uma restrição de recursos, mas não reproduz a velocidade do Xeon antigo, o disco quase cheio, o hipervisor nem a rota de rede do cartório até o Google. O Docker Desktop desta máquina tem aproximadamente 8 GiB de memória disponíveis, abaixo da RAM registrada na VM. Uma simulação local, portanto, não substitui a medição no ambiente de destino.

Na VM, depois de implantar o piloto sem inferência Ollama, repetir o script com `N=1` e `N=5` e medir também o fluxo completo pela interface. Registrar tempos, uso de CPU/RAM, espaço em disco, erros de cota e proporção de respostas com citações, sem conteúdo de usuários nos logs. O teste local acima é a referência para essa comparação.
