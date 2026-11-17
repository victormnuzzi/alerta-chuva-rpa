"""Coleta da previsão de chuva (Open-Meteo) com retry, validação e cache."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta


class ClimaIndisponivel(Exception):
    """API fora do ar e sem cache válido."""


class DadosClimaInvalidos(Exception):
    """Resposta chegou, mas os dados não passam na validação."""


def buscar_json_http(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "rpa-alerta-chuva/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def validar_horas(horas, janela: int) -> list[float]:
    """Regras de qualidade da série horária de chuva."""
    if not isinstance(horas, list) or len(horas) < janela:
        raise DadosClimaInvalidos(f"esperadas {janela} horas, recebidas {len(horas) if isinstance(horas, list) else 0}")
    horas = horas[:janela]
    faltantes = sum(1 for h in horas if h is None)
    if faltantes > 2:
        raise DadosClimaInvalidos(f"{faltantes} horas sem valor (máximo tolerado: 2)")
    limpas = []
    for h in horas:
        if h is None:
            limpas.append(0.0)
            continue
        if not isinstance(h, (int, float)) or isinstance(h, bool):
            raise DadosClimaInvalidos(f"valor não numérico: {h!r}")
        if h < 0 or h > 200:
            raise DadosClimaInvalidos(f"valor fora da faixa física (0 a 200 mm/h): {h}")
        limpas.append(float(h))
    return limpas


class ColetorClima:
    def __init__(self, regras, pasta_cache, auditoria, buscar_json=buscar_json_http,
                 fixture: dict | None = None, dormir=time.sleep):
        self.cfg = regras["api"]
        self.janela = regras["janela_horas"]
        self.validade_cache = timedelta(hours=regras["cache_validade_horas"])
        self.pasta_cache = pasta_cache
        self.aud = auditoria
        self.buscar_json = buscar_json
        self.fixture = fixture
        self.dormir = dormir
        os.makedirs(pasta_cache, exist_ok=True)

    # --------------------------------------------------------------- público
    def obter(self, municipio: dict, agora: datetime) -> dict:
        """Retorna {'horas': [...24 valores...], 'fonte': 'api'|'fixture'|'cache'}."""
        cod = municipio["codigo_ibge"]
        try:
            if self.fixture is not None:
                horas = validar_horas(self._da_fixture(cod), self.janela)
                fonte = "fixture"
            else:
                horas = validar_horas(self._da_api(municipio, agora), self.janela)
                fonte = "api"
                self._salvar_cache(cod, horas, agora)  # só dado real vai para o cache
            return {"horas": horas, "fonte": fonte}
        except (ClimaIndisponivel, DadosClimaInvalidos) as erro:
            self.aud.evento("CLIMA_FALHA", "WARNING", municipio=municipio["nome"],
                            tipo_erro=type(erro).__name__, detalhe=str(erro))
            cache = self._ler_cache(cod, agora)
            if cache is not None:
                self.aud.evento("CLIMA_CACHE", "WARNING", municipio=municipio["nome"],
                                salvo_em=cache["salvo_em"])
                return {"horas": cache["horas"], "fonte": "cache"}
            raise

    # --------------------------------------------------------------- fontes
    def _da_fixture(self, cod):
        if cod not in self.fixture:
            raise ClimaIndisponivel("município ausente no arquivo de cenário")
        return self.fixture[cod]

    def _da_api(self, municipio, agora):
        params = urllib.parse.urlencode({
            "latitude": municipio["lat"], "longitude": municipio["lon"],
            "hourly": "precipitation", "timezone": "America/Sao_Paulo", "forecast_days": 2,
        })
        url = f"{self.cfg['url']}?{params}"
        espera = self.cfg["espera_inicial_s"]
        ultimo_erro = None
        for tentativa in range(1, self.cfg["tentativas"] + 1):   # retry com backoff
            try:
                dados = self.buscar_json(url, self.cfg["timeout_s"])
                return self._recortar_janela(dados, agora)
            except urllib.error.HTTPError as e:
                ultimo_erro = f"HTTP {e.code}"
                if 400 <= e.code < 500 and e.code != 429:
                    break  # erro do pedido: repetir não resolve
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, OSError) as e:
                ultimo_erro = f"{type(e).__name__}: {e}"
            self.aud.evento("API_TENTATIVA_FALHOU", "WARNING", municipio=municipio["nome"],
                            tentativa=tentativa, erro=ultimo_erro)
            if tentativa < self.cfg["tentativas"]:
                self.dormir(espera)
                espera *= 2
        raise ClimaIndisponivel(f"Open-Meteo indisponível após tentativas: {ultimo_erro}")

    def _recortar_janela(self, dados, agora):
        try:
            tempos = dados["hourly"]["time"]
            chuva = dados["hourly"]["precipitation"]
        except (KeyError, TypeError):
            raise DadosClimaInvalidos("resposta sem o bloco 'hourly'")
        chave = agora.strftime("%Y-%m-%dT%H:00")
        if chave not in tempos:
            raise DadosClimaInvalidos(f"hora atual {chave} não está na previsão")
        i = tempos.index(chave)
        return chuva[i:i + self.janela]

    # --------------------------------------------------------------- cache
    def _arq_cache(self, cod):
        return os.path.join(self.pasta_cache, f"clima_{cod}.json")

    def _salvar_cache(self, cod, horas, agora):
        with open(self._arq_cache(cod), "w", encoding="utf-8") as f:
            json.dump({"salvo_em": agora.isoformat(timespec="seconds"), "horas": horas}, f)

    def _ler_cache(self, cod, agora):
        try:
            with open(self._arq_cache(cod), encoding="utf-8") as f:
                cache = json.load(f)
            salvo = datetime.fromisoformat(cache["salvo_em"])
            if agora - salvo <= self.validade_cache:
                return cache
        except (OSError, ValueError, KeyError):
            pass
        return None
