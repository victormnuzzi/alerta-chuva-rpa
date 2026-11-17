"""Le e valida as inscricoes (arquivo jsonl)."""
import json
import os
import re

from .lgpd import hash_email, mascarar_telefone

EMAIL_OK = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
CAMPOS = ("id_inscricao", "nome", "email", "telefone", "codigo_ibge", "canal", "aceite_lgpd")


class ArquivoInscricoesAusente(Exception):
    pass


def _motivo_invalido(reg, codigos_monitorados):
    faltando = [c for c in CAMPOS if c not in reg]
    if faltando:
        return "campos_ausentes"
    if reg.get("aceite_lgpd") is not True:
        return "sem_consentimento"
    if not reg.get("ativo", True):
        return "inscricao_inativa"
    if not EMAIL_OK.match(str(reg["email"]).strip()):
        return "email_invalido"
    if len(re.sub(r"\D", "", str(reg["telefone"]))) not in (10, 11):
        return "telefone_invalido"
    if str(reg["codigo_ibge"]) not in codigos_monitorados:
        return "municipio_nao_monitorado"
    if reg["canal"] not in ("email", "sms"):
        return "canal_invalido"
    return None


def carregar_inscritos(caminho, codigos_monitorados):
    """Devolve (inscritos_validos_protegidos, contagem_de_rejeicoes_por_motivo).

    Cada inscrito válido já sai protegido: e-mail vira hash e telefone é mascarado.
    """
    if not os.path.exists(caminho):
        raise ArquivoInscricoesAusente(f"arquivo não encontrado: {os.path.basename(caminho)}")

    validos = []
    rejeitados = {}  # motivo -> quantidade
    vistos = set()
    with open(caminho, encoding="utf-8") as f:
        for linha in f:  # repetição: lote de inscrições
            linha = linha.strip()
            if not linha:
                continue
            try:
                reg = json.loads(linha)
            except json.JSONDecodeError:
                rejeitados["linha_nao_json"] = rejeitados.get("linha_nao_json", 0) + 1
                continue
            if not isinstance(reg, dict):
                rejeitados["linha_nao_json"] = rejeitados.get("linha_nao_json", 0) + 1
                continue
            motivo = _motivo_invalido(reg, codigos_monitorados)  # decisão
            if motivo:
                rejeitados[motivo] = rejeitados.get(motivo, 0) + 1
                continue
            email_h = hash_email(reg["email"])
            chave = (email_h, str(reg["codigo_ibge"]))
            if chave in vistos:
                rejeitados["duplicado"] = rejeitados.get("duplicado", 0) + 1
                continue
            vistos.add(chave)
            validos.append({
                "id_inscricao": str(reg["id_inscricao"]),
                "codigo_ibge": str(reg["codigo_ibge"]),
                "canal": reg["canal"],
                "email_hash": email_h,
                "telefone_mascarado": mascarar_telefone(str(reg["telefone"])),
            })
    return validos, rejeitados
