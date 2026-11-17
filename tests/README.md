# Testes e evidências

## Testes automatizados

```bash
python -m unittest discover -s tests -v
```

Cada teste roda numa cópia temporária do projeto, **sem internet** (a API é simulada) e sem mexer nos dados reais.

| Grupo | Teste | O que prova |
|---|---|---|
| Sucesso | `test_cenario_seco_gera_painel_sem_alertas` | Fluxo completo, 12 municípios, painel gerado |
| Sucesso | `test_api_real_simulada_responde_ok` | Leitura correta do formato da Open-Meteo |
| Sucesso | `test_log_registra_execucao_com_data_hora` | Log de auditoria com data e hora e resumo em CSV |
| Decisão | `test_classificacao_por_acumulado` | Baixo, Moderado, Forte e Muito forte |
| Decisão | `test_escalonamento_por_chuva_concentrada` | 16 mm em 1 h sobe para Forte |
| Decisão | `test_so_notifica_forte_e_muito_forte` | Moderado não notifica |
| Decisão | `test_notifica_apenas_inscritos_do_municipio_em_alerta` | Filtro por município |
| Decisão | `test_nao_repete_aviso_na_segunda_execucao` | Ninguém recebe o mesmo aviso duas vezes |
| Falha | `test_api_fora_do_ar_faz_retry_e_nao_quebra` | 3 tentativas por município, status PARCIAL |
| Falha | `test_api_fora_do_ar_usa_cache_recente` | Recuperação pelo cache |
| Falha | `test_http_404_nao_repete` | Erro 4xx não é repetido |
| Falha | `test_dados_invalidos_isolados_por_municipio` | 3 municípios ruins, 9 seguem |
| Falha | `test_validacao_rejeita_valor_negativo` | Regra de qualidade |
| Falha | `test_arquivo_de_inscricoes_ausente` | Painel sai, envio é bloqueado e registrado |
| Falha | `test_config_ausente_e_falha_fatal` | Código 2, sem falha silenciosa |
| Falha | `test_inscricoes_invalidas_e_duplicadas_sao_rejeitadas` | JSON quebrado, e-mail inválido, duplicada |
| LGPD | `test_mascaras` | Hash e máscaras |
| LGPD | `test_nenhum_email_ou_telefone_em_claro_nas_saidas` | Nada pessoal em logs ou saídas |

Resultado: **18 testes, todos OK**. Veja [evidencias/08_testes_automatizados.txt](evidencias/08_testes_automatizados.txt).

## Evidências de execução real (pasta `evidencias/`)

| Arquivo | Cenário | Resultado |
|---|---|---|
| `01_sucesso_api_real.txt` | Previsão real da Open-Meteo | SUCESSO: 12 municípios, nenhum alerta (tempo seco no dia) |
| `02_decisao_chuva_forte.txt` | Cenário de chuva forte | 3 alertas (SP Muito forte, Guarulhos Forte, Diadema Forte **por escalonamento**), 183 avisos |
| `03_decisao_sem_duplicar.txt` | Mesmo cenário rodado de novo | 0 avisos novos, 183 ignorados por já terem sido enviados |
| `04_falha_api_retry_cache.txt` | API fora do ar, com cache | 3 tentativas por município e depois recuperação pelo cache |
| `05_falha_api_sem_cache.txt` | API fora do ar, sem cache | PARCIAL: 12 municípios "Sem dados", todos com ERROR no log |
| `06_falha_dados_invalidos.txt` | Valor negativo, horas faltando, município ausente | PARCIAL: 3 rejeitados, 9 processados |
| `07_falha_inscricoes_ausentes.txt` | Arquivo de inscrições não existe | PARCIAL: painel gerado, envio bloqueado |
| `09_execucao_final_api_real.txt` | Previsão real de novo | SUCESSO |
