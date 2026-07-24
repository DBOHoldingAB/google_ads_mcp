"""
Update Google Ads: replace sitelink asset and add callout asset.
"""

from google.ads.googleads.client import GoogleAdsClient

YAML_PATH = r"C:\Users\danie\source\repos\Tools\google_ads_mcp\google-ads.yaml"
CUSTOMER_ID = "1485437843"
CAMPAIGN_ID = "22488375028"

client = GoogleAdsClient.load_from_storage(YAML_PATH, version="v23")
asset_service = client.get_service("AssetService")
campaign_asset_service = client.get_service("CampaignAssetService")

# ─── Task 1: Create new sitelink and link it (old one already removed) ───

asset_op = client.get_type("AssetOperation")
sitelink_asset = asset_op.create
sitelink_asset.name = "Priser Sitelink"
sitelink_asset.sitelink_asset.link_text = "Priser"
sitelink_asset.sitelink_asset.description1 = "Bara 4,8% per faktura"
sitelink_asset.sitelink_asset.description2 = "Inga dolda avgifter"
sitelink_asset.final_urls.append("https://paidin.se")

print("Creating new sitelink asset...")
response = asset_service.mutate_assets(
    customer_id=CUSTOMER_ID,
    operations=[asset_op],
)
new_sitelink_resource = response.results[0].resource_name
print(f"Created sitelink asset: {new_sitelink_resource}")

# Link new sitelink to campaign
link_op = client.get_type("CampaignAssetOperation")
campaign_asset = link_op.create
campaign_asset.campaign = f"customers/{CUSTOMER_ID}/campaigns/{CAMPAIGN_ID}"
campaign_asset.asset = new_sitelink_resource
campaign_asset.field_type = client.enums.AssetFieldTypeEnum.SITELINK

print("Linking new sitelink to campaign...")
response = campaign_asset_service.mutate_campaign_assets(
    customer_id=CUSTOMER_ID,
    operations=[link_op],
)
print(f"Linked: {response.results[0].resource_name}")

# ─── Task 2: Add callout "Första Fakturan Gratis" ───

callout_op = client.get_type("AssetOperation")
callout_asset = callout_op.create
callout_asset.name = "Första Fakturan Gratis Callout"
callout_asset.callout_asset.callout_text = "Första Fakturan Gratis"

print("\nCreating callout asset...")
response = asset_service.mutate_assets(
    customer_id=CUSTOMER_ID,
    operations=[callout_op],
)
new_callout_resource = response.results[0].resource_name
print(f"Created callout asset: {new_callout_resource}")

# Link callout to campaign
callout_link_op = client.get_type("CampaignAssetOperation")
callout_campaign_asset = callout_link_op.create
callout_campaign_asset.campaign = f"customers/{CUSTOMER_ID}/campaigns/{CAMPAIGN_ID}"
callout_campaign_asset.asset = new_callout_resource
callout_campaign_asset.field_type = client.enums.AssetFieldTypeEnum.CALLOUT

print("Linking callout to campaign...")
response = campaign_asset_service.mutate_campaign_assets(
    customer_id=CUSTOMER_ID,
    operations=[callout_link_op],
)
print(f"Linked: {response.results[0].resource_name}")

print("\nAll operations completed successfully.")
