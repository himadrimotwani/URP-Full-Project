# URP Codebase Bug Review

**Project:** Fashion Supply Chain Simulation  
**Review date:** November 2, 2026  
**Status:** Nine actionable bugs identified; no application code changed

## Review Summary

The review identified two high-priority security issues and seven gameplay or data-integrity issues. The security findings should be addressed first because they allow participant-controlled content to run in an instructor's browser and allow unauthenticated users to modify shared simulation settings.

| Priority | Count | Meaning |
| --- | ---: | --- |
| P1 | 2 | High priority security issue |
| P2 | 7 | Gameplay, reliability, or data-integrity issue |

## Findings

### 1. Stored XSS in the instructor dashboard

**Priority:** P1  
**Location:** [`frontend/main.js:2049`](frontend/main.js#L2049)

Participant names, emails, student IDs, and section values are inserted directly into `innerHTML` when the instructor records table is rendered. A participant can submit HTML that the browser interprets when an instructor loads the records dashboard. This could compromise the instructor's browser session.

**Evidence:** A targeted Node reproduction confirmed that participant markup reaches the generated HTML without escaping. Browser script execution was not tested.

**Recommended fix:** Build table cells with DOM elements and assign values through `textContent`. Escaping each value before inserting it would also address the immediate issue, but avoiding HTML string construction is less error-prone. Add a regression test showing that HTML in participant fields is displayed as literal text.

### 2. Configuration changes require no instructor authentication

**Priority:** P1  
**Locations:** [`backend/app/routes/config.py:60`](backend/app/routes/config.py#L60), [`backend/app/routes/config.py:140`](backend/app/routes/config.py#L140)

Both configuration update endpoints allow unauthenticated callers to change shared economic parameters, demand history, and negotiation constraints. These changes can affect other participants and undermine simulation or research results.

**Evidence:** Neither handler has an instructor authentication dependency or access-code check. A direct no-op update call succeeded without credentials.

**Recommended fix:** Apply server-side instructor authorization to both write endpoints. Verify that missing and invalid credentials are rejected and that authorized configuration updates continue to work.

### 3. Negative orders corrupt simulation results

**Priority:** P2  
**Location:** [`backend/app/schemas.py:761`](backend/app/schemas.py#L761)

`OrderRequest` accepts negative quantities. Submitting `order_quantity=-10` produces negative sales and production costs while advancing the game round and updating cumulative results.

**Evidence:** A direct route reproduction returned `-10` sales and a negative production cost, then advanced the round from 1 to 2.

**Recommended fix:** Enforce `order_quantity >= 0` in the request schema. Verify that a negative order fails before game state or research records are changed.

### 4. Rejected proposals strand players when AI is unavailable

**Priority:** P2  
**Locations:** [`backend/app/services/ai_service.py:264`](backend/app/services/ai_service.py#L264), [`frontend/main.js:864`](frontend/main.js#L864)

Fallback chat returns a generic response without creating a draft contract. After a proposal is rejected, the frontend hides the proposal form and ordering remains unavailable. This leaves players without a normal route to an accepted contract.

**Evidence:** With AI disabled, a rejected proposal followed by acceptable revised terms and an agreement message never produced a draft contract. A Node check confirmed that both the proposal form and ordering were hidden.

**Recommended fix:** Provide a functional fallback negotiation path or allow players to submit a revised proposal. Test the complete rejection-to-acceptance flow with no AI provider configured.

### 5. Game summaries discard negotiation details

**Priority:** P2  
**Location:** [`backend/app/routes/game.py:316`](backend/app/routes/game.py#L316)

Game summary construction copies only `final_contract` into `NegotiationHistory`. Existing chat messages, final decisions, and start and end timestamps are replaced by empty lists or `null` values in the summary response.

**Evidence:** A session containing recorded messages, an acceptance decision, and timestamps returned an empty chat list and null decision and timestamps.

**Recommended fix:** Copy every recorded field when constructing `NegotiationHistory`. Verify that the summary response preserves the original negotiation record.

### 6. Chat can replace an active contract before it expires

**Priority:** P2  
**Locations:** [`backend/app/routes/negotiation.py:238`](backend/app/routes/negotiation.py#L238), [`backend/app/routes/negotiation.py:310`](backend/app/routes/negotiation.py#L310)

Chat and counteroffer acceptance omit the active-contract guard used by initial proposals. API calls can therefore create and accept a new draft while the current contract still has rounds remaining.

**Evidence:** With draft generation mocked, chat followed by acceptance replaced an active contract with wholesale price 30 and length 5 with a contract having wholesale price 20 and length 3.

**Recommended fix:** Reject chat and counteroffer acceptance while an active contract exists. Test that both endpoints leave current terms unchanged until the contract expires.

### 7. The AI uses the wrong demand history

**Priority:** P2  
**Locations:** [`backend/app/services/ai_service.py:273`](backend/app/services/ai_service.py#L273), [`backend/app/services/negotiation_service.py:83`](backend/app/services/negotiation_service.py#L83)

Negotiation reads the global default demand history even when a game selects a different scenario. Supplier reasoning can therefore use demand statistics that do not match the scenario shown to the player.

**Evidence:** A mocked provider captured chat messages for a session whose demand values were set to `99999`. Those session values were absent from the prompt, which used the global history.

**Recommended fix:** Pass the session's demand history consistently to proposal evaluation and chat generation. Test that different scenarios produce the corresponding demand context.

### 8. Instructor prompt changes have no effect

**Priority:** P2  
**Locations:** [`backend/app/services/ai_service.py:307`](backend/app/services/ai_service.py#L307), [`backend/app/services/negotiation_service.py:86`](backend/app/services/negotiation_service.py#L86)

The application saves `system_prompt_template` and `example_dialog`, but neither negotiation path uses them. Hardcoded prompts make instructor changes appear successful while leaving supplier behavior unchanged.

**Evidence:** A distinctive custom instruction was set in the loaded configuration and was absent from captured provider messages. Code inspection found no use of either setting in prompt construction.

**Recommended fix:** Incorporate the configured prompt and examples into provider messages while preserving required response parsing. Verify that a saved instruction reaches both negotiation paths.

### 9. Invalid proposals destroy the current negotiation state

**Priority:** P2  
**Location:** [`backend/app/routes/negotiation.py:103`](backend/app/routes/negotiation.py#L103)

The initial proposal handler clears the existing chat and draft contract before validating the new proposal. An invalid contract length returns HTTP 400 but still removes the current draft and active discussion state.

**Evidence:** Submitting `length=999` to a session with an existing chat history and draft returned HTTP 400 and left the chat empty and the draft `null`. The previous discussion was archived instead of being retained as the active negotiation.

**Recommended fix:** Validate the complete request before modifying session state or writing negotiation records. Verify that rejected requests preserve the current draft and discussion unchanged.

## Suggested Fix Order

1. Remove the stored XSS path from the instructor records table.
2. Protect configuration write endpoints with instructor authorization.
3. Validate order quantities at the API boundary.
4. Prevent negotiation endpoints from replacing active contracts.
5. Preserve negotiation state when a new proposal is invalid.
6. Restore negotiation details in game summaries.
7. Make the no-AI fallback negotiation completeable.
8. Pass session-specific demand history into AI negotiation.
9. Apply instructor prompt configuration to AI requests.

## Validation Scope

The findings were checked through source inspection and targeted Python and Node reproductions. External AI calls and research-record writes were mocked. No automated test suite was found, and full browser integration testing was not performed. Source line numbers refer to the reviewed checkout and may shift after edits.
