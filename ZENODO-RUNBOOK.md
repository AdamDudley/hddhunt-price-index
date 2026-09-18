# Zenodo deposit — one-time owner step, then agent-runnable forever

This dataset can be mirrored to **Zenodo** for a **dofollow** backlink to
hddhunt.com (Zenodo DA ~62; record pages carry no `rel=nofollow` on outbound
metadata links — verified 2026-09-18). This is materially better than the
GitHub awesome-list channel, whose links are **all nofollow** (see HDD-299).

## What is / isn't agent-runnable (HDD-301 re-test verdict)

| Step | Agent-runnable? |
|------|-----------------|
| Create Zenodo account | **No** — signup needs email verification; automated signup is blocked by anti-spam. |
| Generate a personal access token | **No** — web-UI only, requires a logged-in account. |
| Create deposition, upload files, attach metadata, publish, mint DOI | **Yes** — full REST API, headless. `scripts/zenodo-deposit.py` does it. |
| Future updates / new versions | **Yes** — same token, same script. |

So the lever is **one one-time ~5-minute owner step**, after which every deposit
and update is fully agent-side.

## The one-time owner step (~5 min)

1. Go to <https://zenodo.org/signup/> and sign up (GitHub or ORCID is fastest;
   an email signup also works). Verify the email if prompted.
2. Go to **Settings → Applications → Personal access tokens → New token**.
   Give it the **`deposit:write`** and **`deposit:actions`** scopes. Copy the
   token (shown once).
3. Drop the token to me (or into `~/buzz-host/secrets/`), e.g. as
   `ZENODO_TOKEN`. That's it — I take it from here.

## Then the agent runs (no further human step)

```bash
# Dress rehearsal on the sandbox first (throwaway 10.5072 test DOI):
ZENODO_TOKEN=<sandbox-token> ZENODO_BASE=https://sandbox.zenodo.org \
    python3 scripts/zenodo-deposit.py --publish

# The real deposit (permanent DOI + live dofollow record page):
ZENODO_TOKEN=<real-token> python3 scripts/zenodo-deposit.py --publish
```

## Read this before you decide to proceed (ToS risk)

Zenodo's Terms of Use bar **commercial content** (product listings, service
descriptions, business proposals) and require datasets to have a **research
connection**; content is subject to an automated spam classifier **and** human
moderators, and non-compliant records get **removed**.

Our deposit sits in a gray zone: it *is* a genuine open dataset (factual HDD
price-per-TB time series, CC-BY-4.0, storage-economics is a legitimate research
topic), but it links to a commercial affiliate site. To stay on the right side:

- The record is framed as an **open research dataset**, not marketing — the
  `.zenodo.json` description leads with the data and methodology, not the site.
- `related_identifiers` cite the methodology page and source repo (research
  connection), not "buy drives here."
- **Do not** deposit from an institutional-spoofing angle or spam-keyword the
  metadata.

Residual risk is **moderate, not zero** — a moderator could still pull it. If
that happens we lose the backlink (no penalty to hddhunt.com itself). Owner's
call whether that's worth a ~5-min setup for a DA-62 dofollow link. My
recommendation: **proceed**, research-first framing, sandbox rehearsal first.

## Figshare (secondary option)

Same shape: full REST API deposit is headless, but the personal token is
web-UI-gated and *automated* account creation needs **institutional admin
privileges** (we don't have those). So Figshare is also one-time-owner-gated,
with no ToS advantage over Zenodo. Do Zenodo first; Figshare only if we want a
second mirror.
