import re 
from typing import Optional
from dataclasses import dataclass, field

COUNTRY_MAP: dict[str, str] = {
	# Africa
	"nigeria": "NG", "niger": "NE", "ghana": "GH", "kenya": "KE",
	"ethiopia": "ET", "tanzania": "TZ", "uganda": "UG", "rwanda": "RW",
	"senegal": "SN", "mali": "ML", "ivory coast": "CI", "cote d'ivoire": "CI",
	"cameroon": "CM", "angola": "AO", "mozambique": "MZ", "zambia": "ZM",
	"zimbabwe": "ZW", "malawi": "MW", "botswana": "BW", "namibia": "NA",
	"south africa": "ZA", "egypt": "EG", "morocco": "MA", "tunisia": "TN",
	"algeria": "DZ", "libya": "LY", "sudan": "SD", "south sudan": "SS",
	"somalia": "SO", "djibouti": "DJ", "eritrea": "ER", "benin": "BJ",
	"togo": "TG", "burkina faso": "BF", "guinea": "GN", "guinea-bissau": "GW",
	"sierra leone": "SL", "liberia": "LR", "gambia": "GM", "mauritania": "MR",
	"cape verde": "CV", "sao tome": "ST", "equatorial guinea": "GQ",
	"gabon": "GA", "republic of the congo": "CG", "democratic republic of the congo": "CD",
	"congo": "CG", "drc": "CD", "central african republic": "CF", "chad": "TD",
	"madagascar": "MG", "comoros": "KM", "seychelles": "SC", "mauritius": "MU",
	"lesotho": "LS", "swaziland": "SZ", "eswatini": "SZ",
	# Americas
	"usa": "US", "united states": "US", "america": "US", "canada": "CA",
	"mexico": "MX", "brazil": "BR", "argentina": "AR", "colombia": "CO",
	"chile": "CL", "peru": "PE", "venezuela": "VE", "ecuador": "EC",
	# Europe
	"uk": "GB", "united kingdom": "GB", "england": "GB", "france": "FR",
	"germany": "DE", "spain": "ES", "italy": "IT", "portugal": "PT",
	"netherlands": "NL", "belgium": "BE", "sweden": "SE", "norway": "NO",
	"denmark": "DK", "finland": "FI", "poland": "PL", "russia": "RU",
	# Asia
	"china": "CN", "india": "IN", "japan": "JP", "south korea": "KR",
	"indonesia": "ID", "pakistan": "PK", "bangladesh": "BD", "philippines": "PH",
	"vietnam": "VN", "thailand": "TH", "malaysia": "MY", "singapore": "SG",
	"turkey": "TR", "iran": "IR", "iraq": "IQ", "saudi arabia": "SA",
	"uae": "AE", "united arab emirates": "AE",
}

AGE_GROUP_KEYWORDS = {
	"child": "child", "children": "child", "kid": "child", "kids": "child",
	"teenager": "teenager", "teenagers": "teenager", "teen": "teenager", "teens": "teenager",
	"adult": "adult", "adults": "adult",
	"senior": "senior", "seniors": "senior", "elderly": "senior", "old": "senior",
}

GENDER_KEYWORDS = {
	"male": "male", "males": "male", "man": "male", "men": "male", "boy": "male", "boys": "male",
	"female": "female", "females": "female", "woman": "female", "women": "female",
	"girl": "female", "girls": "female",
}


@dataclass
class ParsedQuery:
	gender: Optional[str] = None
	age_group: Optional[str] = None
	country_id: Optional[str] = None
	min_age: Optional[int] = None
	max_age: Optional[int] = None
	both_genders: bool = False
	valid: bool = True
	has_any_filter: bool = False


def parse_natural_query(q: str) -> ParsedQuery:
	result = ParsedQuery()
	text = q.lower().strip()

	if not text:
		result.valid = False
		return result

	# Gender Detection
	both_pattern = re.search(
		r"\b(male and female|female and male|men and women|women and men|both genders?)\b",
		text
	)

	if both_pattern:
		result.both_genders = True
		result.has_any_filter = True
	else:
		for keyword, gender_val in GENDER_KEYWORDS.items():
			if re.search(rf"\b{re.escape(keyword)}\b", text):
				if (result.gender) and (result.gender != gender_val):
					# If it ends up being both genders still
					result.both_genders = True
					result.gender = None
				else:
					result.gender = gender_val
				result.has_any_filter = True

	# For Young Queries
	if re.search(r"\byoung\b", text):
		result.min_age = 16
		result.max_age = 24
		result.has_any_filter = True

	above_match = re.search(r"\b(?:above|over|older than|at least|minimum)\s+(\d+)\b", text)
	if above_match:
		result.min_age = int(above_match.group(1)) + 1
		result.has_any_filter = True

	below_match = re.search(r"\b(?:below|under|younger than|at most|maximym)\s+(\d+)\b", text)
	if below_match:
		result.max_age = int(below_match.group(1)) - 1
		result.has_any_filter = True


	# Age group keywords
	for keyword, group_val in AGE_GROUP_KEYWORDS.items():
		if re.search(rf"\b{re.escape(keyword)}\b", text):
			result.age_group = group_val
			result.has_any_filter = True
			break

	# Country Detection
	country_text = re.sub(r"\b(from|in|of|living in|based in)\b", " ", text)
	sorted_countries = sorted(COUNTRY_MAP.keys(), key=len, reverse=True)
	for country_name in sorted_countries:
		if re.search(rf"\b{re.escape(country_name)}\b", country_text):
			result.country_id = COUNTRY_MAP[country_name]
			result.has_any_filter = True
			break

	if not result.has_any_filter:
		result.valid = False

	return result

# jfjfjfjfjfjfjfjfj


