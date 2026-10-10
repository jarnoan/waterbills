import json
from datetime import date

import pytest

from water_billing.services.portal import (
    PortalError,
    PortalReading,
    fetch_latest_reading,
    parse_login_form,
    parse_reading_date,
    parse_reading_value,
    select_consumption_place,
    select_water_meter,
)

_LOGIN_HTML = """
<form method="get" action="/nokia/Identity/Account/Login">
  <input name="SignInType" type="hidden" value="20" />
  <input type="radio" name="SignInTypePrivateCustomer" value="20">
</form>
<form id="account" method="post" autocomplete="off">
  <input type="text" id="Input_UserName" name="Input.UserName" value="" />
  <input type="hidden" name="SignInType" value="20" />
  <input type="text" id="Input_Password" name="Input.Password" value="" />
  <input name="SignInTypePrivateCustomer" type="hidden" value="10" />
  <button type="submit">Kirjaudu sisään</button>
  <input name="__RequestVerificationToken" type="hidden" value="tok&amp;en" />
</form>
"""


def test_parse_login_form_collects_only_account_form_fields():
    form = parse_login_form(_LOGIN_HTML)
    assert form.action is None
    assert form.fields == {
        "Input.UserName": "",
        "SignInType": "20",
        "Input.Password": "",
        "SignInTypePrivateCustomer": "10",
        "__RequestVerificationToken": "tok&en",
    }


def test_parse_login_form_missing_form_raises():
    with pytest.raises(PortalError):
        parse_login_form("<html><body><main></main></body></html>")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("30.8.2026", date(2026, 8, 30)),
        ("01.09.2026 12:30:00.000", date(2026, 9, 1)),
        ("2026-08-30T00:00:00", date(2026, 8, 30)),
    ],
)
def test_parse_reading_date(value, expected):
    assert parse_reading_date(value) == expected


def test_parse_reading_date_invalid_raises():
    with pytest.raises(PortalError):
        parse_reading_date("eilen")


@pytest.mark.parametrize(
    "value,expected", [(1234, 1234), (1234.9, 1234), ("1234,5", 1234), (" 77 ", 77)]
)
def test_parse_reading_value(value, expected):
    assert parse_reading_value(value) == expected


def _customers():
    return [
        {
            "guid": "c1",
            "consumptionPlaces": [
                {"guid": "p1", "consumptionPlaceId": "11111", "waterMeters": [{"guid": "m1", "id": "A1"}]},
                {
                    "guid": "p2",
                    "consumptionPlaceId": 22222,
                    "waterMeters": [{"guid": "m2", "id": "B1"}, {"guid": "m3", "id": "B2"}],
                },
            ],
        }
    ]


def test_select_consumption_place_matches_site_number():
    customer, place = select_consumption_place(_customers(), "22222")
    assert (customer["guid"], place["guid"]) == ("c1", "p2")


def test_select_consumption_place_falls_back_to_only_place():
    customers = [{"guid": "c1", "consumptionPlaces": [{"guid": "p1", "consumptionPlaceId": "X"}]}]
    assert select_consumption_place(customers, "99999")[1]["guid"] == "p1"


def test_select_consumption_place_unknown_site_raises():
    with pytest.raises(PortalError):
        select_consumption_place(_customers(), "99999")
    with pytest.raises(PortalError):
        select_consumption_place([], "11111")


def test_select_water_meter_prefers_matching_meter_id():
    place = _customers()[0]["consumptionPlaces"][1]
    assert select_water_meter(place, "B2")["guid"] == "m3"
    assert select_water_meter(place, None)["guid"] == "m2"
    with pytest.raises(PortalError):
        select_water_meter({"waterMeters": []}, None)


class _FakePortal:
    """Minimal stand-in for the portal: login form, token exchange, API, logout."""

    def __init__(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from urllib.parse import parse_qs, urlsplit

        portal = self
        self.calls = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, body="", headers=None, ctype="text/html"):
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Type", ctype)
                data = body.encode()
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _form(self):
                length = int(self.headers.get("Content-Length", 0))
                return {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}

            def do_GET(self):
                url = urlsplit(self.path)
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                portal.calls.append(url.path)
                if url.path == "/nokia/openid/authorize":
                    portal.state = query["state"]
                    portal.redirect_uri = query["redirect_uri"]
                    assert query["signInType"] == "20"
                    self._send(302, headers={"Location": "/nokia/Identity/Account/Login?x=1",
                                             "Set-Cookie": "openid-session=s1; path=/"})
                elif url.path == "/nokia/Identity/Account/Login":
                    self._send(200, _LOGIN_HTML)
                elif url.path == "/nokia/openid/login":
                    assert "auth=ok" in self.headers.get("Cookie", "")
                    self._send(302, headers={
                        "Location": f"{portal.redirect_uri}?code=CODE&state={portal.state}"})
                elif url.path == "/nokia/portal/api/customers":
                    assert self.headers["Authorization"] == "Bearer AT"
                    self._send(200, json.dumps(_customers()), ctype="application/json")
                elif url.path.endswith("/customers/c1/consumptionplaces/p1/watermeters/m1/latestreading"):
                    self._send(200, json.dumps({"reading": 1234.0, "readingDate": "30.8.2026"}),
                               ctype="application/json")
                elif url.path == "/nokia/openid/logout":
                    assert query["id_token_hint"] == "IT"
                    self._send(302, headers={"Location": query["post_logout_redirect_uri"]})
                else:
                    self._send(404)

            def do_POST(self):
                url = urlsplit(self.path)
                form = self._form()
                portal.calls.append(url.path)
                if url.path == "/nokia/Identity/Account/Login":
                    assert form["__RequestVerificationToken"] == "tok&en"
                    assert "openid-session=s1" in self.headers.get("Cookie", "")
                    if (form["Input.UserName"], form["Input.Password"]) == ("555", "11111"):
                        self._send(302, headers={"Location": "/nokia/openid/login",
                                                 "Set-Cookie": "auth=ok; path=/"})
                    else:
                        self._send(200, _LOGIN_HTML)
                elif url.path == "/nokia/openid/token":
                    assert form["code"] == "CODE" and form["code_verifier"]
                    self._send(200, json.dumps({"access_token": "AT", "id_token": "IT"}),
                               ctype="application/json")
                else:
                    self._send(404)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/nokia/"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake_portal():
    portal = _FakePortal()
    yield portal
    portal.close()


def test_fetch_latest_reading_logs_in_reads_and_logs_out(fake_portal):
    result = fetch_latest_reading("555", "11111", "A1", base_url=fake_portal.base_url)
    assert result == PortalReading(reading=1234, reading_date=date(2026, 8, 30), meter_id="A1")
    assert fake_portal.calls[-1] == "/nokia/openid/logout"
    assert "/nokia/portal/authentication/login-callback" not in fake_portal.calls


def test_fetch_latest_reading_wrong_numbers_raises(fake_portal):
    with pytest.raises(PortalError, match="Kirjautuminen epäonnistui"):
        fetch_latest_reading("555", "wrong", base_url=fake_portal.base_url)
    assert "/nokia/openid/logout" not in fake_portal.calls
