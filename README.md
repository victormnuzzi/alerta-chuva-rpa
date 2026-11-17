# Robô RPA: Alerta Chuva SP

**Global Solution 2026.2 · CitizenTech · Robotic Process Automation · Engenharia de Software 4º ano**

Este robô automatiza o processo que hoje seria manual no **Alerta Chuva SP**: ver a previsão de chuva de cada município da Grande São Paulo, decidir se o risco é alto e avisar os cidadãos inscritos. Ele roda sozinho de hora em hora, trata as falhas sem parar o processo, registra tudo em log de auditoria e publica o resultado num arquivo JSON que o painel do MVP lê.

| Integrante | RM |
|---|---|
| Cassio Valezzi | 551059 |
| Gabriel Antony Cadima | 98215 |
| Lucca Sabatini Tambellini | 98169 |
| Victor Nuzzi | 98209 |

**Vídeo:** _colocar link_

---

## O problema e o processo automatizado

Sem o robô, alguém da equipe teria que, para **cada um dos 12 municípios**, consultar a previsão, somar a chuva das próximas 24 h, comparar com a tabela de níveis, filtrar os inscritos daquela cidade, conferir se já foram avisados e mandar a mensagem. Isso é repetitivo, lento e sujeito a erro, e o aviso precisa sair **antes** da chuva.

| Etapa | Manual (antes) | Robô (agora) |
|---|---|---|
| Consultar previsão | Abrir site por cidade | Open-Meteo via API, com 3 tentativas e cache |
| Classificar risco | Olhar tabela | Regra de negócio configurável (`config/regras.json`) |
| Separar inscritos | Planilha | Validação, deduplicação e mascaramento automáticos |
| Avisar | Mensagem por mensagem | Lote por município, sem repetir aviso |
| Registro | Nenhum | Log com data e hora, JSONL de auditoria e CSV de execuções |
| Atualizar o MVP | Editar à mão | `saida/painel_alertas.json` gravado de forma atômica |

## Arquitetura

```
             ┌──────────────── a cada hora (Agendador de Tarefas) ─────────────────────┐
             ▼                                                                         │
 config/ ─► Carregar configuração ─► Ler e validar inscrições (JSONL)                  │
                                         │                                             │
                                         ▼                                             │
                    ┌──── para cada município (12) ────────────────────────┐           │
 Open-Meteo API ──► │ Coletar 24 h (retry+backoff) ─► válido? ─não─► cache?│           │
                    │                                  │sim        sim/não │           │
                    │                    Classificar nível ◄─────┘   └► "Sem dados"     │
                    │                                  │                   │           │
                    │                   Forte/Muito forte? ─sim─► Notificar (sem dup.) │
                    └───────────────────────────────────────────────────────┘           │
                                         ▼                                             │
                saida/painel_alertas.json ──► MVP (mvp/index.html)                     │
                saida/notificacoes/AAAA-MM-DD.jsonl                                    │
                logs/ (robo_*.log · auditoria.jsonl · execucoes.csv) ──────────────────┘
```

O fluxo completo em BPMN 2.0 está em [docs/processo_alerta_chuva.bpmn](docs/processo_alerta_chuva.bpmn). Ele abre em [bpmn.io](https://demo.bpmn.io) ou na página [docs/ver_bpmn.html](docs/ver_bpmn.html).

**Tecnologia:** Python 3.10+ **só com a biblioteca padrão** (não precisa de `pip install`). Escolhemos Python porque o código fica versionado no Git, roda em qualquer máquina e em CI, e pode ser testado automaticamente, o que não acontece com um fluxo em ferramenta visual.

## Estrutura do repositório

```
executar.py                 ponto de entrada (linha de comando)
src/robo/
  main.py                   orquestração do fluxo
  coleta.py                 Open-Meteo: retry, backoff, validação, cache
  regras.py                 classificação do nível de alerta (decisões)
  inscritos.py              leitura/validação/deduplicação das inscrições
  notificacao.py            envio simulado e controle para não repetir aviso
  auditoria.py              logs, eventos JSONL, resumo CSV
  lgpd.py                   hash, máscaras e limpeza de dados pessoais nos logs
config/                     municípios (IBGE, Censo 2022) e regras de negócio
dados/entrada/              inscrições SIMULADAS (com erros de propósito)
dados/cenarios/             séries de chuva para demonstrar cada caminho
mvp/index.html              painel do MVP que consome a saída do robô
docs/                       fluxo BPMN do processo
logs/                       amostras reais de log (sem dados sensíveis)
saida/                      painel e notificações gerados
tests/                      testes automatizados + evidências de execução
assets/                     prints para o relatório
```

## Como rodar

```bash
python executar.py                                   # previsão real (Open-Meteo)
python executar.py --cenario chuva-forte             # demonstra a decisão de alerta
python executar.py --simular-falha-api               # API fora do ar: retry e depois cache
python executar.py --cenario dados-invalidos         # dados ruins isolados por município
python executar.py --cenario chuva-forte --inscricoes nao_existe.jsonl   # arquivo ausente
python -m unittest discover -s tests -v              # roda os testes
```

Para ver o MVP, abra um servidor local na raiz do projeto e acesse `http://localhost:8000/mvp/`:

```bash
python -m http.server 8000
```

**Códigos de saída:** `0` sucesso · `1` parcial (houve erros, todos tratados e registrados) · `2` falha fatal (configuração inválida).

**Variável de ambiente:** `RPA_HASH_SALT` (sal do hash de e-mail).

## Regras de negócio

| Nível | Chuva prevista em 24 h | Notifica? |
|---|---|---|
| Baixo | < 5 mm | não |
| Moderado | 5 a 19,9 mm | não |
| Forte | 20 a 49,9 mm | **sim** |
| Muito forte | ≥ 50 mm | **sim** |

* **Escalonamento por intensidade:** se a maior chuva em 1 h for de 15 mm ou mais, o nível sobe para no mínimo **Forte**, mesmo com acumulado menor. Chuva concentrada é a que mais alaga.
* As faixas são as mesmas da tabela `dim_nivel_alerta` do pipeline de Big Data do projeto.
* **Sem aviso repetido:** cada inscrito recebe no máximo 1 aviso por município e por dia. Só recebe de novo se o nível **subir**, por exemplo de Forte para Muito forte.
* **Só avisa quem pode receber:** precisa ter consentimento LGPD, estar ativo, ter e-mail e telefone válidos e morar em município monitorado.

Todos os limites ficam em `config/regras.json`, então dá para mudar sem alterar o código.

## Exceções e resiliência

| Situação | Tratamento | Onde ver |
|---|---|---|
| API fora do ar ou timeout | 3 tentativas com espera exponencial; depois usa o cache de até 6 h; sem cache, marca "Sem dados" e segue | evidência 3 |
| HTTP 4xx | Não repete (erro do pedido), registra e segue | — |
| Dado de chuva inválido (negativo, faltando, não numérico) | Rejeita só aquele município | evidência 4 |
| Arquivo de inscrições ausente | Painel é gerado mesmo assim; envio bloqueado e registrado como ERROR | teste `test_sem_arquivo_de_inscricoes` |
| Linha corrompida, e-mail ou telefone inválido, duplicada, sem consentimento | Inscrição rejeitada e contada por motivo | log `INSCRICOES_CARREGADAS` |
| Estado de notificações corrompido | Aviso no log e o controle recomeça | `notificacao.py` |
| Configuração ausente ou inválida | Falha fatal **explícita** (código 2) | teste `test_config_ausente_e_falha_fatal` |
| Queda durante a gravação | Escrita atômica (`.tmp` e depois `os.replace`), então o MVP nunca lê arquivo pela metade | `main.py` |

Nenhuma falha é silenciosa: todas geram evento `WARNING` ou `ERROR` e mudam o status da execução.

## Logs e auditoria

* `logs/robo_AAAA-MM-DD.log`: log legível com data e hora, nível e evento
* `logs/auditoria.jsonl`: um evento estruturado por linha (`INICIO_EXECUCAO`, `MUNICIPIO_PROCESSADO`, `API_TENTATIVA_FALHOU`, `CLIMA_CACHE`, `FIM_EXECUCAO`…)
* `logs/execucoes.csv`: uma linha por execução com itens processados, sucessos, falhas, notificações e duração

## Integração com o MVP

O robô grava `saida/painel_alertas.json` e o painel em `mvp/index.html` lê esse arquivo a cada 60 s. O painel mostra o nível por município, a população em alerta e os avisos enviados. Também avisa quando os dados estão desatualizados (robô parado) ou quando algum município ficou sem dados.

## Segurança e LGPD

* As inscrições são **fictícias** (dados simulados).
* O e-mail vira **hash SHA-256 com sal** (o sal fica em variável de ambiente, não no código) e o telefone é **mascarado**: `(11) *****-1234`.
* Nome, e-mail e telefone **nunca** aparecem no painel, nas notificações gravadas ou nos logs. Um filtro em `auditoria.py` apaga qualquer e-mail ou telefone que escape, e um teste automatizado confere isso.
* Só recebe aviso quem deu consentimento (`aceite_lgpd = true`) e está ativo.

## Testes

9 testes automatizados, divididos em **sucesso**, **decisão**, **falha** e **LGPD**: `python -m unittest discover -s tests -v`. As saídas reais de cada cenário estão em [tests/evidencias/](tests/evidencias/). Veja também [tests/README.md](tests/README.md).

## Limitações

* O envio de e-mail e SMS é **simulado** (gravado em `saida/notificacoes/`), para não usar dados de pessoas reais.
* A população é a do Censo 2022, fixa em `config/municipios.json`.
* Os limiares são uma adaptação nossa. Não é aviso oficial: emergências, Defesa Civil 199.
