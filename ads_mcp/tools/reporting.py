# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Reporting tools for Google Ads API."""

from google.protobuf import message
from google.protobuf.json_format import MessageToDict
import json
from typing import Any

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.tools._utils import get_ads_client
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.util import get_nested_attr
from google.ads.googleads.v24.services.services.google_ads_service import GoogleAdsServiceClient
import proto


def preprocess_gaql(query: str) -> str:
  """Preprocesses a GAQL query to add omit_unselected_resource_names=true."""
  if "omit_unselected_resource_names" not in query:
    if "PARAMETERS" in query and "include_drafts" in query:
      return query + " omit_unselected_resource_names=true"
    return query + " PARAMETERS omit_unselected_resource_names=true"
  return query


def format_value(value: Any) -> Any:
  """Formats a value from a Google Ads API response."""
  if isinstance(value, proto.marshal.collections.repeated.Repeated):
    return_value = [format_value(i) for i in value]
  elif isinstance(value, proto.Message):
    # convert to json first to avoid serialization issues
    return_value = proto.Message.to_dict(
        value,
        use_integers_for_enums=False,
    )
  elif isinstance(value, proto.Enum):
    return_value = value.name
  elif isinstance(value, message.Message):
    # Handle raw google.protobuf types that are not proto-plus messages.
    # (e.g. FieldMask from change_event.changed_fields)
    return_value = MessageToDict(value)
  else:
    return_value = value

  return return_value


@mcp.tool(
    output_schema={
        "type": "object",
        "properties": {
            "data": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["data"],
    }
)
def execute_gaql(
    query: str,
    customer_id: str,
    login_customer_id: str | None = None,
) -> list[dict[str, Any]]:
  """Executes a Google Ads Query Language (GAQL) query to get reporting data.

  Args:
      query: The GAQL query to execute.
      customer_id: The ID of the customer being queried. It is only digits.
      login_customer_id: (Optional) The ID of the customer being logged in.
        Usually, it is the MCC on top of the target customer account. It is only
        digits. In most cases, a default account is set, it could be optional.

  Returns:
      An array of object, each object representing a row of the query results.
  """
  query = preprocess_gaql(query)
  ads_client = get_ads_client()
  if login_customer_id:
    ads_client.login_customer_id = login_customer_id
  ads_service: GoogleAdsServiceClient = ads_client.get_service(
      "GoogleAdsService"
  )
  try:
    query_res = ads_service.search_stream(query=query, customer_id=customer_id)
    output = []
    for batch in query_res:
      for row in batch.results:
        output.append(
            {
                i: format_value(get_nested_attr(row, i))
                for i in batch.field_mask.paths
            }
        )
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(i) for i in e.failure.errors)) from e

  return {"data": output}


def _get_mutate_client(customer_id: str, login_customer_id: str | None = None):
  """Helper to get ads client and service configured for mutations."""
  ads_client = get_ads_client()
  if login_customer_id:
    ads_client.login_customer_id = login_customer_id
  return ads_client


@mcp.tool()
def update_campaign_budget(
    campaign_id: str,
    budget_amount_micros: int,
    customer_id: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Updates the daily budget for a campaign.

  Args:
      campaign_id: The campaign ID whose budget to update.
      budget_amount_micros: The new daily budget in micros (1 SEK = 1000000 micros).
          Example: 200 SEK/day = 200000000.
      customer_id: The customer account ID (digits only).
      login_customer_id: (Optional) The MCC account ID.

  Returns:
      A dict with the updated budget resource name.
  """
  ads_client = _get_mutate_client(customer_id, login_customer_id)

  # First find the budget resource for this campaign
  ga_service = ads_client.get_service("GoogleAdsService")
  query = f"""
    SELECT campaign.id, campaign_budget.resource_name
    FROM campaign_budget
    WHERE campaign.id = {campaign_id}
  """
  try:
    results = ga_service.search_stream(query=query, customer_id=customer_id)
    budget_resource = None
    for batch in results:
      for row in batch.results:
        budget_resource = row.campaign_budget.resource_name
        break
    if not budget_resource:
      raise ToolError(f"No budget found for campaign {campaign_id}")
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(i) for i in e.failure.errors)) from e

  # Update the budget
  budget_service = ads_client.get_service("CampaignBudgetService")
  budget_operation = ads_client.get_type("CampaignBudgetOperation")
  budget = budget_operation.update
  budget.resource_name = budget_resource
  budget.amount_micros = budget_amount_micros
  budget_operation.update_mask.paths.append("amount_micros")

  try:
    response = budget_service.mutate_campaign_budgets(
        customer_id=customer_id,
        operations=[budget_operation],
    )
    return {"updated": response.results[0].resource_name}
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(i) for i in e.failure.errors)) from e


@mcp.tool()
def add_negative_keywords(
    campaign_id: str,
    keywords: list[dict[str, str]],
    customer_id: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Adds negative keywords to a campaign.

  Args:
      campaign_id: The campaign ID to add negative keywords to.
      keywords: List of keyword dicts, each with "text" and "match_type".
          match_type is one of: BROAD, PHRASE, EXACT.
          Example: [{"text": "cool company", "match_type": "BROAD"}]
      customer_id: The customer account ID (digits only).
      login_customer_id: (Optional) The MCC account ID.

  Returns:
      A dict with a list of created resource names.
  """
  ads_client = _get_mutate_client(customer_id, login_customer_id)
  campaign_criterion_service = ads_client.get_service("CampaignCriterionService")

  operations = []
  for kw in keywords:
    operation = ads_client.get_type("CampaignCriterionOperation")
    criterion = operation.create
    criterion.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
    criterion.negative = True
    criterion.keyword.text = kw["text"]
    match_type = kw.get("match_type", "BROAD").upper()
    criterion.keyword.match_type = ads_client.enums.KeywordMatchTypeEnum[match_type].value
    operations.append(operation)

  try:
    response = campaign_criterion_service.mutate_campaign_criteria(
        customer_id=customer_id,
        operations=operations,
    )
    return {
        "created": [r.resource_name for r in response.results],
        "count": len(response.results),
    }
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(i) for i in e.failure.errors)) from e


@mcp.tool()
def update_keyword_status(
    ad_group_id: str,
    criterion_id: str,
    status: str,
    customer_id: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Updates the status of a keyword (enable or pause).

  Args:
      ad_group_id: The ad group ID containing the keyword.
      criterion_id: The criterion (keyword) ID to update.
      status: New status: ENABLED or PAUSED.
      customer_id: The customer account ID (digits only).
      login_customer_id: (Optional) The MCC account ID.

  Returns:
      A dict with the updated resource name.
  """
  ads_client = _get_mutate_client(customer_id, login_customer_id)
  ad_group_criterion_service = ads_client.get_service("AdGroupCriterionService")

  operation = ads_client.get_type("AdGroupCriterionOperation")
  criterion = operation.update
  criterion.resource_name = (
      f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{criterion_id}"
  )
  criterion.status = ads_client.enums.AdGroupCriterionStatusEnum[status.upper()].value
  operation.update_mask.paths.append("status")

  try:
    response = ad_group_criterion_service.mutate_ad_group_criteria(
        customer_id=customer_id,
        operations=[operation],
    )
    return {"updated": response.results[0].resource_name}
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(i) for i in e.failure.errors)) from e


@mcp.tool()
def add_keywords(
    ad_group_id: str,
    keywords: list[dict[str, str]],
    customer_id: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Adds keywords to an ad group.

  Args:
      ad_group_id: The ad group ID to add keywords to.
      keywords: List of keyword dicts, each with "text", "match_type",
          and optionally "cpc_bid_micros".
          match_type is one of: BROAD, PHRASE, EXACT.
          Example: [{"text": "egenanställning", "match_type": "PHRASE"}]
      customer_id: The customer account ID (digits only).
      login_customer_id: (Optional) The MCC account ID.

  Returns:
      A dict with a list of created resource names.
  """
  ads_client = _get_mutate_client(customer_id, login_customer_id)
  ad_group_criterion_service = ads_client.get_service("AdGroupCriterionService")

  operations = []
  for kw in keywords:
    operation = ads_client.get_type("AdGroupCriterionOperation")
    criterion = operation.create
    criterion.ad_group = f"customers/{customer_id}/adGroups/{ad_group_id}"
    criterion.status = ads_client.enums.AdGroupCriterionStatusEnum.ENABLED.value
    criterion.keyword.text = kw["text"]
    match_type = kw.get("match_type", "PHRASE").upper()
    criterion.keyword.match_type = ads_client.enums.KeywordMatchTypeEnum[match_type].value
    if "cpc_bid_micros" in kw:
      criterion.cpc_bid_micros = int(kw["cpc_bid_micros"])
    operations.append(operation)

  try:
    response = ad_group_criterion_service.mutate_ad_group_criteria(
        customer_id=customer_id,
        operations=operations,
    )
    return {
        "created": [r.resource_name for r in response.results],
        "count": len(response.results),
    }
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(i) for i in e.failure.errors)) from e


@mcp.tool()
def update_campaign_bidding_strategy(
    campaign_id: str,
    strategy_type: str,
    target_cpa_micros: int | None = None,
    customer_id: str = "",
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Updates a campaign's bidding strategy.

  Args:
      campaign_id: The campaign ID to update.
      strategy_type: One of: MAXIMIZE_CONVERSIONS, TARGET_CPA, MANUAL_CPC.
      target_cpa_micros: (Optional) Target CPA in micros when using
          MAXIMIZE_CONVERSIONS or TARGET_CPA. Example: 900 SEK = 900000000.
      customer_id: The customer account ID (digits only).
      login_customer_id: (Optional) The MCC account ID.

  Returns:
      A dict with the updated resource name.
  """
  ads_client = _get_mutate_client(customer_id, login_customer_id)
  campaign_service = ads_client.get_service("CampaignService")

  operation = ads_client.get_type("CampaignOperation")
  campaign = operation.update
  campaign.resource_name = f"customers/{customer_id}/campaigns/{campaign_id}"

  if strategy_type.upper() == "MAXIMIZE_CONVERSIONS":
    if target_cpa_micros:
      campaign.maximize_conversions.target_cpa_micros = target_cpa_micros
      operation.update_mask.paths.append("maximize_conversions.target_cpa_micros")
    else:
      operation.update_mask.paths.append("maximize_conversions")
  elif strategy_type.upper() == "TARGET_CPA":
    if target_cpa_micros:
      campaign.target_cpa.target_cpa_micros = target_cpa_micros
      operation.update_mask.paths.append("target_cpa.target_cpa_micros")
    else:
      operation.update_mask.paths.append("target_cpa")
  elif strategy_type.upper() == "MANUAL_CPC":
    campaign.manual_cpc.enhanced_cpc_enabled = False
    operation.update_mask.paths.append("manual_cpc.enhanced_cpc_enabled")

  try:
    response = campaign_service.mutate_campaigns(
        customer_id=customer_id,
        operations=[operation],
    )
    return {"updated": response.results[0].resource_name}
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(i) for i in e.failure.errors)) from e


@mcp.tool()
def update_campaign_url_settings(
    campaign_id: str,
    customer_id: str,
    tracking_url_template: str | None = None,
    custom_parameters: list[dict[str, str]] | None = None,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Updates a campaign's tracking URL template and/or custom URL parameters.

  Used for ValueTrack-baserade UTM-mallar (t.ex. {lpurl}?utm_source=google&...&utm_campaign={_campaign})
  och de associerade custom parameters som mallen refererar till.

  Args:
      campaign_id: The campaign ID to update.
      customer_id: The customer account ID (digits only).
      tracking_url_template: (Optional) Tracking template, t.ex.
          "{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign={_campaign}&utm_content={_adgroup}&utm_term={keyword}&gclid={gclid}".
          Skicka None för att låta nuvarande mall vara orörd, tom strang "" för att rensa.
      custom_parameters: (Optional) Lista av {"key": "...", "value": "..."}-dicts.
          Ersätter alla befintliga custom parameters om angivet. Skicka None för att
          lämna orörda, tom lista [] för att rensa.
          Exempel: [{"key": "_campaign", "value": "fakturera_utan_foretag"}]
      login_customer_id: (Optional) The MCC account ID.

  Returns:
      A dict with the updated resource name and what fields were changed.
  """
  if tracking_url_template is None and custom_parameters is None:
    raise ToolError("Anger minst ett av tracking_url_template eller custom_parameters.")

  ads_client = _get_mutate_client(customer_id, login_customer_id)
  campaign_service = ads_client.get_service("CampaignService")

  operation = ads_client.get_type("CampaignOperation")
  campaign = operation.update
  campaign.resource_name = f"customers/{customer_id}/campaigns/{campaign_id}"

  changed = []

  if tracking_url_template is not None:
    campaign.tracking_url_template = tracking_url_template
    operation.update_mask.paths.append("tracking_url_template")
    changed.append("tracking_url_template")

  if custom_parameters is not None:
    # Bygg om hela listan av CustomParameter
    for param in custom_parameters:
      cp = ads_client.get_type("CustomParameter")
      cp.key = param["key"]
      cp.value = param["value"]
      campaign.url_custom_parameters.append(cp)
    operation.update_mask.paths.append("url_custom_parameters")
    changed.append(f"url_custom_parameters ({len(custom_parameters)} st)")

  try:
    response = campaign_service.mutate_campaigns(
        customer_id=customer_id,
        operations=[operation],
    )
    return {"updated": response.results[0].resource_name, "changed": changed}
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(i) for i in e.failure.errors)) from e


@mcp.tool()
def rename_ad_group(
    ad_group_id: str,
    new_name: str,
    customer_id: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Renames an ad group.

  Args:
      ad_group_id: The ad group ID to rename.
      new_name: The new ad group name (max 255 chars, must be unique within campaign).
      customer_id: The customer account ID (digits only).
      login_customer_id: (Optional) The MCC account ID.

  Returns:
      A dict with the updated resource name.
  """
  ads_client = _get_mutate_client(customer_id, login_customer_id)
  ad_group_service = ads_client.get_service("AdGroupService")

  operation = ads_client.get_type("AdGroupOperation")
  ad_group = operation.update
  ad_group.resource_name = f"customers/{customer_id}/adGroups/{ad_group_id}"
  ad_group.name = new_name
  operation.update_mask.paths.append("name")

  try:
    response = ad_group_service.mutate_ad_groups(
        customer_id=customer_id,
        operations=[operation],
    )
    return {"updated": response.results[0].resource_name, "new_name": new_name}
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(i) for i in e.failure.errors)) from e


@mcp.tool()
def rename_campaign(
    campaign_id: str,
    new_name: str,
    customer_id: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Renames a campaign.

  Args:
      campaign_id: The campaign ID to rename.
      new_name: The new campaign name (max 255 chars, must be unique within account).
      customer_id: The customer account ID (digits only).
      login_customer_id: (Optional) The MCC account ID.

  Returns:
      A dict with the updated resource name.
  """
  ads_client = _get_mutate_client(customer_id, login_customer_id)
  campaign_service = ads_client.get_service("CampaignService")

  operation = ads_client.get_type("CampaignOperation")
  campaign = operation.update
  campaign.resource_name = f"customers/{customer_id}/campaigns/{campaign_id}"
  campaign.name = new_name
  operation.update_mask.paths.append("name")

  try:
    response = campaign_service.mutate_campaigns(
        customer_id=customer_id,
        operations=[operation],
    )
    return {"updated": response.results[0].resource_name, "new_name": new_name}
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(i) for i in e.failure.errors)) from e


@mcp.tool()
def set_campaign_status(
    campaign_id: str,
    status: str,
    customer_id: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Pausar eller aktiverar en kampanj.

  Tillagd 2026-10-07: kampanjen "Fakturera utan företag – Paidin" stod ENABLED
  trots att all annonsering pausats 2026-09-30 (DEC-2026-0149), och servern
  saknade ett sätt att pausa en kampanj. REMOVED tillåts inte: borttagning går
  inte att ångra och görs i Google Ads-gränssnittet.

  Args:
      campaign_id: The campaign ID.
      status: PAUSED or ENABLED.
      customer_id: The customer account ID (digits only).
      login_customer_id: (Optional) The MCC account ID.

  Returns:
      A dict with the updated resource name and the new status.
  """
  status = status.upper()
  if status not in ("PAUSED", "ENABLED"):
    raise ToolError("status måste vara PAUSED eller ENABLED.")

  ads_client = _get_mutate_client(customer_id, login_customer_id)
  campaign_service = ads_client.get_service("CampaignService")

  operation = ads_client.get_type("CampaignOperation")
  campaign = operation.update
  campaign.resource_name = f"customers/{customer_id}/campaigns/{campaign_id}"
  campaign.status = ads_client.enums.CampaignStatusEnum[status].value
  operation.update_mask.paths.append("status")

  try:
    response = campaign_service.mutate_campaigns(
        customer_id=customer_id,
        operations=[operation],
    )
    return {"updated": response.results[0].resource_name, "status": status}
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(i) for i in e.failure.errors)) from e


@mcp.tool()
def update_ad_group_url_settings(
    ad_group_id: str,
    customer_id: str,
    tracking_url_template: str | None = None,
    custom_parameters: list[dict[str, str]] | None = None,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Updates an ad group's tracking URL template and/or custom URL parameters.

  Custom parameters på ad_group-nivå skriver över de på campaign-nivå för samma key.
  Tracking template på ad_group-nivå skriver över campaign-nivå om satt.

  Args:
      ad_group_id: The ad group ID to update.
      customer_id: The customer account ID (digits only).
      tracking_url_template: (Optional) Tracking template. Skicka None för att lamna orord,
          tom strang "" för att rensa.
      custom_parameters: (Optional) Lista av {"key": "...", "value": "..."}-dicts.
          Ersätter alla befintliga custom parameters för annonsgruppen.
          Exempel: [{"key": "_adgroup", "value": "hantverkare_search"}]
      login_customer_id: (Optional) The MCC account ID.

  Returns:
      A dict with the updated resource name and what fields were changed.
  """
  if tracking_url_template is None and custom_parameters is None:
    raise ToolError("Anger minst ett av tracking_url_template eller custom_parameters.")

  ads_client = _get_mutate_client(customer_id, login_customer_id)
  ad_group_service = ads_client.get_service("AdGroupService")

  operation = ads_client.get_type("AdGroupOperation")
  ad_group = operation.update
  ad_group.resource_name = f"customers/{customer_id}/adGroups/{ad_group_id}"

  changed = []

  if tracking_url_template is not None:
    ad_group.tracking_url_template = tracking_url_template
    operation.update_mask.paths.append("tracking_url_template")
    changed.append("tracking_url_template")

  if custom_parameters is not None:
    for param in custom_parameters:
      cp = ads_client.get_type("CustomParameter")
      cp.key = param["key"]
      cp.value = param["value"]
      ad_group.url_custom_parameters.append(cp)
    operation.update_mask.paths.append("url_custom_parameters")
    changed.append(f"url_custom_parameters ({len(custom_parameters)} st)")

  try:
    response = ad_group_service.mutate_ad_groups(
        customer_id=customer_id,
        operations=[operation],
    )
    return {"updated": response.results[0].resource_name, "changed": changed}
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(i) for i in e.failure.errors)) from e
