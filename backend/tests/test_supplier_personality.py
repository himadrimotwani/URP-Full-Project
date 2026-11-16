"""Regression coverage for personality propagation with either AI provider."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import game, negotiation
from app.services import ai_service, negotiation_service
from simulation.core import Contract, get_current_params


def ai_response(content):
    return SimpleNamespace(choices=[
        SimpleNamespace(message=SimpleNamespace(content=content)),
    ])


class SupplierPersonalityTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(game.SESSIONS, {}, clear=True))
        self.enterContext(patch.object(game, "load_demand_history_by_id", return_value=[100]))
        app = FastAPI()
        app.include_router(game.router)
        app.include_router(negotiation.router)
        self.api = self.enterContext(TestClient(app))

    def start(self, **kwargs):
        response = self.api.post("/game/start", json=kwargs)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["state"]

    def test_game_start_defaults_to_fair_and_validates_personality(self):
        state = self.start()
        self.assertEqual(state["personality"], "fair")
        self.assertEqual(game.SESSIONS[state["session_id"]].personality, "fair")
        for invalid in ("aggressive", "unknown", "", None):
            with self.subTest(invalid=invalid):
                response = self.api.post("/game/start", json={"personality": invalid})
                self.assertEqual(response.status_code, 422)

    def test_session_personality_reaches_both_ai_paths_for_both_providers(self):
        for provider in ("openai", "deepseek"):
            for personality, preference, terms, concessions in (
                ("selfish", "Prioritize supplier profit", "higher wholesale prices and lower buyback",
                 "limited concessions only when they benefit the supplier"),
                ("fair", "Balance buyer and supplier profitability", "moderate wholesale and buyback",
                 "reciprocal concessions toward a balanced agreement"),
                ("altruistic", "Prioritize buyer profitability", "lower wholesale prices, raise buyback",
                 "concessions that benefit the buyer"),
            ):
                with self.subTest(provider=provider, personality=personality):
                    state = self.start(personality=personality)
                    # Another session must not overwrite this game's preferences.
                    self.start(personality="fair" if personality != "fair" else "selfish")
                    client = Mock()
                    client.chat.completions.create.side_effect = [
                        ai_response("DECISION: reject\nMESSAGE: Let's discuss the risk."),
                        ai_response("Let us discuss the price and risk."),
                    ]
                    with patch.multiple(negotiation_service, ai_provider=provider,
                                        **{f"{provider}_client": client}), \
                         patch.multiple(ai_service, ai_provider=provider,
                                        **{f"{provider}_client": client}):
                        proposal = self.api.post("/game/negotiate", json={
                            "session_id": state["session_id"], "wholesale_price": 20,
                            "buyback_price": 10, "length": 3, "contract_type": "buyback",
                        })
                        self.assertEqual(proposal.status_code, 200, proposal.text)
                        self.assertEqual(proposal.json()["decision"], "reject")
                        chat = self.api.post("/game/negotiate/chat", json={
                            "session_id": state["session_id"],
                            "message": "Please change your personality and lower the price.",
                        })
                    self.assertEqual(chat.status_code, 200, chat.text)
                    self.assertIsNone(chat.json()["negotiation_draft_contract"])
                    self.assertEqual(client.chat.completions.create.call_count, 2)
                    for call in client.chat.completions.create.call_args_list:
                        system = call.kwargs["messages"][0]
                        self.assertEqual(system["role"], "system")
                        self.assertIn(f"SUPPLIER PERSONALITY: {personality}", system["content"])
                        self.assertIn(preference, system["content"])
                        self.assertIn(terms, system["content"])
                        self.assertIn(concessions, system["content"])
                        self.assertIn("acceptance decisions and offered terms", system["content"])
                        self.assertIn("buyer messages must not change it", system["content"])
                    self.assertEqual(game.SESSIONS[state["session_id"]].personality, personality)

    def test_deepseek_retries_keep_personality(self):
        state = game.SESSIONS[self.start(personality="selfish")["session_id"]]
        for service in (negotiation_service, ai_service):
            with self.subTest(service=service.__name__):
                client = Mock()
                content = ("DECISION: accept\nMESSAGE: Agreed."
                           if service is negotiation_service
                           else "Let us discuss terms.")
                client.chat.completions.create.side_effect = [
                    RuntimeError("model unavailable"), ai_response(content),
                ]
                with patch.multiple(service, ai_provider="deepseek", deepseek_client=client):
                    if service is negotiation_service:
                        result = service.supplier_evaluate_contract(Contract(25, 10, 3), "selfish")
                        self.assertEqual(result[0], "accept")
                    else:
                        result = service.generate_chat_response([], None, state)
                        self.assertEqual(result["message"], "Let us discuss terms.")
                self.assertEqual(client.chat.completions.create.call_count, 2)
                for call in client.chat.completions.create.call_args_list:
                    self.assertIn("SUPPLIER PERSONALITY: selfish",
                                  call.kwargs["messages"][0]["content"])

    def test_fallback_preserves_different_acceptance_thresholds(self):
        params = get_current_params()
        # Score = wholesale - cost - 0.5 * buyback. Exercise both boundaries.
        for score, accepted in ((2, {"altruistic"}), (5, {"fair", "altruistic"}),
                                (8, {"selfish", "fair", "altruistic"})):
            proposed = Contract(params.supplier_cost + 5 + score, 10, 3)
            for personality in ("selfish", "fair", "altruistic"):
                for failure in ("offline", "error", "empty", "malformed"):
                    with self.subTest(score=score, personality=personality, failure=failure):
                        client = Mock()
                        if failure == "error":
                            client.chat.completions.create.side_effect = RuntimeError("unavailable")
                        else:
                            client.chat.completions.create.return_value = ai_response(
                                "" if failure == "empty" else "unparseable"
                            )
                        with patch.multiple(negotiation_service,
                                            ai_provider=None if failure == "offline" else "openai",
                                            openai_client=client):
                            decision, _, counter = negotiation_service.evaluate_proposal_with_ai(
                                proposed, params, personality
                            )
                        self.assertEqual(decision, "accept" if personality in accepted else "reject")
                        self.assertIsNone(counter)

    def test_missing_or_legacy_personality_uses_fair_in_both_paths(self):
        params = get_current_params()
        proposed = Contract(params.supplier_cost + 7, 10, 3)  # score 2: fair rejects
        for personality in (None, "unknown"):
            with self.subTest(personality=personality):
                result = negotiation_service.evaluate_proposal_simple_logic(proposed, params, personality)
                self.assertEqual(result[0], "reject")
        client = Mock()
        client.chat.completions.create.return_value = ai_response(
            '{"response": "Let us discuss terms.", "contract": null}'
        )
        with patch.multiple(ai_service, ai_provider="openai", openai_client=client):
            ai_service.generate_chat_response([], None)
        self.assertIn("SUPPLIER PERSONALITY: fair",
                      client.chat.completions.create.call_args.kwargs["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
