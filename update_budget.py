"""
Update Google Ads campaign daily budget.
"""

from google.ads.googleads.client import GoogleAdsClient

YAML_PATH = "/sessions/festive-serene-pascal/mnt/repos/Tools/google_ads_mcp/google-ads.yaml"
CUSTOMER_ID = "1485437843"
LOGIN_CUSTOMER_ID = "2332806327"
CAMPAIGN_ID = "22488375028"
NEW_BUDGET_MICROS = 250000000  # 250 kr in micros

client = GoogleAdsClient.load_from_storage(YAML_PATH, version="v23")
client.login_customer_id = LOGIN_CUSTOMER_ID

# Get the budget resource for this campaign
ga_service = client.get_service("GoogleAdsService")
query = f"""
    SELECT campaign.id, campaign_budget.resource_name, campaign_budget.amount_micros
    FROM campaign_budget
    WHERE campaign.id = {CAMPAIGN_ID}
"""

print("Searching for campaign budget...")
results = ga_service.search_stream(query=query, customer_id=CUSTOMER_ID)
budget_resource = None
old_budget = None
for batch in results:
    for row in batch.results:
        budget_resource = row.campaign_budget.resource_name
        old_budget = row.campaign_budget.amount_micros
        break

if not budget_resource:
    print(f"ERROR: No budget found for campaign {CAMPAIGN_ID}")
    exit(1)

print(f"Found budget: {budget_resource}")
print(f"Old budget: {old_budget} micros ({old_budget / 1000000} kr)")
print(f"New budget: {NEW_BUDGET_MICROS} micros ({NEW_BUDGET_MICROS / 1000000} kr)")

# Update the budget
budget_service = client.get_service("CampaignBudgetService")
budget_operation = client.get_type("CampaignBudgetOperation")
budget = budget_operation.update
budget.resource_name = budget_resource
budget.amount_micros = NEW_BUDGET_MICROS
budget_operation.update_mask.paths.append("amount_micros")

print("\nUpdating campaign budget...")
response = budget_service.mutate_campaign_budgets(
    customer_id=CUSTOMER_ID,
    operations=[budget_operation],
)
print(f"Successfully updated: {response.results[0].resource_name}")

# Verify the change
print("\nVerifying updated budget...")
results = ga_service.search_stream(query=query, customer_id=CUSTOMER_ID)
for batch in results:
    for row in batch.results:
        verified_budget = row.campaign_budget.amount_micros
        print(f"Verified new budget: {verified_budget} micros ({verified_budget / 1000000} kr)")
        if verified_budget == NEW_BUDGET_MICROS:
            print("✓ Budget update verified successfully!")
        else:
            print(f"✗ Budget mismatch! Expected {NEW_BUDGET_MICROS}, got {verified_budget}")
        break
