"""Testes do robo (sucesso, decisao e falha).

Rodar: python -m unittest discover -s tests -v
Cada teste roda numa pasta temporaria e sem internet (a API e simulada).
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

from robo.main import executar  # noqa: E402
from robo.regras import classificar  # noqa: E402

AGORA = datetime(2026, 11, 16, 10, 0)


def ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


REGRAS = json.loads(ler(os.path.join(RAIZ, "config", "regras.json")))


def resposta_api(valor_hora):
    # mesmo formato que a Open-Meteo devolve
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
        return json.loads(ler(os.path.join(self.dir, "saida", "painel_alertas.json")))

    def logs(self):
        pasta = os.path.join(self.dir, "logs")
        return "".join(ler(os.path.join(pasta, n)) for n in os.listdir(pasta))


class TestSucesso(Base):
    def test_cenario_seco_gera_painel_sem_alertas(self):
        codigo, resumo = self.rodar(cenario="seco")
        self.assertEqual(codigo, 0)
        self.assertEqual(len(self.painel()["municipios"]), 12)
        self.assertEqual(resumo["alertas_emitidos"], 0)


class TestDecisao(Base):
    def test_classificacao(self):
        self.assertEqual(classificar(3, 1, REGRAS)[0], "Baixo")
        self.assertEqual(classificar(10, 2, REGRAS)[0], "Moderado")
        self.assertEqual(classificar(35, 5, REGRAS)[0], "Forte")
        self.assertEqual(classificar(60, 9, REGRAS)[0], "Muito forte")

    def test_chuva_concentrada_sobe_para_forte(self):
        self.assertEqual(classificar(17, 16, REGRAS)[0], "Forte")

    def test_nao_repete_aviso(self):
        _, r1 = self.rodar(cenario="chuva-forte")
        _, r2 = self.rodar(cenario="chuva-forte")
        self.assertGreater(r1["notificacoes_enviadas"], 0)
        self.assertEqual(r2["notificacoes_enviadas"], 0)


class TestFalha(Base):
    def test_api_fora_do_ar(self):
        chamadas = []

        def falha(url, t):
            chamadas.append(url)
            raise urllib.error.URLError("sem rede")

        codigo, _ = self.rodar(cenario="real", buscar_json=falha)
        self.assertEqual(codigo, 1)
        self.assertEqual(len(chamadas), 12 * 3)  # 3 tentativas por cidade

    def test_api_fora_usa_cache(self):
        self.rodar(cenario="real", buscar_json=lambda u, t: resposta_api(2.0))
        _, resumo = self.rodar(cenario="real", buscar_json=lambda u, t: (_ for _ in ()).throw(TimeoutError()))
        self.assertEqual(resumo["municipios_via_cache"], 12)

    def test_dados_invalidos(self):
        codigo, resumo = self.rodar(cenario="dados-invalidos")
        self.assertEqual(codigo, 1)
        self.assertEqual(resumo["municipios_com_erro"], 3)

    def test_sem_arquivo_de_inscricoes(self):
        codigo, resumo = self.rodar(cenario="chuva-forte",
                                    arquivo_inscricoes=os.path.join(self.dir, "nao_existe.jsonl"))
        self.assertEqual(codigo, 1)
        self.assertEqual(resumo["notificacoes_enviadas"], 0)
        self.assertIn("INSCRICOES_AUSENTES", self.logs())


class TestLGPD(Base):
    def test_email_nao_aparece_nos_logs(self):
        self.rodar(cenario="chuva-forte")
        linhas = ler(os.path.join(self.dir, "dados", "entrada", "inscricoes.jsonl")).splitlines()
        emails = [json.loads(l)["email"] for l in linhas[:30] if l.strip().endswith("}")]
        texto = self.logs() + ler(os.path.join(self.dir, "saida", "painel_alertas.json"))
        for e in emails:
            self.assertNotIn(e, texto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
