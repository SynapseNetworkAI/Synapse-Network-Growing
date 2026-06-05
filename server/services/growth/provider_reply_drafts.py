from __future__ import annotations

OFFICIAL_SITE = "https://www.synapse-network.ai/"


def draft_provider_reply(
    *,
    organization: str,
    company_description: str,
    inbound_subject: str,
    classification: str,
) -> tuple[str, str]:
    subject = reply_subject(inbound_subject)
    if classification == "not_interested":
        body = (
            f"Hi {organization} team,\n\n"
            "Thanks for the quick reply. I understand this is not relevant right now, "
            "and I will not follow up further.\n\n"
            "Best,\nCliff\nSynapse Network\n"
            f"{OFFICIAL_SITE}\n"
        )
    elif classification == "question":
        body = (
            f"Hi {organization} team,\n\n"
            "Thanks for the question. The short version: Synapse lets agent builders "
            "discover provider services, call metered APIs with budget caps, and keep "
            "receipt evidence for every successful call.\n\n"
            "For a provider, the next step is a small service contract that defines the "
            "API surface, pricing unit, auth boundary, and success criteria. I can send "
            "a concrete example tailored to your service if helpful.\n\n"
            f"Official site: {OFFICIAL_SITE}\n\n"
            "Best,\nCliff\nSynapse Network\n"
        )
    else:
        fit_line = company_description or (
            f"{organization} looks aligned with agent-callable API workflows."
        )
        body = (
            f"Hi {organization} team,\n\n"
            "Thanks for getting back to me. Based on your reply, the useful next step "
            "would be to send the provider registration details and a sample service "
            "contract.\n\n"
            f"My read on the fit: {fit_line}\n\n"
            "The sample will cover API registration, usage pricing, budget-isolated "
            "agent calls, and USDC settlement evidence. No guaranteed volume or revenue "
            "claims, just the concrete integration path.\n\n"
            f"Official site: {OFFICIAL_SITE}\n\n"
            "Best,\nCliff\nSynapse Network\n"
        )
    return subject, body


def reply_subject(subject: str) -> str:
    clean = subject.strip() or "Synapse provider channel"
    return clean if clean.lower().startswith("re:") else f"Re: {clean}"
