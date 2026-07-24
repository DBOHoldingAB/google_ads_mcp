"""
Verify negative keywords in a Google Ads campaign.
"""

from google.ads.googleads.client import GoogleAdsClient
import json

YAML_PATH = "/sessions/festive-serene-pascal/mnt/repos/Tools/google_ads_mcp/google-ads.yaml"
CUSTOMER_ID = "1485437843"
CAMPAIGN_ID = "22488375028"

client = GoogleAdsClient.load_from_storage(YAML_PATH, version="v23")
ga_service = client.get_service("GoogleAdsService")

# Query to get all negative keywords in the campaign
query = f"""
SELECT
    campaign_criterion.criterion_id,
    campaign_criterion.keyword.text,
    campaign_criterion.keyword.match_type,
    campaign_criterion.negative
FROM campaign_criterion
WHERE campaign.id = {CAMPAIGN_ID}
    AND campaign_criterion.type = 'KEYWORD'
    AND campaign_criterion.negative = true
ORDER BY campaign_criterion.criterion_id
"""

print(f"Querying negative keywords for campaign {CAMPAIGN_ID}...")
print()

try:
    results = ga_service.search_stream(query=query, customer_id=CUSTOMER_ID)

    keywords = []
    for batch in results:
        for row in batch.results:
            keywords.append({
                "criterion_id": row.campaign_criterion.criterion_id,
                "text": row.campaign_criterion.keyword.text,
                "match_type": row.campaign_criterion.keyword.match_type.name,
            })

    output = {
        "total_negative_keywords": len(keywords),
        "campaign_id": CAMPAIGN_ID,
        "keywords": keywords
    }

    print("SUCCESS: Retrieved negative keywords")
    print()
    print(json.dumps(output, indent=2, ensure_ascii=False))

except Exception as e:
    print(f"ERROR: {str(e)}")
    import traceback
    traceback.print_exc()
    exit(1)
