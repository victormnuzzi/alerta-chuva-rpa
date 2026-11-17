"""Logs do robo: log normal (robo_AAAA-MM-DD.log) e um resumo por execucao (execucoes.csv)."""
import csv
import logging
import os
import uuid
from datetime import datetime

from .lgpd import sanitizar_texto


class _FiltroLGPD(logging.Filter):
    def filter(self, record):
        record.msg = sanitizar_texto(str(record.msg))
        return True


class Auditoria:
    def __init__(self, pasta_logs, agora = None, console = True):
        self.pasta = pasta_logs
        os.makedirs(self.pasta, exist_ok=True)
        self.inicio = agora or datetime.now()
        self.execucao_id = self.inicio.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
        self.contadores = {}
        self.erros = []

        self.log = logging.getLogger(f"robo.{self.execucao_id}")
        self.log.setLevel(logging.INFO)
        self.log.propagate = False
        fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%Y-%m-%d %H:%M:%S")
        arq = logging.FileHandler(
            os.path.join(self.pasta, f"robo_{self.inicio:%Y-%m-%d}.log"), encoding="utf-8"
        )
        arq.setFormatter(fmt)
        arq.addFilter(_FiltroLGPD())
        self.log.addHandler(arq)
        if console:
            tela = logging.StreamHandler()
            tela.setFormatter(fmt)
            tela.addFilter(_FiltroLGPD())
            self.log.addHandler(tela)

    def evento(self, tipo, nivel = "INFO", **dados):
        # escreve uma linha no log, ex: [MUNICIPIO_PROCESSADO] municipio=Osasco nivel_alerta=Baixo
        texto = f"[{tipo}] " + " ".join(f"{k}={v}" for k, v in dados.items())
        if nivel == "ERROR":
            self.log.error(texto)
        elif nivel == "CRITICAL":
            self.log.critical(texto)
        elif nivel == "WARNING":
            self.log.warning(texto)
        else:
            self.log.info(texto)
        if nivel in ("ERROR", "CRITICAL"):
            self.erros.append(texto)

    def contar(self, chave, n = 1):
        self.contadores[chave] = self.contadores.get(chave, 0) + n

    def finalizar(self, status):
        fim = datetime.now()
        resumo = {
            "execucao_id": self.execucao_id,
            "inicio": self.inicio.isoformat(timespec="seconds"),
            "fim": fim.isoformat(timespec="seconds"),
            "duracao_s": round((fim - self.inicio).total_seconds(), 2),
            "status": status,
            "municipios_processados": self.contadores.get("municipios_processados", 0),
            "municipios_com_erro": self.contadores.get("municipios_com_erro", 0),
            "municipios_via_cache": self.contadores.get("municipios_via_cache", 0),
            "alertas_emitidos": self.contadores.get("alertas_emitidos", 0),
            "inscritos_validos": self.contadores.get("inscritos_validos", 0),
            "inscritos_rejeitados": self.contadores.get("inscritos_rejeitados", 0),
            "notificacoes_enviadas": self.contadores.get("notificacoes_enviadas", 0),
            "notificacoes_ignoradas_duplicadas": self.contadores.get("notificacoes_duplicadas", 0),
            "total_erros": len(self.erros),
        }
        caminho = os.path.join(self.pasta, "execucoes.csv")
        novo = not os.path.exists(caminho)
        with open(caminho, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(resumo.keys()))
            if novo:
                w.writeheader()
            w.writerow(resumo)
        self.evento("FIM_EXECUCAO", "INFO" if status == "SUCESSO" else "WARNING", **resumo)
        for h in list(self.log.handlers):
            h.close()
            self.log.removeHandler(h)
        return resumo
