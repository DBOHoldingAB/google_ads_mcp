"""Keyword Planner tools (read-only) for Google Ads API.

Wraps KeywordPlanIdeaService so search volumes and keyword ideas can be
fetched without the Google Ads web UI. Neither call changes anything in the
account; they are registered regardless of ADS_MCP_ENABLE_MUTATIONS.
"""

from typing import Any

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.tools._utils import get_ads_client
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException

# Defaults for Paidin: Swedish language, Sweden as location.
DEFAULT_LANGUAGE_ID = "1015"
DEFAULT_GEO_TARGET_IDS = ("2752",)
MAX_KEYWORDS_PER_REQUEST = 10_000
MAX_SEED_KEYWORDS = 20


def _metrics_to_dict(metrics: Any) -> dict[str, Any]:
  """Converts KeywordPlanHistoricalMetrics to a plain dict."""
  if metrics is None:
    return {}
  return {
      "avg_monthly_searches": metrics.avg_monthly_searches,
      "competition": metrics.competition.name,
      "competition_index": metrics.competition_index,
      "low_top_of_page_bid_micros": metrics.low_top_of_page_bid_micros,
      "high_top_of_page_bid_micros": metrics.high_top_of_page_bid_micros,
      "average_cpc_micros": metrics.average_cpc_micros,
      "monthly_search_volumes": [
          {
              "year": m.year,
              "month": m.month.name,
              "monthly_searches": m.monthly_searches,
          }
          for m in metrics.monthly_search_volumes
      ],
  }


def _prepare(
    customer_id: str,
    language_id: str,
    geo_target_ids: list[str] | None,
    login_customer_id: str | None,
):
  """Returns (client, service, language resource, geo resources)."""
  ads_client = get_ads_client()
  if login_customer_id:
    ads_client.login_customer_id = login_customer_id
  service = ads_client.get_service("KeywordPlanIdeaService")
  language = ads_client.get_service(
      "GoogleAdsService"
  ).language_constant_path(language_id)
  geo_service = ads_client.get_service("GeoTargetConstantService")
  geos = [
      geo_service.geo_target_constant_path(g)
      for g in (geo_target_ids or DEFAULT_GEO_TARGET_IDS)
  ]
  return ads_client, service, language, geos


def _network(ads_client, include_partners: bool):
  enum = ads_client.enums.KeywordPlanNetworkEnum
  return enum.GOOGLE_SEARCH_AND_PARTNERS if include_partners else enum.GOOGLE_SEARCH


@mcp.tool()
def get_keyword_historical_metrics(
    keywords: list[str],
    customer_id: str,
    language_id: str = DEFAULT_LANGUAGE_ID,
    geo_target_ids: list[str] | None = None,
    include_search_partners: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Gets historical search volume and competition for given keywords.

  Read-only. Same data as "Get search volume and forecasts" in Keyword
  Planner: average monthly searches (last 12 months), monthly volumes,
  competition and top-of-page bid range.

  Args:
      keywords: Exact keyword texts to look up.
      customer_id: A non-manager customer ID (digits only).
      language_id: Language constant ID. Default 1015 (Swedish).
      geo_target_ids: Geo target constant IDs. Default ["2752"] (Sweden).
      include_search_partners: Include Google search partners.
      login_customer_id: (Optional) The MCC account ID.

  Returns:
      {"data": [{"keyword", "close_variants", "metrics": {...}}]}. Keywords
      Google merges as close variants are returned once.
  """
  if not keywords:
    raise ToolError("keywords must not be empty")
  if len(keywords) > MAX_KEYWORDS_PER_REQUEST:
    raise ToolError(f"max {MAX_KEYWORDS_PER_REQUEST} keywords per request")
  ads_client, service, language, geos = _prepare(
      customer_id, language_id, geo_target_ids, login_customer_id
  )
  request = ads_client.get_type("GenerateKeywordHistoricalMetricsRequest")
  request.customer_id = customer_id
  request.keywords.extend(keywords)
  request.language = language
  request.geo_target_constants.extend(geos)
  request.keyword_plan_network = _network(ads_client, include_search_partners)
  try:
    response = service.generate_keyword_historical_metrics(request=request)
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(i) for i in e.failure.errors)) from e
  return {
      "data": [
          {
              "keyword": r.text,
              "close_variants": list(r.close_variants),
              "metrics": _metrics_to_dict(r.keyword_metrics),
          }
          for r in response.results
      ]
  }


@mcp.tool()
def generate_keyword_ideas(
    customer_id: str,
    seed_keywords: list[str] | None = None,
    page_url: str | None = None,
    language_id: str = DEFAULT_LANGUAGE_ID,
    geo_target_ids: list[str] | None = None,
    include_search_partners: bool = False,
    min_avg_monthly_searches: int = 0,
    limit: int = 200,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Generates keyword ideas with search volumes (Keyword Planner "Discover").

  Read-only. Give seed keywords, a page URL, or both.

  Args:
      customer_id: A non-manager customer ID (digits only).
      seed_keywords: Up to 20 seed keywords.
      page_url: A URL to use as seed (with seed_keywords: keyword+URL seed).
      language_id: Language constant ID. Default 1015 (Swedish).
      geo_target_ids: Geo target constant IDs. Default ["2752"] (Sweden).
      include_search_partners: Include Google search partners.
      min_avg_monthly_searches: Drop ideas below this average.
      limit: Max number of ideas returned, sorted by avg monthly searches.
      login_customer_id: (Optional) The MCC account ID.

  Returns:
      {"data": [{"keyword", "metrics": {...}}]} sorted by volume, descending.
  """
  if not seed_keywords and not page_url:
    raise ToolError("give seed_keywords, page_url or both")
  if seed_keywords and len(seed_keywords) > MAX_SEED_KEYWORDS:
    raise ToolError(f"max {MAX_SEED_KEYWORDS} seed keywords")
  ads_client, service, language, geos = _prepare(
      customer_id, language_id, geo_target_ids, login_customer_id
  )
  request = ads_client.get_type("GenerateKeywordIdeasRequest")
  request.customer_id = customer_id
  request.language = language
  request.geo_target_constants.extend(geos)
  request.include_adult_keywords = False
  request.keyword_plan_network = _network(ads_client, include_search_partners)
  if seed_keywords and page_url:
    request.keyword_and_url_seed.url = page_url
    request.keyword_and_url_seed.keywords.extend(seed_keywords)
  elif seed_keywords:
    request.keyword_seed.keywords.extend(seed_keywords)
  else:
    request.url_seed.url = page_url
  try:
    results = list(service.generate_keyword_ideas(request=request))
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(i) for i in e.failure.errors)) from e
  ideas = [
      {"keyword": r.text, "metrics": _metrics_to_dict(r.keyword_idea_metrics)}
      for r in results
  ]
  ideas = [
      i for i in ideas
      if (i["metrics"].get("avg_monthly_searches") or 0) >= min_avg_monthly_searches
  ]
  ideas.sort(
      key=lambda i: i["metrics"].get("avg_monthly_searches") or 0, reverse=True
  )
  return {"data": ideas[: max(limit, 0)], "total_ideas": len(results)}
