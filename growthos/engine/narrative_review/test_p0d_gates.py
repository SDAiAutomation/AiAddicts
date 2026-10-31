"""Prérequis P0-D 1/2/3/4 : autorisation de campagne, transport instrumenté, tokenizer, budget à arrêt automatique. Hors fournisseur réel ; boucle locale seulement pour le transport."""
from __future__ import annotations

import copy
import http.server
import json
import socketserver
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from growthos.engine.narrative_review import contract as c
from growthos.engine.narrative_review.harness import corpus as corp
from growthos.engine.narrative_review.harness import policy
from growthos.engine.narrative_review.harness.simulation import simulated_critic, simulated_generator
from growthos.engine.narrative_review.p0d import authorization as au
from growthos.engine.narrative_review.p0d import profiles as pf
from growthos.engine.narrative_review.p0d import tokenizer as tk
from growthos.engine.narrative_review.p0d import transport as tr
from growthos.engine.narrative_review.providers import Budget, Prices, ProviderResult
from growthos.engine.narrative_review.reviewer import Caller

NOW = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
FIX = corp.FIXTURES / "p0d"
CORPUS_SHA = corp.load_corpus()["hashes"]["corpus_sha256"]
BASELINE_SHA = policy.load_manifest()["standard"]["rendered_sha256"]
EGRESS = "e" * 64
MODEL = "model-x"
PROFILE = pf.BodyPolicy(model=MODEL, max_output_param="max_tokens", reasoning_policy="not_supported_by_model", tokenizer_id=tk.HEURISTIC_ID)
SAMPLES = [("S" * 100, "U" * 100, 90)] * 25                                      # consommation réelle (simulée) INFÉRIEURE à l'estimation : 90 <= 128
RECORD = tk.validate_counter(tk.CharHeuristic(), MODEL, SAMPLES)


def setUpModule():
    pf.register_profile(PROFILE)
    unittest.addModuleCleanup(pf._profiles.pop, MODEL, None)


def good_auth(**over):
    raw = {"campaign_id": "P0D-TEST", "approved_by": "Owner", "approved_at": "2026-11-03T09:00:00+00:00", "expires_at": "2026-11-03T21:00:00+00:00",
           "model": "model-x", "provider_host": "api.provider-example.com", "endpoint_path": "/v1/chat/completions", "currency": "USD", "ceiling_usd": 5.0,
           "input_per_m": 1.0, "output_per_m": 4.0, "prices_as_of": "2026-11-01", "prices_source": "https://provider-example.com/pricing",
           "max_logical_calls": 20, "strata": ["standard"], "topics": sorted(corp.PILOT_IDS), "max_input_tokens": 16000, "max_output_tokens": 4000,
           "tokenizer_id": tk.HEURISTIC_ID, "tokenizer_validation_sha256": RECORD.sha256, "reasoning_policy": "not_supported_by_model", "corpus_sha256": CORPUS_SHA, "baseline_rendered_sha256": BASELINE_SHA, "egress_attestation_sha256": EGRESS}
    raw.update(over)
    return raw


def problems(raw, **kw):
    return au.validate(raw, now=NOW, corpus_sha256=CORPUS_SHA, baseline_rendered_sha256=BASELINE_SHA, **kw)


class TestAuthorization(unittest.TestCase):
    def test_the_template_is_invalid_by_design_and_a_complete_record_is_valid(self):
        template = json.loads((FIX / "authorization.template.json").read_text(encoding="utf-8"))
        self.assertGreater(len(problems(template)), 5)
        self.assertEqual(template["corpus_sha256"], CORPUS_SHA)           # les empreintes figées y sont déjà ; le reste est au propriétaire
        self.assertEqual(problems(good_auth()), [])

    def test_every_required_field_is_enforced_and_unknown_fields_refused(self):
        for key in au.REQUIRED:
            raw = good_auth()
            del raw[key]
            self.assertTrue(any(key in p for p in problems(raw)), key)
        self.assertTrue(any("unexpected" in p for p in problems(good_auth(extra=1))))
        self.assertEqual(problems([]), ["authorization must be a JSON object"])

    def test_scope_is_locked_to_the_standard_pilot(self):
        for bad in ({"strata": ["standard", "story_visual"]}, {"strata": ["quiz"]}, {"topics": ["N01"]}, {"topics": sorted(corp.PILOT_IDS) + ["N07"]},
                    {"max_logical_calls": 21}, {"max_logical_calls": 0}, {"max_logical_calls": True}):
            self.assertTrue(problems(good_auth(**bad)), bad)

    def test_money_and_time_are_strict(self):
        for bad in ({"ceiling_usd": float("nan")}, {"ceiling_usd": float("inf")}, {"ceiling_usd": -1}, {"ceiling_usd": 0}, {"ceiling_usd": "5"},
                    {"input_per_m": -1}, {"output_per_m": float("nan")}, {"ceiling_usd": 0.001},          # ne finance même pas un appel au maximum
                    {"prices_as_of": "2026-09-01"}, {"prices_as_of": "2026-11-20"}, {"prices_source": "http://x"},
                    {"approved_at": "2026-11-03T09:00:00"}, {"expires_at": "2026-11-06T09:00:01+00:00"}, {"expires_at": "2026-11-03T08:00:00+00:00"}):
            self.assertTrue(problems(good_auth(**bad)), bad)
        self.assertTrue(au.validate(good_auth(), now=NOW + timedelta(hours=13), corpus_sha256=CORPUS_SHA))       # fenêtre expirée
        self.assertTrue(au.validate(good_auth(), now=NOW - timedelta(hours=2), corpus_sha256=CORPUS_SHA))        # fenêtre pas encore ouverte

    def test_host_and_endpoint_are_one_exact_target(self):
        for bad in ({"provider_host": "https://api.x.com"}, {"provider_host": "*.x.com"}, {"provider_host": "127.0.0.1"}, {"provider_host": "api.x.com:443"},
                    {"provider_host": "API.X.COM"}, {"provider_host": "localhost"}, {"endpoint_path": "v1/x"}, {"endpoint_path": "/v1/../x"}, {"endpoint_path": "/v1/x?a=1"}):
            self.assertTrue(problems(good_auth(**bad)), bad)

    def test_frozen_inputs_must_match_and_the_egress_attestation_is_required(self):
        self.assertTrue(problems(good_auth(corpus_sha256="0" * 64)))
        self.assertTrue(problems(good_auth(baseline_rendered_sha256="0" * 64)))
        self.assertTrue(problems(good_auth(egress_attestation_sha256="TODO")))

    def test_load_refuses_an_invalid_file_and_accepts_a_valid_one(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.json"
            path.write_text(json.dumps(good_auth()), encoding="utf-8")
            with self.assertRaises(c.ReviewError):
                au.load(path, now=NOW + timedelta(days=9))
            self.assertEqual(au.load(path, now=NOW, corpus_sha256=CORPUS_SHA).model, "model-x")
            path.write_text(json.dumps(good_auth(ceiling_usd=float("nan"))), encoding="utf-8")
            with self.assertRaises(c.ReviewError):
                au.load(path, now=NOW)

    def test_the_window_opens_only_with_the_approved_attestation_and_closes_for_good(self):
        auth, w = au.CampaignAuthorization(good_auth()), au.Window()
        with self.assertRaises(c.ReviewError):
            w.check()                                                                    # jamais ouverte
        with self.assertRaises(c.ReviewError):
            w.open(auth, egress_attestation_sha256="f" * 64, tokenizer_validation=RECORD, now=NOW, corpus_sha256=CORPUS_SHA)   # autre attestation
        w.open(auth, egress_attestation_sha256=EGRESS, tokenizer_validation=RECORD, now=NOW, corpus_sha256=CORPUS_SHA)
        self.assertEqual(w.check(NOW).campaign_id, "P0D-TEST")
        with self.assertRaises(c.ReviewError):
            w.check(NOW + timedelta(hours=13))                                           # expirée => fermée définitivement
        with self.assertRaises(c.ReviewError):
            w.open(auth, egress_attestation_sha256=EGRESS, tokenizer_validation=RECORD, now=NOW, corpus_sha256=CORPUS_SHA)   # pas de réouverture
        self.assertEqual(len(auth.digest), 64)


class FakeSender:
    def __init__(self, body=None, status=200, headers=None, boom=None):
        self.calls, self.body, self.status, self.headers, self.boom = [], body, status, headers or {}, boom

    def __call__(self, req):
        self.calls.append(req)
        if self.boom:
            raise self.boom
        return tr.HttpResponse(self.status, self.headers, self.body if self.body is not None else completion())


def completion(text="{}", prompt=1000, completion_tokens=200, **usage_extra):
    return json.dumps({"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": prompt, "completion_tokens": completion_tokens, **usage_extra}}).encode()


def open_window(**auth_over):
    w = au.Window()
    record = auth_over.pop("_record", RECORD)
    w.open(au.CampaignAuthorization(good_auth(**auth_over)), egress_attestation_sha256=EGRESS, tokenizer_validation=record, corpus_sha256=CORPUS_SHA)
    return w


def request(**over):
    base = dict(method="POST", host="api.provider-example.com", path="/v1/chat/completions", headers={}, body=b"{}", timeout_s=30.0)
    base.update(over)
    return tr.HttpRequest(**base)


class TestMeteredTransport(unittest.TestCase):
    """Les fenêtres sont ouvertes avec l'horloge réelle : on construit donc des autorisations valides MAINTENANT."""

    def setUp(self):
        now = datetime.now(timezone.utc)
        self.dates = {"approved_at": (now - timedelta(hours=1)).isoformat(), "expires_at": (now + timedelta(hours=6)).isoformat(),
                      "prices_as_of": (now - timedelta(days=2)).date().isoformat()}

    def transport(self, sender, **over):
        return tr.MeteredTransport(sender, open_window(**{**self.dates, **over}), body_validator=lambda req, auth: None)   # mécanique du transport : le corps est testé à part

    def test_no_send_without_an_open_window_and_only_to_the_one_authorised_target(self):
        sender = FakeSender()
        with self.assertRaises(c.ReviewError):
            tr.MeteredTransport(sender, au.Window(), body_validator=lambda r, a: None).send(request())
        t = self.transport(sender)
        for bad in (request(host="evil.example.com"), request(path="/other"), request(method="GET"), request(body=b"x" * 300_000), request(timeout_s=float("nan")),
                    request(timeout_s=0), request(timeout_s=999)):
            with self.assertRaises(c.ReviewError):
                t.send(bad)
        self.assertEqual((sender.calls, t.attempts), ([], []))                  # aucune tentative n'a atteint l'émetteur

    def test_one_attempt_per_send_is_measured_and_logged(self):
        sender = FakeSender(headers={"x-request-id": "req_1"})
        t = self.transport(sender)
        resp, attempt = t.send(request())
        self.assertEqual((len(sender.calls), attempt.attempt_no, attempt.status, attempt.http_attempts, attempt.request_id, attempt.error), (1, 1, 200, 1, "req_1", None))
        self.assertEqual((attempt.bytes_sent, attempt.extra_connection_detected), (2, False))

    def test_errors_429_5xx_3xx_and_exceptions_are_never_retried(self):
        for sender in (FakeSender(status=429, headers={"retry-after": "7"}), FakeSender(status=503), FakeSender(status=302, headers={"location": "http://x"}),
                       FakeSender(boom=TimeoutError("t"))):
            t = self.transport(sender)
            with self.assertRaises(tr.TransportError) as ctx:
                t.send(request())
            self.assertEqual(len(sender.calls), 1)                              # une seule tentative, jamais de reprise
            self.assertEqual((len(t.attempts), ctx.exception.attempt.http_attempts), (1, 1))
        t = self.transport(FakeSender(status=429, headers={"retry-after": "7"}))
        with self.assertRaises(tr.TransportError):
            t.send(request())
        self.assertEqual(t.attempts[0].retry_after, "7")

    def test_the_authorised_call_count_is_a_hard_stop(self):
        sender = FakeSender()
        t = self.transport(sender, max_logical_calls=2)
        t.send(request())
        t.send(request())
        with self.assertRaises(c.ReviewError):
            t.send(request())
        self.assertEqual(len(sender.calls), 2)

    def test_a_hidden_retry_is_detected_by_the_measured_connections_even_if_the_sender_lies(self):
        server = socketserver.TCPServer(("127.0.0.1", 0), socketserver.BaseRequestHandler)   # écoute (le test ne lit pas : seule la connexion compte)
        server.timeout = 0.2
        self.addCleanup(server.server_close)
        addr = server.server_address

        def lying_sender(req):               # prétend n'émettre qu'une requête, mais rouvre une connexion (reprise cachée)
            import socket
            for _ in range(2):
                s = socket.create_connection(addr, timeout=1)
                s.close()
            return tr.HttpResponse(200, {}, completion())
        t = self.transport(lying_sender)
        resp, attempt = t.send(request())
        self.assertEqual((attempt.connects, attempt.http_attempts, attempt.extra_connection_detected), (2, 2, True))
        self.assertIn("extra connection", t.tripped)
        with self.assertRaises(c.ReviewError):                                  # le transport est déclenché : plus aucun envoi
            t.send(request())

    def test_the_real_http_sender_makes_exactly_one_connection_and_never_follows_a_redirect(self):
        seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append((self.path, self.headers.get("Host")))
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                if self.path == "/v1/chat/completions":
                    body = completion("ok")
                    self.send_response(200)
                    self.send_header("x-request-id", "rid")
                    self.send_header("content-length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(302)
                    self.send_header("Location", "/elsewhere")
                    self.end_headers()

            def log_message(self, *a):
                pass
        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        sender = tr.HttpClientSender(tls=False, connect_override=server.server_address)
        t = self.transport(sender)
        resp, attempt = t.send(request())
        self.assertEqual((attempt.connects, attempt.http_attempts, attempt.status, attempt.request_id), (1, 1, 200, "rid"))
        self.assertEqual(seen, [("/v1/chat/completions", "api.provider-example.com")])    # nom d'hôte autorisé dans l'en-tête, adresse fournie par le propriétaire
        t2 = self.transport(sender, endpoint_path="/redirect")
        with self.assertRaises(tr.TransportError):
            t2.send(request(path="/redirect"))
        self.assertEqual(len(seen), 2)                                                    # la redirection n'a PAS été suivie

    def make_tls_server(self, common_name):
        """Serveur TLS sur la boucle locale avec un certificat auto-signé pour `common_name` (généré avec l'openssl de Git ; test sauté s'il est absent)."""
        import shutil
        import ssl
        import subprocess
        import tempfile
        openssl = shutil.which("openssl") or r"C:\Program Files\Git\usr\bin\openssl.exe"
        if not Path(openssl).exists() and not shutil.which("openssl"):
            self.skipTest("openssl not available: pinned TLS path not exercised")
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(tmp / "k.pem"), "-out", str(tmp / "c.pem"), "-days", "2",
                        "-subj", f"/CN={common_name}", "-addext", f"subjectAltName=DNS:{common_name}"], check=True, capture_output=True)

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                body = completion("tls-ok")
                self.send_response(200)
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(tmp / "c.pem"), str(tmp / "k.pem"))
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        client = ssl.create_default_context(cafile=str(tmp / "c.pem"))
        return server.server_address, client

    def test_pinned_tls_connects_to_the_given_ip_without_dns_and_checks_the_authorised_hostname(self):
        addr, client_ctx = self.make_tls_server("api.provider-example.com")
        t = self.transport(tr.HttpClientSender(tls=True, connect_override=addr, ssl_context=client_ctx))
        resp, attempt = t.send(request())
        self.assertEqual((attempt.status, attempt.connects, json.loads(resp.body)["choices"][0]["message"]["content"]), (200, 1, "tls-ok"))

    def test_a_certificate_for_another_hostname_is_refused_with_no_retry(self):
        addr, client_ctx = self.make_tls_server("evil.example.net")                     # IP correcte, certificat pour un autre nom
        t = self.transport(tr.HttpClientSender(tls=True, connect_override=addr, ssl_context=client_ctx))
        with self.assertRaises(tr.TransportError) as ctx:
            t.send(request())
        self.assertEqual((len(t.attempts), ctx.exception.attempt.http_attempts), (1, 1))
        self.assertIn("SSL", ctx.exception.attempt.error)

    def test_usage_and_cost_come_only_from_the_provider_response_and_unknown_stays_none(self):
        u = tr.usage_from_body(completion(prompt=1200, completion_tokens=300, cost=0.0123, completion_tokens_details={"reasoning_tokens": 120}))
        self.assertEqual({k: u[k] for k in ("input", "output", "reasoning", "provider_cost_usd")}, {"input": 1200, "output": 300, "reasoning": 120, "provider_cost_usd": 0.0123})
        self.assertEqual(tr.usage_from_body(json.dumps({"usage": {"input_tokens": 5, "output_tokens": 6}}).encode())["input"], 5)
        for body in (b"not json", b"{}", b'{"usage": 3}', json.dumps({"usage": {"prompt_tokens": float("nan"), "completion_tokens": -1}}).encode()):
            self.assertEqual(tr.usage_from_body(body), {"input": None, "output": None, "reasoning": None, "provider_cost_usd": None, "finish_reason": None}, body)
        self.assertIsNone(tr.usage_from_body(completion())["provider_cost_usd"])            # pas de coût renvoyé => inconnu, jamais calculé

    def provider(self, sender, **over):
        t = tr.MeteredTransport(sender, open_window(**{**self.dates, **over}))          # sans validateur : le fournisseur installe celui du profil
        return tr.ChatCompletionsProvider(t, api_key=lambda: "sk-test-not-real"), t

    def test_the_chat_provider_returns_measured_attempts_usage_and_observed_cost(self):
        sender = FakeSender(body=completion("hello", prompt=900, completion_tokens=150, cost=0.002))
        provider, t = self.provider(sender)
        result = provider({"role": "generation", "system": "S" * 1800, "user": "U", "max_output_tokens": 99999, "timeout_s": 30})   # estimation >= 900 jetons facturés
        self.assertEqual((result.text, result.usage, result.http_attempts, result.observed_cost_usd), ("hello", {"input": 900, "output": 150}, 1, 0.002))
        body = json.loads(sender.calls[0].body)
        self.assertEqual((body["model"], body["max_tokens"]), ("model-x", 4000))           # plafond de sortie ramené à l'autorisation
        self.assertNotIn("sk-test-not-real", json.dumps([a.__dict__ for a in t.attempts]))  # la clé n'est jamais journalisée

    def test_unknown_usage_is_unknown_not_zero(self):
        provider, _ = self.provider(FakeSender(body=json.dumps({"choices": [{"message": {"content": "x"}}]}).encode()))
        result = provider({"system": "S", "user": "U", "max_output_tokens": 10, "timeout_s": 30})
        self.assertEqual((result.text, result.usage, result.observed_cost_usd), ("x", None, None))

    def test_transport_failures_become_a_visible_failed_result(self):
        provider, _ = self.provider(FakeSender(status=429))
        result = provider({"system": "S", "user": "U", "max_output_tokens": 10, "timeout_s": 30})
        self.assertEqual((result.text, result.usage, result.http_attempts, result.error), (None, None, 1, "http_429"))

    def test_an_oversized_prompt_is_refused_before_any_send(self):
        sender = FakeSender()
        provider, _ = self.provider(sender, max_input_tokens=100)
        with self.assertRaises(c.ReviewError):
            provider({"system": "x" * 1000, "user": "u", "max_output_tokens": 10, "timeout_s": 30})
        self.assertEqual(sender.calls, [])


class TestTokenizer(unittest.TestCase):
    def test_the_conservative_bound_and_the_overhead(self):
        counter = tk.resolve(tk.HEURISTIC_ID)
        self.assertEqual((counter.count("abcd"), counter.count("abc"), counter.exact), (2, 2, False))
        self.assertEqual(tk.estimate_input_tokens(counter, "a" * 100, "b" * 100), 128)         # (50 + 50 + 16) x 1,10 = 127,6 arrondi au-dessus
        with self.assertRaises(ValueError):
            tk.estimate_input_tokens(counter, "a", "b", safety=float("nan"))

    def test_an_unregistered_model_tokenizer_means_no_call(self):
        with self.assertRaises(tk.TokenizerRequired):
            tk.resolve("some-model-bpe")
        sender = FakeSender()
        now = datetime.now(timezone.utc)
        # le profil du modèle déclare un tokenizer qui n'est PAS enregistré : la fenêtre s'ouvre (enregistrement valide fourni) mais l'appel est refusé
        pf.register_profile(pf.BodyPolicy(model="model-bpe", max_output_param="max_tokens", reasoning_policy="not_supported_by_model", tokenizer_id="some-model-bpe"))
        self.addCleanup(pf._profiles.pop, "model-bpe", None)
        record = tk.validate_counter(tk.CharHeuristic(), "model-bpe", SAMPLES)
        record = tk.ValidationRecord("some-model-bpe", "model-bpe", record.samples, record.max_reported_over_estimate, record.safety, True, "b" * 64)
        w = open_window(approved_at=(now - timedelta(hours=1)).isoformat(), expires_at=(now + timedelta(hours=2)).isoformat(),
                        prices_as_of=(now - timedelta(days=1)).date().isoformat(), tokenizer_id="some-model-bpe", model="model-bpe",
                        tokenizer_validation_sha256="b" * 64, _record=record)
        provider = tr.ChatCompletionsProvider(tr.MeteredTransport(sender, w), api_key=lambda: "k")
        with self.assertRaises(tk.TokenizerRequired):
            provider({"system": "S", "user": "U", "max_output_tokens": 10, "timeout_s": 30})
        self.assertEqual(sender.calls, [])

    def test_a_registered_exact_counter_is_used_and_calibration_trips_the_transport_when_it_underestimates(self):
        class Tiny:
            id, exact = "tiny-test", True

            def count(self, text):
                return 1                       # sous-estime volontairement

        tk.register(Tiny)
        self.addCleanup(tk._registry.pop, "tiny-test", None)
        pf.register_profile(pf.BodyPolicy(model="model-tiny", max_output_param="max_tokens", reasoning_policy="not_supported_by_model", tokenizer_id="tiny-test"))
        self.addCleanup(pf._profiles.pop, "model-tiny", None)
        record = tk.ValidationRecord("tiny-test", "model-tiny", 25, 0.5, 1.1, True, "c" * 64)       # « validé » à une époque ; sous-estime désormais
        now = datetime.now(timezone.utc)
        dates = dict(approved_at=(now - timedelta(hours=1)).isoformat(), expires_at=(now + timedelta(hours=2)).isoformat(),
                     prices_as_of=(now - timedelta(days=1)).date().isoformat(), tokenizer_id="tiny-test", model="model-tiny",
                     tokenizer_validation_sha256="c" * 64, _record=record)
        sender = FakeSender(body=completion("x", prompt=5000, completion_tokens=10))        # le fournisseur facture bien plus que compté
        t = tr.MeteredTransport(sender, open_window(**dates))
        provider = tr.ChatCompletionsProvider(t, api_key=lambda: "k")
        result = provider({"system": "S", "user": "U", "max_output_tokens": 10, "timeout_s": 30})
        self.assertIsNone(result.usage)                                                      # coût non établi : jamais présenté comme connu
        self.assertIn("underestimates", result.error)
        self.assertIn("underestimates", t.tripped)
        with self.assertRaises(c.ReviewError):
            provider({"system": "S", "user": "U", "max_output_tokens": 10, "timeout_s": 30})
        self.assertEqual(len(sender.calls), 1)
        self.assertTrue(tk.underestimated(100, 101))
        self.assertFalse(tk.underestimated(100, 100))
        self.assertFalse(tk.underestimated(100, None))


class TestHardCapAutoStop(unittest.TestCase):
    """Plafond dur en dollars, réservation avant chaque appel, arrêt automatique sur dépassement ou usage inconnu (runner du harness)."""

    def setUp(self):
        cm = policy.baseline_override("synthetic")
        cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)

    def run_with(self, generator, critic=None, budget=None, strata=("standard",)):
        from growthos.engine.narrative_review.harness import runner
        return runner.run_campaign(corp.load_corpus(), generator=generator, critic=critic or simulated_critic(), budget=budget or Budget(5.0),
                                   gen_prices=Prices(1.0, 4.0), critic_prices=Prices(1.0, 4.0), gen_model="g", critic_model="k", campaign_id="H",
                                   caller=Caller("o", "a"), source_commit="x", strata=strata)

    def test_a_response_with_unknown_usage_stops_the_campaign(self):
        from growthos.engine.narrative_review.harness.offline import offline
        inner = simulated_generator()
        count = {"n": 0}

        def no_usage(request):
            count["n"] += 1
            r = inner(request)
            return ProviderResult(text=r.text, usage=None, latency_s=1.0)
        result = self.run_with(offline(no_usage))
        self.assertEqual(count["n"], 1)                                                   # un seul appel : on s'arrête dès que l'usage est inconnu
        self.assertTrue(result["summary"]["halted_on_hidden_retry"])
        self.assertEqual(result["summary"]["halt_reasons"], ["UNKNOWN_USAGE"])
        self.assertEqual(sum(r["error_code"] == "HALTED_RETRY_DETECTED" for r in result["rows"]), 9)

    def test_a_critic_answer_without_usage_stops_the_campaign(self):
        from growthos.engine.narrative_review.harness.offline import offline
        inner = simulated_critic()
        n = {"n": 0}

        def no_usage(request):
            n["n"] += 1
            r = inner(request)
            return ProviderResult(text=r.text, usage=None, latency_s=1.0)
        result = self.run_with(simulated_generator(), critic=offline(no_usage))
        self.assertEqual(n["n"], 1)
        self.assertEqual(result["summary"]["halt_reasons"], ["UNKNOWN_USAGE"])

    def test_an_overrun_of_the_reservation_stops_the_campaign(self):
        from growthos.engine.narrative_review.harness.offline import offline
        inner = simulated_generator()
        n = {"n": 0}

        def expensive(request):
            n["n"] += 1
            r = inner(request)
            return ProviderResult(text=r.text, usage={"input": 50_000_000, "output": 50_000_000}, latency_s=1.0)   # bien au-delà de la réservation
        result = self.run_with(offline(expensive), budget=Budget(1000.0))
        self.assertEqual(n["n"], 1)
        self.assertIn("COST_EXCEEDED_RESERVATION", result["summary"]["halt_reasons"])   # incident explicite
        self.assertTrue(any(i["code"] == "COST_EXCEEDED_RESERVATION" for i in result["summary"]["incidents"]))

    def test_the_dollar_ceiling_is_hard_and_refuses_before_the_call(self):
        gen, crit = simulated_generator(), simulated_critic()
        result = self.run_with(gen, critic=crit, budget=Budget(0.05))                    # ne finance qu'environ deux appels au maximum
        calls = len(gen.requests) + len(crit.requests)
        self.assertLess(calls, 20)
        self.assertTrue(any(r["error_code"] == c.BUDGET_EXHAUSTED for r in result["rows"]))
        self.assertLessEqual(result["summary"]["costs"]["budget_committed_usd"], 0.05 + 1e-9)

    def test_a_provider_reported_cost_is_journaled_as_observed_and_never_invented(self):
        from growthos.engine.narrative_review.harness.offline import offline
        inner = simulated_generator()

        def with_cost(request):
            r = inner(request)
            return ProviderResult(text=r.text, usage=r.usage, latency_s=1.0, observed_cost_usd=0.01)
        result = self.run_with(offline(with_cost))
        gen_rows = [r for r in result["rows"] if r["task"] == "generation"]
        self.assertTrue(all(r["observed_cost"] == 0.01 for r in gen_rows))
        crit_rows = [r for r in result["rows"] if r["task"] == "critique"]
        self.assertTrue(all(r["observed_cost"] == "" for r in crit_rows))                # la critique factice n'a renvoyé aucun coût


if __name__ == "__main__":
    unittest.main()
