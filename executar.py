"""Roda o robo.

Exemplos:
  python executar.py
  python executar.py --cenario chuva-forte
  python executar.py --simular-falha-api
  python executar.py --inscricoes nao_existe.jsonl
"""
import argparse
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "src"))

from robo.main import CENARIOS, executar  # noqa: E402


def main():
    for fluxo in (sys.stdout, sys.stderr):  # acentos corretos no Windows, inclusive com '>' para arquivo
        fluxo.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Robô RPA - Alerta Chuva SP")
    ap.add_argument("--cenario", choices=CENARIOS, default="real",
                    help="real = Open-Meteo; demais = arquivos em dados/cenarios/")
    ap.add_argument("--simular-falha-api", action="store_true", help="força a API a falhar")
    ap.add_argument("--inscricoes", help="caminho alternativo do arquivo de inscrições")
    args = ap.parse_args()

    codigo, resumo = executar(BASE, cenario=args.cenario, simular_falha_api=args.simular_falha_api,
                              arquivo_inscricoes=args.inscricoes)
    print("\n===== RESUMO DA EXECUÇÃO =====")
    for k, v in resumo.items():
        print(f"{k:35s} {v}")
    sys.exit(codigo)


if __name__ == "__main__":
    main()
