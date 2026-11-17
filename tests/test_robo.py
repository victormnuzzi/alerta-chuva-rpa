"""Testes do robô: cenários de SUCESSO, DECISÃO e FALHA.

Rodar:  python -m unittest discover -s tests -v
Cada teste roda numa cópia temporária do projeto, sem rede e sem tocar nos dados reais.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from robo.coleta import DadosClimaInvalidos, validar_horas  # noqa: E402
from robo.inscritos import carregar_inscritos  # noqa: E402
from robo.lgpd import hash_email, mascarar_nome, mascarar_telefone  # noqa: E402
from robo.main import executar  # noqa: E402
from robo.regras import classificar  # noqa: E402

AGORA = datetime(2026, 11, 16, 10, 0)


def ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


REGRAS = json.loads(ler(os.path.join(RAIZ, "config", "regras.json")))


def resposta_api(valor_hora):
    """Resposta no formato da Open-Meteo, com 48 horas a partir de 00:00."""
    tempos = [f"2026-11-{16 + h // 24:02d}T{h % 24:02d}:00" for h in range(48)]
    return {"hourly": {"time": tempos, "precipitation": [valor_hora] * 48}}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        for pasta in ("config", os.path.join("dados", "entrada"), os.path.join("dados", "cenarios")):
            shutil.copytree(os.path.join(RAIZ, pasta), os.path.join(self.dir, pasta))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def rodar(self, **kw):
        kw.setdefault("agora", AGORA)
        kw.setdefault("dormir", lambda s: None)
        return executar(self.dir, console=False, **kw)

    def painel(self):
        with open(os.path.join(self.dir, "saida", "painel_alertas.json"), encoding="utf-8") as f:
            return json.load(f)

    def logs(self):
        texto = ""
        for nome in os.listdir(os.path.join(self.dir, "logs")):
            with open(os.path.join(self.dir, "logs", nome), encoding="utf-8") as f:
                texto += f.read()
        return texto


# ============================================================ SUCESSO
class TestSucesso(Base):
    def test_cenario_seco_gera_painel_sem_alertas(self):
        codigo, resumo = self.rodar(cenario="seco")
        self.assertEqual(codigo, 0)
        self.assertEqual(resumo["status"], "SUCESSO")
        p = self.painel()
        self.assertEqual(len(p["municipios"]), 12)
        self.assertEqual(p["resumo"]["municipios_em_alerta"], 0)
        self.assertEqual(resumo["notificacoes_enviadas"], 0)

    def test_api_real_simulada_responde_ok(self):
        codigo, _ = self.rodar(cenario="real", buscar_json=lambda url, t: resposta_api(0.1))
        self.assertEqual(codigo, 0)
        self.assertTrue(all(m["fonte"] == "api" for m in self.painel()["municipios"]))

    def test_log_registra_execucao_com_data_hora(self):
        self.rodar(cenario="seco")
        self.assertTrue(os.path.exists(os.path.join(self.dir, "logs", "execucoes.csv")))
        primeira = ler(os.path.join(self.dir, "logs", "auditoria.jsonl")).splitlines()[0]
        evento = json.loads(primeira)
        self.assertEqual(evento["tipo"], "INICIO_EXECUCAO")
        datetime.fromisoformat(evento["data_hora"])  # data/hora válida


# ============================================================ DECISÃO
class TestDecisao(Base):
    def test_classificacao_por_acumulado(self):
        self.assertEqual(classificar(3, 1, REGRAS)[0], "Baixo")
        self.assertEqual(classificar(10, 2, REGRAS)[0], "Moderado")
        self.assertEqual(classificar(35, 5, REGRAS)[0], "Forte")
        self.assertEqual(classificar(60, 9, REGRAS)[0], "Muito forte")

    def test_escalonamento_por_chuva_concentrada(self):
        nivel, motivo = classificar(17, 16, REGRAS)
        self.assertEqual(nivel, "Forte")
        self.assertIn("escalonado", motivo)

    def test_so_notifica_forte_e_muito_forte(self):
        self.rodar(cenario="chuva-forte")
        niveis = {m["municipio"]: m for m in self.painel()["municipios"]}
        self.assertGreater(niveis["São Paulo"]["notificacoes_enviadas"], 0)
        self.assertEqual(niveis["Osasco"]["nivel"], "Moderado")
        self.assertEqual(niveis["Osasco"]["notificacoes_enviadas"], 0)
        self.assertEqual(niveis["Diadema"]["nivel"], "Forte")

    def test_notifica_apenas_inscritos_do_municipio_em_alerta(self):
        self.rodar(cenario="chuva-forte")
        arq = os.path.join(self.dir, "saida", "notificacoes", "2026-11-16.jsonl")
        enviados = [json.loads(l) for l in ler(arq).splitlines()]
        self.assertTrue(enviados)
        self.assertTrue({e["municipio"] for e in enviados} <= {"São Paulo", "Guarulhos", "Diadema"})

    def test_nao_repete_aviso_na_segunda_execucao(self):
        _, r1 = self.rodar(cenario="chuva-forte")
        _, r2 = self.rodar(cenario="chuva-forte")
        self.assertGreater(r1["notificacoes_enviadas"], 0)
        self.assertEqual(r2["notificacoes_enviadas"], 0)
        self.assertEqual(r2["notificacoes_ignoradas_duplicadas"], r1["notificacoes_enviadas"])


# ============================================================ FALHA
class TestFalha(Base):
    def test_api_fora_do_ar_faz_retry_e_nao_quebra(self):
        chamadas = []

        def falha(url, t):
            chamadas.append(url)
            raise urllib.error.URLError("sem rede")

        codigo, resumo = self.rodar(cenario="real", buscar_json=falha)
        self.assertEqual(codigo, 1)                       # PARCIAL, não silencioso
        self.assertEqual(len(chamadas), 12 * 3)           # 3 tentativas por município
        self.assertEqual(resumo["municipios_com_erro"], 12)
        self.assertTrue(all(m["nivel"] == "Sem dados" for m in self.painel()["municipios"]))

    def test_api_fora_do_ar_usa_cache_recente(self):
        self.rodar(cenario="real", buscar_json=lambda u, t: resposta_api(2.0))   # popula cache
        codigo, resumo = self.rodar(cenario="real",
                                    buscar_json=lambda u, t: (_ for _ in ()).throw(TimeoutError()))
        self.assertEqual(resumo["municipios_via_cache"], 12)
        self.assertTrue(all(m["fonte"] == "cache" for m in self.painel()["municipios"]))

    def test_http_404_nao_repete(self):
        chamadas = []

        def nao_encontrado(url, t):
            chamadas.append(1)
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

        self.rodar(cenario="real", buscar_json=nao_encontrado)
        self.assertEqual(len(chamadas), 12)               # 1 tentativa por município

    def test_dados_invalidos_isolados_por_municipio(self):
        codigo, resumo = self.rodar(cenario="dados-invalidos")
        self.assertEqual(codigo, 1)
        self.assertEqual(resumo["municipios_com_erro"], 3)
        processados = [m for m in self.painel()["municipios"] if m["fonte"] != "indisponivel"]
        self.assertEqual(len(processados), 9)             # os outros 9 seguem normalmente

    def test_validacao_rejeita_valor_negativo(self):
        with self.assertRaises(DadosClimaInvalidos):
            validar_horas([1.0] * 23 + [-1.0], 24)

    def test_arquivo_de_inscricoes_ausente(self):
        codigo, resumo = self.rodar(cenario="chuva-forte",
                                    arquivo_inscricoes=os.path.join(self.dir, "nao_existe.jsonl"))
        self.assertEqual(codigo, 1)
        self.assertEqual(resumo["notificacoes_enviadas"], 0)
        self.assertEqual(self.painel()["resumo"]["municipios_em_alerta"], 3)  # painel continua
        self.assertIn("INSCRICOES_AUSENTES", self.logs())

    def test_config_ausente_e_falha_fatal(self):
        os.remove(os.path.join(self.dir, "config", "regras.json"))
        codigo, resumo = self.rodar(cenario="seco")
        self.assertEqual(codigo, 2)
        self.assertEqual(resumo["status"], "FALHA")

    def test_inscricoes_invalidas_e_duplicadas_sao_rejeitadas(self):
        arq = os.path.join(self.dir, "teste.jsonl")
        base = {"id_inscricao": "1", "nome": "Ana Lima", "email": "ana@ex.com", "telefone": "11987654321",
                "codigo_ibge": "3550308", "canal": "sms", "aceite_lgpd": True}
        with open(arq, "w", encoding="utf-8") as f:
            f.write(json.dumps(base) + "\n")
            f.write(json.dumps(dict(base, id_inscricao="2")) + "\n")             # duplicada
            f.write(json.dumps(dict(base, id_inscricao="3", email="x")) + "\n")  # e-mail inválido
            f.write("{quebrada\n")
        validos, rej = carregar_inscritos(arq, {"3550308"})
        self.assertEqual(len(validos), 1)
        self.assertEqual(rej["duplicado"], 1)
        self.assertEqual(rej["email_invalido"], 1)
        self.assertEqual(rej["linha_nao_json"], 1)


# ============================================================ LGPD
class TestLGPD(Base):
    def test_mascaras(self):
        self.assertEqual(mascarar_telefone("(11) 98765-4321"), "(11) *****-4321")
        self.assertEqual(mascarar_nome("Ana Souza Lima"), "Ana L.")
        self.assertEqual(len(hash_email("A@B.com")), 64)
        self.assertEqual(hash_email("a@b.com"), hash_email(" A@B.COM "))

    def test_nenhum_email_ou_telefone_em_claro_nas_saidas(self):
        self.rodar(cenario="chuva-forte")
        emails = [json.loads(l)["email"] for l in
                  ler(os.path.join(self.dir, "dados", "entrada", "inscricoes.jsonl")).splitlines()
                  if l.strip().endswith("}")]
        saidas = self.logs()
        for raiz, _, arquivos in os.walk(os.path.join(self.dir, "saida")):
            for a in arquivos:
                saidas += ler(os.path.join(raiz, a))
        for e in emails[:50]:
            self.assertNotIn(e, saidas)


if __name__ == "__main__":
    unittest.main(verbosity=2)
