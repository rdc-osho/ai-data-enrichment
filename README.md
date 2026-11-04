# AI Company Data Enrichment with Human Review

B2B publishers keep long lists of organisations for news, events and marketing. Researching each company by hand is slow. AI assistants are fast but sometimes guess. This tool lets AI do the first pass and makes sure a person checks anything uncertain.

## What it does

1. Reads a CSV of company names. The sample has 12 UK energy and water companies.
2. Asks the Claude API for four public facts about each company, which are sector, regulator (Ofgem or Ofwat), head office city and website.
3. Checks every answer against allowed values and simple rules. For example, a water company should never show Ofgem as its regulator.
4. Flags a row for human review when confidence is not high, an answer is Unknown, or a rule fails.
5. Saves a CSV ready for review and prints the tokens used and a time comparison.

## Privacy and safety

* **No personal data.** It only asks for facts about companies, and it removes anything that looks like an email address or phone number.
* **The API key never goes in the code.** It lives in a local `.env` file, which `.gitignore` keeps out of GitHub. The `.env.example` file shows the format.
* **Nothing irreversible.** Results go to a local CSV for a person to check. Nothing is written to a live database or CRM.
* **Honest about uncertainty.** The prompt tells the model to answer Unknown rather than guess.

## Results from the first real run

12 companies enriched in 32 seconds using 7,399 tokens, which cost a few pence.

8 rows passed every check and 4 were flagged for review, all for good reasons.

* **British Gas.** The head office given was Windsor, which belongs to its parent company Centrica.
* **Severn Trent.** The group and the water company use different websites.
* **E.ON Next and National Grid.** The head office depends on which part of the group you list.

I then checked every row by hand. All the core fields were correct. One row marked high confidence (United Utilities) had a wrong claim in its notes, saying it sold Electricity North West in 2024. It actually sold it in 2007.

**What I learned.** A confidence score is not proof, which is why a person stays in the loop. The next step is to check each answer against a second source such as Companies House.

**Time saved.** About 40 minutes, assuming 4 minutes to research each company by hand.

## How to run it

```
pip install -r requirements.txt
cp .env.example .env
python enrich.py companies.csv
```

Add your own API key to `.env` before running. To try it offline without a key, run `python enrich.py companies.csv --mock`.

## Next steps

1. Check each website automatically by requesting the domain.
2. Compare answers with Companies House and the Ofgem and Ofwat public registers.
3. Run the same flow on a schedule in Zapier or Power Automate.

## Tools

Python, requests, Claude API, CSV and regular expressions.
