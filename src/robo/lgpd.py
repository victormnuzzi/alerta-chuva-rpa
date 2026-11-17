"""Funcoes de LGPD: hash do email, mascara do telefone/nome e limpeza dos logs."""
import hashlib
import os
import re

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TEL_RE = re.compile(r"(?<![\w-])\(?\d{2}\)?\s?9?\d{4}-?\d{4}(?!\w)")  # nao pega numero grudado em letra (ex: id da execucao)


def _sal():
    # O "sal" do hash vem de variável de ambiente, nunca do código.
    return os.environ.get("RPA_HASH_SALT", "sal-padrao-apenas-para-desenvolvimento")


def hash_email(email):
    """SHA-256 do e-mail normalizado. Não dá para ler, mas permite comparar."""
    normal = email.strip().lower()
    return hashlib.sha256((_sal() + normal).encode("utf-8")).hexdigest()


def mascarar_telefone(telefone):
    """(11) 98765-4321 -> (11) *****-4321"""
    digitos = re.sub(r"\D", "", telefone)
    if len(digitos) < 10:
        return "***"
    return f"({digitos[:2]}) *****-{digitos[-4:]}"


def mascarar_nome(nome):
    """Ana Souza Lima -> Ana S."""
    partes = nome.split()
    if not partes:
        return "***"
    if len(partes) == 1:
        return partes[0]
    return f"{partes[0]} {partes[-1][0]}."


def sanitizar_texto(texto):
    """Rede de segurança para logs: apaga qualquer e-mail/telefone que escape."""
    texto = _EMAIL_RE.sub("[email-removido]", texto)
    return _TEL_RE.sub("[telefone-removido]", texto)
