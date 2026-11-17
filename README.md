# Alerta Chuva SP - Robô RPA

Global Solution 2026.2 - Robotic Process Automation - Engenharia de Software 4º ano

## Integrantes

- Cassio Valezzi - RM 551059
- Gabriel Antony Cadima - RM 98215
- Lucca Sabatini Tambellini - RM 98169
- Victor Nuzzi - RM 98209

Vídeo: _colocar link_

## Sobre

O Alerta Chuva SP avisa os moradores da Grande São Paulo quando vai chover forte na cidade deles.

Sem automação, alguém teria que olhar a previsão das 12 cidades toda hora, ver se a chuva é forte, separar os inscritos de cada cidade e mandar o aviso. O robô faz isso sozinho:

1. Lê a configuração (cidades e regras) e as inscrições
2. Para cada cidade, busca a previsão das próximas 24 h na API da Open-Meteo
3. Classifica o nível de alerta
4. Se for Forte ou Muito forte, avisa os inscritos daquela cidade (envio simulado)
5. Grava o resultado em `saida/painel_alertas.json`, que é lido pelo painel do MVP (`mvp/index.html`)
6. Registra tudo em `logs/`

O fluxo em BPMN está em `docs/processo_alerta_chuva.bpmn` (dá para abrir no [bpmn.io](https://demo.bpmn.io)).

Feito em Python, só com a biblioteca padrão. Não precisa instalar nada.

## Como rodar

```
python executar.py                              # previsão real
python executar.py --cenario chuva-forte        # simula um temporal
python executar.py --simular-falha-api          # simula a API fora do ar
python executar.py --cenario dados-invalidos    # simula dados com erro
python -m unittest discover -s tests -v         # testes
```

Para ver o painel do MVP:

```
python -m http.server 8000
```

e abrir http://localhost:8000/mvp/

## Regras

| Nível | Chuva em 24 h | Avisa? |
|---|---|---|
| Baixo | menos de 5 mm | não |
| Moderado | 5 a 20 mm | não |
| Forte | 20 a 50 mm | sim |
| Muito forte | mais de 50 mm | sim |

- Se chover 15 mm ou mais em 1 hora, sobe para Forte (chuva concentrada é a que mais alaga).
- A mesma pessoa não recebe o mesmo aviso duas vezes no dia. Só recebe de novo se o nível aumentar.
- Só recebe aviso quem aceitou os termos (LGPD), está ativo e tem e-mail e telefone válidos.

Os valores ficam em `config/regras.json`.

## Erros tratados

- **API fora do ar:** tenta 3 vezes. Se não der, usa a última previsão salva (até 6 h). Se não tiver, marca a cidade como "Sem dados" e continua com as outras.
- **Dado de chuva inválido** (negativo, faltando hora etc.): ignora só aquela cidade.
- **Arquivo de inscrições não existe:** gera o painel mesmo assim, mas não envia aviso.
- **Inscrição com erro** (e-mail inválido, duplicada, linha quebrada): é descartada e contada no log.
- **Config faltando:** para o robô com erro.

O robô termina com código 0 (ok), 1 (teve erro, mas continuou) ou 2 (erro grave).

## Logs

- `logs/robo_AAAA-MM-DD.log`: o que aconteceu em cada execução, com data e hora
- `logs/execucoes.csv`: uma linha por execução (status, cidades processadas, erros, avisos enviados)

## LGPD

- As inscrições são fictícias.
- O e-mail vira hash (SHA-256) e o telefone é mascarado: `(11) *****-1234`.
- Nome, e-mail e telefone não aparecem nos logs nem no painel.
- O "sal" do hash vem da variável de ambiente `RPA_HASH_SALT`.

## Pastas

- `src/robo/`: código do robô
- `config/`: cidades e regras
- `dados/`: inscrições e cenários de teste
- `mvp/`: painel que mostra o resultado
- `docs/`: fluxo BPMN
- `logs/`: logs gerados
- `saida/`: painel e avisos gerados
- `tests/`: testes e evidências
- `assets/`: prints
