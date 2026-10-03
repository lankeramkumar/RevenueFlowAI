"""Demo-mode entity extraction: both intent.md-style bare IDs (RCP-2001)
and scenario-prefixed synthetic IDs (S01-RCP, S09-INV-USD) must resolve to
the same entity key, since the specialist handlers don't know which
naming convention produced the data they're querying.
"""

from revenueflowai.agents.providers.demo import extract_entities


def test_bare_ids_match_intent_md_style():
    assert extract_entities("Why is invoice INV-1003 overdue?") == {"invoice_id": "INV-1003"}
    assert extract_entities("Which invoices might match receipt RCP-2001?") == {"receipt_id": "RCP-2001"}
    assert extract_entities("Why is order ORD-3001 on hold?") == {"order_id": "ORD-3001"}


def test_scenario_prefixed_ids_also_match():
    assert extract_entities("Which invoices might match receipt S01-RCP?") == {"receipt_id": "S01-RCP"}
    assert extract_entities("What about invoice S09-INV-USD?") == {"invoice_id": "S09-INV-USD"}


def test_no_id_returns_empty():
    assert extract_entities("What's the weather like today?") == {}


def test_multiple_ids_in_one_question():
    entities = extract_entities("Does receipt RCP-2001 cover invoice INV-1003?")
    assert entities == {"receipt_id": "RCP-2001", "invoice_id": "INV-1003"}
