# Prisma — pós-formatação do Windows 11

App em Python (PySide6) com visual *liquid glass* preto e branco que faz o debloat,
a otimização, instala os drivers que faltam, remove apps inúteis (incluindo o Microsoft Edge)
e instala Brave, Steam, Discord, WhatsApp e Claude.

## Download

**[Baixar o Prisma.exe (última versão)](https://github.com/renatonack/prisma-windows/releases/latest)**

O `.exe` é independente: não precisa instalar Python.

## Depois de formatar

1. Conecte na internet e baixe o `Prisma.exe` pelo link acima.
2. Abra o `Prisma.exe` e aceite o aviso de administrador.
   - Se aparecer "O Windows protegeu o computador": **Mais informações → Executar assim mesmo**
     (o app não tem assinatura digital paga).
3. Escolha:
   - **Aplicar recomendações do vídeo** — exatamente o que o vídeo ativa.
   - **Fazer tudo** — vídeo + drivers + tudo o que estiver marcado nas páginas (instala os apps antes de remover o Edge).
4. Reinicie o PC no final.

Quer só ver o que aconteceria? Rode `Prisma.exe --dry-run` (modo simulação, não altera nada).
O registro de cada execução fica em `%LOCALAPPDATA%\Prisma\logs`.

## Drivers

A página **Drivers** mostra a placa de vídeo detectada e os dispositivos com problema, e tem duas tarefas:

- **Instalar todos os drivers que faltam** — procura no Windows Update (fonte oficial da Microsoft) os drivers
  deste PC, baixa e instala um por um e, no fim, lista se algum dispositivo ficou sem driver.
- **Driver mais novo da placa de vídeo** — detecta NVIDIA, AMD ou Intel, baixa o app oficial da fabricante
  (NVIDIA App, AMD Software: Adrenalin Edition ou Intel Driver & Support Assistant) direto do site dela,
  confere a assinatura digital e abre o instalador. Roda por último; é só seguir os passos na tela.
  Se o download falhar, abre a página oficial de drivers da fabricante.

## O que o botão do vídeo faz

Baseado em [“Windows 11 lento? Como fazer DEBLOAT” (Canaltech)](https://youtu.be/BQjZOr1Nye4),
que usa o **WinUtil (Chris Titus Tech)** e o **O&O ShutUp10**. O Prisma aplica os mesmos itens
direto no registro, sem baixar ferramentas de terceiros:

- **Segurança:** ponto de restauração antes de tudo.
- **Essenciais:** recursos de consumidor, telemetria, histórico de atividades e da área de transferência,
  descoberta automática de pastas, Game DVR, localização, telemetria do PowerShell 7,
  "Finalizar tarefa" no botão direito, serviços em modo manual. (Hibernação fica como está, igual no vídeo.)
- **Avançados:** debloat do Edge, apps da Store em segundo plano, otimizações de tela cheia, Copilot/Recall,
  notificações do Windows, Início e Galeria do Explorador, efeitos visuais para desempenho,
  menu clássico do botão direito.
- **Preferências:** tema escuro, sem Bing na pesquisa, NumLock ligado, mensagens detalhadas,
  sem recomendações no Iniciar, sem teclas de aderência, sem pesquisa na barra, barra à esquerda,
  sem Widgets, tela azul detalhada, sem "continuar em outro dispositivo".
- **Windows Update:** modo "Segurança" (recursos adiados 1 ano, segurança 4 dias, sem reinício automático).
- **O&O ShutUp10:** permissões de apps, tela de bloqueio, anúncios, pesquisa, Meet Now/Pessoas/Phone Link,
  sincronização, bloqueios do sistema.
- **Limpeza:** arquivos temporários e Limpeza de Disco.
- **Edge:** removido de verdade (o vídeo desativa e torna desinstalável).

### Diferenças em relação ao vídeo (de propósito)

Para não quebrar os apps que você vai instalar:

| No vídeo | No Prisma | Por quê |
|---|---|---|
| Desliga **todas** as notificações | Desliga só as do Windows (dicas, sugestões) | WhatsApp e Discord continuariam mudos. A opção "todas" existe, desmarcada. |
| Bloqueia câmera e microfone para apps | Mantém liberados | Chamadas no WhatsApp/Discord. |
| Bloqueia apps em segundo plano | Bloqueia, com exceção do WhatsApp e da Store | Senão o WhatsApp não recebe mensagens fechado. |
| Modo Segurança do Update bloqueia drivers | Drivers continuam vindo | PC recém-formatado precisa deles. |
| Desliga o indicador de conexão (NCSI) | Não mexe | Faz o Windows achar que está sem internet. |

O WebView2 nunca é removido (WhatsApp e outros apps dependem dele). Se não houver nenhum outro
navegador instalado, o Edge não é removido — o Prisma instala o Brave antes.

## Desenvolvimento

```powershell
python -m venv .venv
.\.venv\Scripts\pip install PySide6-Essentials pyinstaller
.\.venv\Scripts\python Prisma.py --dry-run     # roda sem alterar nada
powershell -ExecutionPolicy Bypass -File build.ps1   # gera dist\Prisma.exe
```

- `prisma/tasks.py` — todas as tarefas (scripts PowerShell) e o que faz parte do vídeo.
- `prisma/runner.py` — executa as tarefas em segundo plano e transmite a saída.
- `prisma/hardware.py` — detecta placa de vídeo e dispositivos sem driver (só leitura).
- `prisma/glass.py` — o visual liquid glass (fundo, vidro, botões, interruptores).
- `prisma/ui.py` — janela, páginas, painel de registro e diálogos.
