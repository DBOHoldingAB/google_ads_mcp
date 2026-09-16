"""Tests for the Keyword Planner tools."""

from unittest import mock

from ads_mcp.tools import _utils
from ads_mcp.tools import keyword_planner as kp
from fastmcp.exceptions import ToolError
import pytest


@pytest.fixture(autouse=True)
def reset_ads_client():
  _utils._ADS_CLIENT = None  # pylint: disable=protected-access
  yield
  _utils._ADS_CLIENT = None  # pylint: disable=protected-access


def _fn(tool):
  return getattr(tool, "fn", tool)


def _metrics(avg):
  m = mock.Mock()
  m.avg_monthly_searches = avg
  m.competition.name = "LOW"
  m.competition_index = 10
  m.low_top_of_page_bid_micros = 1
  m.high_top_of_page_bid_micros = 2
  m.average_cpc_micros = 0
  month = mock.Mock(year=2026, monthly_searches=avg)
  month.month.name = "AUGUST"
  m.monthly_search_volumes = [month]
  return m


@pytest.fixture(name="client")
def fixture_client(mocker):
  client = mock.MagicMock()
  mocker.patch.object(kp, "get_ads_client", return_value=client)
  return client


def test_historical_metrics_maps_results(client):
  result = mock.Mock(text="sms api", close_variants=["sms apis"])
  result.keyword_metrics = _metrics(110)
  service = client.get_service.return_value
  service.generate_keyword_historical_metrics.return_value.results = [result]

  out = _fn(kp.get_keyword_historical_metrics)(
      keywords=["sms api"], customer_id="1", login_customer_id="2"
  )

  assert client.login_customer_id == "2"
  assert out["data"][0]["keyword"] == "sms api"
  assert out["data"][0]["close_variants"] == ["sms apis"]
  assert out["data"][0]["metrics"]["avg_monthly_searches"] == 110
  assert out["data"][0]["metrics"]["monthly_search_volumes"][0]["month"] == "AUGUST"


def test_historical_metrics_requires_keywords(client):
  with pytest.raises(ToolError):
    _fn(kp.get_keyword_historical_metrics)(keywords=[], customer_id="1")


def test_ideas_requires_seed(client):
  with pytest.raises(ToolError):
    _fn(kp.generate_keyword_ideas)(customer_id="1")


def test_ideas_filters_sorts_and_limits(client):
  rows = []
  for text, avg in [("a", 10), ("b", 500), ("c", 0), ("d", 50)]:
    r = mock.Mock(text=text)
    r.keyword_idea_metrics = _metrics(avg)
    rows.append(r)
  client.get_service.return_value.generate_keyword_ideas.return_value = iter(rows)

  out = _fn(kp.generate_keyword_ideas)(
      customer_id="1", seed_keywords=["sms"], min_avg_monthly_searches=10, limit=2
  )

  assert [i["keyword"] for i in out["data"]] == ["b", "d"]
  assert out["total_ideas"] == 4
