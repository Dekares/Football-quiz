"""Country display metadata used by API responses and game comparisons.

The region is the player's football confederation, not strictly the geographic
continent. This keeps partial nationality hints aligned with football context
(for example Australia is AFC and Guyana is CONCACAF).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CountryData:
    flag_code: str
    confederation: str


def _group(confederation: str, countries: dict[str, str]) -> dict[str, CountryData]:
    return {
        name: CountryData(flag_code=flag_code, confederation=confederation)
        for name, flag_code in countries.items()
    }


COUNTRY_DATA: dict[str, CountryData] = {
    **_group("UEFA", {
        "Albania": "al", "Armenia": "am", "Austria": "at", "Azerbaijan": "az",
        "Belarus": "by", "Belgium": "be", "Bosnia-Herzegovina": "ba",
        "Bulgaria": "bg", "Croatia": "hr", "Cyprus": "cy", "Czech Republic": "cz",
        "Denmark": "dk", "England": "gb-eng", "Estonia": "ee", "Finland": "fi",
        "France": "fr", "Georgia": "ge", "Germany": "de", "Greece": "gr",
        "Hungary": "hu", "Iceland": "is", "Ireland": "ie", "Israel": "il",
        "Italy": "it", "Kosovo": "xk", "Latvia": "lv", "Lithuania": "lt",
        "Luxembourg": "lu", "Moldova": "md", "Montenegro": "me",
        "Netherlands": "nl", "North Macedonia": "mk", "Northern Ireland": "gb-nir",
        "Norway": "no", "Poland": "pl", "Portugal": "pt", "Romania": "ro",
        "Russia": "ru", "Scotland": "gb-sct", "Serbia": "rs", "Slovakia": "sk",
        "Slovenia": "si", "Spain": "es", "Sweden": "se", "Switzerland": "ch",
        "Türkiye": "tr", "Ukraine": "ua", "Wales": "gb-wls",
    }),
    **_group("CONMEBOL", {
        "Argentina": "ar", "Bolivia": "bo", "Brazil": "br", "Chile": "cl",
        "Colombia": "co", "Ecuador": "ec", "Paraguay": "py", "Peru": "pe",
        "Uruguay": "uy", "Venezuela": "ve",
    }),
    **_group("CONCACAF", {
        "Antigua and Barbuda": "ag", "Canada": "ca", "Costa Rica": "cr",
        "Curacao": "cw", "Dominican Republic": "do", "El Salvador": "sv",
        "French Guiana": "gf", "Grenada": "gd", "Guadeloupe": "gp",
        "Guatemala": "gt", "Guyana": "gy", "Haiti": "ht", "Honduras": "hn",
        "Jamaica": "jm", "Martinique": "mq", "Mexico": "mx", "Panama": "pa",
        "Puerto Rico": "pr", "Suriname": "sr", "Trinidad and Tobago": "tt",
        "United States": "us",
    }),
    **_group("CAF", {
        "Algeria": "dz", "Angola": "ao", "Benin": "bj", "Burkina Faso": "bf",
        "Burundi": "bi", "Cameroon": "cm", "Cape Verde": "cv",
        "Central African Republic": "cf", "Chad": "td", "Comoros": "km",
        "Congo": "cg", "Cote d'Ivoire": "ci", "DR Congo": "cd", "Egypt": "eg",
        "Equatorial Guinea": "gq", "Eritrea": "er", "Gabon": "ga", "Ghana": "gh",
        "Guinea": "gn", "Guinea-Bissau": "gw", "Kenya": "ke", "Libya": "ly",
        "Madagascar": "mg", "Mali": "ml", "Mauritania": "mr", "Morocco": "ma",
        "Mozambique": "mz", "Niger": "ne", "Nigeria": "ng", "Rwanda": "rw",
        "Senegal": "sn", "Sierra Leone": "sl", "South Africa": "za", "Sudan": "sd",
        "Tanzania": "tz", "The Gambia": "gm", "Togo": "tg", "Tunisia": "tn",
        "Uganda": "ug", "Zambia": "zm", "Zimbabwe": "zw",
    }),
    **_group("AFC", {
        "Australia": "au", "China": "cn", "Indonesia": "id", "Iran": "ir",
        "Iraq": "iq", "Japan": "jp", "Jordan": "jo", "Korea, South": "kr",
        "Palestine": "ps", "Philippines": "ph", "Saudi Arabia": "sa", "Syria": "sy",
        "Thailand": "th", "Uzbekistan": "uz",
    }),
    **_group("OFC", {"New Caledonia": "nc", "New Zealand": "nz"}),
}

# Harici veri kaynaklarında görülebilen eş anlamlılar.
COUNTRY_DATA.update({
    "Bosnia and Herzegovina": COUNTRY_DATA["Bosnia-Herzegovina"],
    "Czechia": COUNTRY_DATA["Czech Republic"],
    "Ivory Coast": COUNTRY_DATA["Cote d'Ivoire"],
    "Republic of Ireland": COUNTRY_DATA["Ireland"],
    "South Korea": COUNTRY_DATA["Korea, South"],
    "Turkey": COUNTRY_DATA["Türkiye"],
    "USA": COUNTRY_DATA["United States"],
})


def country_data(name: str | None) -> CountryData | None:
    return COUNTRY_DATA.get(name or "")


def flag_code_for(name: str | None) -> str | None:
    item = country_data(name)
    return item.flag_code if item else None


def confederation_for(name: str | None) -> str | None:
    item = country_data(name)
    return item.confederation if item else None
