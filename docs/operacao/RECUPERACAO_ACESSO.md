# Acesso e recuperação local — Tabeleão

## Primeiro acesso após a atualização

1. Abra http://localhost:3000/login no servidor.
2. Entre com seu login e PIN anterior. Ele permite apenas iniciar a configuração.
3. Escolha uma senha diferente, com pelo menos 5 caracteres, contendo letras e números (máximo 72 bytes UTF-8).
4. No autenticador, adicione uma conta manualmente: nome Tabeleão, chave mostrada na tela, baseada em tempo (TOTP), SHA1, seis dígitos e intervalo de 30 segundos.
5. Digite o código gerado. Celular e servidor precisam estar com o horário correto; a geração dos códigos não depende de internet.
6. Guarde os dez códigos de recuperação em local protegido, separado do computador e do autenticador. Eles são mostrados somente uma vez. Não envie capturas de tela deles.
7. Confirme que guardou os códigos e entre no sistema.

A chave manual substitui a necessidade de QR nesta primeira versão. Nenhum segredo é enviado a um gerador de QR externo.

## Acesso diário

Login e senha → código do autenticador → Consulta. Aguarde o próximo código se acabou de usá-lo no cadastro: o mesmo intervalo não pode ser reutilizado. Cada autenticação completa invalida as sessões anteriores dessa conta. Contas não devem ser compartilhadas.

## Perdi somente o autenticador

Após entrar com a senha, marque **Perdi o autenticador** e informe um código de recuperação.
O sistema revoga o autenticador e todos os códigos antigos, exige cadastrar um novo e fornece nova lista. Não concede acesso pleno antes desse cadastro.

## Usuário perdeu senha ou foi bloqueado

O ADMIN autenticado acessa Configurações → Usuários → redefinição de senha.
Essa ação define uma senha temporária e invalida sessões, autenticador e códigos anteriores.
O usuário entra com a senha temporária, escolhe outra e cadastra seu autenticador.
A identidade do solicitante deve ser conferida pelo responsável antes da redefinição.

## ADMIN perdeu senha, autenticador ou todos os códigos

É necessário acesso autorizado ao sistema operacional do servidor. Não há recuperação pública pelo Swagger, e o comando não deve ser exposto por API.

No PowerShell, execute:

```powershell
Set-Location 'C:\Users\joaog\Projetos\cartorio-ai\backend'
.\.venv\Scripts\python.exe -m scripts.recover_account
```

Informe o login, a senha temporária duas vezes (não aparece na tela) e a confirmação `RECUPERAR`.
Não passe senhas por argumentos, não grave a sessão de terminal e não compartilhe o `.env`.
Em Linux, a entrada equivalente será `.venv/bin/python -m scripts.recover_account`, no diretório backend do servidor.

Depois abra o login, use a senha temporária e conclua o cadastramento de nova senha e novo autenticador.
Contas inativas não são reativadas por esse comando. Uma recuperação não altera perfil, documentos ou histórico.

A auditoria registra conta, ação e horário; recuperação local é identificada como `RECUPERACAO_SERVIDOR`, sem inventar identidade do operador do sistema operacional. Restrinja acesso ao servidor e registre externamente quem executou a intervenção.

## Limites e segurança operacional

- Cinco tentativas por padrão, configuráveis por MAX_LOGIN_ATTEMPTS; falhas de 2FA não são zeradas ao repetir uma senha correta.
- Não há desbloqueio automático: use recuperação administrativa/local quando atingir o limite.
- Cadastro e desafios expiram em cinco minutos. Se expirar, volte ao início.
- Chaves TOTP são criptografadas; a chave de criptografia é derivada com separação de domínio de TABELEAO_SECRET_KEY. Códigos de recuperação têm apenas hashes no banco.
- Preserve o segredo de implantação em backup protegido separado do banco. Alterá-lo invalida JWTs e impede ler segredos TOTP anteriores; nesse caso será necessário recuperar as contas e cadastrar novamente o 2FA.
- Senha antiga não é recuperável: sempre redefinida.
- Use HTTPS para acesso pela rede interna antes de uso com dados reais; HTTP localhost é destinado ao desenvolvimento no próprio servidor. TOTP não protege contra phishing em tempo real.
- O autenticador pode ter sincronização em nuvem própria: escolha/configure conforme a política do tabelionato. O servidor não depende dela.
- Não há e-mail, SMS, IA externa ou chamada remota no fluxo de autenticação.
- Swagger não é mecanismo de recuperação nem substitui o segundo fator. Tokens completos só são emitidos após confirmação do 2FA.

## Aplicação e retorno de versão

Antes de atualizar: backup de código, banco, uploads e segredos protegidos; valide restauração em banco isolado.
Execute `python -m alembic upgrade head` no backend. A migração preserva contas e hashes antigos, mas exige novo cadastramento e invalida tokens antigos.
Para retorno completo à versão anterior, restaure em conjunto o código, banco e configuração correspondentes ao backup. Não aplique downgrade isolado mantendo código novo em execução.
