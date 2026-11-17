"""Gera as notificacoes (envio simulado) sem mandar aviso repetido."""
import json
import os

from .regras import ordem_do_nivel


class Notificador:
    """Guarda em dados/estado/notificados.json o maior nível já avisado por
    (inscrito, município, dia). Só avisa de novo se o nível SUBIR."""

    def __init__(self, pasta_estado, pasta_saida, regras, auditoria, execucao_id):
        self.regras = regras
        self.aud = auditoria
        self.execucao_id = execucao_id
        self.arq_estado = os.path.join(pasta_estado, "notificados.json")
        self.pasta_saida = os.path.join(pasta_saida, "notificacoes")
        os.makedirs(pasta_estado, exist_ok=True)
        os.makedirs(self.pasta_saida, exist_ok=True)
        self.estado = self._ler_estado()

    def _ler_estado(self):
        try:
            with open(self.arq_estado, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError):
            self.aud.evento("ESTADO_CORROMPIDO", "WARNING",
                            detalhe="notificados.json ilegível; recomeçando o controle de duplicidade")
            return {}

    def salvar_estado(self):
        tmp = self.arq_estado + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.estado, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.arq_estado)

    def notificar_municipio(self, municipio, nivel, chuva_24h, inscritos, data_ref) -> tuple[int, int]:
        """Retorna (enviadas, ignoradas_por_duplicidade)."""
        enviadas = ignoradas = 0
        ordem = ordem_do_nivel(nivel, self.regras)
        arq = os.path.join(self.pasta_saida, f"{data_ref}.jsonl")
        mensagem = (f"Alerta Chuva SP: previsão de chuva {nivel.upper()} em {municipio['nome']} "
                    f"nas próximas 24 h ({chuva_24h:.0f} mm). Evite áreas de alagamento. "
                    f"Emergências: Defesa Civil 199.")
        with open(arq, "a", encoding="utf-8") as f:
            for insc in inscritos:  # repetição
                chave = f"{insc['id_inscricao']}|{municipio['codigo_ibge']}|{data_ref}"
                if self.estado.get(chave, -1) >= ordem:  # decisão: já avisado
                    ignoradas += 1
                    continue
                f.write(json.dumps({
                    "execucao_id": self.execucao_id,
                    "id_inscricao": insc["id_inscricao"],
                    "canal": insc["canal"],
                    "destino": insc["email_hash"][:12] if insc["canal"] == "email" else insc["telefone_mascarado"],
                    "codigo_ibge": municipio["codigo_ibge"],
                    "municipio": municipio["nome"],
                    "nivel": nivel,
                    "mensagem": mensagem,
                    "status": "ENVIADA_SIMULADA",
                }, ensure_ascii=False) + "\n")
                self.estado[chave] = ordem
                enviadas += 1
        return enviadas, ignoradas
