"""Replace RSA ad: change headline #2 from '1:a Fakturan Gratis!' to 'Första Fakturan Gratis!'"""

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.v23.enums import ServedAssetFieldTypeEnum

CUSTOMER_ID = "1485437843"
AD_GROUP_ID = "181470611511"
OLD_AD_ID = "800636021980"
AD_GROUP_RESOURCE = f"customers/{CUSTOMER_ID}/adGroups/{AD_GROUP_ID}"
OLD_AD_RESOURCE = f"customers/{CUSTOMER_ID}/adGroupAds/{AD_GROUP_ID}~{OLD_AD_ID}"
FINAL_URL = "https://paidin.se"

HEADLINES = [
    ("Fakturera Utan Företag", ServedAssetFieldTypeEnum.ServedAssetFieldType.HEADLINE_1),
    ("Första Fakturan Gratis!", ServedAssetFieldTypeEnum.ServedAssetFieldType.HEADLINE_2),
    ("Egenanställning Med Paidin", None),
    ("Inga Dolda Avgifter", None),
    ("BankID-inloggning", None),
    ("Snabb Utbetalning", None),
    ("4,72/5 På Google Reviews", None),
    ("Frilansa? Vi Sköter Allt", None),
    ("Få Betalt Snabbt & Tryggt", None),
    ("Skapa Konto Gratis Idag", None),
    ("Ingen Startavgift", None),
    ("Snabbt, Enkelt, Personligt", None),
]

DESCRIPTIONS = [
    "Fakturera dina uppdrag utan eget bolag. Vi hanterar skatt, moms och utbetalning.",
    "Skapa konto gratis med BankID. Snabb utbetalning och personlig support.",
    "Ingen startavgift. Pengarna på ditt konto när kunden betalat. Prova utan risk.",
    "Över 10 års erfarenhet av egenanställning. Personlig support och BankID-inloggning.",
]

def main():
    client = GoogleAdsClient.load_from_storage(
        path="C:/Users/danie/source/repos/Tools/google_ads_mcp/google-ads.yaml",
        version="v23",
    )

    service = client.get_service("AdGroupAdService")

    # Operation 1: REMOVE old ad
    remove_op = client.get_type("AdGroupAdOperation")
    remove_op.remove = OLD_AD_RESOURCE

    # Operation 2: CREATE new ad
    create_op = client.get_type("AdGroupAdOperation")
    ad_group_ad = create_op.create
    ad_group_ad.ad_group = AD_GROUP_RESOURCE
    ad_group_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED

    ad = ad_group_ad.ad
    ad.final_urls.append(FINAL_URL)

    # Add headlines
    for text, pin in HEADLINES:
        headline = client.get_type("AdTextAsset")
        headline.text = text
        if pin is not None:
            headline.pinned_field = pin
        ad.responsive_search_ad.headlines.append(headline)

    # Add descriptions
    for text in DESCRIPTIONS:
        desc = client.get_type("AdTextAsset")
        desc.text = text
        ad.responsive_search_ad.descriptions.append(desc)

    # Execute both operations in a single mutate call
    response = service.mutate_ad_group_ads(
        customer_id=CUSTOMER_ID,
        operations=[remove_op, create_op],
    )

    print(f"Operations completed: {len(response.results)} results")
    for result in response.results:
        print(f"  Resource: {result.resource_name}")

    # Extract new ad ID from the CREATE result (second result)
    new_resource = response.results[1].resource_name
    new_ad_id = new_resource.split("~")[1]
    print(f"\nOld ad removed: {OLD_AD_ID}")
    print(f"New ad created: {new_ad_id}")


if __name__ == "__main__":
    main()
