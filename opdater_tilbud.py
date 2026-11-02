#!/usr/bin/env python3
"""MealPreppe: standalone offer updater. Python 3.12; no pip packages, keys or AI."""
import sys as _sys
from types import ModuleType as TrustedModuleType
_module = TrustedModuleType("netto_feed")
_module.__file__ = "netto_feed.py"
_sys.modules["netto_feed"] = _module
exec(compile("\"\"\"Public eTilbudsavis HTML adapter. No login, API key, browser or AI required.\n\nOnly literal JSON already published on search pages is read. JavaScript is never\nexecuted. This is an undocumented website contract and can change; callers must\nretain previous verified offers on failure, without extending their dates.\n\"\"\"\nfrom __future__ import annotations\n\nimport html\nimport json\nimport math\nimport re\nimport urllib.parse\nimport urllib.request\nfrom concurrent.futures import ThreadPoolExecutor\nfrom datetime import datetime, timezone\nfrom zoneinfo import ZoneInfo\n\nSEARCH_TERMS = ('havregryn', 'skyr', 'kyllingebryst', 'kartofler', 'gulerødder',\n                'broccoli', 'ris', 'pasta', 'hvidkål', 'hakket oksekød', 'æg')\nCHAIN_IDS = {'netto': '9ba51', 'rema': '11deC'}\nSEARCH_BASE = 'https://etilbudsavis.dk/soeg/'\nMAX_BYTES = 8 * 1024 * 1024\nDK = ZoneInfo('Europe/Copenhagen')\n\n\ndef _number(value):\n    if isinstance(value, bool) or not isinstance(value, (int, float)):\n        return None\n    return float(value) if math.isfinite(value) and value >= 0 else None\n\n\ndef extract_records(document: str) -> list[dict]:\n    \"\"\"Extract product records from plain/HTML-escaped embedded JSON.\n\n    Covers application/json scripts and literal JSON islands. Fail closed when\n    the site stops publishing product JSON instead of parsing visible price text.\n    \"\"\"\n    if not isinstance(document, str) or len(document) > MAX_BYTES:\n        raise ValueError('Kilden er tom eller for stor.')\n    decoder, found = json.JSONDecoder(), {}\n\n    def walk(value):\n        if isinstance(value, dict):\n            if (isinstance(value.get('publicId'), str)\n                    and isinstance(value.get('name'), str)\n                    and ('businessPublicId' in value or isinstance(value.get('business'), dict))\n                    and ('price' in value or 'membershipPrice' in value or 'appPrice' in value)):\n                found[value['publicId']] = value\n            for child in value.values():\n                if isinstance(child, (dict, list)):\n                    walk(child)\n        elif isinstance(value, list):\n            for child in value:\n                walk(child)\n\n    candidates = [document, html.unescape(document)]\n    for match in re.finditer(r'<script\\b[^>]*>([\\s\\S]*?)</script\\s*>', document, re.I):\n        content = html.unescape(match.group(1)).strip()\n        candidates.append(content)\n        try:\n            value = json.loads(content)\n            if isinstance(value, str):\n                candidates.append(value)\n            else:\n                walk(value)\n        except (ValueError, TypeError):\n            pass\n    for candidate in candidates:\n        for match in re.finditer(r'\\{\\s*\"(?:data|publicId|products|offers)\"\\s*:', candidate):\n            try:\n                value, _ = decoder.raw_decode(candidate, match.start())\n                walk(value)\n            except (ValueError, TypeError, RecursionError):\n                continue\n    if not found:\n        raise ValueError('Ingen læsbare produktdata i kilden; HTML-formatet kan være ændret.')\n    return list(found.values())\n\n\ndef match_ingredient(name: str, description: str = '') -> str | None:\n    \"\"\"Conservatively recognise a raw food TYPE, never a mere substring.\n\n    Prepared foods that mention a raw ingredient are not that ingredient. Unknown\n    branded potato/prepared lines and mixed variants require human confirmation.\n    \"\"\"\n    n = ' '.join(str(name).lower().split())\n    text = n + ' ' + str(description).lower()\n    if (any(word in text for word in (' eller ', 'tilsat lage', 'mariner', 'paneret',\n            'røget', 'færdigret', 'færdigstegt', 'krydret', 'pålæg', 'skiveskåret',\n            'spiseklar', 'stegt', 'kogt', 'grillet', 'sous vide', 'sousvide',\n            'vanilje', 'jordbær', 'blåbær', 'suppe', 'juice', 'bolognese',\n            'carbonara', 'lasagne', 'karry', 'risotto', 'risengrød', 'riskiks',\n            'risret', 'havregrynskug', 'havrekug', 'müslibar', 'mueslibar',\n            'kartoffelsalat', 'kartoffelmel', 'kartoffelmos', 'kartoffelgratin',\n            'kartoffelfritter', 'kartoffeldippers', 'kartoffelrösti', 'kartoffelrosti',\n            'rösti', 'rosti', 'røsti', 'pommes', 'fritter', 'dippers', 'gratin',\n            'spegepølse', 'pølse', 'frugtkiks', 'æblekiks', 'babyfood', 'babymad',\n            'børnemad', 'smoothie', 'frugtmos', 'æblemos', 'puré', 'puree', 'kiks', 'frugtstang',\n            'frugtstænger', 'tørret', 'tørrede', 'snack', 'på glas', 'konserves'))\n            or re.search(r'\\b(?:mel|mos|salat|cuisine|drik|mælk|dessert|kage|chips)\\b', text)\n            or re.search(r'\\s(?:og|med|m/)\\s', n)):\n        return None\n    # Peka's \"friske kartofler\" is a prepared refrigerated product line, not a\n    # reliable identification of raw potatoes from the reference catalogue.\n    if re.search(r'\\bpeka\\b', n):\n        return None\n    if re.search(r'\\b(?:kyllinge?bryst(?:filet)?|brystfilet(?:er)?)\\b', n) and 'kylling' in n:\n        return 'chicken'\n    if re.search(r'\\bhakket\\b', n) and re.search(r'\\boksekød\\b', n):\n        return 'beef' if re.search(r'(?<![\\d–\\-])5\\s*%', text) and not re.search(r'\\d\\s*[-–]\\s*\\d', text) else None\n    if re.search(r'\\bsvinemørbrad\\b', n) and not any(w in text for w in ('bacon', 'fyldt', 'medaljon')):\n        return 'pork'\n    if re.search(r'\\bhavregryn\\b', n) and not any(w in text for w in ('blanding', 'müsli', 'grød')):\n        return 'oats'\n    if re.search(r'\\bskyr\\b', n) and re.search(r'\\bnaturel\\b', n):\n        return 'skyr'\n    if re.search(r'\\b(?:kartofler|kartoffel|skrællekartofler|bagekartofler|spisekartofler)\\b', n) and not any(w in text for w in ('fløde', 'bagte', 'fros', 'perle')):\n        return 'potato'\n    if re.search(r'\\b(?:gulerødder|gulerod)\\b', n) and not any(w in text for w in ('revet', 'fros')):\n        return 'carrot'\n    if re.search(r'\\bbroccoli\\b', n) and not any(w in text for w in ('blanding', 'fros')):\n        return 'broccoli'\n    if re.search(r'\\bhvidkål\\b', n) and 'snittet' not in text:\n        return 'cabbage'\n    if re.search(r'\\b(?:basmatiris|jasminris|langkornede\\s+ris|ris)\\b', n) and not any(w in text for w in ('brune', 'fuldkorn', 'sushi', 'paella')):\n        return 'rice'\n    if re.search(r'\\b(?:pasta|spaghetti|penne|fusilli|macaroni)\\b', n) and not any(w in text for w in ('frisk', 'fyldt', 'tortellini', 'ravioli', 'fuldkorn', 'sauce', 'glutenfri')):\n        return 'pasta'\n    if re.search(r'\\bløg\\b', n) and not any(w in text for w in ('røde', 'rødløg', 'forår', 'sylt', 'rist')):\n        return 'onion'\n    if re.search(r'\\btomater\\b', n) and re.search(r'\\b(?:hakkede|knuste)\\b', n) and not any(w in text for w in ('krydder', 'basilikum', 'chili', 'sauce')):\n        return 'tomato'\n    if re.search(r'\\bpeberfrugt(?:er)?\\b', n) and 'rød' in text and not any(w in text for w in ('sylt', 'fyldt', 'blanding')):\n        return 'pepper'\n    if re.search(r'\\bæbler\\b|\\bæble\\b', n) and not any(w in text for w in ('most', 'stang', 'stænger', 'barer', 'bar ')):\n        return 'apple'\n    return None\n\n\ndef _local_date(value):\n    if not isinstance(value, str):\n        return None\n    try:\n        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))\n        if parsed.tzinfo is None:\n            parsed = parsed.replace(tzinfo=DK)\n        return parsed.astimezone(DK).date().isoformat()\n    except ValueError:\n        return None\n\n\ndef normalize_record(record: dict, source_url: str, chain: str = 'netto', now=None):\n    \"\"\"Return (usable normalized offers, unmatched real records).\n\n    Member/app prices become separate memberOnly offers. No estimate is made for\n    ambiguous weights or piece counts. Product source times are kept unchanged.\n    \"\"\"\n    business = record.get('business') if isinstance(record.get('business'), dict) else {}\n    business_id = record.get('businessPublicId') or business.get('publicId')\n    if business_id != CHAIN_IDS.get(chain) or record.get('currencyCode') != 'DKK':\n        return [], []\n    start, end = _local_date(record.get('validFrom')), _local_date(record.get('validUntil'))\n    if not start or not end or start > end:\n        return [], []\n    clock = now or datetime.now(timezone.utc)\n    if clock.tzinfo is None:\n        clock = clock.replace(tzinfo=timezone.utc)\n    checked = clock.astimezone(timezone.utc).isoformat()\n    minimum, maximum = _number(record.get('unitSizeFrom')), _number(record.get('unitSizeTo'))\n    unit = str(record.get('unitSymbol', '')).lower()\n    grams = minimum * (1000 if unit == 'kg' else 1) if minimum and minimum == maximum and unit in ('g', 'kg') else None\n    pieces = record.get('pieceCountFrom') == record.get('pieceCountTo') == 1\n    # pieceCountGet/GetFor are not documented as monetary bundle fields; do not\n    # reinterpret them or pretend a product is available as a single pack.\n    ambiguous_bundle = any(record.get(k) is not None for k in ('pieceCountGet', 'pieceCountGetFor'))\n    ingredient = match_ingredient(record.get('name', ''), record.get('description', ''))\n    base = {'name': record.get('name', ''), 'store': chain, 'packageGrams': grams,\n            'validFrom': start, 'validTo': end, 'source': source_url,\n            'verifiedAt': checked, 'type': 'offer', 'origin': 'automatic-etilbudsavis',\n            'postalCode': None, 'multiBuy': None,\n            'note': 'Offentlig landsavis via eTilbudsavis. Lokal lagerstatus og butiksundtagelser er ikke kontrolleret.'}\n    prices = []\n    for key in ('price', 'membershipPrice', 'appPrice'):\n        price = _number(record.get(key))\n        if price is not None:\n            prices.append((key, price))\n    if not prices:\n        return [], []\n    if not grams or not pieces or ambiguous_bundle or not ingredient:\n        reason = 'Ukendt eller varierende pakning' if not grams or not pieces else 'Flerstyksvilkår skal kontrolleres' if ambiguous_bundle else 'Variant matcher ikke næringskataloget entydigt'\n        return [], [{**base, 'id': f\"tjek-{chain}-{record.get('publicId')}\", 'ingredientId': None,\n                     'suggestedIngredientId': ingredient,\n                     'price': prices[0][1], 'memberOnly': prices[0][0] != 'price',\n                     'description': record.get('description', ''), 'reason': reason}]\n    offers = []\n    seen = set()\n    for key, price in prices:\n        member = key != 'price'\n        if (member, price) in seen:\n            continue\n        seen.add((member, price))\n        offers.append({**base, 'id': f\"tjek-{chain}-{record['publicId']}-{key}\",\n                       'ingredientId': ingredient, 'price': price, 'memberOnly': member,\n                       'pricePerKg': round(price / grams * 1000, 4)})\n    return offers, []\n\n\ndef fetch_search_page(term: str, timeout: float = 15):\n    url = SEARCH_BASE + urllib.parse.quote(term, safe='')\n    request = urllib.request.Request(url, headers={\n        'User-Agent': 'MealPreppe/2.0 (public grocery-offer reader)',\n        'Accept': 'text/html,application/xhtml+xml', 'Accept-Language': 'da-DK,da;q=0.9'})\n    with urllib.request.urlopen(request, timeout=timeout) as response:\n        data = response.read(MAX_BYTES + 1)\n        if len(data) > MAX_BYTES:\n            raise ValueError('Tilbudssiden overstiger størrelsesgrænsen.')\n    return url, extract_records(data.decode('utf-8'))\n\n\ndef fetch_netto(timeout: float = 15, queries=SEARCH_TERMS, now=None):\n    \"\"\"Fetch a bounded set of ingredient search pages and filter to Netto only.\"\"\"\n    queries = tuple(queries)\n    offers, unmatched, errors, pages = {}, {}, [], 0\n    def read(term):\n        try:\n            return term, fetch_search_page(term, timeout), None\n        except Exception as exc:\n            return term, None, exc\n    # At most four polite concurrent reads; a failed source cannot serially hold\n    # all eleven searches for nearly three minutes.\n    with ThreadPoolExecutor(max_workers=min(4, max(1, len(queries)))) as executor:\n      for term, result, error in executor.map(read, queries):\n        if error is None:\n            source, records = result\n            pages += 1\n            for record in records:\n                usable, pending = normalize_record(record, source, 'netto', now)\n                for item in usable:\n                    offers[item['id']] = item\n                for item in pending:\n                    unmatched[item['id']] = item\n        else:\n            errors.append(f'{term}: {type(error).__name__}: {str(error)[:180]}')\n    return {'offers': list(offers.values()), 'unmatched': list(unmatched.values()),\n            'status': {'id': 'netto', 'status': 'ok' if pages and not errors else 'partial' if pages else 'error',\n                       'source': SEARCH_BASE, 'pagesRead': pages, 'queries': len(queries),\n                       'offersRead': len(offers), 'unmatchedRead': len(unmatched), 'errors': errors,\n                       'note': 'Udvalgte ingredienser fra Nettos landsavis via offentlige eTilbudsavis-sider; ikke et komplet lokalt sortiment.'}}\n\n\nif __name__ == '__main__':\n    print(json.dumps(fetch_netto(), ensure_ascii=False, indent=2))\n", "netto_feed.py", 'exec'), _module.__dict__)
_module = TrustedModuleType("rema_feed")
_module.__file__ = "rema_feed.py"
_sys.modules["rema_feed"] = _module
exec(compile("\"\"\"Read REMA 1000's public product API; no account, key or paid service.\n\nThe v3 product response and pagination were verified with a real HTTP 200 on\n2026-11-02. `query=` is ignored by this API; always paginate the catalogue and\nmatch names conservatively. Do not describe the result as a complete local\nassortment. Only explicit grams and nationwide fixed-price products are usable.\n\"\"\"\nfrom __future__ import annotations\n\nimport html\nimport json\nimport math\nimport re\nimport urllib.parse\nimport urllib.request\nfrom datetime import datetime, timezone\nfrom zoneinfo import ZoneInfo\n\nfrom netto_feed import match_ingredient\n\nAPI = 'https://api.digital.rema1000.dk/api/v3/products'\nMAX_BYTES = 16 * 1024 * 1024\nDK = ZoneInfo('Europe/Copenhagen')\n\n\ndef _number(value):\n    if isinstance(value, bool) or not isinstance(value, (int, float)):\n        return None\n    return float(value) if math.isfinite(value) and value >= 0 else None\n\n\ndef _clock(now=None):\n    value = now or datetime.now(timezone.utc)\n    if value.tzinfo is None:\n        value = value.replace(tzinfo=timezone.utc)\n    return value\n\n\ndef _calendar_date(value):\n    # The API's campaign dates are calendar boundaries stamped at 00:00 UTC.\n    # Its 2026-11-01 / 2026-11-07 pair corresponds to the printed Nov 1–7 leaflet.\n    if not isinstance(value, str):\n        return None\n    candidate = value[:10]\n    try:\n        return datetime.strptime(candidate, '%Y-%m-%d').date().isoformat()\n    except ValueError:\n        return None\n\n\ndef package_grams(product):\n    \"\"\"Use only a literal fixed gram/kg pack size printed in `underline`.\"\"\"\n    text = html.unescape(str(product.get('underline') or '')).lower()\n    if product.get('is_weight_item') or product.get('is_self_scale_item'):\n        return None\n    if re.search(r'\\d\\s*[-–]\\s*\\d[\\d.,]*\\s*(?:kg|gr\\.?|g)\\b', text):\n        return None\n    match = re.search(r'(?:(\\d+)\\s*[x×]\\s*)?(\\d+(?:[.,]\\d+)?)\\s*(kg|gr\\.?|g)\\b', text)\n    if not match:\n        return None\n    count = int(match[1]) if match[1] else 1\n    grams = float(match[2].replace(',', '.')) * (1000 if match[3] == 'kg' else 1) * count\n    return round(grams, 3) if 0 < grams <= 100000 else None\n\n\ndef _ingredient(product):\n    name = str(product.get('name') or '')\n    underline = str(product.get('underline') or '')\n    description = re.sub('<[^>]+>', ' ', str(product.get('description') or ''))\n    # The full catalogue has baby food, sausages, sweets and ready meals. A\n    # keyword is NOT enough: use closed positive food-name patterns below.\n    text = (name + ' ' + underline + ' ' + description).lower()\n    n = name.lower()\n    if any(term in text for term in (' i glas', ' på glas', 'frugtsnack', 'frugtstænger',\n                                    'tørrede æbl', 'æblemos', 'æblepure', 'æblepuré',\n                                    'stegte', 'stegt', 'grillede', 'grillet', 'syltede')):\n        return None\n    candidate = match_ingredient(name, underline + ' ' + description)\n    clean = re.sub(r'\\s+', ' ', n).strip()\n    prefixless = re.sub(r'^(?:(?:øko\\.?|økologiske?|danske?)\\s+)+', '', clean)\n    if candidate == 'chicken':\n        # Cold cuts, diced preparations and flavoured chicken are deliberately\n        # excluded even when they contain the word \"kyllingebryst\".\n        if prefixless != 'kyllingebrystfilet':\n            return None\n        # This exact API SKU is advertised as \"tilsat lage\" in its leaflet,\n        # although the short catalogue name silently omits that qualification.\n        if str(product.get('id')) == '404995':\n            return None\n        # The actual v3 detail records for 404891/404997 expose origin and short\n        # names but no composition. Do not silently equate their package grams\n        # with 100% raw edible meat; an explicit declaration is required.\n        if not re.search(r'\\b100\\s*%\\s*(?:dansk\\s+)?kyllingebryst(?:filet)?\\b', description, re.I):\n            return None\n    if candidate == 'oats' and not re.fullmatch(r'havregryn(?: (?:finvalsede|grovvalsede))?', prefixless):\n        return None\n    if candidate == 'skyr' and prefixless != 'skyr naturel':\n        return None\n    if candidate == 'pasta':\n        pasta_name = re.sub(r'\\s+økologisk(?:e)?$', '', prefixless)\n        if pasta_name not in ('pasta skruer', 'penne rigate', 'spaghetti', 'penne', 'pastaskruer', 'fusilli'):\n            return None\n    if candidate == 'rice':\n        rice_name = re.sub(r'\\b(?:langk\\.?|langkornede|økologiske?|øko)\\b\\.?', ' ', clean)\n        rice_name = re.sub(r'\\s+', ' ', rice_name).strip()\n        if rice_name not in ('basmati ris', 'basmatiris', 'jasmin ris', 'jasminris', 'parboiled ris', 'langkornede ris'):\n            return None\n    if candidate == 'tomato' and prefixless not in ('hakkede tomater', 'knuste tomater'):\n        return None\n    if candidate in ('carrot', 'broccoli', 'cabbage', 'pepper', 'onion', 'potato', 'apple'):\n        positive_names = {\n            'carrot': r'gulerødder', 'broccoli': r'broccoli', 'cabbage': r'hvidkål',\n            'pepper': r'rød peber(?:frugt)?', 'onion': r'løg',\n            'potato': r'(?:skrælle |små |brune )?kartofler|bagekartofler',\n            'apple': r'æbler(?: i pose)?',\n        }\n        if not re.fullmatch(positive_names[candidate], prefixless):\n            return None\n        # Actual fresh produce in this API states a quality class (KL.1/KL.2).\n        # This positive signal distinguishes it from preserves and prepared food.\n        if not re.search(r'\\bkl\\.?\\s*[12i](?:\\b|\\.)', underline.lower()):\n            return None\n    if candidate in ('carrot', 'broccoli', 'cabbage', 'pepper', 'onion', 'potato'):\n        if any(term in text for term in ('ærter', 'bonduelle', 'blanding', 'mix', 'miks',\n                                        'tilberedt', 'færdig', 'konserves', 'dressing', 'sauce')) or '&' in n:\n            return None\n    if candidate == 'tomato' and any(term in text for term in ('hvidløg', 'basilikum', 'krydder', 'm/chili', 'med chili')):\n        return None\n    if candidate == 'pasta' and any(term in n for term in ('tomat', 'paste', 'pasta sauce', 'pasta-sauce')):\n        return None\n    return candidate\n\n\ndef normalize_product(product, source_url=API, now=None):\n    \"\"\"Return `(offers, unmatched)` from the actually verified v3 record shape.\"\"\"\n    if not isinstance(product, dict) or not isinstance(product.get('name'), str):\n        return [], []\n    name, underline = product['name'], str(product.get('underline') or '')\n    description = re.sub('<[^>]+>', ' ', str(product.get('description') or ''))\n    ingredient = _ingredient(product)\n    grams = package_grams(product)\n    clock = _clock(now)\n    checked = clock.astimezone(timezone.utc).isoformat()\n    offers, unmatched = [], []\n    for index, price in enumerate(product.get('prices') or []):\n        value = _number(price.get('price'))\n        start, end = _calendar_date(price.get('starting_at')), _calendar_date(price.get('ending_at'))\n        if value is None or not start or not end or start > end:\n            continue\n        # Keep current and future prices only; never extend an expired record.\n        if end < clock.astimezone(DK).date().isoformat():\n            continue\n        source_start, source_end = start, end\n        advertised = bool(price.get('is_campaign') or price.get('is_advertised'))\n        if not advertised:\n            # Long sentinel dates such as 2099 are NOT a promise about future\n            # shelf prices. A normal price is documented for the observation day.\n            today = clock.astimezone(DK).date().isoformat()\n            if start > today:\n                continue\n            start, end = today, min(end, today)\n        base = {\n            'id': f\"rema-api-{product.get('id')}-{start}-{index}\",\n            'name': f'{name} · {underline}' if underline else name,\n            'store': 'rema', 'packageGrams': grams, 'price': value,\n            'multiBuy': None, 'memberOnly': False, 'validFrom': start, 'validTo': end,\n            'source': source_url, 'verifiedAt': checked,\n            'type': 'offer' if advertised else 'regular',\n            'origin': 'automatic-rema-api', 'postalCode': None,\n            'retailerProductId': product.get('id'),\n            'sourceValidFrom': source_start, 'sourceValidTo': source_end,\n            'note': 'REMA 1000 offentlig produktpris. Lokalt lager er ikke kontrolleret. Næring bruger appens dokumenterede ingrediensreference.',\n        }\n        reason = None\n        if not ingredient:\n            reason = 'Variant matcher ikke næringskataloget entydigt'\n            if re.search('kyllingebryst', name, re.I):\n                reason = 'Rå kødandel og fravær af lage er ikke dokumenteret; kontrollér ingrediensdeklarationen'\n        elif not grams:\n            reason = 'Pakningen har ikke en fast, spiselig gramvægt'\n        elif product.get('is_available_in_all_stores') is not True:\n            reason = 'Produktet er ikke bekræftet landsdækkende'\n        elif price.get('max_quantity') is not None or price.get('price_over_max_quantity') is not None:\n            reason = 'Prisen har et mængdeloft, som kræver manuel kontrol'\n        elif ingredient == 'kidneyBeans' and not re.search('drænet|draenet', underline + ' ' + description, re.I):\n            reason = 'Drænet vægt er ikke dokumenteret'\n        if reason:\n            # Non-food and irrelevant catalogue entries are not useful manual suggestions.\n            if ingredient or any(k in name.lower() for k in ('kylling', 'skyr', 'æg', 'havregryn', 'bønner', 'olie', 'oksekød')):\n                unmatched.append({**base, 'reason': reason, 'description': description})\n            continue\n        offers.append({**base, 'ingredientId': ingredient,\n                       'pricePerKg': round(value / grams * 1000, 4)})\n    return offers, unmatched\n\n\ndef fetch_product_page(page=1, per_page=500, timeout=15):\n    url = API + '?' + urllib.parse.urlencode({'page': page, 'per_page': per_page})\n    request = urllib.request.Request(url, headers={\n        'User-Agent': 'MealPreppe/2.0 (personal public grocery-price reader)',\n        'Accept': 'application/json', 'Accept-Language': 'da-DK,da;q=0.9',\n    })\n    with urllib.request.urlopen(request, timeout=timeout) as response:\n        raw = response.read(MAX_BYTES + 1)\n        if len(raw) > MAX_BYTES:\n            raise ValueError('REMA-svaret overstiger størrelsesgrænsen.')\n        result = json.loads(raw)\n    if not isinstance(result, dict) or not isinstance(result.get('data'), list):\n        raise ValueError('REMA API-formatet er ændret: produktlisten mangler.')\n    return url, result\n\n\ndef fetch_rema(timeout=15, per_page=500, max_pages=25, now=None):\n    \"\"\"Read a bounded catalogue; return an honest partial status if truncated.\"\"\"\n    offers, unmatched, errors = {}, {}, []\n    products_read, pages_read, last_page = 0, 0, 1\n    for page in range(1, max_pages + 1):\n        try:\n            source, result = fetch_product_page(page, per_page, timeout)\n            pages_read += 1\n            pagination = result.get('meta', {}).get('pagination', {})\n            declared_last = pagination.get('last_page')\n            if not isinstance(declared_last, int) or declared_last < page:\n                raise ValueError('REMA-paginering mangler eller er ugyldig.')\n            last_page = declared_last\n            products_read += len(result['data'])\n            for product in result['data']:\n                usable, pending = normalize_product(product, source, now)\n                for item in usable:\n                    offers[item['id']] = item\n                for item in pending:\n                    unmatched[item['id']] = item\n            if page >= last_page:\n                break\n        except Exception as exc:\n            errors.append(f'Side {page}: {type(exc).__name__}: {str(exc)[:180]}')\n            break\n    truncated = pages_read < last_page\n    if truncated and not errors:\n        errors.append(f'Sikkerhedsgrænsen på {max_pages} sider er nået; kataloget er delvist læst.')\n    status = 'ok' if pages_read and not errors else 'partial' if pages_read else 'error'\n    return {\n        'offers': list(offers.values()), 'unmatched': list(unmatched.values()),\n        'status': {'id': 'rema', 'status': status, 'source': API,\n                   'pagesRead': pages_read, 'pagesAvailable': last_page,\n                   'productsRead': products_read, 'offersRead': len(offers),\n                   'unmatchedRead': len(unmatched), 'errors': errors,\n                   'note': 'Offentlig REMA 1000-produkt-API: daterede tilbud og normalpriser. Kun entydige ingredienser, faste gram og landsdækkende varer indgår.'},\n    }\n\n\nif __name__ == '__main__':\n    print(json.dumps(fetch_rema(), ensure_ascii=False, indent=2))\n", "rema_feed.py", 'exec'), _module.__dict__)

"""Build MealPreppe's public price file. Standard library only; no secrets.

Run this project copy with the adjacent feed adapters, or use the generated
standalone opdater_tilbud.py. Existing observations are never redated on failure.
"""
import argparse
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from netto_feed import fetch_netto
from rema_feed import fetch_rema

CHAINS = ('rema', 'netto')
DK = ZoneInfo('Europe/Copenhagen')


def _clock(now=None):
    value = now or datetime.now(timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _date(value):
    if not isinstance(value, str):
        return False
    try:
        return datetime.strptime(value, '%Y-%m-%d').date().isoformat() == value
    except ValueError:
        return False


def _number(value, positive=False):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and (value > 0 if positive else value >= 0))


def _source(value):
    if isinstance(value, dict):
        value = value.get('url')
    return isinstance(value, str) and value.startswith(('https://', 'http://'))


def _valid_row(row, chain, raw=False):
    if not isinstance(row, dict) or row.get('store') != chain:
        return False
    if not all(isinstance(row.get(k), str) and row[k].strip() for k in ('id', 'name', 'verifiedAt')):
        return False
    if not _date(row.get('validFrom')) or not _date(row.get('validTo')) or row['validFrom'] > row['validTo']:
        return False
    if not _source(row.get('source')) or not isinstance(row.get('memberOnly'), bool):
        return False
    bundle = row.get('multiBuy')
    valid_bundle = (isinstance(bundle, dict) and isinstance(bundle.get('count'), int)
                    and not isinstance(bundle['count'], bool) and bundle['count'] >= 2
                    and _number(bundle.get('price')))
    if not _number(row.get('price')) and not (row.get('price') is None and valid_bundle):
        return False
    if bundle is not None and not valid_bundle:
        return False
    if row.get('type') not in ('offer', 'regular'):
        return False
    if not raw and (not isinstance(row.get('ingredientId'), str) or not row['ingredientId'].strip()
                    or not _number(row.get('packageGrams'), positive=True)):
        return False
    if raw and row.get('packageGrams') is not None and not _number(row['packageGrams'], positive=True):
        return False
    return True


def _rows(rows, chain, today, raw=False):
    accepted, invalid = {}, 0
    if not isinstance(rows, list):
        return {}, 1
    for row in rows:
        if not _valid_row(row, chain, raw):
            invalid += 1
            continue
        # Expired observations are removed, never extended to make a plan work.
        if row['validTo'] < today:
            continue
        accepted[row['id']] = dict(row)
    return accepted, invalid


def _previous_chain(previous, chain):
    statuses = previous.get('chains', []) if isinstance(previous, dict) else []
    if isinstance(statuses, dict):
        item = statuses.get(chain, {})
        return item if isinstance(item, dict) else {}
    if isinstance(statuses, list):
        return next((s for s in statuses if isinstance(s, dict) and s.get('id') == chain), {})
    return {}


def assemble_feed(results, previous=None, now=None):
    """Merge actual adapter results with dated last-known observations.

    `results` is keyed by rema/netto, each value using the adapters' documented
    offers/unmatched/status shape. This pure entry point also supports testing
    and packaging observations already fetched by a developer.
    """
    previous = previous if isinstance(previous, dict) else {}
    clock = _clock(now)
    generated = clock.astimezone(timezone.utc).isoformat()
    today = clock.astimezone(DK).date().isoformat()
    offers, raw_offers, statuses = [], [], []
    for chain in CHAINS:
        result = results.get(chain, {}) if isinstance(results, dict) else {}
        result = result if isinstance(result, dict) else {}
        incoming = result.get('status', {})
        incoming = incoming if isinstance(incoming, dict) else {}
        level = incoming.get('status')
        if level not in ('ok', 'partial', 'error'):
            level = 'error'
        current, invalid = _rows(result.get('offers', []), chain, today)
        current_raw, invalid_raw = _rows(result.get('unmatched', []), chain, today, raw=True)
        if invalid or invalid_raw:
            level = 'partial' if current or current_raw else 'error'
        old, _ = _rows(previous.get('offers', []), chain, today)
        old_raw, _ = _rows(previous.get('rawOffers', []), chain, today, raw=True)
        retained = len(set(old) - set(current)) if level != 'ok' else 0
        retained_raw = len(set(old_raw) - set(current_raw)) if level != 'ok' else 0
        if level == 'error':
            # An adapter reporting failure cannot refresh even a partial result.
            current, current_raw = {}, {}
            retained, retained_raw = len(old), len(old_raw)
        if level != 'ok':
            old.update(current)
            old_raw.update(current_raw)
            current, current_raw = old, old_raw
        old_status = _previous_chain(previous, chain)
        status = {**incoming, 'id': chain, 'status': level,
                  'lastAttemptAt': generated,
                  'lastSuccessAt': generated if level == 'ok' else old_status.get('lastSuccessAt'),
                  'offersAvailable': len(current), 'rawOffersAvailable': len(current_raw),
                  'retainedOffers': retained, 'retainedRawOffers': retained_raw}
        note = incoming.get('note') if isinstance(incoming.get('note'), str) else 'Kilden kunne ikke hentes.'
        if level == 'error':
            note += f' Hentning mislykkedes. {retained} tidligere, stadig gyldige priser er bevaret med deres oprindelige datoer.'
        elif level == 'partial':
            note += f' Kilden er delvist læst. {retained} tidligere, stadig gyldige priser er bevaret med deres oprindelige datoer.'
        if invalid or invalid_raw:
            status['invalidRecords'] = invalid + invalid_raw
            note += ' Poster med ugyldige felter blev udeladt.'
        status['note'] = note
        if not status.get('lastSuccessAt'):
            # Older feeds may lack a chain timestamp. An observed price is still
            # not proof that a complete fetch succeeded, so do not invent one.
            status['lastSuccessAt'] = None
        offers.extend(current.values())
        raw_offers.extend(current_raw.values())
        statuses.append(status)
    key = lambda row: (row['store'], row['name'].lower(), row['validFrom'], row['id'])
    return {'schemaVersion': 1, 'generatedAt': generated,
            'automated': os.environ.get('GITHUB_ACTIONS') == 'true',
            'offers': sorted(offers, key=key), 'rawOffers': sorted(raw_offers, key=key),
            'chains': statuses}


def _failure(chain, error):
    return {'offers': [], 'unmatched': [],
            'status': {'id': chain, 'status': 'error',
                       'note': 'Kilden kunne ikke hentes.',
                       'errors': [f'{type(error).__name__}: {str(error)[:180]}']}}


def update(previous=None, timeout=15, now=None, fetchers=None):
    clock = _clock(now)
    readers = fetchers or {'rema': fetch_rema, 'netto': fetch_netto}
    results = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = {chain: executor.submit(readers[chain], timeout=timeout, now=clock) for chain in CHAINS}
        for chain, future in pending.items():
            try:
                results[chain] = future.result()
            except Exception as error:
                results[chain] = _failure(chain, error)
    return assemble_feed(results, previous, clock)


def read_previous(path):
    try:
        with Path(path).open(encoding='utf-8') as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) and value.get('schemaVersion') == 1 else {}
    except (OSError, ValueError):
        return {}


def write_feed(path, feed):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.tmp')
    payload = json.dumps(feed, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    try:
        temporary.write_text(payload, encoding='utf-8')
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description='Opdatér MealPreppes REMA- og Netto-priser uden API-nøgle.')
    parser.add_argument('--output', default='offers.json', help='Prisfil, der også bruges som sidste kendte observationer')
    parser.add_argument('--timeout', type=float, default=15, help='Netværkstidsgrænse pr. kald i sekunder, 1–30')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 30:
        parser.error('--timeout skal være mellem 1 og 30 sekunder')
    result = update(read_previous(args.output), timeout=args.timeout)
    write_feed(args.output, result)
    for status in result['chains']:
        print(f"{status['id']}: {status['status']} · {status['offersAvailable']} priser · {status['retainedOffers']} tidligere bevaret")


if __name__ == '__main__':
    main()
