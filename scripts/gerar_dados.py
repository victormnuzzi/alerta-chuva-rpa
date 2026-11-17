"""Gera os dados simulados (inscricoes ficticias e cenarios de chuva).

Usa semente fixa, entao sempre gera a mesma coisa. Nenhum dado e de pessoa real.
"""
import json
import os
import random

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rnd = random.Random(2026)

NOMES = ["Ana", "Bruno", "Carla", "Diego", "Elisa", "Felipe", "Gabriela", "Hugo", "Isabela", "João",
         "Larissa", "Marcos", "Natália", "Otávio", "Paula", "Rafael", "Sofia", "Tiago", "Vanessa", "Wagner"]
SOBRENOMES = ["Silva", "Souza", "Oliveira", "Santos", "Lima", "Pereira", "Costa", "Almeida", "Ferreira", "Rocha"]

with open(os.path.join(BASE, "config", "municipios.json"), encoding="utf-8") as _f:
    municipios = json.load(_f)
codigos = [m["codigo_ibge"] for m in municipios]
pesos = [m["populacao"] for m in municipios]


def inscricao(i):
    nome = f"{rnd.choice(NOMES)} {rnd.choice(SOBRENOMES)}"
    usuario = nome.lower().replace(" ", ".").encode("ascii", "ignore").decode() + str(i)
    return {
        "id_inscricao": f"INS-{i:05d}",
        "nome": nome,
        "email": f"{usuario}@exemplo.com.br",
        "telefone": f"(11) 9{rnd.randint(1000, 9999)}-{rnd.randint(1000, 9999)}",
        "codigo_ibge": rnd.choices(codigos, weights=pesos)[0],
        "canal": rnd.choice(["email", "sms"]),
        "aceite_lgpd": True,
        "ativo": True,
    }


linhas = []
for i in range(1, 301):
    r = inscricao(i)
    sorteio = rnd.random()
    if sorteio < 0.04:
        r["email"] = r["email"].replace("@", "")  # e-mail inválido
    elif sorteio < 0.08:
        r["telefone"] = "1234"  # telefone inválido
    elif sorteio < 0.10:
        r["aceite_lgpd"] = False  # sem consentimento
    elif sorteio < 0.12:
        r["codigo_ibge"] = "3304557"  # Rio de Janeiro: fora da região
    elif sorteio < 0.13:
        r["ativo"] = False  # cancelou a inscrição
    linhas.append(json.dumps(r, ensure_ascii=False))
    if rnd.random() < 0.03:  # duplicada (mesmo e-mail e cidade)
        dup = dict(r, id_inscricao=f"INS-{i:05d}-DUP")
        linhas.append(json.dumps(dup, ensure_ascii=False))
linhas.insert(57, '{"id_inscricao": "INS-QUEBRADA", "nome": ')  # linha corrompida

os.makedirs(os.path.join(BASE, "dados", "entrada"), exist_ok=True)
with open(os.path.join(BASE, "dados", "entrada", "inscricoes.jsonl"), "w", encoding="utf-8") as f:
    f.write("\n".join(linhas) + "\n")


# Cenários de chuva
def serie(total, pico_hora=17, pico=None):
    """24 valores horários somando ~total, concentrados à tarde."""
    pesos_h = [0.2 + (3 if abs(h - pico_hora) <= 2 else 0) + rnd.random() * 0.3 for h in range(24)]
    s = sum(pesos_h)
    valores = [round(total * w / s, 1) for w in pesos_h]
    if pico is not None:
        valores[pico_hora] = pico
    return valores


seco = {c: serie(rnd.uniform(0, 2)) for c in codigos}

chuva_forte = {c: serie(rnd.uniform(0.5, 4)) for c in codigos}
chuva_forte["3550308"] = serie(62)  # São Paulo: Muito forte
chuva_forte["3518800"] = serie(36)  # Guarulhos: Forte
chuva_forte["3534401"] = serie(12)  # Osasco: Moderado (não notifica)
chuva_forte["3513801"] = serie(2, pico=16.0)  # Diadema: ~18 mm (Moderado), mas 16 mm em 1 h escala p/ Forte

dados_invalidos = dict(chuva_forte)
dados_invalidos["3505708"] = serie(10)[:-1] + [-5.0]  # Barueri: valor negativo
dados_invalidos["3552809"] = [None] * 6 + serie(5)[6:]  # Taboão: 6 horas faltando
del dados_invalidos["3516408"]  # Franco da Rocha: sem dado

os.makedirs(os.path.join(BASE, "dados", "cenarios"), exist_ok=True)
for nome, dados in [("seco", seco), ("chuva-forte", chuva_forte), ("dados-invalidos", dados_invalidos)]:
    with open(os.path.join(BASE, "dados", "cenarios", f"{nome}.json"), "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=1)

print(f"{len(linhas)} linhas de inscrição e 3 cenários gerados.")
