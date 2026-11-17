# Testes

Para rodar:

```
python -m unittest discover -s tests -v
```

Os testes rodam numa pasta temporária e não usam internet (a resposta da API é simulada).

- **Sucesso:** cenário sem chuva, painel gerado com os 12 municípios
- **Decisão:** classificação dos níveis, chuva concentrada subindo para Forte, aviso que não se repete
- **Falha:** API fora do ar (3 tentativas), uso do cache, dados inválidos, arquivo de inscrições faltando
- **LGPD:** e-mail não aparece nos logs nem no painel

## Evidências

Na pasta `evidencias/` estão as saídas de execuções reais do robô:

1. `1_sucesso.txt`: previsão real da Open-Meteo
2. `2_decisao_chuva_forte.txt`: cenário de temporal (SP, Guarulhos e Diadema em alerta)
3. `3_falha_api_fora.txt`: API fora do ar, robô tenta 3 vezes e usa o cache
4. `4_falha_dados_invalidos.txt`: 3 cidades com dado ruim são ignoradas e as outras seguem
5. `5_testes.txt`: resultado dos testes
