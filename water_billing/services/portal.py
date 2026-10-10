"""Mittarilukemien haku Vesitili-asiakasportaalista (vesitili.fi).

Portaali on selainsovellus, jonka taustalla on OpenID Connect -kirjautuminen
ja JSON-rajapinta. Tämä moduuli tekee samat HTTP-kutsut kuin selain:
kirjautuu yksityisasiakkaana asiakasnumerolla ja käyttöpaikan numerolla,
lukee etusivulla näkyvän edellisen lukeman ja kirjautuu ulos.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from typing import Callable, Dict, List, Optional

from water_billing.domain.models import ContactInfo, Customer, MeterReading

PORTAL_BASE_URL = "https://vesitili.fi/nokia/"
MAIN_METER_NAME = "päämittari"

_CLIENT_ID = "Vesitili"
_SCOPE = "VesitiliApi openid profile"
_SIGN_IN_TYPE_PRIVATE_CUSTOMER = "20"
_LOGIN_FORM_ID = "account"
_USER_AGENT = "Mozilla/5.0 (water-billing; mittarilukemien haku)"
_TIMEOUT_SECONDS = 30


class PortalError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class PortalReading:
    reading: int
    reading_date: date
    meter_id: Optional[str]


class _CallbackReached(Exception):
    """Raised instead of following the redirect back to the portal app."""

    def __init__(self, url: str) -> None:
        super().__init__(url)
        self.url = url


class _StopAtCallback(urllib.request.HTTPRedirectHandler):
    def __init__(self, callback_prefixes: List[str]) -> None:
        self._callback_prefixes = callback_prefixes

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if any(newurl.startswith(p) for p in self._callback_prefixes):
            raise _CallbackReached(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _LoginFormParser(HTMLParser):
    """Collects the action and input values of the login form."""

    def __init__(self) -> None:
        super().__init__()
        self._in_form = False
        self.found = False
        self.action: Optional[str] = None
        self.fields: Dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and a.get("id") == _LOGIN_FORM_ID:
            self._in_form = True
            self.found = True
            self.action = a.get("action")
        elif tag == "input" and self._in_form and a.get("name"):
            self.fields[a["name"]] = a.get("value") or ""

    def handle_endtag(self, tag):
        if tag == "form":
            self._in_form = False


def parse_login_form(html: str) -> _LoginFormParser:
    parser = _LoginFormParser()
    parser.feed(html)
    if not parser.found:
        raise PortalError("Kirjautumislomaketta ei löytynyt portaalin sivulta")
    return parser


def parse_reading_date(value: object) -> date:
    text = str(value or "").strip()
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        raise PortalError(f"Tuntematon lukeman päivämäärä: '{text}'")


def parse_reading_value(value: object) -> int:
    # Lukemat käsitellään kokonaisina kuutioina, kuten mittarin lukemakin.
    try:
        return int(Decimal(str(value).strip().replace(",", ".")))
    except (InvalidOperation, ValueError):
        raise PortalError(f"Tuntematon mittarilukema: '{value}'")


def select_consumption_place(customers: object, site_number: str) -> tuple:
    """Returns (customer, consumption place) matching the site number."""
    places = [
        (c, p)
        for c in (customers if isinstance(customers, list) else [])
        for p in (c.get("consumptionPlaces") or [])
    ]
    if not places:
        raise PortalError("Portaali ei palauttanut yhtään käyttöpaikkaa")
    for c, p in places:
        if str(p.get("consumptionPlaceId") or "").strip() == site_number.strip():
            return c, p
    if len(places) == 1:
        return places[0]
    raise PortalError(f"Käyttöpaikkaa {site_number} ei löytynyt portaalista")


def select_water_meter(place: dict, meter_id: Optional[str]) -> dict:
    meters = place.get("waterMeters") or []
    if not meters:
        raise PortalError("Käyttöpaikalla ei ole vesimittaria")
    if meter_id:
        for m in meters:
            if str(m.get("id") or "").strip() == meter_id.strip():
                return m
    return meters[0]


class _PortalSession:
    def __init__(self, base_url: str) -> None:
        self._base = base_url
        self._redirect_uri = base_url + "portal/authentication/login-callback"
        self._logout_redirect_uri = base_url + "portal/authentication/logout-callback"
        self._api = base_url + "portal/api/"
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar()),
            _StopAtCallback([self._redirect_uri, self._logout_redirect_uri]),
        )
        self._access_token: Optional[str] = None
        self._id_token: Optional[str] = None

    def _open(self, url: str, data: Optional[dict] = None, bearer: bool = False):
        headers = {"User-Agent": _USER_AGENT, "Accept-Language": "fi"}
        if bearer:
            headers["Authorization"] = f"Bearer {self._access_token}"
            headers["Accept"] = "application/json"
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, headers=headers)
        return self._opener.open(req, timeout=_TIMEOUT_SECONDS)

    def _get_json(self, path: str) -> object:
        with self._open(self._api + path, bearer=True) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def login(self, customer_number: str, site_number: str) -> None:
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        state = secrets.token_urlsafe(16)
        authorize_url = self._base + "openid/authorize?" + urllib.parse.urlencode({
            "client_id": _CLIENT_ID,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": _SCOPE,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "response_mode": "query",
            "signInType": _SIGN_IN_TYPE_PRIVATE_CUSTOMER,
            "language": "fi",
        })
        with self._open(authorize_url) as resp:
            login_url = resp.geturl()
            form = parse_login_form(resp.read().decode("utf-8", errors="replace"))

        fields = dict(form.fields)
        fields["Input.UserName"] = customer_number
        fields["Input.Password"] = site_number
        post_url = urllib.parse.urljoin(login_url, form.action) if form.action else login_url
        try:
            with self._open(post_url, data=fields):
                pass
        except _CallbackReached as reached:
            callback_url = reached.url
        else:
            # Portaali näytti kirjautumissivun uudelleen eikä ohjannut eteenpäin.
            raise PortalError(
                "Kirjautuminen epäonnistui (tarkista asiakasnumero ja käyttöpaikan numero)"
            )

        params = urllib.parse.parse_qs(urllib.parse.urlsplit(callback_url).query)
        code = (params.get("code") or [""])[0]
        if not code or (params.get("state") or [""])[0] != state:
            error = (params.get("error_description") or params.get("error") or [""])[0]
            raise PortalError(f"Kirjautuminen epäonnistui{': ' + error if error else ''}")

        with self._open(self._base + "openid/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri,
            "code_verifier": verifier,
            "client_id": _CLIENT_ID,
        }) as resp:
            tokens = json.loads(resp.read().decode("utf-8"))
        self._access_token = tokens.get("access_token")
        self._id_token = tokens.get("id_token")
        if not self._access_token:
            raise PortalError("Kirjautuminen epäonnistui (portaali ei palauttanut istuntoa)")

    def latest_reading(self, site_number: str, meter_id: Optional[str]) -> PortalReading:
        customer, place = select_consumption_place(self._get_json("customers"), site_number)
        meter = select_water_meter(place, meter_id)
        data = self._get_json(
            f"customers/{customer['guid']}/consumptionplaces/{place['guid']}"
            f"/watermeters/{meter['guid']}/latestreading?cb={int(time.time() * 1000)}"
        )
        if not isinstance(data, dict) or data.get("reading") is None:
            raise PortalError("Portaalissa ei ole aiempaa lukemaa")
        return PortalReading(
            reading=parse_reading_value(data["reading"]),
            reading_date=parse_reading_date(data.get("readingDate")),
            meter_id=str(meter.get("id")).strip() if meter.get("id") is not None else None,
        )

    def logout(self) -> None:
        if not self._access_token:
            return
        params = {"post_logout_redirect_uri": self._logout_redirect_uri, "language": "fi"}
        if self._id_token:
            params["id_token_hint"] = self._id_token
        try:
            with self._open(self._base + "openid/logout?" + urllib.parse.urlencode(params)):
                pass
        except _CallbackReached:
            pass


def fetch_latest_reading(
    customer_number: str,
    site_number: str,
    meter_id: Optional[str] = None,
    base_url: str = PORTAL_BASE_URL,
) -> PortalReading:
    """Log in, read the latest reported meter reading and log out."""
    session = _PortalSession(base_url)
    try:
        try:
            session.login(customer_number, site_number)
            return session.latest_reading(site_number, meter_id)
        finally:
            try:
                session.logout()
            except (urllib.error.URLError, OSError):
                pass
    except urllib.error.HTTPError as exc:
        raise PortalError(f"Portaali vastasi virheellä {exc.code}")
    except (urllib.error.URLError, OSError) as exc:
        raise PortalError(f"Portaaliin ei saatu yhteyttä: {getattr(exc, 'reason', exc)}")
    except (ValueError, KeyError, TypeError) as exc:
        raise PortalError(f"Portaalin vastausta ei voitu tulkita: {exc}")


def fetch_portal_readings(
    customers: List[Customer],
    contact_info: ContactInfo,
    report: Callable[[str], None],
) -> Dict[str, MeterReading]:
    """Fetch the latest portal reading for every meter whose customer number
    and site number are known. Returns readings keyed by customer name
    (the main meter under ``päämittari``); failures are reported and skipped.
    """
    targets = [
        (c.name, c.customer_number, c.consumption_point, c.meter_id)
        for c in customers
        if c.is_active() and c.customer_number and c.consumption_point
    ]
    if contact_info.main_meter_customer_number and contact_info.main_meter_consumption_point:
        targets.append((
            MAIN_METER_NAME,
            contact_info.main_meter_customer_number,
            contact_info.main_meter_consumption_point,
            contact_info.main_meter_id,
        ))

    readings: Dict[str, MeterReading] = {}
    for name, customer_number, site_number, meter_id in targets:
        try:
            result = fetch_latest_reading(customer_number, site_number, meter_id)
        except PortalError as exc:
            report(f"  {name}: haku epäonnistui – {exc.message}")
            continue
        readings[name] = MeterReading(
            customer_name=name,
            reading_date=result.reading_date,
            reading=result.reading,
        )
        note = ""
        if meter_id and result.meter_id and result.meter_id != meter_id.strip():
            note = f" (huom: portaalin mittarinro {result.meter_id}, odotettiin {meter_id})"
        report(
            f"  {name}: {result.reading} m³ "
            f"({result.reading_date.day}.{result.reading_date.month}.{result.reading_date.year}){note}"
        )
    return readings
