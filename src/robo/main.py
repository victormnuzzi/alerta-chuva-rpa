"""Fluxo principal do robo.

Saida: 0 = sucesso, 1 = parcial (teve erro tratado), 2 = falha (config quebrada).
"""
import json
import os
import time
import urllib.error
from datetime import datetime

from .auditoria import Auditoria
from .coleta import ClimaIndisponivel, ColetorClima, DadosClimaInvalidos, buscar_json_http
from .inscritos import ArquivoInscricoesAusente, carregar_inscritos
from .notificacao import Notificador
from .regras import classificar, deve_notificar

CENARIOS = ("real", "seco", "chuva-forte", "dados-invalidos")


def _ler_json(caminho):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def _falha_simulada(url, timeout):
    raise urllib.error.URLError("falha simulada: Open-Meteo fora do ar")


def _gravar_atomico(caminho, conteudo):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(conteudo, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)  # o MVP nunca lê um arquivo pela metade


def executar(base_dir, cenario="real", simular_falha_api=False, arquivo_inscricoes=None,
             agora=None, buscar_json=None, dormir=None, console=True):
    agora = (agora or datetime.now()).replace(minute=0, second=0, microsecond=0)

    def caminho(*partes):
        # monta o caminho de um arquivo dentro da pasta do projeto
        return os.path.join(base_dir, *partes)

    aud = Auditoria(caminho("logs"), console=console)
    aud.evento("INICIO_EXECUCAO", cenario=cenario, simular_falha_api=simular_falha_api,
               referencia=agora.isoformat(timespec="minutes"))

    # Configuração
    try:
        municipios = _ler_json(caminho("config", "municipios.json"))
        regras = _ler_json(caminho("config", "regras.json"))
        if cenario not in CENARIOS:
            raise ValueError(f"cenário desconhecido: {cenario}")
        fixture = None if cenario == "real" else _ler_json(caminho("dados", "cenarios", f"{cenario}.json"))
    except (OSError, ValueError) as e:
        aud.evento("CONFIG_INVALIDA", "CRITICAL", erro=type(e).__name__, detalhe=str(e))
        return 2, aud.finalizar("FALHA")

    # Inscrições
    codigos = {m["codigo_ibge"] for m in municipios}
    inscritos = None
    try:
        inscritos, rejeitados = carregar_inscritos(
            arquivo_inscricoes or caminho("dados", "entrada", "inscricoes.jsonl"), codigos)
        aud.contar("inscritos_validos", len(inscritos))
        aud.contar("inscritos_rejeitados", sum(rejeitados.values()))
        aud.evento("INSCRICOES_CARREGADAS", validos=len(inscritos), rejeitados=dict(rejeitados))
    except ArquivoInscricoesAusente as e:
        aud.evento("INSCRICOES_AUSENTES", "ERROR", detalhe=str(e),
                   consequencia="painel será gerado, notificações bloqueadas")

    # Coleta + decisão por município
    if buscar_json is None:
        buscar_json = _falha_simulada if simular_falha_api else buscar_json_http
    if dormir is None:
        dormir = time.sleep
    coletor = ColetorClima(regras, caminho("dados", "cache"), aud, buscar_json=buscar_json,
                           fixture=fixture, dormir=dormir)
    notificador = Notificador(caminho("dados", "estado"), caminho("saida"), regras, aud, aud.execucao_id)
    data_ref = agora.strftime("%Y-%m-%d")
    linhas = []

    for mun in municipios:  # repetição
        aud.contar("municipios_processados")
        base = {"codigo_ibge": mun["codigo_ibge"], "municipio": mun["nome"], "populacao": mun["populacao"]}
        try:
            clima = coletor.obter(mun, agora)
        except (ClimaIndisponivel, DadosClimaInvalidos) as e:
            aud.contar("municipios_com_erro")
            aud.evento("MUNICIPIO_SEM_DADOS", "ERROR", municipio=mun["nome"], detalhe=str(e))
            linhas.append({**base, "chuva_24h_mm": None, "max_1h_mm": None, "nivel": "Sem dados",
                           "motivo": "previsão indisponível", "fonte": "indisponivel",
                           "inscritos_ativos": None, "notificacoes_enviadas": 0})
            continue

        if clima["fonte"] == "cache":
            aud.contar("municipios_via_cache")
        horas = clima["horas"]
        total, pico = round(sum(horas), 1), round(max(horas), 1)
        nivel, motivo = classificar(total, pico, regras)
        do_municipio = [i for i in (inscritos or []) if i["codigo_ibge"] == mun["codigo_ibge"]]
        enviadas = 0

        if deve_notificar(nivel, regras):  # decisão
            aud.contar("alertas_emitidos")
            if inscritos is None:
                decisao = "ALERTA_SEM_ENVIO (inscrições indisponíveis)"
            else:
                enviadas, dup = notificador.notificar_municipio(mun, nivel, total, do_municipio, data_ref)
                aud.contar("notificacoes_enviadas", enviadas)
                aud.contar("notificacoes_duplicadas", dup)
                decisao = f"NOTIFICAR enviadas={enviadas} ja_avisados={dup}"
        else:
            decisao = "SEM_ALERTA"

        aud.evento("MUNICIPIO_PROCESSADO", municipio=mun["nome"], fonte=clima["fonte"],
                   chuva_24h_mm=total, max_1h_mm=pico, nivel_alerta=nivel, motivo=motivo, decisao=decisao)
        linhas.append({**base, "chuva_24h_mm": total, "max_1h_mm": pico, "nivel": nivel, "motivo": motivo,
                       "fonte": clima["fonte"],
                       "inscritos_ativos": len(do_municipio) if inscritos is not None else None,
                       "notificacoes_enviadas": enviadas})

    notificador.salvar_estado()

    # Entrega ao MVP
    em_alerta = [l for l in linhas if deve_notificar(l["nivel"], regras)]
    painel = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "referencia": agora.isoformat(timespec="minutes"),
        "janela_horas": regras["janela_horas"],
        "execucao_id": aud.execucao_id,
        "cenario": cenario,
        "resumo": {
            "municipios": len(linhas),
            "municipios_em_alerta": len(em_alerta),
            "populacao_em_alerta": sum(l["populacao"] for l in em_alerta),
            "municipios_sem_dados": sum(1 for l in linhas if l["fonte"] == "indisponivel"),
            "notificacoes_enviadas": sum(l["notificacoes_enviadas"] for l in linhas),
        },
        "municipios": linhas,
    }
    try:
        _gravar_atomico(caminho("saida", "painel_alertas.json"), painel)
        aud.evento("PAINEL_PUBLICADO", arquivo="saida/painel_alertas.json",
                   municipios_em_alerta=len(em_alerta))
    except OSError as e:
        aud.evento("PAINEL_FALHOU", "ERROR", erro=type(e).__name__, detalhe=str(e))

    status = "SUCESSO" if not aud.erros else "PARCIAL"
    return (0 if status == "SUCESSO" else 1), aud.finalizar(status)
