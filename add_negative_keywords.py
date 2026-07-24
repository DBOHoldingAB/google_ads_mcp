"""
Add negative keywords to a Google Ads campaign.
"""

from google.ads.googleads.client import GoogleAdsClient
import json

YAML_PATH = "C:/Users/danie/source/repos/Tools/google_ads_mcp/google-ads.yaml"
CUSTOMER_ID = "1485437843"
CAMPAIGN_ID = "22488375028"

client = GoogleAdsClient.load_from_storage(YAML_PATH, version="v23")
campaign_criterion_service = client.get_service("CampaignCriterionService")

# Negative keywords to add
keywords = [
    {"text": "billigast", "match_type": "BROAD"},
    {"text": "billigaste", "match_type": "BROAD"},
    {"text": "lägst avgift", "match_type": "BROAD"},
    {"text": "cheapest", "match_type": "BROAD"},
    {"text": "fakturamall", "match_type": "EXACT"},
    {"text": "hejfaktura", "match_type": "BROAD"},
    {"text": "gln nummer", "match_type": "BROAD"},
    {"text": "småföretagarnas a kassa", "match_type": "BROAD"},
    {"text": "konsultfaktura", "match_type": "BROAD"},
]

operations = []
for kw in keywords:
    operation = client.get_type("CampaignCriterionOperation")
    criterion = operation.create
    criterion.campaign = f"customers/{CUSTOMER_ID}/campaigns/{CAMPAIGN_ID}"
    criterion.negative = True
    criterion.keyword.text = kw["text"]
    match_type = kw.get("match_type", "BROAD").upper()
    criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum[match_type].value
    operations.append(operation)

print(f"Adding {len(operations)} negative keywords to campaign {CAMPAIGN_ID}...")
print()

try:
    response = campaign_criterion_service.mutate_campaign_criteria(
        customer_id=CUSTOMER_ID,
        operations=operations,
    )

    results = {
        "created": [r.resource_name for r in response.results],
        "count": len(response.results),
        "keywords_added": keywords
    }

    print("SUCCESS: Negative keywords added")
    print()
    print(json.dumps(results, indent=2, ensure_ascii=False))

except Exception as e:
    print(f"ERROR: {str(e)}")
    import traceback
    traceback.print_exc()
    exit(1)
