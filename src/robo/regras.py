"""Regras para classificar o nivel de alerta."""


def classificar(chuva_24h_mm, max_1h_mm, regras):
    """Devolve (nivel, motivo).

    1) Nível pelo acumulado previsto em 24 h (maior faixa cujo mínimo foi atingido).
    2) Escalonamento: chuva concentrada em 1 h sobe o nível para no mínimo 'Forte'.
    """
    niveis = regras["niveis"]  # no json ja estao do menor para o maior
    escolhido = niveis[0]
    for faixa in niveis:  # repetição sobre as faixas
        if chuva_24h_mm >= faixa["min_mm_24h"]:  # decisão
            escolhido = faixa
    motivo = f"acumulado {chuva_24h_mm:.1f} mm >= {escolhido['min_mm_24h']} mm"

    esc = regras.get("escalonamento_intensidade")
    if esc and max_1h_mm >= esc["max_1h_mm"]:
        minimo = next(n for n in niveis if n["nivel"] == esc["nivel_minimo"])
        if minimo["ordem"] > escolhido["ordem"]:
            escolhido = minimo
            motivo = f"escalonado: {max_1h_mm:.1f} mm em 1 h >= {esc['max_1h_mm']} mm"
    return escolhido["nivel"], motivo


def ordem_do_nivel(nivel, regras):
    for n in regras["niveis"]:
        if n["nivel"] == nivel:
            return n["ordem"]
    return -1


def deve_notificar(nivel, regras):
    return nivel in regras["niveis_que_notificam"]
