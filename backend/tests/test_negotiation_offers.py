"""Run from backend with: python -m unittest discover -s tests -v."""

import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import negotiation
from app.services import ai_service
from simulation.core import Contract, GameState


def contract(price=30):
    return Contract(wholesale_price=price, buyback_price=10, length=3)


class NegotiationOfferTests(unittest.TestCase):
    def setUp(self):
        self.state = GameState(
            round_number=1,
            total_rounds=10,
            contract=Contract(0, 0, 0, remaining_rounds=0),
            cumulative_buyer_profit=0,
            cumulative_supplier_profit=0,
            historical_demands=[100],
            initial_contract_type="buyback",
        )
        self.enterContext(patch.dict(negotiation.SESSIONS, {"test": self.state}))
        self.log = self.enterContext(patch.object(negotiation, "log_chat_record"))
        app = FastAPI()
        app.include_router(negotiation.router)
        self.client = self.enterContext(TestClient(app))

    def chat(self, draft, message="Let's revise the wholesale price to $25."):
        with patch.object(negotiation, "generate_chat_response", return_value={
            "message": message, "draft_contract": draft,
        }):
            response = self.client.post("/game/negotiate/chat", json={
                "session_id": "test", "message": "Can you lower the price?",
            })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def decide(self, version, accept=True):
        return self.client.post("/game/negotiate/accept-counter", json={
            "session_id": "test", "accept": accept, "offer_version": version,
        })

    def test_revised_message_without_draft_withdraws_old_thirty_dollar_offer(self):
        first = self.chat(contract())
        revised = self.chat(None)
        self.assertIsNone(revised["negotiation_draft_contract"])
        self.assertIsNone(revised["offer_version"])
        self.assertIsNone(self.state.negotiation_draft_contract)
        self.assertEqual(self.decide(first["offer_version"]).status_code, 409)
        self.assertEqual(self.state.contract.remaining_rounds, 0)
        self.log.assert_not_called()

    def test_revised_offer_requires_its_own_version_and_activates_twenty_five(self):
        first = self.chat(contract())
        revised = self.chat(contract(25))
        self.assertGreater(revised["offer_version"], first["offer_version"])
        # Neither a stale acceptance nor a stale rejection may mutate the new offer.
        for accept in (True, False):
            self.assertEqual(self.decide(first["offer_version"], accept).status_code, 409)
            self.assertEqual(self.state.negotiation_draft_contract.wholesale_price, 25)
        accepted = self.decide(revised["offer_version"])
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["state"]["contract"]["wholesale_price"], 25)
        self.assertEqual(self.state.contract.remaining_rounds, 3)
        self.assertIsNone(self.state.negotiation_draft_contract)
        self.assertEqual(self.state.negotiation_history[-1]["final_contract"].wholesale_price, 25)
        self.log.assert_called_once()
        self.assertEqual(self.decide(revised["offer_version"]).status_code, 400)

    def test_offer_version_is_required_and_strict(self):
        self.chat(contract())
        for extra in ({}, {"offer_version": None}, {"offer_version": 0},
                      {"offer_version": True}, {"offer_version": "1"}):
            response = self.client.post("/game/negotiate/accept-counter", json={
                "session_id": "test", "accept": True, **extra,
            })
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.state.contract.remaining_rounds, 0)

    def test_rejection_withdraws_offer_and_does_not_reuse_version(self):
        first = self.chat(contract())
        self.assertEqual(self.decide(first["offer_version"], False).status_code, 200)
        self.assertEqual(self.decide(first["offer_version"]).status_code, 409)
        second = self.chat(contract(25))
        self.assertGreater(second["offer_version"], first["offer_version"])

    def test_new_negotiation_does_not_reuse_offer_version(self):
        first = self.chat(contract())
        with patch.object(negotiation, "supplier_evaluate_contract", return_value=(
            "reject", "Let's discuss these terms.", None,
        )):
            response = self.client.post("/game/negotiate", json={
                "session_id": "test", "wholesale_price": 20,
                "buyback_price": 10, "length": 3, "contract_type": "buyback",
            })
        self.assertEqual(response.status_code, 200, response.text)
        second = self.chat(contract(25))
        self.assertGreater(second["offer_version"], first["offer_version"])
        self.assertEqual(self.decide(first["offer_version"]).status_code, 409)

    def test_chat_cannot_create_offer_after_acceptance(self):
        offer = self.chat(contract())
        self.assertEqual(self.decide(offer["offer_version"]).status_code, 200)
        with patch.object(negotiation, "generate_chat_response") as generate:
            response = self.client.post("/game/negotiate/chat", json={
                "session_id": "test", "message": "Make it $25.",
            })
        self.assertEqual(response.status_code, 400)
        generate.assert_not_called()

    def test_acceptance_during_revision_cannot_activate_old_offer(self):
        first = self.chat(contract())
        generating, release, accepting = Event(), Event(), Event()

        def generate(*args):
            self.assertIsNone(self.state.negotiation_draft_contract)
            generating.set()
            if not release.wait(5):
                raise AssertionError("Test did not release the supplier response")
            return {"message": "Revised wholesale price: $25", "draft_contract": contract(25)}

        def accept():
            accepting.set()
            return self.decide(first["offer_version"])

        with patch.object(negotiation, "generate_chat_response", side_effect=generate):
            with ThreadPoolExecutor(max_workers=2) as pool:
                chat = pool.submit(self.client.post, "/game/negotiate/chat", json={
                    "session_id": "test", "message": "Lower the price.",
                })
                try:
                    self.assertTrue(generating.wait(5))
                    decision = pool.submit(accept)
                    self.assertTrue(accepting.wait(5))
                finally:
                    release.set()
                self.assertEqual(chat.result(timeout=5).status_code, 200)
                self.assertEqual(decision.result(timeout=5).status_code, 409)
        self.assertEqual(self.state.contract.remaining_rounds, 0)
        self.assertEqual(self.state.negotiation_draft_contract.wholesale_price, 25)


class SupplierDraftTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.enterContext(patch.object(ai_service, "ai_provider", "openai"))
        self.enterContext(patch.object(ai_service, "openai_client", self.client))
        self.history = [
            {"role": "supplier", "content": "Wholesale price $30, buyback price $10, length 3 rounds."},
            {"role": "student", "content": "Can you lower the wholesale price to $25?"},
        ]

    def generate(self, content):
        self.client.chat.completions.create.return_value = SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(content=content)),
        ])
        return ai_service.generate_chat_response(self.history, contract(), initial_contract_type="buyback")

    def test_existing_draft_does_not_prevent_parsing_revised_terms(self):
        result = self.generate(json.dumps({
            "response": "I can offer wholesale $25, buyback $10, for 3 rounds.",
            "contract": {"wholesale_price": 25, "buyback_price": 10, "contract_length": 3},
        }))
        self.assertEqual(result["draft_contract"].wholesale_price, 25)
        self.assertEqual(result["draft_contract"].buyback_price, 10)
        self.assertEqual(result["draft_contract"].length, 3)

    def test_plain_text_does_not_reconstruct_offer_from_old_history(self):
        result = self.generate("My revised wholesale price is $25.")
        self.assertIsNone(result["draft_contract"])

    def test_malformed_output_does_not_reconstruct_offer(self):
        result = self.generate('{"response": "Revised wholesale price $25", "contract":')
        self.assertIsNone(result["draft_contract"])

    def test_partial_or_null_contract_is_not_an_offer(self):
        for terms in (None, {"wholesale_price": 25},
                      {"wholesale_price": 25, "buyback_price": 10},
                      {"wholesale_price": 25, "buyback_price": 30, "length": 3}):
            with self.subTest(terms=terms):
                result = self.generate(json.dumps({"response": "Let's discuss $25.", "contract": terms}))
                self.assertIsNone(result["draft_contract"])

    def test_provider_error_does_not_restore_previous_offer(self):
        self.client.chat.completions.create.side_effect = RuntimeError("Provider unavailable")
        result = ai_service.generate_chat_response(self.history, contract())
        self.assertIsNone(result["draft_contract"])

    def test_unconfigured_provider_does_not_restore_previous_offer(self):
        with patch.object(ai_service, "ai_provider", None):
            result = ai_service.generate_chat_response(self.history, contract())
        self.assertIsNone(result["draft_contract"])


if __name__ == "__main__":
    unittest.main()
