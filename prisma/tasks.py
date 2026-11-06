"""Catálogo de tarefas do Prisma.

Cada tarefa é um script PowerShell independente. O prelúdio (PRELUDE) é colado
antes de cada script e traz as funções auxiliares (Set-Reg, Remove-App, etc.).

A lista "do vídeo" segue o que o Canaltech marca no WinUtil (Chris Titus Tech) e
no O&O ShutUp10 no vídeo https://youtu.be/BQjZOr1Nye4 — com quatro adaptações
para não quebrar os apps que você vai instalar (WhatsApp/Discord):
  * notificações de apps continuam ligadas (só as do Windows são desligadas);
  * câmera, microfone e captura de tela continuam liberados para apps;
  * o Windows Update continua entregando drivers (PC recém-formatado precisa);
  * o indicador de conexão (NCSI) não é desligado (quebra o "sem internet").
"""
from __future__ import annotations

from dataclasses import dataclass

PAGE_DEBLOAT = "debloat"
PAGE_OTIMIZACAO = "otimizacao"
PAGE_DRIVERS = "drivers"
PAGE_REMOVER = "remover"
PAGE_INSTALAR = "instalar"


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    desc: str
    page: str
    section: str
    script: str
    order: int
    default: bool = True
    video: bool = False
    note: str = ""          # aviso exibido em destaque na linha
    glyph: str = ""         # letra/ícone (usado nos cards de apps)


# ---------------------------------------------------------------------------
# Prelúdio PowerShell
# ---------------------------------------------------------------------------
PRELUDE = r"""
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch {}
$OutputEncoding = New-Object System.Text.UTF8Encoding $false

function Say([string]$m)  { Write-Output "  $m" }
function Ok([string]$m)   { Write-Output "[ok] $m" }
function Warn([string]$m) { Write-Output "[aviso] $m" }
function Fail([string]$m) { Write-Output "[erro] $m" }

$script:RegOk = 0
$script:RegFail = 0
function Set-Reg {
    param([string]$Path, [string]$Name, $Value, [string]$Type = 'DWord', [switch]$Quiet)
    try {
        if (-not (Test-Path -LiteralPath $Path)) { New-Item -Path $Path -Force -ErrorAction Stop | Out-Null }
        New-ItemProperty -LiteralPath $Path -Name $Name -Value $Value -PropertyType $Type -Force -ErrorAction Stop | Out-Null
        $script:RegOk++
    } catch {
        $script:RegFail++
        if (-not $Quiet) { Warn ("Não foi possível gravar {0} ({1})" -f $Name, $_.Exception.Message) }
    }
}
function Reg-Done([string]$What) {
    if ($script:RegFail -eq 0) { Ok ("{0} ({1} valores)" -f $What, $script:RegOk) }
    else { Warn ("{0}: {1} aplicados, {2} não aplicados" -f $What, $script:RegOk, $script:RegFail) }
}

function Set-Svc([string]$Name, [string]$Start) {
    if (-not (Get-Service -Name $Name -ErrorAction SilentlyContinue)) { return $null }
    $map = @{ Manual = 'demand'; Disabled = 'disabled'; Automatic = 'auto'; Delayed = 'delayed-auto' }
    $null = & sc.exe config $Name start= $map[$Start] 2>&1
    return ($LASTEXITCODE -eq 0)
}

function Disable-Task([string]$Path, [string]$Name) {
    try { Disable-ScheduledTask -TaskPath $Path -TaskName $Name -ErrorAction Stop | Out-Null; return $true }
    catch { return $false }
}

$script:ProvCache = $null
function Remove-App([string[]]$Patterns) {
    if ($null -eq $script:ProvCache) { $script:ProvCache = @(Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue) }
    foreach ($p in $Patterns) {
        $found = $false
        foreach ($k in @(Get-AppxPackage -AllUsers -Name $p -ErrorAction SilentlyContinue)) {
            $found = $true
            try { Remove-AppxPackage -Package $k.PackageFullName -AllUsers -ErrorAction Stop; Ok ("Removido: {0}" -f $k.Name) }
            catch {
                try { Remove-AppxPackage -Package $k.PackageFullName -ErrorAction Stop; Ok ("Removido: {0}" -f $k.Name) }
                catch { Warn ("Não deu para remover {0}: {1}" -f $k.Name, ($_.Exception.Message -split "`n")[0]) }
            }
        }
        foreach ($v in @($script:ProvCache | Where-Object { $_.DisplayName -like $p })) {
            $found = $true
            try { Remove-AppxProvisionedPackage -Online -PackageName $v.PackageName -ErrorAction Stop | Out-Null; Say ("Não volta em novos usuários: {0}" -f $v.DisplayName) }
            catch { Warn ("Pacote base mantido: {0}" -f $v.DisplayName) }
        }
        if (-not $found) { Say ("Não está instalado: {0}" -f $p) }
    }
}

$script:UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

function Get-Page([string]$Url) {
    $req = [Net.HttpWebRequest]::Create($Url)
    $req.UserAgent = $script:UA
    $req.AutomaticDecompression = [Net.DecompressionMethods]'GZip, Deflate'
    $resp = $req.GetResponse()
    try { (New-Object IO.StreamReader($resp.GetResponseStream())).ReadToEnd() } finally { $resp.Close() }
}

function Download-File([string]$Url, [string]$OutFile, [string]$Referer = '') {
    New-Item -ItemType Directory -Force (Split-Path $OutFile) | Out-Null
    $req = [Net.HttpWebRequest]::Create($Url)
    $req.UserAgent = $script:UA
    if ($Referer) { $req.Referer = $Referer }
    $resp = $req.GetResponse()
    try {
        if ($resp.ContentType -like 'text/html*') { throw 'o site devolveu uma página em vez do instalador' }
        $in = $resp.GetResponseStream()
        $out = [IO.File]::Create($OutFile)
        try { $in.CopyTo($out) } finally { $out.Close(); $in.Close() }
    } finally { $resp.Close() }
}

# Abre um link no navegador do usuário (via Explorer, para o navegador não abrir como administrador)
function Open-Url([string]$Url) { Start-Process -FilePath 'explorer.exe' -ArgumentList $Url }

function Test-Signed([string]$File, [string]$Publisher) {
    $sig = Get-AuthenticodeSignature -FilePath $File
    if ($sig.Status -ne 'Valid' -or ($Publisher -and $sig.SignerCertificate.Subject -notmatch $Publisher)) {
        Remove-Item $File -Force -ErrorAction SilentlyContinue
        return $false
    }
    Say ("Assinatura digital OK ({0})" -f ($sig.SignerCertificate.Subject -split ',')[0])
    return $true
}

function Get-Winget {
    $cmd = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    Say 'winget não encontrado - tentando ativar o Instalador de Aplicativos...'
    try { Add-AppxPackage -RegisterByFamilyName -MainPackage Microsoft.DesktopAppInstaller_8wekyb3d8bbwe -ErrorAction Stop } catch {}
    $cmd = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $c = Get-ChildItem "$env:ProgramFiles\WindowsApps\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\winget.exe" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($c) { return $c.FullName }
    return $null
}

function Install-App {
    param([string]$Name, [string]$Id, [string]$Source = 'winget', [string]$Url = '',
          [string]$SilentArgs = '', [string]$Publisher = '', [string]$Page = '')
    $wg = Get-Winget
    if ($wg) {
        Say ("Instalando {0} pelo winget ({1})..." -f $Name, $Id)
        $wargs = @('install', '--id', $Id, '--exact', '--source', $Source, '--silent',
                   '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity')
        & $wg @wargs 2>&1 | ForEach-Object {
            $l = "$_".Trim()
            if ($l -and $l -notmatch '^[-\\|/ ]+$' -and $l -notmatch '[▀-▟]') { Say $l }
        }
        $code = $LASTEXITCODE
        if ($code -eq 0 -or $code -eq -1978335189 -or $code -eq -1978335135) { Ok ("{0} instalado" -f $Name); return }
        Warn ("winget terminou com código 0x{0:X8}" -f $code)
    }
    if ($Url) {
        try {
            $file = Join-Path (Join-Path $env:TEMP 'prisma-dl') (($Name -replace '\W', '') + '-setup.exe')
            Say ("Baixando {0} do site oficial..." -f $Name)
            Download-File $Url $file
            if (-not (Test-Signed $file $Publisher)) {
                Fail ("Assinatura digital de {0} não confere - instalador descartado." -f $Name)
                if ($Page) { Open-Url $Page }
                return
            }
            if ($SilentArgs) { $p = Start-Process -FilePath $file -ArgumentList $SilentArgs -Wait -PassThru }
            else { $p = Start-Process -FilePath $file -Wait -PassThru }
            if ($p.ExitCode -eq 0) { Ok ("{0} instalado" -f $Name) }
            else { Warn ("Instalador de {0} saiu com código {1}" -f $Name, $p.ExitCode) }
            return
        } catch {
            Fail ("Falha ao baixar {0}: {1}" -f $Name, $_.Exception.Message)
        }
    }
    if ($Page) {
        Open-Url $Page
        Warn ("Abri a página oficial do {0} para você instalar manualmente." -f $Name)
    }
}
"""

CDM = r"HKCU:\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
ADV = r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"

TASKS: list[Task] = []


def _add(**kw) -> None:
    TASKS.append(Task(**kw))


# ---------------------------------------------------------------------------
# DEBLOAT — Segurança
# ---------------------------------------------------------------------------
_add(
    id="restore_point", page=PAGE_DEBLOAT, section="Segurança", order=0, video=True,
    title="Criar ponto de restauração",
    desc="Feito antes de tudo. Se algo der errado, dá para voltar o Windows a este ponto.",
    script=r"""
Say 'Ativando a Proteção do Sistema no disco do Windows...'
try { Enable-ComputerRestore -Drive "$env:SystemDrive\" -ErrorAction Stop } catch { Warn ("Proteção do Sistema: {0}" -f $_.Exception.Message) }
Set-Reg 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore' 'SystemRestorePointCreationFrequency' 0 -Quiet
try {
    Checkpoint-Computer -Description 'Prisma - antes das otimizacoes' -RestorePointType 'MODIFY_SETTINGS' -ErrorAction Stop
    Ok 'Ponto de restauração criado'
} catch { Warn ("Não foi possível criar o ponto de restauração: {0}" -f $_.Exception.Message) }
""",
)

# ---------------------------------------------------------------------------
# DEBLOAT — Essenciais (WinUtil > Essential Tweaks)
# ---------------------------------------------------------------------------
_add(
    id="consumer_features", page=PAGE_DEBLOAT, section="Essenciais", order=10, video=True,
    title="Desligar recursos de consumidor",
    desc="O Windows para de instalar sozinho jogos, apps de terceiros e atalhos patrocinados.",
    script=rf"""
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableWindowsConsumerFeatures' 1
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableConsumerAccountStateContent' 1
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableCloudOptimizedContent' 1
foreach ($n in 'ContentDeliveryAllowed','OemPreInstalledAppsEnabled','PreInstalledAppsEnabled','PreInstalledAppsEverEnabled','SilentInstalledAppsEnabled','SoftLandingEnabled','FeatureManagementEnabled') {{
    Set-Reg '{CDM}' $n 0
}}
Reg-Done 'Recursos de consumidor desligados'
""",
)

_add(
    id="telemetry", page=PAGE_DEBLOAT, section="Essenciais", order=11, video=True,
    title="Desligar telemetria",
    desc="Corta o envio de dados de uso, diagnóstico e digitação para a Microsoft.",
    script=rf"""
$dc = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection'
Set-Reg $dc 'AllowTelemetry' 0
Set-Reg $dc 'MaxTelemetryAllowed' 0
Set-Reg $dc 'DoNotShowFeedbackNotifications' 1
Set-Reg $dc 'LimitDiagnosticLogCollection' 1
Set-Reg $dc 'DisableOneSettingsDownloads' 1
Set-Reg 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection' 'AllowTelemetry' 0
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Privacy' 'TailoredExperiencesWithDiagnosticDataEnabled' 0
Set-Reg 'HKCU:\Software\Policies\Microsoft\Windows\CloudContent' 'DisableTailoredExperiencesWithDiagnosticData' 1
Set-Reg 'HKCU:\Software\Microsoft\Siuf\Rules' 'NumberOfSIUFInPeriod' 0
Set-Reg 'HKCU:\Software\Microsoft\Input\TIPC' 'Enabled' 0
Set-Reg 'HKCU:\Software\Microsoft\InputPersonalization' 'RestrictImplicitInkCollection' 1
Set-Reg 'HKCU:\Software\Microsoft\InputPersonalization' 'RestrictImplicitTextCollection' 1
Set-Reg 'HKCU:\Software\Microsoft\InputPersonalization\TrainedDataStore' 'HarvestContacts' 0
Set-Reg 'HKCU:\Software\Microsoft\Personalization\Settings' 'AcceptedPrivacyPolicy' 0
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\AppCompat' 'AITEnable' 0
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\SQMClient\Windows' 'CEIPEnable' 0
Set-Reg 'HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting' 'Disabled' 1
Set-Reg '{ADV}' 'ShowSyncProviderNotifications' 0
Reg-Done 'Registro de telemetria'

$svc = 0
if (Set-Svc 'DiagTrack' 'Disabled') {{ $svc++ }}
if (Set-Svc 'dmwappushservice' 'Manual') {{ $svc++ }}
Stop-Service DiagTrack -Force -ErrorAction SilentlyContinue
Say ("Serviços de telemetria ajustados: {{0}}" -f $svc)

$tasks = @(
    @('\Microsoft\Windows\Application Experience\', 'Microsoft Compatibility Appraiser'),
    @('\Microsoft\Windows\Application Experience\', 'ProgramDataUpdater'),
    @('\Microsoft\Windows\Application Experience\', 'MareBackup'),
    @('\Microsoft\Windows\Autochk\', 'Proxy'),
    @('\Microsoft\Windows\Customer Experience Improvement Program\', 'Consolidator'),
    @('\Microsoft\Windows\Customer Experience Improvement Program\', 'UsbCeip'),
    @('\Microsoft\Windows\DiskDiagnostic\', 'Microsoft-Windows-DiskDiagnosticDataCollector'),
    @('\Microsoft\Windows\Feedback\Siuf\', 'DmClient'),
    @('\Microsoft\Windows\Feedback\Siuf\', 'DmClientOnScenarioDownload'),
    @('\Microsoft\Windows\Windows Error Reporting\', 'QueueReporting')
)
$n = 0
foreach ($t in $tasks) {{ if (Disable-Task $t[0] $t[1]) {{ $n++ }} }}
Ok ("Tarefas agendadas de telemetria desativadas: {{0}}" -f $n)
""",
)

_add(
    id="activity_history", page=PAGE_DEBLOAT, section="Essenciais", order=12, video=True,
    title="Desligar histórico de atividades",
    desc="O Windows deixa de registrar documentos, sites e apps que você usou.",
    script=r"""
$s = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System'
Set-Reg $s 'EnableActivityFeed' 0
Set-Reg $s 'PublishUserActivities' 0
Set-Reg $s 'UploadUserActivities' 0
Reg-Done 'Histórico de atividades desligado'
""",
)

_add(
    id="clipboard_history", page=PAGE_DEBLOAT, section="Essenciais", order=13, video=True,
    title="Desligar histórico da área de transferência",
    desc="Desativa o Win+V e a sincronização do Ctrl+C entre dispositivos. Copiar e colar normal continua.",
    script=r"""
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System' 'AllowClipboardHistory' 0
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System' 'AllowCrossDeviceClipboard' 0
Set-Reg 'HKCU:\Software\Microsoft\Clipboard' 'EnableClipboardHistory' 0
Reg-Done 'Histórico da área de transferência desligado'
""",
)

_add(
    id="folder_discovery", page=PAGE_DEBLOAT, section="Essenciais", order=14, video=True,
    title="Desligar descoberta automática de pastas",
    desc="O Explorador para de adivinhar o tipo de cada pasta (deixa de abrir pastas grandes devagar).",
    script=r"""
$shell = 'HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell'
Remove-Item -Path "$shell\Bags" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$shell\BagMRU" -Recurse -Force -ErrorAction SilentlyContinue
Set-Reg "$shell\Bags\AllFolders\Shell" 'FolderType' 'NotSpecified' 'String'
Reg-Done 'Descoberta automática de pastas desligada'
""",
)

_add(
    id="game_dvr", page=PAGE_DEBLOAT, section="Essenciais", order=15, video=True,
    title="Desligar Game DVR",
    desc="Desliga a gravação em segundo plano da Xbox Game Bar (você grava com outro app se quiser).",
    script=r"""
$g = 'HKCU:\System\GameConfigStore'
Set-Reg $g 'GameDVR_Enabled' 0
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\GameDVR' 'AppCaptureEnabled' 0
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\GameDVR' 'AllowGameDVR' 0
Reg-Done 'Game DVR desligado'
""",
)

_add(
    id="location", page=PAGE_DEBLOAT, section="Essenciais", order=16, video=True,
    title="Desligar rastreamento de localização",
    desc="Nenhum app nem o Windows acessa sua localização. Mapas offline deixam de atualizar.",
    script=r"""
Set-Reg 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\location' 'Value' 'Deny' 'String'
Set-Reg 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Sensor\Overrides\{BFA794E4-F964-4FDB-90F6-51056BFE4B44}' 'SensorPermissionState' 0
Set-Reg 'HKLM:\SYSTEM\CurrentControlSet\Services\lfsvc\Service\Configuration' 'Status' 0
Set-Reg 'HKLM:\SYSTEM\Maps' 'AutoUpdateEnabled' 0
Reg-Done 'Localização desligada'
""",
)

_add(
    id="ps7_telemetry", page=PAGE_DEBLOAT, section="Essenciais", order=17, video=True,
    title="Desligar telemetria do PowerShell 7",
    desc="Define POWERSHELL_TELEMETRY_OPTOUT=1 para o sistema todo.",
    script=r"""
[Environment]::SetEnvironmentVariable('POWERSHELL_TELEMETRY_OPTOUT', '1', 'Machine')
Ok 'Telemetria do PowerShell 7 desligada'
""",
)

_add(
    id="end_task", page=PAGE_DEBLOAT, section="Essenciais", order=18, video=True,
    title="“Finalizar tarefa” no botão direito da barra",
    desc="Clique direito em um app travado na barra de tarefas e feche na hora.",
    script=r"""
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\TaskbarDeveloperSettings' 'TaskbarEndTask' 1
Reg-Done 'Finalizar tarefa ativado'
""",
)

_add(
    id="services_manual", page=PAGE_DEBLOAT, section="Essenciais", order=19, video=True,
    title="Serviços em modo manual",
    desc="Serviços que ficam parados na memória passam a abrir só quando algum programa precisa.",
    note="Em 90% dos casos nada muda no uso, mas libera memória (explicado no vídeo).",
    script=r"""
$manual = @('ALG','AppMgmt','AppReadiness','AxInstSV','BDESVC','BTAGService','CDPSvc','CertPropSvc','COMSysApp',
 'CscService','DevQueryBroker','DeviceAssociationService','DisplayEnhancementService','DmEnrollmentSvc','dmwappushservice',
 'DsSvc','EFS','EapHost','edgeupdate','edgeupdatem','Fax','fdPHost','FDResPub','fhsvc','FrameServer','GraphicsPerfSvc',
 'HvHost','icssvc','IKEEXT','InventorySvc','iphlpsvc','IpxlatCfgSvc','KtmRm','lfsvc','lltdsvc','lmhosts','MapsBroker',
 'McpManagementService','MicrosoftEdgeElevationService','MSDTC','MSiSCSI','NaturalAuthentication','NcaSvc','NcbService',
 'NcdAutoSetup','Netman','NetSetupSvc','PcaSvc','PeerDistSvc','perceptionsimulation','PerfHost','PhoneSvc','pla',
 'PolicyAgent','PrintNotify','PushToInstall','QWAVE','RasAuto','RasMan','RetailDemo','RmSvc','RpcLocator','SCardSvr',
 'ScDeviceEnum','SCPolicySvc','SDRSVC','seclogon','SEMgrSvc','SensorDataService','SensorService','SensrSvc','SessionEnv',
 'SharedAccess','smphost','SmsRouter','SNMPTRAP','spectrum','SSDPSRV','SstpSvc','StiSvc','svsvc','swprv','TapiSrv',
 'TermService','TieringEngineService','TrkWks','TroubleshootingSvc','UmRdpService','upnphost','vds',
 'vmicguestinterface','vmicheartbeat','vmickvpexchange','vmicrdv','vmicshutdown','vmictimesync','vmicvmsession','vmicvss',
 'W32Time','WalletService','WarpJITSvc','wbengine','WbioSrvc','wcncsvc','WdiServiceHost','WdiSystemHost','WebClient',
 'Wecsvc','WEPHOSTSVC','wercplsupport','WerSvc','WFDSConMgrSvc','WiaRpc','WinRM','wisvc','wlidsvc','wlpasvc','WManSvc',
 'wmiApSrv','WMPNetworkSvc','workfolderssvc','WpcMonSvc','WPDBusEnum','XblAuthManager','XblGameSave','XboxGipSvc','XboxNetApiSvc')
$disabled = @('DiagTrack','DialogBlockingService','RemoteRegistry','RemoteAccess','NetTcpPortSharing','AppVClient','UevAgentService','shpamsvc','ssh-agent')
$delayed = @('BITS','WSearch')
$ok = 0; $fail = 0
foreach ($s in $manual)   { $r = Set-Svc $s 'Manual';   if ($r -eq $true) { $ok++ } elseif ($r -eq $false) { $fail++ } }
foreach ($s in $disabled) { $r = Set-Svc $s 'Disabled'; if ($r -eq $true) { $ok++ } elseif ($r -eq $false) { $fail++ } }
foreach ($s in $delayed)  { $r = Set-Svc $s 'Delayed';  if ($r -eq $true) { $ok++ } elseif ($r -eq $false) { $fail++ } }
if ($fail -gt 0) { Say ("{0} serviços protegidos pelo Windows foram mantidos como estavam" -f $fail) }
Ok ("{0} serviços ajustados" -f $ok)
""",
)

# ---------------------------------------------------------------------------
# DEBLOAT — Avançados (WinUtil > Advanced Tweaks)
# ---------------------------------------------------------------------------
_add(
    id="edge_debloat", page=PAGE_DEBLOAT, section="Avançados", order=20, video=True,
    title="Debloat do Edge",
    desc="Políticas que cortam compras, recompensas, barra lateral, telemetria e inicialização em segundo plano do Edge.",
    script=r"""
$e = 'HKLM:\SOFTWARE\Policies\Microsoft\Edge'
$vals = [ordered]@{
  EdgeEnhanceImagesEnabled = 0; PersonalizationReportingEnabled = 0; ShowRecommendationsEnabled = 0; HideFirstRunExperience = 1;
  UserFeedbackAllowed = 0; ConfigureDoNotTrack = 1; AlternateErrorPagesEnabled = 0; EdgeCollectionsEnabled = 0;
  EdgeShoppingAssistantEnabled = 0; MicrosoftEdgeInsiderPromotionEnabled = 0; ShowMicrosoftRewards = 0; WebWidgetAllowed = 0;
  DiagnosticData = 0; EdgeAssetDeliveryServiceEnabled = 0; CryptoWalletEnabled = 0; WalletDonationEnabled = 0;
  HubsSidebarEnabled = 0; StartupBoostEnabled = 0; BackgroundModeEnabled = 0; SpotlightExperiencesAndRecommendationsEnabled = 0
}
foreach ($k in $vals.Keys) { Set-Reg $e $k $vals[$k] }
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\EdgeUpdate' 'CreateDesktopShortcutDefault' 0
Reg-Done 'Edge sem bloat'
""",
)

_add(
    id="background_apps", page=PAGE_DEBLOAT, section="Avançados", order=21, video=True,
    title="Bloquear apps da Store em segundo plano",
    desc="Apps da Microsoft Store não rodam escondidos. Exceções: WhatsApp (para receber mensagens) e a própria Store.",
    script=r"""
$ap = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy'
Set-Reg $ap 'LetAppsRunInBackground' 2
Set-Reg $ap 'LetAppsRunInBackground_ForceAllowTheseApps' ([string[]]@('5319275A.WhatsAppDesktop_cv1g1gvanyjgm','Microsoft.WindowsStore_8wekyb3d8bbwe')) 'MultiString'
Reg-Done 'Apps em segundo plano bloqueados (WhatsApp liberado)'
""",
)

_add(
    id="fso", page=PAGE_DEBLOAT, section="Avançados", order=22, video=True,
    title="Desativar otimizações de tela cheia",
    desc="Jogos em tela cheia rodam em modo exclusivo de verdade (menos input lag em alguns jogos).",
    script=r"""
$g = 'HKCU:\System\GameConfigStore'
Set-Reg $g 'GameDVR_DXGIHonorFSEWindowsCompatible' 1
Set-Reg $g 'GameDVR_FSEBehaviorMode' 2
Set-Reg $g 'GameDVR_FSEBehavior' 2
Set-Reg $g 'GameDVR_HonorUserFSEBehaviorMode' 1
Set-Reg $g 'GameDVR_EFSEFeatureFlags' 0
Reg-Done 'Otimizações de tela cheia desativadas'
""",
)

_add(
    id="copilot", page=PAGE_DEBLOAT, section="Avançados", order=23, video=True,
    title="Desativar Copilot, Recall e IA do Windows",
    desc="Remove o Copilot, bloqueia o Recall/Click to Do e a IA do Paint e do Bloco de Notas.",
    script=rf"""
Set-Reg 'HKCU:\Software\Policies\Microsoft\Windows\WindowsCopilot' 'TurnOffWindowsCopilot' 1
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot' 'TurnOffWindowsCopilot' 1
Set-Reg '{ADV}' 'ShowCopilotButton' 0
Set-Reg 'HKLM:\SOFTWARE\Microsoft\Windows\Shell\Copilot' 'IsCopilotAvailable' 0
Set-Reg 'HKCU:\Software\Microsoft\Windows\Shell\Copilot\BingChat' 'IsUserEligible' 0
$ai = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsAI'
Set-Reg $ai 'DisableAIDataAnalysis' 1
Set-Reg $ai 'AllowRecallEnablement' 0
Set-Reg $ai 'DisableClickToDo' 1
Set-Reg 'HKCU:\Software\Policies\Microsoft\Windows\WindowsAI' 'DisableAIDataAnalysis' 1
Set-Reg 'HKCU:\Software\Policies\Microsoft\Windows\WindowsAI' 'DisableClickToDo' 1
Set-Reg 'HKLM:\SOFTWARE\Policies\WindowsNotepad' 'DisableAIFeatures' 1
$paint = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Paint'
Set-Reg $paint 'DisableCocreator' 1
Set-Reg $paint 'DisableGenerativeFill' 1
Set-Reg $paint 'DisableImageCreator' 1
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Edge' 'CopilotCDPPageContext' 0
Reg-Done 'Políticas de IA'
Remove-App @('Microsoft.Copilot', 'Microsoft.Windows.Ai.Copilot.Provider')
$f = Get-WindowsOptionalFeature -Online -FeatureName 'Recall' -ErrorAction SilentlyContinue
if ($f -and $f.State -eq 'Enabled') {{
    Disable-WindowsOptionalFeature -Online -FeatureName 'Recall' -NoRestart -ErrorAction SilentlyContinue | Out-Null
    Ok 'Recall desinstalado'
}} else {{ Say 'Recall não está ativo neste PC' }}
""",
)

_add(
    id="notifications", page=PAGE_DEBLOAT, section="Avançados", order=24, video=True,
    title="Desativar notificações do Windows",
    desc="Some com dicas, sugestões, “aproveite ainda mais o Windows” e avisos na tela de bloqueio. Notificações do WhatsApp e Discord continuam.",
    script=rf"""
$ns = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Notifications\Settings'
Set-Reg "$ns\Windows.SystemToast.Suggested" 'Enabled' 0
Set-Reg "$ns\Windows.SystemToast.StartupApp" 'Enabled' 0
Set-Reg "$ns\Windows.ActionCenter.SmartOptOut" 'Enabled' 0
Set-Reg $ns 'NOC_GLOBAL_SETTING_ALLOW_CRITICAL_TOASTS_ABOVE_LOCK' 0
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\PushNotifications' 'LockScreenToastEnabled' 0
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\UserProfileEngagement' 'ScoobeSystemSettingEnabled' 0
Set-Reg '{CDM}' 'SubscribedContent-338389Enabled' 0
Set-Reg '{ADV}' 'Start_AccountNotifications' 0
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\SystemSettings\AccountNotifications' 'EnableAccountNotifications' 0
Reg-Done 'Notificações do Windows desligadas'
""",
)

_add(
    id="notifications_all", page=PAGE_DEBLOAT, section="Avançados", order=25, default=False,
    title="Desativar TODAS as notificações (igual ao vídeo)",
    desc="Desliga a central de notificações inteira, inclusive de apps.",
    note="WhatsApp e Discord deixam de avisar mensagens novas. Por isso fica desmarcado.",
    script=r"""
Set-Reg 'HKCU:\Software\Policies\Microsoft\Windows\Explorer' 'DisableNotificationCenter' 1
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\PushNotifications' 'ToastEnabled' 0
Reg-Done 'Todas as notificações desligadas'
""",
)

_add(
    id="explorer_home_gallery", page=PAGE_DEBLOAT, section="Avançados", order=26, video=True,
    title="Remover Início e Galeria do Explorador",
    desc="O Explorador de Arquivos abre direto em “Este Computador”.",
    script=rf"""
Remove-Item -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Desktop\NameSpace\{{f874310e-b6b7-47dc-bc84-b9e6b38f5903}}' -Force -ErrorAction SilentlyContinue
Set-Reg 'HKCU:\Software\Classes\CLSID\{{f874310e-b6b7-47dc-bc84-b9e6b38f5903}}' 'System.IsPinnedToNameSpaceTree' 0
Set-Reg 'HKCU:\Software\Classes\CLSID\{{e88865ea-0e1c-4e20-9aa6-edcd0212c87c}}' 'System.IsPinnedToNameSpaceTree' 0
Set-Reg '{ADV}' 'LaunchTo' 1
Reg-Done 'Início e Galeria removidos'
""",
)

_add(
    id="display_performance", page=PAGE_DEBLOAT, section="Avançados", order=27, video=True,
    title="Efeitos visuais para desempenho",
    desc="Desliga animações, sombras e transparências (mantém a fonte suavizada).",
    note="Ao arrastar uma janela aparece só o contorno — é o preço do ganho.",
    script=rf"""
$d = 'HKCU:\Control Panel\Desktop'
Set-Reg $d 'DragFullWindows' '0' 'String'
Set-Reg $d 'MenuShowDelay' '200' 'String'
Set-Reg $d 'FontSmoothing' '2' 'String'
Set-Reg $d 'UserPreferencesMask' ([byte[]](0x90,0x12,0x03,0x80,0x10,0x00,0x00,0x00)) 'Binary'
Set-Reg 'HKCU:\Control Panel\Desktop\WindowMetrics' 'MinAnimate' '0' 'String'
Set-Reg 'HKCU:\Control Panel\Keyboard' 'KeyboardDelay' '0' 'String'
Set-Reg '{ADV}' 'ListviewAlphaSelect' 0
Set-Reg '{ADV}' 'ListviewShadow' 0
Set-Reg '{ADV}' 'TaskbarAnimations' 0
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects' 'VisualFXSetting' 3
Set-Reg 'HKCU:\Software\Microsoft\Windows\DWM' 'EnableAeroPeek' 0
Reg-Done 'Efeitos visuais em modo desempenho'
""",
)

_add(
    id="classic_menu", page=PAGE_DEBLOAT, section="Avançados", order=28, video=True,
    title="Menu clássico do botão direito",
    desc="Volta o menu de contexto completo do Windows 10, sem precisar de “Mostrar mais opções”.",
    script=r"""
$null = & reg.exe add 'HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32' /f /ve 2>&1
if ($LASTEXITCODE -eq 0) { Ok 'Menu clássico ativado' } else { Warn 'Não foi possível ativar o menu clássico' }
""",
)

# ---------------------------------------------------------------------------
# DEBLOAT — Preferências (WinUtil > Customize Preferences)
# ---------------------------------------------------------------------------
_add(
    id="dark_theme", page=PAGE_DEBLOAT, section="Preferências", order=30, video=True,
    title="Tema escuro",
    desc="Windows e apps no modo escuro.",
    script=r"""
$t = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize'
Set-Reg $t 'AppsUseLightTheme' 0
Set-Reg $t 'SystemUsesLightTheme' 0
Reg-Done 'Tema escuro'
""",
)

_add(
    id="bing_search", page=PAGE_DEBLOAT, section="Preferências", order=31, video=True,
    title="Tirar o Bing da pesquisa do Iniciar",
    desc="A busca do menu Iniciar procura só no seu PC.",
    script=r"""
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Search' 'BingSearchEnabled' 0
Set-Reg 'HKCU:\Software\Policies\Microsoft\Windows\Explorer' 'DisableSearchBoxSuggestions' 1
Reg-Done 'Bing fora da pesquisa'
""",
)

_add(
    id="numlock", page=PAGE_DEBLOAT, section="Preferências", order=32, video=True,
    title="NumLock ligado ao iniciar",
    desc="O teclado numérico já funciona na tela de login.",
    script=r"""
Set-Reg 'Registry::HKEY_USERS\.DEFAULT\Control Panel\Keyboard' 'InitialKeyboardIndicators' '2' 'String'
Set-Reg 'HKCU:\Control Panel\Keyboard' 'InitialKeyboardIndicators' '2' 'String'
Reg-Done 'NumLock ao iniciar'
""",
)

_add(
    id="verbose_logon", page=PAGE_DEBLOAT, section="Preferências", order=33, video=True,
    title="Mensagens detalhadas ao ligar e desligar",
    desc="Mostra o que o Windows está fazendo em vez de só “Aguarde”.",
    script=r"""
Set-Reg 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' 'VerboseStatus' 1
Reg-Done 'Mensagens detalhadas'
""",
)

_add(
    id="start_recommendations", page=PAGE_DEBLOAT, section="Preferências", order=34, video=True,
    title="Remover recomendações do Iniciar",
    desc="Some a seção “Recomendado” com arquivos e apps sugeridos.",
    script=rf"""
Set-Reg 'HKLM:\SOFTWARE\Microsoft\PolicyManager\current\device\Start' 'HideRecommendedSection' 1
Set-Reg 'HKLM:\SOFTWARE\Microsoft\PolicyManager\current\device\Education' 'IsEducationEnvironment' 1
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Explorer' 'HideRecommendedSection' 1
Set-Reg '{ADV}' 'Start_IrisRecommendations' 0
Reg-Done 'Recomendações do Iniciar removidas'
""",
)

_add(
    id="sticky_keys", page=PAGE_DEBLOAT, section="Preferências", order=35, video=True,
    title="Desativar teclas de aderência",
    desc="Apertar Shift 5 vezes (no meio do jogo) não abre mais aquele aviso.",
    script=r"""
Set-Reg 'HKCU:\Control Panel\Accessibility\StickyKeys' 'Flags' '506' 'String'
Set-Reg 'HKCU:\Control Panel\Accessibility\ToggleKeys' 'Flags' '58' 'String'
Set-Reg 'HKCU:\Control Panel\Accessibility\Keyboard Response' 'Flags' '122' 'String'
Reg-Done 'Teclas de aderência desativadas'
""",
)

_add(
    id="taskbar_search", page=PAGE_DEBLOAT, section="Preferências", order=36, video=True,
    title="Esconder a pesquisa da barra de tarefas",
    desc="A busca continua no menu Iniciar (é só começar a digitar).",
    script=r"""
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Search' 'SearchboxTaskbarMode' 0
Reg-Done 'Pesquisa escondida da barra'
""",
)

_add(
    id="taskbar_left", page=PAGE_DEBLOAT, section="Preferências", order=37, video=True,
    title="Barra de tarefas alinhada à esquerda",
    desc="Botão Iniciar no canto, como no Windows 10.",
    script=rf"""
Set-Reg '{ADV}' 'TaskbarAl' 0
Reg-Done 'Barra à esquerda'
""",
)

_add(
    id="widgets", page=PAGE_DEBLOAT, section="Preferências", order=38, video=True,
    title="Desativar Widgets",
    desc="Some o painel de notícias/clima da barra de tarefas.",
    script=rf"""
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Dsh' 'AllowNewsAndInterests' 0
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Windows Feeds' 'EnableFeeds' 0
Set-Reg '{ADV}' 'TaskbarDa' 0 -Quiet
Reg-Done 'Widgets desativados'
""",
)

_add(
    id="detailed_bsod", page=PAGE_DEBLOAT, section="Preferências", order=39, video=True,
    title="Tela azul detalhada",
    desc="Se o PC travar, a tela azul mostra o código técnico do erro.",
    script=r"""
Set-Reg 'HKLM:\SYSTEM\CurrentControlSet\Control\CrashControl' 'DisplayParameters' 1
Set-Reg 'HKLM:\SYSTEM\CurrentControlSet\Control\CrashControl' 'DisableEmoticon' 1
Reg-Done 'Tela azul detalhada'
""",
)

_add(
    id="cross_device", page=PAGE_DEBLOAT, section="Preferências", order=40, video=True,
    title="Desativar “continuar em outro dispositivo”",
    desc="O PC não fica sugerindo continuar o que você fazia no celular.",
    script=r"""
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\CrossDeviceResume\Configuration' 'IsResumeAllowed' 0
Reg-Done 'Continuar entre dispositivos desligado'
""",
)

# ---------------------------------------------------------------------------
# DEBLOAT — Windows Update (WinUtil > Updates > Security)
# ---------------------------------------------------------------------------
_add(
    id="updates_security", page=PAGE_DEBLOAT, section="Windows Update", order=41, video=True,
    title="Windows Update em modo “Segurança”",
    desc="Recebe atualizações de segurança (4 dias depois) e segura atualizações de recursos por 1 ano. Sem reinício automático.",
    note="Diferente do WinUtil, os drivers continuam vindo pelo Windows Update (PC recém-formatado precisa deles).",
    script=r"""
$wu = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate'
Set-Reg $wu 'DeferFeatureUpdates' 1
Set-Reg $wu 'DeferFeatureUpdatesPeriodInDays' 365
Set-Reg $wu 'DeferQualityUpdates' 1
Set-Reg $wu 'DeferQualityUpdatesPeriodInDays' 4
Set-Reg "$wu\AU" 'NoAutoRebootWithLoggedOnUsers' 1
Set-Reg "$wu\AU" 'AUPowerManagement' 0
$ux = 'HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings'
Set-Reg $ux 'BranchReadinessLevel' 20
Set-Reg $ux 'DeferFeatureUpdatesPeriodInDays' 365
Set-Reg $ux 'DeferQualityUpdatesPeriodInDays' 4
Reg-Done 'Windows Update em modo Segurança'
""",
)

# ---------------------------------------------------------------------------
# DEBLOAT — Privacidade (O&O ShutUp10++, feito direto no registro)
# ---------------------------------------------------------------------------
_SHUTUP = "Privacidade (O&O ShutUp10)"

_add(
    id="oosu_permissions", page=PAGE_DEBLOAT, section=_SHUTUP, order=42, video=True,
    title="Bloquear permissões de apps da Store",
    desc="Agenda, contatos, chamadas, e-mail, mensagens, diagnóstico, rádios e conta ficam bloqueados.",
    note="Câmera, microfone e captura de tela continuam liberados (chamadas no WhatsApp/Discord).",
    script=r"""
$cs = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore'
foreach ($c in 'appointments','contacts','phoneCallHistory','phoneCall','chat','email','userAccountInformation',
               'userDataTasks','userNotificationListener','radios','bluetoothSync','appDiagnostics','cellularData',
               'gazeInput','activity','humanPresence') {
    Set-Reg "$cs\$c" 'Value' 'Deny' 'String'
}
Reg-Done 'Permissões de apps bloqueadas'
""",
)

_add(
    id="oosu_lockscreen", page=PAGE_DEBLOAT, section=_SHUTUP, order=43, video=True,
    title="Tela de bloqueio limpa",
    desc="Sem Windows Spotlight, “curiosidades e dicas” e o ícone “Saiba mais sobre esta imagem”.",
    script=rf"""
Set-Reg '{CDM}' 'RotatingLockScreenEnabled' 0
Set-Reg '{CDM}' 'RotatingLockScreenOverlayEnabled' 0
Set-Reg '{CDM}' 'SubscribedContent-338387Enabled' 0
$cc = 'HKCU:\Software\Policies\Microsoft\Windows\CloudContent'
Set-Reg $cc 'DisableWindowsSpotlightFeatures' 1
Set-Reg $cc 'DisableWindowsSpotlightOnActionCenter' 1
Set-Reg $cc 'DisableWindowsSpotlightOnSettings' 1
Set-Reg $cc 'DisableWindowsSpotlightWindowsWelcomeExperience' 1
Set-Reg $cc 'DisableThirdPartySuggestions' 1
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\HideDesktopIcons\NewStartPanel' '{{2cc5ca98-6485-489a-920e-b3e88a6ccce3}}' 1
Reg-Done 'Tela de bloqueio limpa'
""",
)

_add(
    id="oosu_ads", page=PAGE_DEBLOAT, section=_SHUTUP, order=44, video=True,
    title="Sem anúncios e sem ID de publicidade",
    desc="Desliga o ID de anúncio, sugestões no Iniciar/Configurações e propaganda no Explorador.",
    script=rf"""
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo' 'Enabled' 0
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\AdvertisingInfo' 'DisabledByGroupPolicy' 1
foreach ($n in 'SystemPaneSuggestionsEnabled','SubscribedContent-310093Enabled','SubscribedContent-314563Enabled',
               'SubscribedContent-338388Enabled','SubscribedContent-338393Enabled','SubscribedContent-353694Enabled',
               'SubscribedContent-353696Enabled','SubscribedContent-353698Enabled','SubscribedContentEnabled') {{
    Set-Reg '{CDM}' $n 0
}}
Set-Reg '{ADV}' 'ShowSyncProviderNotifications' 0
Set-Reg '{ADV}' 'Start_IrisRecommendations' 0
Reg-Done 'Anúncios desligados'
""",
)

_add(
    id="oosu_search", page=PAGE_DEBLOAT, section=_SHUTUP, order=45, video=True,
    title="Pesquisa sem Cortana, web e IA",
    desc="Bloqueia Cortana, resultados da web, destaques da pesquisa e histórico de busca.",
    script=r"""
$ws = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Windows Search'
Set-Reg $ws 'AllowCortana' 0
Set-Reg $ws 'AllowCloudSearch' 0
Set-Reg $ws 'ConnectedSearchUseWeb' 0
Set-Reg $ws 'DisableWebSearch' 1
Set-Reg $ws 'AllowSearchToUseLocation' 0
$ss = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\SearchSettings'
Set-Reg $ss 'IsDynamicSearchBoxEnabled' 0
Set-Reg $ss 'IsAADCloudSearchEnabled' 0
Set-Reg $ss 'IsMSACloudSearchEnabled' 0
Set-Reg $ss 'IsDeviceSearchHistoryEnabled' 0
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Search' 'CortanaConsent' 0
Reg-Done 'Pesquisa privada'
""",
)

_add(
    id="oosu_misc", page=PAGE_DEBLOAT, section=_SHUTUP, order=46, video=True,
    title="Sem Meet Now, Pessoas, Phone Link e sincronização",
    desc="Também desliga lembretes de feedback e o diagnóstico do Media Player.",
    script=r"""
Set-Reg 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer' 'HideSCAMeetNow' 1
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer' 'HideSCAMeetNow' 1
Set-Reg 'HKCU:\Software\Policies\Microsoft\Windows\Explorer' 'HidePeopleBar' 1
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System' 'EnableMmx' 0
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\SettingSync' 'DisableSettingSync' 2
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\SettingSync' 'DisableSettingSyncUserOverride' 1
Set-Reg 'HKCU:\Software\Microsoft\Siuf\Rules' 'NumberOfSIUFInPeriod' 0
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection' 'DoNotShowFeedbackNotifications' 1
Set-Reg 'HKCU:\Software\Microsoft\MediaPlayer\Preferences' 'UsageTracking' 0
Reg-Done 'Extras desligados'
""",
)

_add(
    id="oosu_machine", page=PAGE_DEBLOAT, section=_SHUTUP, order=47, video=True,
    title="Bloqueios do sistema",
    desc="Sem botão de revelar senha, gravador de passos, assistência remota, P2P do Update, mapas e voz automáticos.",
    script=r"""
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CredUI' 'DisablePasswordReveal' 1
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\AppCompat' 'DisableUAR' 1
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\AppCompat' 'DisableInventory' 1
Set-Reg 'HKLM:\SYSTEM\CurrentControlSet\Control\Remote Assistance' 'fAllowToGetHelp' 0
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization' 'DODownloadMode' 0
Set-Reg 'HKLM:\SYSTEM\Maps' 'AutoUpdateEnabled' 0
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Maps' 'AutoDownloadAndUpdateMapData' 0
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Maps' 'AllowUntriggeredNetworkTrafficOnSettingsPage' 0
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Speech' 'AllowSpeechModelUpdate' 0
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\CurrentVersion\Software Protection Platform' 'NoGenTicket' 1
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\OneDrive' 'PreventNetworkTrafficPreUserSignIn' 1
Reg-Done 'Bloqueios do sistema'
""",
)

# ---------------------------------------------------------------------------
# OTIMIZAÇÃO
# ---------------------------------------------------------------------------
_add(
    id="temp_files", page=PAGE_OTIMIZACAO, section="Limpeza", order=95, video=True,
    title="Apagar arquivos temporários",
    desc="Limpa as pastas Temp do usuário e do Windows.",
    script=r"""
$drive = $env:SystemDrive.TrimEnd(':')
$before = (Get-PSDrive $drive).Free
foreach ($dir in @($env:TEMP, (Join-Path $env:SystemRoot 'Temp'))) {
    Get-ChildItem -LiteralPath $dir -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch '^(_MEI|prisma)' } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
$freed = ((Get-PSDrive $drive).Free - $before) / 1MB
Ok ("Temporários apagados ({0:N0} MB liberados)" -f [math]::Max(0, $freed))
""",
)

_add(
    id="disk_cleanup", page=PAGE_OTIMIZACAO, section="Limpeza", order=96, video=True,
    title="Limpeza de disco",
    desc="Roda a Limpeza de Disco do Windows e limpa componentes antigos do Windows Update.",
    note="Pode demorar alguns minutos. Downloads e Lixeira não são tocados.",
    script=r"""
$drive = $env:SystemDrive.TrimEnd(':')
$before = (Get-PSDrive $drive).Free
$vc = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VolumeCaches'
Get-ChildItem $vc -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -notin @('DownloadsFolder', 'Recycle Bin') } | ForEach-Object {
    New-ItemProperty -Path $_.PSPath -Name 'StateFlags0077' -Value 2 -PropertyType DWord -Force -ErrorAction SilentlyContinue | Out-Null
}
Say 'Rodando a Limpeza de Disco...'
$p = Start-Process -FilePath "$env:SystemRoot\System32\cleanmgr.exe" -ArgumentList '/sagerun:77' -WindowStyle Hidden -PassThru
if (-not $p.WaitForExit(900000)) { $p.Kill(); Warn 'Limpeza de Disco demorou demais e foi interrompida' }
Say 'Limpando componentes antigos do Windows (DISM)...'
$null = & dism.exe /Online /Cleanup-Image /StartComponentCleanup 2>&1
$freed = ((Get-PSDrive $drive).Free - $before) / 1MB
Ok ("Limpeza de disco concluída ({0:N0} MB liberados)" -f [math]::Max(0, $freed))
""",
)

_add(
    id="power_plan", page=PAGE_OTIMIZACAO, section="Desempenho", order=50,
    title="Plano de energia Desempenho Máximo",
    desc="Processador sem economia de energia. Em notebook é ignorado para não drenar a bateria.",
    script=r"""
if (Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue) {
    Say 'Notebook detectado: mantendo o plano Equilibrado para poupar bateria.'
    return
}
$existing = (powercfg /list) | Select-String 'Prisma' | Select-Object -First 1
if ($existing -and ($existing.Line -match '([0-9a-fA-F-]{36})')) { $guid = $Matches[1] }
else {
    $out = powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61 2>&1 | Out-String
    if ($out -match '([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})') {
        $guid = $Matches[1]
        powercfg -changename $guid 'Prisma - Desempenho Maximo' | Out-Null
    } else { $guid = '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c' }
}
powercfg -setactive $guid 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Ok 'Plano de energia de alto desempenho ativo' } else { Warn 'Este PC não aceitou o plano de alto desempenho' }
""",
)

_add(
    id="gpu_scheduling", page=PAGE_OTIMIZACAO, section="Desempenho", order=51,
    title="Agendamento de GPU acelerado por hardware",
    desc="A placa de vídeo gerencia a própria memória. Reduz latência em GPUs atuais (NVIDIA GTX 10+ / AMD RX 5000+).",
    script=r"""
Set-Reg 'HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers' 'HwSchMode' 2
Reg-Done 'Agendamento de GPU ativado'
""",
)

_add(
    id="game_mode", page=PAGE_OTIMIZACAO, section="Desempenho", order=52,
    title="Modo de Jogo ligado",
    desc="Windows prioriza o jogo aberto e segura atualizações durante a partida.",
    script=r"""
Set-Reg 'HKCU:\Software\Microsoft\GameBar' 'AutoGameModeEnabled' 1
Set-Reg 'HKCU:\Software\Microsoft\GameBar' 'AllowAutoGameMode' 1
Reg-Done 'Modo de Jogo ligado'
""",
)

_add(
    id="mmcss", page=PAGE_OTIMIZACAO, section="Desempenho", order=53,
    title="Prioridade de CPU e GPU para jogos",
    desc="Ajusta o agendador multimídia do Windows para dar prioridade a jogos.",
    script=r"""
$mm = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile'
Set-Reg $mm 'SystemResponsiveness' 10
Set-Reg $mm 'NetworkThrottlingIndex' ([int32]-1)
$g = "$mm\Tasks\Games"
Set-Reg $g 'GPU Priority' 8
Set-Reg $g 'Priority' 6
Set-Reg $g 'Scheduling Category' 'High' 'String'
Set-Reg $g 'SFIO Priority' 'High' 'String'
Reg-Done 'Prioridade para jogos'
""",
)

_add(
    id="startup_delay", page=PAGE_OTIMIZACAO, section="Desempenho", order=54,
    title="Sem atraso para abrir apps na inicialização",
    desc="O Windows segura os apps de inicialização por alguns segundos; isso tira a espera.",
    script=r"""
Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize' 'StartupDelayInMSec' 0
Reg-Done 'Atraso de inicialização removido'
""",
)

_add(
    id="brave_debloat", page=PAGE_OTIMIZACAO, section="Navegador", order=55,
    title="Debloat do Brave",
    desc="Desliga Rewards, Wallet, VPN, Leo (IA), Notícias e telemetria do Brave.",
    note="O Brave vai mostrar “gerenciado pela sua organização” — é normal com políticas.",
    script=r"""
$b = 'HKLM:\SOFTWARE\Policies\BraveSoftware\Brave'
Set-Reg $b 'BraveRewardsDisabled' 1
Set-Reg $b 'BraveWalletDisabled' 1
Set-Reg $b 'BraveVPNDisabled' 1
Set-Reg $b 'BraveAIChatEnabled' 0
Set-Reg $b 'BraveNewsDisabled' 1
Set-Reg $b 'BraveTalkDisabled' 1
Set-Reg $b 'BraveStatsPingEnabled' 0
Set-Reg $b 'BraveP3AEnabled' 0
Set-Reg $b 'BraveWebDiscoveryEnabled' 0
Reg-Done 'Brave sem bloat'
""",
)

_add(
    id="mouse_accel", page=PAGE_OTIMIZACAO, section="Extras", order=56, default=False,
    title="Desativar aceleração do mouse",
    desc="Desmarca “Aumentar precisão do ponteiro”. Mira mais consistente em jogos.",
    script=r"""
$m = 'HKCU:\Control Panel\Mouse'
Set-Reg $m 'MouseSpeed' '0' 'String'
Set-Reg $m 'MouseThreshold1' '0' 'String'
Set-Reg $m 'MouseThreshold2' '0' 'String'
Reg-Done 'Aceleração do mouse desativada'
""",
)

_add(
    id="file_ext", page=PAGE_OTIMIZACAO, section="Extras", order=57, default=False,
    title="Mostrar extensões de arquivo",
    desc="Mostra .exe, .pdf, .jpg... (ajuda a perceber arquivo falso tipo foto.jpg.exe).",
    script=rf"""
Set-Reg '{ADV}' 'HideFileExt' 0
Reg-Done 'Extensões visíveis'
""",
)

# ---------------------------------------------------------------------------
# DRIVERS
# ---------------------------------------------------------------------------
_add(
    id="drivers_wu", page=PAGE_DRIVERS, section="Windows Update", order=60,
    title="Instalar todos os drivers que faltam",
    desc="Procura no Windows Update os drivers deste PC (rede, áudio, chipset, Bluetooth, vídeo...), baixa e "
         "instala um por um. No fim, mostra se sobrou algum dispositivo sem driver.",
    note="Pode levar de 2 a 20 minutos na primeira vez, dependendo da internet.",
    script=r"""
Say 'Procurando drivers no Windows Update (pode levar alguns minutos)...'
try {
    $session = New-Object -ComObject Microsoft.Update.Session
    $session.ClientApplicationID = 'Prisma'
    $searcher = $session.CreateUpdateSearcher()
    $searcher.ServerSelection = 2
    $result = $searcher.Search("IsInstalled=0 and Type='Driver' and IsHidden=0")
} catch {
    Fail ("Não consegui consultar o Windows Update: {0}" -f $_.Exception.Message)
    Say 'Confira se a internet está funcionando e tente de novo.'
    return
}
# um driver por dispositivo: fica o mais novo
$best = @{}
foreach ($u in $result.Updates) {
    $key = if ($u.DriverHardwareID) { $u.DriverHardwareID } else { $u.Identity.UpdateID }
    if (-not $best.ContainsKey($key) -or $u.DriverVerDate -gt $best[$key].DriverVerDate) { $best[$key] = $u }
}
$updates = @($best.Values)
if ($updates.Count -eq 0) {
    Ok 'Nenhum driver pendente: o Windows Update não tem nada mais novo para este PC'
} else {
    Say ("{0} drivers encontrados" -f $updates.Count)
    $i = 0; $okN = 0; $reboot = $false
    foreach ($u in $updates) {
        $i++
        Say ("[{0}/{1}] {2} ({3:N0} MB)" -f $i, $updates.Count, $u.Title, ($u.MaxDownloadSize / 1MB))
        try {
            if (-not $u.EulaAccepted) { $u.AcceptEula() }
            $coll = New-Object -ComObject Microsoft.Update.UpdateColl
            [void]$coll.Add($u)
            $dl = $session.CreateUpdateDownloader()
            $dl.Updates = $coll
            $dr = $dl.Download()
            if ($dr.ResultCode -ne 2 -and $dr.ResultCode -ne 3) { Warn ("Download falhou: {0}" -f $u.Title); continue }
            $inst = $session.CreateUpdateInstaller()
            $inst.Updates = $coll
            try { $inst.AllowSourcePrompts = $false } catch {}
            $ir = $inst.Install()
            if ($ir.ResultCode -eq 2 -or $ir.ResultCode -eq 3) {
                $okN++
                Ok ("Instalado: {0}" -f $u.Title)
                if ($ir.RebootRequired) { $reboot = $true }
            } else { Warn ("Não instalou: {0} (código {1})" -f $u.Title, $ir.ResultCode) }
        } catch { Warn ("Falha em {0}: {1}" -f $u.Title, $_.Exception.Message) }
    }
    Ok ("{0} de {1} drivers instalados" -f $okN, $updates.Count)
    if ($reboot) { Say 'Alguns drivers só terminam de instalar depois de reiniciar.' }
}
$missing = @(Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue | Where-Object { $_.ConfigManagerErrorCode -eq 28 })
if ($missing.Count -gt 0) {
    Warn ("{0} dispositivo(s) ainda sem driver:" -f $missing.Count)
    $missing | Select-Object -First 8 | ForEach-Object { Say ("- {0}" -f $_.Name) }
    Say 'Reinicie e rode de novo. Se continuar, baixe no site da placa-mãe ou do notebook.'
} else { Ok 'Todos os dispositivos estão com driver' }
""",
)

_add(
    id="drivers_gpu", page=PAGE_DRIVERS, section="Placa de vídeo", order=97,
    title="Driver mais novo da placa de vídeo",
    desc="Detecta sua placa (NVIDIA, AMD ou Intel), baixa o app oficial da fabricante — NVIDIA App, AMD Adrenalin "
         "ou Intel Driver & Support Assistant — confere a assinatura digital e abre o instalador.",
    note="Roda por último. O instalador abre na tela: é só seguir os passos. Ele traz drivers mais novos que os do "
         "Windows Update, o que importa para jogos.",
    script=r"""
function Install-GpuTool([string]$Vendor) {
    $all = @{
        nvidia = @{ Name = 'NVIDIA App'; Page = 'https://www.nvidia.com/en-us/software/nvidia-app/';
                    Pattern = 'https://[^"''\s<>]*NVIDIA_app_v[0-9.]+_x64\.exe'; Publisher = 'NVIDIA';
                    Referer = ''; Open = 'https://www.nvidia.com/pt-br/software/nvidia-app/' }
        amd    = @{ Name = 'AMD Software: Adrenalin Edition'; Page = 'https://www.amd.com/en/support/download/drivers.html';
                    Pattern = 'https://drivers\.amd\.com/[^"''\s<>]*minimalsetup[^"''\s<>]*\.exe'; Publisher = 'Advanced Micro Devices';
                    Referer = 'https://www.amd.com/'; Open = 'https://www.amd.com/pt/support/download/drivers.html' }
        intel  = @{ Name = 'Intel Driver & Support Assistant'; Url = 'https://dsadata.intel.com/installer'; Publisher = 'Intel';
                    Referer = ''; Open = 'https://www.intel.com.br/content/www/br/pt/support/detect.html' }
    }
    $info = $all[$Vendor]
    try {
        $url = $info.Url
        if (-not $url) {
            $m = [regex]::Match((Get-Page $info.Page), $info.Pattern)
            if (-not $m.Success) { throw 'link do instalador não encontrado no site' }
            $url = $m.Value
        }
        $file = Join-Path (Join-Path $env:TEMP 'prisma-dl') ($Vendor + '-driver-setup.exe')
        Say ("Baixando {0}..." -f $info.Name)
        Download-File $url $file $info.Referer
        if (-not (Test-Signed $file $info.Publisher)) { throw 'assinatura digital não confere' }
        Start-Process -FilePath $file
        Ok ("Instalador do {0} aberto na tela: siga os passos para instalar o driver mais novo." -f $info.Name)
    } catch {
        Warn ("Não deu para baixar o {0} automaticamente ({1}). Abri a página oficial." -f $info.Name, $_.Exception.Message)
        Open-Url $info.Open
    }
}

$gpus = @(Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | Where-Object { $_.PNPDeviceID -like 'PCI\*' })
if ($gpus.Count -eq 0) { Warn 'Nenhuma placa de vídeo encontrada'; return }
$done = @{}
foreach ($g in $gpus) {
    $vendor = switch -Regex ($g.PNPDeviceID) { 'VEN_10DE' { 'nvidia' } 'VEN_1002' { 'amd' } 'VEN_8086' { 'intel' } default { '' } }
    Say ("Placa de vídeo: {0} (driver atual {1})" -f $g.Name, $g.DriverVersion)
    if (-not $vendor) { Say 'Fabricante não reconhecido: use o driver do Windows Update.'; continue }
    if ($done.ContainsKey($vendor)) { continue }
    $done[$vendor] = $true
    Install-GpuTool $vendor
}
""",
)

# ---------------------------------------------------------------------------
# INSTALAR APPS
# ---------------------------------------------------------------------------
_add(
    id="install_brave", page=PAGE_INSTALAR, section="Apps", order=70, glyph="B",
    title="Brave", desc="Navegador rápido, com bloqueador de anúncios embutido.",
    script=r"""Install-App -Name 'Brave' -Id 'Brave.Brave' -Url 'https://github.com/brave/brave-browser/releases/latest/download/BraveBrowserStandaloneSilentSetup.exe' -Publisher 'Brave Software' -Page 'https://brave.com/download/'""",
)
_add(
    id="install_steam", page=PAGE_INSTALAR, section="Apps", order=71, glyph="S",
    title="Steam", desc="Loja e biblioteca de jogos da Valve.",
    script=r"""Install-App -Name 'Steam' -Id 'Valve.Steam' -Url 'https://cdn.akamai.steamstatic.com/client/installer/SteamSetup.exe' -SilentArgs '/S' -Publisher 'Valve' -Page 'https://store.steampowered.com/about/'""",
)
_add(
    id="install_discord", page=PAGE_INSTALAR, section="Apps", order=72, glyph="D",
    title="Discord", desc="Voz, vídeo e chat com os amigos.",
    script=r"""Install-App -Name 'Discord' -Id 'Discord.Discord' -Url 'https://discord.com/api/downloads/distributions/app/installers/latest?channel=stable&platform=win&arch=x64' -SilentArgs '-s' -Publisher 'Discord' -Page 'https://discord.com/download'""",
)
_add(
    id="install_whatsapp", page=PAGE_INSTALAR, section="Apps", order=73, glyph="W",
    title="WhatsApp", desc="App oficial da Microsoft Store.",
    script=r"""Install-App -Name 'WhatsApp' -Id '9NKSQGP7F2NH' -Source 'msstore' -Page 'ms-windows-store://pdp/?ProductId=9NKSQGP7F2NH'""",
)
_add(
    id="install_claude", page=PAGE_INSTALAR, section="Apps", order=74, glyph="C",
    title="Claude", desc="App de desktop da Anthropic.",
    script=r"""Install-App -Name 'Claude' -Id 'Anthropic.Claude' -Page 'https://claude.ai/download'""",
)

# ---------------------------------------------------------------------------
# REMOVER APPS
# ---------------------------------------------------------------------------
_add(
    id="remove_edge", page=PAGE_REMOVER, section="Navegador", order=90, video=True, glyph="E",
    title="Microsoft Edge",
    desc="Desinstala o Edge de verdade (o vídeo desativa e torna o Edge desinstalável). Roda depois da instalação do Brave.",
    note="O WebView2 é mantido — WhatsApp, Discord e outros apps precisam dele.",
    script=r"""
$edgeExe = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edgeExe)) { Ok 'O Edge já não está instalado'; return }

$browsers = @(
    "$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe",
    "${env:ProgramFiles(x86)}\BraveSoftware\Brave-Browser\Application\brave.exe",
    "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\Application\brave.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles\Mozilla Firefox\firefox.exe",
    "$env:LOCALAPPDATA\Programs\Opera\opera.exe",
    "$env:LOCALAPPDATA\Programs\Opera GX\opera.exe",
    "$env:LOCALAPPDATA\Vivaldi\Application\vivaldi.exe"
)
if (-not ($browsers | Where-Object { Test-Path $_ })) {
    Fail 'Nenhum outro navegador instalado: o Edge foi mantido para você não ficar sem internet. Instale o Brave e rode de novo.'
    return
}

Say 'Fechando o Edge...'
Get-Process msedge, widgets -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# 1) "Tornar o Edge desinstalável": libera a regra que a Microsoft só ativa na Europa
$json = Join-Path $env:SystemRoot 'System32\IntegratedServicesRegionPolicySet.json'
if (Test-Path $json) {
    try {
        $null = & takeown.exe /f $json /a 2>&1
        $null = & icacls.exe $json /grant '*S-1-5-32-544:F' 2>&1
        $bytes = [IO.File]::ReadAllBytes($json)
        $bom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
        $text = [IO.File]::ReadAllText($json)
        $bak = "$json.prisma.bak"
        if (-not (Test-Path $bak)) { [IO.File]::WriteAllText($bak, $text, (New-Object Text.UTF8Encoding $bom)) }
        $pat1 = '("\$comment"\s*:\s*"Edge is uninstallable\."(?:(?!"\$comment").)*?"defaultState"\s*:\s*)"disabled"'
        $pat2 = '("\$comment"\s*:\s*"Promotion and direct launch of Edge[^"]*"(?:(?!"\$comment").)*?"defaultState"\s*:\s*)"enabled"'
        $new = [regex]::Replace($text, $pat1, '$1"enabled"', 'Singleline')
        $new = [regex]::Replace($new, $pat2, '$1"disabled"', 'Singleline')
        if ($new -ne $text) { [IO.File]::WriteAllText($json, $new, (New-Object Text.UTF8Encoding $bom)) }
        $null = & icacls.exe $json /setowner 'NT SERVICE\TrustedInstaller' 2>&1
        Ok 'Edge marcado como desinstalável'
    } catch { Warn ("Não consegui editar a regra regional: {0}" -f $_.Exception.Message) }
}

# 2) Região temporária na UE + permissões do instalador (mesmo truque do WinUtil)
$geoPaths = @('Registry::HKEY_USERS\.DEFAULT\Control Panel\International\Geo', 'HKCU:\Control Panel\International\Geo')
$oldGeo = @{}
foreach ($g in $geoPaths) { $oldGeo[$g] = (Get-ItemProperty -Path $g -Name Nation -ErrorAction SilentlyContinue).Nation }
$fakeDir = Join-Path $env:SystemRoot 'SystemApps\Microsoft.MicrosoftEdge_8wekyb3d8bbwe'
$fakeExe = Join-Path $fakeDir 'MicrosoftEdge.exe'
$madeFake = $false
try {
    foreach ($g in $geoPaths) { Set-Reg $g 'Nation' '68' 'String' -Quiet }
    Set-Reg 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdateDev' 'AllowUninstall' 1 -Quiet
    Set-Reg 'HKLM:\SOFTWARE\Microsoft\EdgeUpdateDev' 'AllowUninstall' 1 -Quiet
    Remove-ItemProperty -Path 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Microsoft Edge' -Name 'NoRemove' -ErrorAction SilentlyContinue
    if (-not (Test-Path $fakeExe)) {
        New-Item -ItemType Directory -Force $fakeDir | Out-Null
        New-Item -ItemType File -Force $fakeExe | Out-Null
        $madeFake = $true
    }

    $cs = 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\ClientState\{56EB18F8-B008-4CBD-B6D2-8C97FE7E9062}'
    Remove-ItemProperty -Path $cs -Name 'experiment_control_labels' -ErrorAction SilentlyContinue
    $info = Get-ItemProperty -Path $cs -ErrorAction SilentlyContinue
    $setup = $info.UninstallString
    $sargs = $info.UninstallArguments
    if (-not $setup -or -not (Test-Path $setup)) {
        $setup = Get-ChildItem "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\*\Installer\setup.exe" -ErrorAction SilentlyContinue |
            Select-Object -Last 1 -ExpandProperty FullName
        $sargs = $null
    }
    if (-not $sargs) { $sargs = '--uninstall --msedge --channel=stable --system-level --verbose-logging' }
    if ($setup) {
        Say 'Rodando o desinstalador do Edge...'
        $p = Start-Process -FilePath $setup -ArgumentList ("{0} --force-uninstall --delete-profile" -f $sargs.Trim()) -Wait -PassThru -WindowStyle Hidden
        Say ("Desinstalador terminou (código {0})" -f $p.ExitCode)
    } else { Warn 'Desinstalador do Edge não encontrado' }
} finally {
    foreach ($g in $geoPaths) { if ($oldGeo[$g]) { Set-Reg $g 'Nation' $oldGeo[$g] 'String' -Quiet } }
    if ($madeFake) { Remove-Item $fakeExe -Force -ErrorAction SilentlyContinue }
}

Start-Sleep -Seconds 2
if (Test-Path $edgeExe) {
    Fail 'O Edge continua instalado — esta versão do Windows bloqueou a remoção.'
    Say 'Tente: Configurações > Aplicativos > Aplicativos instalados > Microsoft Edge > Desinstalar.'
} else {
    Ok 'Microsoft Edge removido'
    # Impede o Edge Update de reinstalar o navegador (não afeta o WebView2)
    Set-Reg 'HKLM:\SOFTWARE\Microsoft\EdgeUpdate' 'DoNotUpdateToEdgeWithChromium' 1 -Quiet
    Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\EdgeUpdate' 'Install{56EB18F8-B008-4CBD-B6D2-8C97FE7E9062}' 0 -Quiet
    $desk = [Environment]::GetFolderPath('Desktop')
    foreach ($l in @("$env:PUBLIC\Desktop\Microsoft Edge.lnk", "$desk\Microsoft Edge.lnk",
                     "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Microsoft Edge.lnk",
                     "$env:APPDATA\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Microsoft Edge.lnk",
                     "$env:APPDATA\Microsoft\Internet Explorer\Quick Launch\Microsoft Edge.lnk")) {
        Remove-Item -LiteralPath $l -Force -ErrorAction SilentlyContinue
    }
}
if (Test-Path "${env:ProgramFiles(x86)}\Microsoft\EdgeWebView\Application") { Ok 'WebView2 mantido (os apps continuam funcionando)' }
""",
)

_add(
    id="remove_onedrive", page=PAGE_REMOVER, section="Microsoft", order=89, glyph="O",
    title="OneDrive",
    desc="Desinstala o OneDrive e desliga a sincronização. Se suas pastas estavam no OneDrive, elas voltam para o PC.",
    note="Nada é apagado: o que já estava no OneDrive fica na pasta OneDrive e na nuvem.",
    script=r"""
Get-Process OneDrive -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$usf = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders'
$map = [ordered]@{
  'Desktop' = 'Desktop'; '{754AC886-DF64-4CBA-86B5-F7FBF4FBCEF5}' = 'Desktop';
  'Personal' = 'Documents'; '{F42EE2D3-909F-4907-8871-4C22FC0BF756}' = 'Documents';
  'My Pictures' = 'Pictures'; '{0DDD015D-B06C-45D5-8C4C-F59713854639}' = 'Pictures';
  'My Music' = 'Music'; '{A0C69A99-21C8-4671-8703-7934162FCF1D}' = 'Music';
  'My Video' = 'Videos'; '{35286A68-3C57-41A1-BBB1-0EAE73D76C95}' = 'Videos'
}
$props = Get-ItemProperty -Path $usf -ErrorAction SilentlyContinue
$moved = 0
foreach ($k in $map.Keys) {
    $v = $props.$k
    if ($v -and $v -match 'OneDrive') {
        New-Item -ItemType Directory -Force (Join-Path $env:USERPROFILE $map[$k]) | Out-Null
        Set-Reg $usf $k ('%USERPROFILE%\' + $map[$k]) 'ExpandString' -Quiet
        $moved++
    }
}
if ($moved -gt 0) { Say ("{0} pastas do sistema voltaram para {1}" -f $moved, $env:USERPROFILE) }

$wg = Get-Winget
if ($wg) { $null = & $wg uninstall --id Microsoft.OneDrive --exact --silent --accept-source-agreements --disable-interactivity 2>&1 }
$setups = @("$env:SystemRoot\System32\OneDriveSetup.exe", "$env:SystemRoot\SysWOW64\OneDriveSetup.exe")
$setups += @(Get-ChildItem "$env:LOCALAPPDATA\Microsoft\OneDrive\*\OneDriveSetup.exe", "$env:ProgramFiles\Microsoft OneDrive\*\OneDriveSetup.exe" -ErrorAction SilentlyContinue | ForEach-Object FullName)
foreach ($s in $setups) {
    if (Test-Path $s) { Start-Process -FilePath $s -ArgumentList '/uninstall' -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue }
}
Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\OneDrive' 'DisableFileSyncNGSC' 1 -Quiet
Set-Reg 'HKCU:\Software\Classes\CLSID\{018D5C66-4533-4307-9B53-224DE2ED1FE6}' 'System.IsPinnedToNameSpaceTree' 0 -Quiet
Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'OneDrive' -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
if ((Test-Path "$env:LOCALAPPDATA\Microsoft\OneDrive\OneDrive.exe") -or (Test-Path "$env:ProgramFiles\Microsoft OneDrive\OneDrive.exe")) {
    Warn 'O OneDrive ainda aparece instalado (a sincronização foi desligada por política)'
} else { Ok 'OneDrive removido' }
""",
)


def _remove(id_: str, title: str, desc: str, patterns: list[str], order: int, section: str,
            default: bool = True, note: str = "", glyph: str = "") -> None:
    pats = ", ".join("'" + p + "'" for p in patterns)
    _add(id=id_, page=PAGE_REMOVER, section=section, order=order, default=default, note=note, glyph=glyph,
         title=title, desc=desc, script=f"Remove-App @({pats})\n")


_remove("remove_copilot", "Copilot e Microsoft 365 (Office Hub)",
        "O app do Copilot e o “Microsoft 365” que só faz propaganda do Office.",
        ["Microsoft.Copilot", "Microsoft.MicrosoftOfficeHub", "Microsoft.Windows.Ai.Copilot.Provider"], 80, "Microsoft")
_remove("remove_outlook", "Outlook (novo) e Email e Calendário",
        "Clientes de e-mail que vêm de fábrica.",
        ["Microsoft.OutlookForWindows", "microsoft.windowscommunicationsapps"], 81, "Microsoft")
_remove("remove_teams", "Microsoft Teams",
        "O Teams pessoal que abre sozinho com o Windows.",
        ["MSTeams", "MicrosoftTeams"], 81, "Microsoft")
_remove("remove_bing", "Notícias, Clima e Bing",
        "Apps do MSN/Bing.",
        ["Microsoft.BingNews", "Microsoft.BingWeather", "Microsoft.BingSearch", "Microsoft.BingFinance",
         "Microsoft.BingSports", "Microsoft.BingTranslator"], 82, "Microsoft")
_remove("remove_tips", "Dicas, Obter Ajuda e Hub de Comentários",
        "Apps de “primeiros passos” e pesquisas de satisfação.",
        ["Microsoft.Getstarted", "Microsoft.GetHelp", "Microsoft.WindowsFeedbackHub"], 82, "Microsoft")
_remove("remove_phonelink", "Vincular ao Celular (Phone Link)",
        "Fica rodando em segundo plano mesmo sem celular conectado (citado no vídeo).",
        ["Microsoft.YourPhone", "MicrosoftWindows.CrossDevice"], 83, "Microsoft")
_remove("remove_misc", "Mapas, Pessoas, To Do, Power Automate e outros",
        "Também: Family, Dev Home, Cortana, Skype, Filmes e TV, Paint 3D, Visualizador 3D, Mixed Reality.",
        ["Microsoft.WindowsMaps", "Microsoft.People", "Microsoft.Todos", "Microsoft.PowerAutomateDesktop",
         "MicrosoftCorporationII.MicrosoftFamily", "Microsoft.Windows.DevHome", "Microsoft.549981C3F5F10",
         "Microsoft.SkypeApp", "Microsoft.ZuneVideo", "Microsoft.MSPaint", "Microsoft.Microsoft3DViewer",
         "Microsoft.MixedReality.Portal", "Microsoft.Print3D", "Microsoft.Wallet", "Microsoft.OneConnect",
         "Microsoft.Messaging", "Microsoft.MicrosoftJournal"], 83, "Microsoft")
_remove("remove_widgets", "Widgets",
        "Remove o pacote do painel de Widgets.",
        ["MicrosoftWindows.Client.WebExperience"], 84, "Microsoft")
_remove("remove_clipchamp", "Clipchamp",
        "Editor de vídeo online pré-instalado.",
        ["Clipchamp.Clipchamp"], 85, "Pré-instalados")
_remove("remove_games", "Paciência e jogos pré-instalados",
        "Microsoft Solitaire Collection, Candy Crush e afins.",
        ["Microsoft.MicrosoftSolitaireCollection", "Microsoft.MicrosoftMahjong", "*CandyCrush*", "king.com.*",
         "*BubbleWitch*", "*MarchofEmpires*", "*HiddenCity*", "*FarmVille*", "*RoyalRevolt*"], 85, "Pré-instalados")
_remove("remove_promos", "Spotify, TikTok, Disney+, Instagram, LinkedIn...",
        "Atalhos e apps de parceiros que a Microsoft coloca no Iniciar.",
        ["SpotifyAB.SpotifyMusic", "*Disney*", "*TikTok*", "*Instagram*", "*Facebook*", "*Twitter*",
         "*Netflix*", "*AmazonVideo*", "*PrimeVideo*", "7EE7776C.LinkedInforWindows", "*Duolingo*",
         "*PicsArt*", "*Flipboard*", "*Hulu*", "*Shazam*", "*WinZipUniversal*", "*PandoraMediaInc*",
         "AdobeSystemsIncorporated.AdobePhotoshopExpress", "*EclipseManager*", "*ActiproSoftware*"], 86, "Pré-instalados")
_remove("remove_xbox", "App Xbox e Xbox Game Bar",
        "O app Xbox e a sobreposição Win+G.",
        ["Microsoft.GamingApp", "Microsoft.XboxApp", "Microsoft.XboxGamingOverlay", "Microsoft.XboxGameOverlay",
         "Microsoft.XboxSpeechToTextOverlay"], 87, "Pré-instalados", default=False,
        note="Alguns jogos da Steam pedem conta Xbox. O login Xbox em si é mantido, mas deixei desmarcado por segurança.")


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------
TASKS.sort(key=lambda t: t.order)
BY_ID: dict[str, Task] = {t.id: t for t in TASKS}


def tasks_for_page(page: str) -> list[Task]:
    return [t for t in TASKS if t.page == page]


def video_tasks() -> list[Task]:
    return [t for t in TASKS if t.video]


def ordered(ids) -> list[Task]:
    wanted = set(ids)
    return [t for t in TASKS if t.id in wanted]


def build_script(task: Task) -> str:
    return PRELUDE + "\n# ---- " + task.id + " ----\n" + task.script
