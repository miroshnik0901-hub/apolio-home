"""Transaction tools — add, edit, delete, find"""
import uuid
import csv
import io
import logging
import unicodedata
from datetime import datetime, timedelta
from typing import Any

from sheets import SheetsClient
from auth import AuthManager, SessionContext, LastAction

logger = logging.getLogger(__name__)


def _normalize_note(text: str) -> set:
    """T-237: Normalize note text for dup detection token comparison.
    Converts accented chars (ò→o, é→e) and strips punctuation from tokens.
    Ensures 'mercatò' == 'mercato', 'MERCATO'' == 'mercato', etc.
    Also handles Cyrillic by returning original lowercase tokens (pass 1)
    so Cyrillic aliases ('паркінг') still work in _infer_subcategory.
    """
    if not text:
        return set()
    import re as _re
    # NFKD decomposition → remove combining diacritics → ASCII
    normalized = unicodedata.normalize("NFKD", text.lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    # Strip punctuation from each token (fixes MERCATO' → mercato)
    tokens = {_re.sub(r"[^\w]", "", t) for t in ascii_text.split()}
    return {t for t in tokens if t}  # remove empty strings


def _infer_subcategory(note: str, known_subs: list, sheets_inst=None) -> str:
    """T-237: Infer subcategory from note text when agent doesn't provide one.
    Checks each token against _CATEGORY_ALIASES → subcategory name.
    Strips punctuation, normalizes accents (ò→o), also checks original
    Cyrillic tokens (паркінг, бар) before ASCII stripping.
    Only assigns if the result is a known valid subcategory.
    """
    if not note or not known_subs:
        return ""
    import re
    known_lower = {k.lower(): k for k in known_subs}

    def _check_token(word):
        # Strip punctuation from both ends
        word = re.sub(r"[^\w]", "", word, flags=re.UNICODE).strip()
        if not word:
            return None
        alias = _CATEGORY_ALIASES.get(word)
        if alias and alias.lower() in known_lower:
            return known_lower[alias.lower()]
        return None

    # Pass 1: original lowercased tokens (covers Cyrillic: паркінг, бар...)
    tokens_orig = note.lower().split()
    for word in tokens_orig:
        result = _check_token(word)
        if result:
            return result

    # T-274: Pass 1b: bigram matching for multi-word aliases ("car wash",
    # "fuel station", "parking lot", "fast food"). Without this, multi-word
    # alias keys in _CATEGORY_ALIASES are dead because the per-token loop
    # only sees single words.
    def _check_phrase(phrase):
        phrase = phrase.strip()
        if not phrase:
            return None
        alias = _CATEGORY_ALIASES.get(phrase)
        if alias and alias.lower() in known_lower:
            return known_lower[alias.lower()]
        return None
    import re as _re
    clean_tokens = [_re.sub(r"[^\w]", "", t, flags=_re.UNICODE) for t in tokens_orig]
    clean_tokens = [t for t in clean_tokens if t]
    for i in range(len(clean_tokens) - 1):
        bigram = f"{clean_tokens[i]} {clean_tokens[i+1]}"
        result = _check_phrase(bigram)
        if result:
            return result

    # Pass 2: ASCII-normalized tokens (covers ò→o, é→e...)
    ascii_note = unicodedata.normalize("NFKD", note.lower()).encode("ascii", "ignore").decode()
    ascii_tokens = ascii_note.split()
    for word in ascii_tokens:
        result = _check_token(word)
        if result:
            return result

    # T-274: Pass 2b: ASCII bigrams
    ascii_clean = [_re.sub(r"[^\w]", "", t, flags=_re.UNICODE) for t in ascii_tokens]
    ascii_clean = [t for t in ascii_clean if t]
    for i in range(len(ascii_clean) - 1):
        bigram = f"{ascii_clean[i]} {ascii_clean[i+1]}"
        result = _check_phrase(bigram)
        if result:
            return result

    # Pass 3: dynamic aliases from AdminSheets
    if sheets_inst:
        try:
            dyn = sheets_inst.get_category_aliases()
            for word in note.lower().split() + ascii_note.split():
                word = re.sub(r"[^\w]", "", word, flags=re.UNICODE).strip()
                canonical = dyn.get(word)
                if canonical and canonical.lower() in known_lower:
                    return known_lower[canonical.lower()]
        except Exception:
            pass
    return ""


def _date_range_for_dup(date: str) -> tuple:
    """T-237: Return (date_from, date_to) with ±1 day tolerance.
    Bank statement posting date can differ from transaction date by 1 day.
    """
    try:
        d = datetime.strptime(date, "%Y-%m-%d").date()
        return (str(d - timedelta(days=1)), str(d + timedelta(days=1)))
    except Exception:
        return (date, date)


def _date_range_for_pair(date: str, days: int = 14) -> tuple:
    """T-253: Return (date_from, date_to) with ±N day tolerance for refund-pair detection.
    Refunds typically arrive 3-14 days after the original expense, so default 14.
    """
    try:
        d = datetime.strptime(date, "%Y-%m-%d").date()
        return (str(d - timedelta(days=days)), str(d + timedelta(days=days)))
    except Exception:
        return (date, date)


# T-253: merchants/categories that must NEVER be treated as refund pairs.
# Top-up = envelope funding transfer; matching a random expense to it would
# produce false pairs. Add more here if new non-user-facing income types appear.
_PAIR_BLACKLIST_CATEGORIES = {"top-up", "transfer", "funding"}


def _detect_refund_pair(
    date: str,
    amount: float,
    currency: str,
    tx_type: str,
    in_note_tokens: set,
    pre_eur,
    existing_txs: list,
):
    """T-253: Detect refund+expense pair within ±14 days.

    A pair = opposite Type (expense vs income) + matching amount
    (EUR strict / non-EUR ±5% / cross-currency via Amount_EUR ±5%)
    + overlapping merchant tokens + not in blacklist categories.

    Returns a confirm_required dict if a pair is detected, else None.
    Empty note on either side = skip (can't safely match on amount alone).
    """
    tx_type_l = (tx_type or "expense").lower()
    if tx_type_l not in ("expense", "income"):
        return None
    opposite_type = "income" if tx_type_l == "expense" else "expense"
    in_cur = currency.upper()

    for ex in existing_txs:
        ex_type_l = str(ex.get("Type", "expense")).lower()
        if ex_type_l != opposite_type:
            continue

        # Skip top-up / transfer rows on either side of the match
        ex_cat_l = str(ex.get("Category", "")).lower()
        if ex_cat_l in _PAIR_BLACKLIST_CATEGORIES:
            continue

        ex_cur = str(ex.get("Currency_Orig", "EUR")).upper()

        # ── Amount match (compare absolute values) ──────────────────────
        if ex_cur == in_cur:
            try:
                ex_amount = float(ex.get("Amount_Orig") or 0)
            except (ValueError, TypeError):
                ex_amount = 0.0
            if in_cur == "EUR":
                same_amount = abs(abs(ex_amount) - abs(amount)) < 0.01
            else:
                tol = max(abs(amount) * 0.05, 0.5)
                same_amount = abs(abs(ex_amount) - abs(amount)) <= tol
            if not same_amount:
                continue
        else:
            # Cross-currency: compare via Amount_EUR
            if pre_eur is None or pre_eur <= 0:
                continue
            try:
                ex_eur = float(ex.get("Amount_EUR") or 0)
            except (ValueError, TypeError):
                ex_eur = 0.0
            if ex_eur <= 0:
                continue
            eur_tol = max(abs(pre_eur) * 0.05, 0.5)
            if abs(abs(ex_eur) - abs(pre_eur)) > eur_tol:
                continue

        # ── Merchant overlap required ───────────────────────────────────
        ex_tokens = _normalize_note(ex.get("Note", ""))
        if not in_note_tokens or not ex_tokens:
            continue
        if not in_note_tokens & ex_tokens:
            continue

        # Pair found
        ex_amount_display = ex.get("Amount_Orig", "")
        return {
            "status": "confirm_required",
            "type": "refund_pair",
            "message": (
                f"🔄 Нашёл пару: {ex.get('Date','')} · "
                f"{ex_amount_display} {ex_cur} · {ex.get('Category','')} · "
                f"{ex.get('Note','')} ({ex_type_l}). "
                f"Новая запись — {tx_type_l} на ту же сумму у того же мерчанта. "
                f"Обе можно удалить — получится чистый ноль."
            ),
            "existing_tx_id": ex.get("ID", ""),
            "hint_for_agent": (
                "Refund pair detected. User will choose: delete both "
                "(hard-delete existing + skip write) or keep both."
            ),
        }
    return None


# T-218: Category/subcategory alias map — covers common agent-generated variants.
# Keys are lowercase aliases; values are canonical names (matching Sheets list).
# Updated via AdminSheets CategoryAliases tab (get_category_aliases).
_CATEGORY_ALIASES: dict[str, str] = {
    # ── Subcategory aliases ──────────────────────────────────────────────
    # Restaurants / Food & Drink
    "dining": "Restaurants", "restaurant": "Restaurants",
    "ristorante": "Restaurants", "ресторан": "Restaurants", "trattoria": "Restaurants",
    "osteria": "Restaurants", "pizzeria": "Restaurants", "gelateria": "Cafes",
    "cantina": "Restaurants", "enoteca": "Restaurants", "taverna": "Restaurants",
    "ristoro": "Restaurants", "trattoria": "Restaurants",
    "gelato": "Cafes", "gelateria": "Cafes", "pasticceria": "Cafes",
    "farmacia": "Pharmacy", "pharmacy": "Pharmacy", "apotheke": "Pharmacy",
    "carrefour": "Groceries", "lidl": "Groceries", "aldi": "Groceries",
    "conad": "Groceries", "coop": "Groceries", "pam": "Groceries",
    "esselunga": "Groceries", "tigros": "Groceries", "simply": "Groceries",
    "ortofrutta": "Groceries", "macelleria": "Groceries", "salumeria": "Groceries",
    "frutteria": "Groceries", "verdura": "Groceries", "frutta": "Groceries",
    "panificio": "Groceries", "forno": "Groceries", "fornaio": "Groceries",
    "parcheggio": "Parking", "autosilo": "Parking", "sosta": "Parking",
    "podologico": "Doctor", "podologia": "Doctor", "fisioterapia": "Doctor",
    "artedanza": "Activities", "danza": "Activities", "yoga": "Activities",
    "kiosco": "Snacks", "kiosk": "Snacks", "bar": "Cafes",
    "sapori": "Groceries", "bontà": "Groceries", "delizia": "Groceries",
    "ortofrutta": "Groceries", "macelleria": "Groceries",
    # T-271: Mix Markt (DE/RU chain in IT) + more IT grocery chains/generic terms.
    # Previous gap: 'MIX MARKT ITALIA SRL' on PROD got empty Subcategory because
    # tokens [mix, markt, italia, srl] matched no alias. Added markt/mixmarkt plus
    # common IT supermarket chains and food-shop types so fallback catches them
    # even when the LLM agent forgets to set subcategory in items[].
    "markt": "Groceries", "mixmarkt": "Groceries",
    "supermercato": "Groceries", "alimentari": "Groceries",
    "eurospin": "Groceries", "penny": "Groceries", "todis": "Groceries",
    "iper": "Groceries", "famila": "Groceries", "despar": "Groceries",
    "crai": "Groceries", "naturasi": "Groceries", "in's": "Groceries",
    "panetteria": "Groceries", "pescheria": "Groceries", "latteria": "Groceries",
    "drogheria": "Groceries", "minimarket": "Groceries",
    "airbnb": "Hotel", "booking": "Hotel", "hotel": "Hotel",
    "rituals": "Personal Care", "kiko": "Personal Care", "mac": "Personal Care",
    "school": "Tuition", "scuola": "Tuition", "university": "Tuition",
    "pepco": "Clothes", "primark": "Clothes", "h&m": "Clothes", "zara": "Clothes",
    "multisala": "Cinema", "cinema": "Cinema",
    "palestra": "Gym", "piscina": "Gym",
    "taxi": "Taxi", "uber": "Taxi", "italo": "Train", "trenitalia": "Train",
    "amazon": "Delivery", "zalando": "Clothes", "sephora": "Personal Care",
    "ikea": "Furniture", "leroy": "Maintenance",
    "кафе": "Cafes", "cafe": "Cafes", "coffee": "Cafes",
    "bakery": "Cafes", "bar": "Alcohol", "бар": "Alcohol",
    "pub": "Alcohol", "паб": "Alcohol",
    "pizza": "Restaurants", "sushi": "Restaurants",
    "fast food": "Restaurants", "fastfood": "Restaurants",
    # Food
    "grocery": "Groceries", "groceries": "Groceries",
    "supermarket": "Groceries", "супермаркет": "Groceries",
    "продукти": "Groceries", "продукты": "Groceries",
    "market": "Groceries", "mercato": "Groceries",
    # Transport
    "gas": "Fuel", "petrol": "Fuel", "gasoline": "Fuel",
    "бензин": "Fuel", "паливо": "Fuel", "заправка": "Fuel",
    "fuel station": "Fuel", "gas station": "Fuel", "petrol station": "Fuel",
    # T-270: "oil" is a common token in IT fuel-station names (e.g. COLDI OIL SERVICE
    # SANREMO). Prior to this change, such notes got no subcategory because no token
    # matched the Fuel alias set. Also added IT brands Erg, Api, Beyfin.
    "oil": "Fuel", "olio": "Fuel", "coldi": "Fuel",
    "esso": "Fuel", "shell": "Fuel", "agip": "Fuel", "ip": "Fuel",
    "tamoil": "Fuel", "q8": "Fuel", "eni": "Fuel",
    "erg": "Fuel", "api": "Fuel", "beyfin": "Fuel", "repsol": "Fuel",
    "азс": "Fuel", "заправочная": "Fuel",
    # T-274: car-wash aliases. Per Mikhail (2026-04-20): мойка/мийка/lavaggio/
    # autolavaggio/car wash → Fuel (treated under same Transport budget bucket as
    # fuel rather than its own subcategory). Evidence: PROD row 162 (CHIERI,
    # edffad68) was mislabeled because agent showed "Парковка" but real merchant
    # was "Мойка" and no alias caught it → empty Subcategory.
    "мойка": "Fuel", "мийка": "Fuel", "автомойка": "Fuel", "автомийка": "Fuel",
    "lavaggio": "Fuel", "autolavaggio": "Fuel",
    "carwash": "Fuel", "car wash": "Fuel",
    # T-274: English 'parking' self-map (we had паркінг/парковка/parking lot but
    # NOT bare 'parking'). 'parking' alone is the most common token in EN
    # merchant strings.
    "parking": "Parking",
    "паркінг": "Parking", "парковка": "Parking", "parking lot": "Parking",
    "метро": "Public Transport", "metro": "Public Transport",
    "bus": "Public Transport", "автобус": "Public Transport",
    "tram": "Public Transport", "трамвай": "Public Transport",
    "cab": "Taxi", "uber": "Taxi", "bolt": "Taxi",
    # Health
    "dentist": "Dental", "dentale": "Dental", "dental": "Dental",
    "дантист": "Dental", "стоматолог": "Dental", "odontoiatra": "Dental",
    "врач": "Doctor", "лікар": "Doctor", "clinic": "Doctor",
    "аптека": "Pharmacy", "drugs": "Pharmacy", "medicine": "Pharmacy",
    # Personal
    "hair": "Haircut", "haircare": "Haircut", "перукарня": "Haircut",
    "salon": "Haircut", "beauty salon": "Haircut",
    "clothes": "Clothes", "clothing": "Clothes", "одяг": "Clothes",
    "одежда": "Clothes", "fashion": "Clothes",
    # Entertainment
    "movie": "Cinema", "кіно": "Cinema", "кино": "Cinema",
    "film": "Cinema", "theatre": "Cinema",
    "gym": "Gym", "фітнес": "Gym", "fitness": "Gym",
    "sport": "Gym", "sport club": "Gym",
    # ── Category aliases ─────────────────────────────────────────────────
    "food": "Food", "еда": "Food", "їжа": "Food", "питание": "Food",
    "transport": "Transport", "транспорт": "Transport",
    "transportation": "Transport", "перевезення": "Transport",
    "health": "Health", "здоров'я": "Health", "здоровье": "Health",
    "entertainment": "Entertainment", "розваги": "Entertainment",
    "розваги": "Entertainment",
    "personal": "Personal", "особисте": "Personal", "личное": "Personal",
    "education": "Education", "освіта": "Education", "образование": "Education",
    "household": "Household", "дім": "Household", "дом": "Household",
    "housing": "Housing", "житло": "Housing", "жилье": "Housing",
    "savings": "Savings", "заощадження": "Savings", "сбережения": "Savings",
    "children": "Children", "діти": "Children", "дети": "Children",
    "travel": "Travel", "подорож": "Travel", "путешествие": "Travel",
    "subscriptions": "Subscriptions",
    "income": "Income", "доход": "Income", "дохід": "Income",
    "top up": "Top-up", "topup": "Top-up", "top-up": "Top-up",
    "поповнення": "Top-up", "пополнение": "Top-up",
}


def _gen_id() -> str:
    return uuid.uuid4().hex[:8]


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _resolve_envelope(params: dict, session: SessionContext,
                       sheets: SheetsClient) -> dict:
    """Find the envelope file_id for the given envelope_id."""
    env_id = params.get("envelope_id") or session.current_envelope_id
    if not env_id:
        raise ValueError("Конверт не выбран. Используйте /envelope для выбора конверта.")
    envelopes = sheets.get_envelopes()
    for e in envelopes:
        if e.get("ID") == env_id:
            return e
    raise ValueError(f"Конверт {env_id} не найден. Проверьте список конвертов командой /envelope.")


def _fuzzy_suggest(value: str, known: list[str], max_results: int = 3) -> list[str]:
    """Return known values that are similar to value (case-insensitive substring match)."""
    value_l = value.lower()
    exact = [k for k in known if k.lower() == value_l]
    if exact:
        return []  # it's actually a match
    contains = [k for k in known if value_l in k.lower() or k.lower() in value_l]
    return contains[:max_results] if contains else known[:max_results]


def _normalize_who(who: str, known_who: list[str], aliases: dict = None) -> str | None:
    """T-215: Resolve name/alias to canonical user name.

    Resolution order:
    1. Exact match against known_who (case-insensitive)
    2. Alias table lookup: Marina→Maryna, Михаил→Mikhail, Миша→Mikhail, etc.
    3. Word-in-phrase match: "Maryna Maslo" → "Maryna"

    Args:
        who: raw name string to resolve
        known_who: list of canonical user names
        aliases: dict from sheets.get_user_aliases() — alias_lower→canonical
    """
    if not who:
        return None
    who_l = who.lower().strip()
    if not who_l:
        return None

    # 1. Exact match (case-insensitive)
    for k in (known_who or []):
        if k.lower() == who_l:
            return k

    # 2. Alias table lookup (T-215)
    if aliases:
        canonical = aliases.get(who_l)
        if canonical:
            return canonical
        # Try individual words in the input against alias table
        for word in who_l.split():
            canonical = aliases.get(word)
            if canonical:
                return canonical

    # 3. Word-in-phrase: "Maryna Maslo" → "Maryna" if "Maryna" in known_who
    who_words = who_l.split()
    for k in (known_who or []):
        if k.lower() in who_words:
            return k

    return None


def _validate_transaction_params(params: dict, ref: dict) -> dict:
    """Check category, who, account against reference data.
    Returns dict of unknown fields and suggestions, or empty dict if all OK.
    Skip validation if force_new=True or if reference list is empty (not set up yet).

    Side effect: normalizes params['who'] in-place if a known user name is found
    within the submitted value (e.g. "Marina Maslo" → "Marina"). This prevents
    phantom users from appearing in contribution reports.
    """
    if params.get("force_new"):
        return {}

    unknown = {}
    suggestions = {}

    # Income transactions: category/subcategory are not from the expense taxonomy.
    # Strip subcategory silently (AI often sets "Top-up" which doesn't exist in expense list).
    # Skip category/subcategory validation entirely for income — validate only who/account.
    tx_type_for_val = params.get("type", "expense")
    if tx_type_for_val == "income":
        params["subcategory"] = ""  # strip — income has no subcategory
        # Leave category as-is (e.g. "Income") but don't validate it against expense list
    else:
        # T-218: Category alias resolution — check alias map before fuzzy matching.
        # Also load dynamic aliases from AdminSheets if available.
        def _resolve_cat_alias(value: str, known: list[str], sheets_inst=None) -> str | None:
            """Try alias map → fuzzy → None."""
            if not value:
                return None
            v_lower = value.lower().strip()
            # 1. Exact match (case-insensitive)
            for k in known:
                if k.lower() == v_lower:
                    return k
            # 2. Hardcoded alias table
            alias = _CATEGORY_ALIASES.get(v_lower)
            if alias and any(k.lower() == alias.lower() for k in known):
                return alias
            # 3. Dynamic aliases from AdminSheets (if available)
            if sheets_inst:
                try:
                    dyn = sheets_inst.get_category_aliases()
                    canonical = dyn.get(v_lower)
                    if canonical and any(k.lower() == canonical.lower() for k in known):
                        return canonical
                except Exception:
                    pass
            # 4. Fuzzy single match
            similar = _fuzzy_suggest(value, known)
            if len(similar) == 1:
                return similar[0]
            return None  # unknown

        # Validate category with alias resolution
        category = params.get("category", "")
        known_cats = ref.get("categories", [])
        _sheets_ref = ref.get("_sheets_instance")  # injected if available
        if category and known_cats:
            resolved = _resolve_cat_alias(category, known_cats, _sheets_ref)
            if resolved:
                params["category"] = resolved  # auto-correct (silent)
            else:
                similar = _fuzzy_suggest(category, known_cats)
                unknown["category"] = category
                suggestions["category"] = similar

        # Validate subcategory with alias resolution (T-218)
        subcategory = params.get("subcategory", "")
        known_subs = ref.get("subcategories", [])
        if subcategory and known_subs and "category" not in unknown:
            resolved_sub = _resolve_cat_alias(subcategory, known_subs, _sheets_ref)
            if resolved_sub:
                params["subcategory"] = resolved_sub  # auto-correct (silent)
            else:
                similar = _fuzzy_suggest(subcategory, known_subs)
                unknown["subcategory"] = subcategory
                suggestions["subcategory"] = similar

    # Validate who — with alias normalization (T-215: Marina→Maryna, Миша→Mikhail)
    who = params.get("who", "")
    known_who = ref.get("who", [])
    # T-215: load alias table for robust name resolution
    _aliases = {}
    try:
        _aliases = sheets.get_user_aliases()
    except Exception:
        pass
    if who and known_who:
        normalized = _normalize_who(who, known_who, aliases=_aliases)
        if normalized and normalized.lower() != who.lower():
            params["who"] = normalized
        elif not any(k.lower() == who.lower() for k in known_who):
            # Try alias lookup before flagging as unknown
            _alias_match = _aliases.get(who.lower().strip())
            if _alias_match:
                params["who"] = _alias_match
            else:
                unknown["who"] = who
                suggestions["who"] = _fuzzy_suggest(who, known_who)

    if unknown:
        return {"unknown": unknown, "suggestions": suggestions, "known": ref}
    return {}


async def tool_add_transaction(params: dict, session: SessionContext,
                                sheets: SheetsClient, auth: AuthManager,
                                skip_sort: bool = False,
                                batch_mode: bool = False) -> Any:
    """batch_mode=True: skip validation + dup check to avoid N×2 Sheets read
    calls that exhaust the 60 req/min quota when adding items in a loop."""
    if not auth.can_write(session.user_id):
        return {"error": "Permission denied."}

    envelope = _resolve_envelope(params, session, sheets)
    if not auth.can_access_envelope(session.user_id, envelope["ID"]):
        return {"error": "You don't have access to this envelope."}

    # batch_mode: inject flags that skip validation and duplicate detection.
    # User already reviewed and confirmed the item list — no need for per-item checks.
    if batch_mode:
        params = dict(params)       # don't mutate caller's dict
        params["force_new"] = True  # skip category/who validation
        params["force_add"] = True  # skip duplicate detection

    # ── Validation against reference data ────────────────────────────────
    # T-211: skip get_reference_data entirely in batch_mode (force_new=True skips anyway)
    # This saves 1 read per batch item = 7 reads for 7 items.
    if batch_mode or params.get("force_new"):
        issues = {}  # no validation in batch mode
    else:
        issues = {}
    try:
        if not batch_mode:
            ref = sheets.get_reference_data(envelope["file_id"])
            issues = _validate_transaction_params(params, ref)
            if issues:
                unknown = issues["unknown"]
                sug = issues["suggestions"]
                known = issues["known"]
                lines = []
                for field, val in unknown.items():
                    s = sug.get(field, [])
                    hint = f"Похожие: {', '.join(s)}" if s else f"Известные: {', '.join(known.get(field + 's', known.get(field, [])))}"
                    lines.append(f"• {field} = «{val}» — не найдено. {hint}")
                return {
                    "status": "confirm_required",
                    "type": "unknown_values",
                    "message": "⚠️ Неизвестные значения:\n" + "\n".join(lines),
                    "unknown_fields": unknown,
                    "suggestions": sug,
                    "hint_for_agent": (
                        "Ask the user: pick one of the suggested values, or confirm "
                        "creating a new one? If user confirms new value, call again with force_new=true."
                    ),
                }
    except Exception:
        pass  # validation is best-effort; don't block the write

    tx_id = _gen_id()
    now = datetime.utcnow().isoformat()
    date = params.get("date") or _today()
    amount = params["amount"]
    # T-248: bank statements pass negative amounts for expenses — use abs() always
    try:
        if float(amount) < 0:
            amount = abs(float(amount))
    except (ValueError, TypeError):
        pass
    currency = params.get("currency", "EUR")
    category = params.get("category", "")
    subcategory = params.get("subcategory", "")
    note = params.get("note", "")

    # T-237/T-245: infer subcategory — merchant memory first, then keyword aliases
    if not subcategory and note and category.lower() != "income":
        try:
            # T-245: check learned merchant→subcategory mappings first
            import db as _db
            _uid = getattr(session, "user_id", 0)
            _learned_sub = await _db.get_merchant_subcategory(_uid, note)
            if _learned_sub:
                subcategory = _learned_sub
                params["subcategory"] = subcategory
            else:
                # T-237: keyword-based inference
                _ref_for_sub = sheets.get_reference_data(envelope["file_id"])
                _known_subs = _ref_for_sub.get("subcategories", [])
                _sheets_inst = _ref_for_sub.get("_sheets_instance")
                subcategory = _infer_subcategory(note, _known_subs, _sheets_inst)
                if subcategory:
                    params["subcategory"] = subcategory
        except Exception:
            pass  # inference is best-effort

    # T-215: resolve `who` from Telegram user_id (most reliable) or alias table.
    # Priority: (1) params who → normalize via alias; (2) session user_id → Users tab lookup
    raw_who = params.get("who", "")
    if raw_who:
        # Normalize whatever the agent/user passed (handles Marina→Maryna, Миша→Mikhail)
        try:
            _al = sheets.get_user_aliases()
            _kw = sheets._admin.get_user_names()
            _resolved = _normalize_who(raw_who, _kw, aliases=_al)
            who = _resolved if _resolved else raw_who
        except Exception:
            who = raw_who
    else:
        # No who set — identify from Telegram user_id via Users tab
        who = session.user_name  # fallback
        try:
            _users = sheets.get_users()
            _uid = str(session.user_id)
            for _u in _users:
                if str(_u.get("telegram_id", "")) == _uid:
                    _name = _u.get("name") or _u.get("Name", "")
                    if _name:
                        who = _name.strip()
                    break
        except Exception:
            pass

    # ── T-253: Refund+expense pair detection (±14 days) ──────────────────
    # Before the narrow ±1-day dup check, look across a wider window for a
    # matching tx of OPPOSITE Type (expense<->income) with the same merchant+
    # amount. That's a refund pair: the real-world money moved out and back in,
    # so net = 0 and the user prefers both rows physically deleted.
    # Skipped when force_add=true (user already confirmed "add anyway") or
    # batch_mode (items in the same batch are pre-reviewed).
    if not params.get("force_add"):
        try:
            in_note_tokens = _normalize_note(params.get("note", ""))
            try:
                in_amount_v = float(amount)
            except (ValueError, TypeError):
                in_amount_v = 0.0
            in_cur_v = currency.upper()
            # Cross-currency support: reuse same FX-based pre-EUR calc as dup block
            _pre_eur_pair = None
            if in_cur_v == "EUR":
                _pre_eur_pair = in_amount_v
            else:
                try:
                    _fx_rows_p = sheets.get_fx_rates(envelope["file_id"])
                    _fx_row_p = next(
                        (r for r in _fx_rows_p if r.get("Month") == date[:7]), None
                    )
                    if _fx_row_p:
                        _rate_p = float(_fx_row_p.get(f"EUR_{in_cur_v}", 0) or 0)
                        if _rate_p:
                            _pre_eur_pair = round(in_amount_v / _rate_p, 2)
                except Exception:
                    pass
            _pair_from, _pair_to = _date_range_for_pair(date, days=14)
            existing_pair = sheets.get_transactions(
                envelope["file_id"],
                {"date_from": _pair_from, "date_to": _pair_to, "limit": 500},
            )
            pair_hit = _detect_refund_pair(
                date=date,
                amount=in_amount_v,
                currency=in_cur_v,
                tx_type=params.get("type", "expense"),
                in_note_tokens=in_note_tokens,
                pre_eur=_pre_eur_pair,
                existing_txs=existing_pair,
            )
            if pair_hit:
                return pair_hit
        except Exception:
            pass  # pair check is best-effort; don't block the write

    # ── Duplicate detection (T-030 / T-182 / T-192) ──────────────────────
    # Checks: same date + amount within tolerance + note overlap.
    # Same-currency tolerance:
    #   EUR  → strict: abs diff < 0.01 (rounding only)
    #   other → ±5%: covers FX rate fluctuation.
    # Cross-currency (T-192): compare Amount_EUR from existing vs pre-computed
    #   EUR equivalent of new tx.  Handles UAH bank stmt vs EUR manual entry.
    # Note/merchant: if both sides have a non-empty note, strings that share
    #   no common tokens are treated as different transactions (not duplicate).
    if not params.get("force_add"):
        try:
            # T-237: use ±1 day range to catch bank-statement vs posting-date mismatches
            _dup_from, _dup_to = _date_range_for_dup(date)
            existing = sheets.get_transactions(
                envelope["file_id"],
                {"date_from": _dup_from, "date_to": _dup_to, "limit": 100},
            )
            try:
                in_amount = float(amount)
            except (ValueError, TypeError):
                in_amount = 0.0
            in_note = _normalize_note(params.get("note", ""))  # T-237: normalized tokens
            in_cur = currency.upper()

            # T-192: pre-compute EUR equivalent of new tx for cross-currency check.
            # Reuses FX_Rates sheet (same read done later for Amount_EUR column).
            _pre_eur: float | None = None
            if in_cur == "EUR":
                _pre_eur = in_amount
            else:
                try:
                    # T-211: use cached get_fx_rates (no raw gspread call)
                    _fx_rows2 = sheets.get_fx_rates(envelope["file_id"])
                    _fx_row2 = next(
                        (r for r in _fx_rows2 if r.get("Month") == date[:7]), None
                    )
                    if _fx_row2:
                        _col2 = f"EUR_{in_cur}"
                        _rate2 = float(_fx_row2.get(_col2, 0) or 0)
                        if _rate2:
                            _pre_eur = round(in_amount / _rate2, 2)
                except Exception:
                    pass  # leave _pre_eur = None; cross-currency check skipped

            for ex in existing:
                ex_cur = str(ex.get("Currency_Orig", "EUR")).upper()

                if ex_cur != in_cur:
                    # ── T-192: cross-currency check via Amount_EUR ───────
                    if _pre_eur is None or _pre_eur <= 0:
                        continue
                    try:
                        ex_eur = float(ex.get("Amount_EUR") or 0)
                    except (ValueError, TypeError):
                        ex_eur = 0.0
                    if ex_eur <= 0:
                        continue
                    eur_tol = max(_pre_eur * 0.05, 0.5)
                    if abs(ex_eur - _pre_eur) > eur_tol:
                        continue
                    # EUR amounts match — check note overlap before flagging
                    # T-237: normalize accents before token split
                    ex_toks_x = _normalize_note(ex.get("Note", ""))
                    if in_note and ex_toks_x:
                        if not in_note & ex_toks_x:
                            continue
                    return {
                        "status": "confirm_required",
                        "type": "duplicate",
                        "message": (
                            f"⚠️ Похожая запись уже есть за {date}: "
                            f"{ex.get('Category', '')} · {ex_eur:.2f} EUR"
                            f" (оригінал: {ex.get('Amount_Orig', '')} {ex_cur})"
                            + (f" · {ex.get('Note', '')}" if ex.get("Note") else "")
                            + f" · {ex.get('Who', '')} (cross-currency ±5% EUR match)"
                        ),
                        "existing_tx_id": ex.get("ID", ""),
                        "hint_for_agent": "Ask user: is this a duplicate? If not, call add_transaction again with force_add=true.",
                    }
                    # end cross-currency branch — continue to next existing tx

                # ── Same-currency amount tolerance ───────────────────────
                try:
                    ex_amount = float(ex.get("Amount_Orig") or 0)
                except (ValueError, TypeError):
                    ex_amount = 0.0
                if in_cur == "EUR":
                    same_amount = abs(ex_amount - in_amount) < 0.01
                else:
                    # ±5% for non-EUR: covers FX rounding and rate differences
                    tolerance = max(in_amount * 0.05, 0.5)
                    same_amount = abs(ex_amount - in_amount) <= tolerance

                if not same_amount:
                    continue

                # ── Category + who ───────────────────────────────────────
                ex_cat = str(ex.get("Category", "")).lower()
                ex_who = str(ex.get("Who", "")).lower()
                same_cat = (ex_cat == category.lower()) if category else True
                same_who = (ex_who == who.lower()) if who else True

                if not (same_cat and same_who):
                    continue

                # ── Note / merchant: reject if both present and no overlap ──
                # T-237: normalize accents (ò→o) before token comparison
                ex_tokens = _normalize_note(ex.get("Note", ""))
                if in_note and ex_tokens:
                    if not in_note & ex_tokens:
                        # No common words → different merchants, not a duplicate
                        continue

                return {
                    "status": "confirm_required",
                    "type": "duplicate",
                    "message": (
                        f"⚠️ Похожая запись уже есть за {date}: "
                        f"{ex.get('Category', '')} · {ex_amount:,.2f} {ex_cur}"
                        + (f" · {ex.get('Note', '')}" if ex.get('Note') else "")
                        + f" · {ex.get('Who', '')}"
                        + (f" (±5% FX tolerance)" if in_cur != "EUR" else "")
                    ),
                    "existing_tx_id": ex.get("ID", ""),
                    "hint_for_agent": "Ask user: is this a duplicate? If not, call add_transaction again with force_add=true.",
                }
        except Exception:
            pass  # duplicate check is best-effort; don't block the write
    account = params.get("account", "")
    tx_type = params.get("type", "expense")
    note = params.get("note", "")

    # Resolve Amount_EUR: direct for EUR, otherwise look up FX rate
    amount_eur = ""
    if currency.upper() == "EUR":
        amount_eur = amount
    else:
        try:
            month = date[:7]  # YYYY-MM
            file_id = envelope["file_id"]
            # T-211: use cached get_fx_rates (5-min TTL via _static_cache).
            # OLD: fx_ws.get_all_records() — uncached, hit quota on every batch item.
            fx_rows = sheets.get_fx_rates(file_id)
            fx_row = next((r for r in fx_rows if r.get("Month") == month), None)
            if fx_row:
                # FX_Rates columns are named EUR_PLN, EUR_UAH, EUR_USD etc.
                # Each value means: 1 EUR = N <currency>
                # To convert to EUR: amount_eur = amount_orig / rate
                col_key = f"EUR_{currency.upper()}"
                rate = float(fx_row.get(col_key, 0) or 0)
                if rate:
                    amount_eur = round(float(amount) / rate, 2)
        except Exception:
            pass  # leave blank; fallback in reporting uses Amount_Orig

    # Column order matches the restructured Transactions sheet (Task 4a):
    # A:Date  B:Amount_Orig  C:Currency_Orig  D:Category  E:Subcategory
    # F:Note  G:Who  H:Amount_EUR  I:Type  J:Account
    # K:ID  L:Envelope  M:Source  N:Wise_ID  O:Created_At  P:Deleted
    row = [
        date,           # A - Date
        amount,         # B - Amount_Orig
        currency,       # C - Currency_Orig
        category,       # D - Category
        subcategory,    # E - Subcategory
        note,           # F - Note
        who,            # G - Who
        amount_eur,     # H - Amount_EUR
        tx_type,        # I - Type
        account,        # J - Account
        tx_id,          # K - ID
        envelope["ID"], # L - Envelope
        "bot",          # M - Source
        "",             # N - Wise_ID
        now,            # O - Created_At
        "FALSE",        # P - Deleted
    ]

    try:
        sheets.add_transaction(envelope["file_id"], row)
    except Exception as e:
        logger.error(f"sheets.add_transaction failed for {tx_id}: {e}", exc_info=True)
        # T-266: persist to error_log for post-mortem (previously only logger.error)
        try:
            import traceback as _tb
            import asyncio as _asyncio
            import db as _db_err
            _coro = _db_err.log_error(
                error_type="sheets_add_transaction_failed",
                context=f"tx_id={tx_id} envelope={envelope.get('file_id','')} user={session.user_id}",
                traceback_str=_tb.format_exc(),
                raw_input=str(row)[:500],
                user_id=session.user_id,
                session_id=getattr(session, "session_id", "") or "",
            )
            # Fire-and-forget: we're already inside an async tool, schedule but don't block error return.
            try:
                _loop = _asyncio.get_event_loop()
                if _loop.is_running():
                    _asyncio.ensure_future(_coro)
                else:
                    _loop.run_until_complete(_coro)
            except Exception:
                pass
        except Exception as _log_err:
            logger.warning(f"[T-266] log_error failed: {_log_err}")
        # T-212: keep TRANSACTION FAILED prefix (test compatibility) but clean raw JSON
        import re as _re
        _err_str = str(e)
        _code_m = _re.search(r"'code':\s*(\d+)", _err_str)
        if _code_m:
            _code = int(_code_m.group(1))
            _friendly = {
                429: "Quota exceeded (60 reads/min). Try again in 30 sec.",
                500: "Sheets server error (transient). Retry in ~30 sec.",
                503: "Sheets unavailable (transient). Retry.",
            }.get(_code, f"Sheets API {_code}")
            return {"error": f"TRANSACTION FAILED: {_friendly}", "tx_id": tx_id}
        return {"error": f"TRANSACTION FAILED to save: {_err_str[:120]}", "tx_id": tx_id}

    # T-176: sort Transactions sheet by Date (asc) after every add.
    # T-183: skip_sort=True in batch mode (cb_split_separate) — caller sorts once at end.
    if not skip_sort:
        try:
            sheets.sort_transactions_by_date(envelope["file_id"], order="asc")
        except Exception as _sort_err:
            logger.warning(f"sort_transactions_by_date failed (non-fatal): {_sort_err}")

    # Update session last_action for undo
    session.last_action = LastAction(
        tx_id=tx_id, action="add",
        envelope_id=envelope["ID"],
        snapshot={"amount": amount, "currency": currency,
                   "date": date, "category": category}
    )

    symbol = "✓" if tx_type == "expense" else "+"
    return {
        "status": "ok",
        "message": (
            f"{symbol} {category} · {amount} {currency} · {who} · {date}"
            + (f" · {note}" if note else "")
        ),
        "tx_id": tx_id,
    }


async def tool_edit_transaction(params: dict, session: SessionContext,
                                 sheets: SheetsClient, auth: AuthManager) -> Any:
    if not auth.can_write(session.user_id):
        return {"error": "Permission denied."}

    tx_id = params["tx_id"]
    field = params["field"]
    new_value = params["new_value"]

    # Find which envelope contains this tx
    envelope_id = params.get("envelope_id") or session.current_envelope_id
    envelopes = sheets.get_envelopes()
    file_id = None
    for e in envelopes:
        if e.get("ID") == envelope_id:
            file_id = e["file_id"]
            break

    if not file_id:
        return {"error": "Envelope not found."}

    sheets.update_transaction_field(file_id, tx_id, field, new_value)
    session.last_action = LastAction(
        tx_id=tx_id, action="edit",
        envelope_id=envelope_id,
        snapshot={"field": field, "new_value": new_value}
    )

    # T-245: auto-save merchant memory when subcategory is corrected
    if field == "Subcategory" and new_value:
        try:
            import db as _db
            # Find the note of this transaction to use as trigger_text
            existing = sheets.get_transactions(file_id)
            tx = next((t for t in existing if t.get("ID") == tx_id), None)
            note = tx.get("Note", "") if tx else ""
            if note:
                await _db.save_learning(
                    user_id=getattr(session, "user_id", 0),
                    event_type="merchant_subcategory",
                    trigger_text=note,
                    learned={"subcategory": new_value},
                    confidence_delta=0.1,
                    envelope_id=envelope_id or "",
                )
        except Exception:
            pass  # best-effort, don't block the edit

    return {"status": "ok", "message": f"✓ Updated {field} → {new_value} ({tx_id})"}


async def tool_enrich_transaction(params: dict, session: SessionContext,
                                   sheets: SheetsClient, auth: AuthManager) -> Any:
    """T-134: Enrich an existing transaction with receipt data.
    Updates multiple fields at once (note, category, subcategory, etc.)
    without creating a duplicate transaction."""
    if not auth.can_write(session.user_id):
        return {"error": "Permission denied."}

    tx_id = params.get("tx_id", "")
    if not tx_id:
        return {"error": "tx_id is required."}

    envelope_id = params.get("envelope_id") or session.current_envelope_id
    envelopes = sheets.get_envelopes()
    file_id = None
    for e in envelopes:
        if e.get("ID") == envelope_id:
            file_id = e["file_id"]
            break
    if not file_id:
        return {"error": "Envelope not found."}

    # Validate category/subcategory/who against reference data
    try:
        ref = sheets.get_reference_data(file_id)
        # Build a mini-params dict for validation
        _vparams = {}
        if params.get("category"):
            _vparams["category"] = params["category"]
        if params.get("subcategory"):
            _vparams["subcategory"] = params["subcategory"]
        if params.get("who"):
            _vparams["who"] = params["who"]
        if _vparams:
            issues = _validate_transaction_params(_vparams, ref)
            if issues:
                unknown = issues.get("unknown", {})
                sug = issues.get("suggestions", {})
                # T-216: For enrichment, subcategory is metadata — don't block on it.
                # If subcategory is invalid → silently drop it, continue with other fields.
                # Only block on category/who unknown values (more critical).
                if "subcategory" in unknown:
                    del unknown["subcategory"]
                    params.pop("subcategory", None)  # drop invalid subcategory
                    if "subcategory" in sug:
                        del sug["subcategory"]
                if unknown:
                    known = issues.get("known", {})
                    lines = []
                    for field, val in unknown.items():
                        s = sug.get(field, [])
                        hint = (f"Похожие: {', '.join(s)}" if s
                                else f"Известные: {', '.join(known.get(field + 's', known.get(field, [])))}")
                        lines.append(f"• {field} = «{val}» — не найдено. {hint}")
                    return {
                        "status": "confirm_required",
                        "type": "unknown_values",
                        "message": "⚠️ Неизвестные значения:\n" + "\n".join(lines),
                        "unknown_fields": unknown,
                        "suggestions": sug,
                        "hint_for_agent": (
                            "Ask user: pick a suggested value, or confirm creating new? "
                            "If confirmed, call enrich_transaction again — the value will be accepted."
                        ),
                    }
            # Apply auto-corrections from validation
            if "category" in _vparams:
                params["category"] = _vparams["category"]
            if "subcategory" in _vparams:
                params["subcategory"] = _vparams["subcategory"]
            if "who" in _vparams:
                params["who"] = _vparams["who"]
    except Exception:
        pass  # validation is best-effort

    # Fields that can be enriched from receipt data
    # T-210: also support amount_orig / currency_orig (e.g. UAH original from bank statement)
    col_map = {
        "note": "Note",
        "category": "Category",
        "subcategory": "Subcategory",
        "who": "Who",
        "account": "Account",
        "amount_orig": "Amount_Orig",
        "currency_orig": "Currency_Orig",
    }
    field_sources = {
        "note": params.get("note"),
        "category": params.get("category"),
        "subcategory": params.get("subcategory"),
        "who": params.get("who"),
        "account": params.get("account"),
        "amount_orig": str(params["amount_orig"]) if params.get("amount_orig") else None,
        "currency_orig": params.get("currency_orig"),
    }
    fields_to_write = {
        col_map[k]: v for k, v in field_sources.items()
        if v is not None and v != ""
    }

    if not fields_to_write:
        return {"error": "No fields to update."}

    # T-209: ONE read + N writes instead of N reads + N writes.
    # Also fixes false-positive: update_transaction_fields returns list of
    # actually-updated field names, not just "no exception raised".
    try:
        written_cols = sheets.update_transaction_fields(file_id, tx_id, fields_to_write)
    except Exception as e:
        logger.error(f"enrich_transaction: batch write failed: {e}")
        return {"error": f"Sheets write failed: {e}"}

    if not written_cols:
        logger.warning(f"enrich_transaction: tx_id {tx_id} not found in {file_id}")
        return {"error": f"Transaction {tx_id} not found in Sheets. It may have been deleted or the ID is wrong."}

    # Build human-readable summary of what was updated
    reverse_map = {v: k for k, v in col_map.items()}
    updated_display = [f"{reverse_map.get(c, c)}={fields_to_write[c]}" for c in written_cols]

    return {
        "status": "ok",
        "message": f"✓ Enriched {tx_id}: {', '.join(updated_display)}",
        "tx_id": tx_id,
        "updated_fields": written_cols,
    }


async def tool_delete_transaction(params: dict, session: SessionContext,
                                   sheets: SheetsClient, auth: AuthManager) -> Any:
    import db as _db
    if not auth.can_write(session.user_id):
        return {"error": "Permission denied."}

    if not params.get("confirmed"):
        return {
            "status": "confirm_required",
            "message": "confirmed=true required to proceed with deletion.",
        }

    tx_id = params.get("tx_id", "").strip()
    if not tx_id:
        return {"error": "tx_id is required."}

    envelope_id = params.get("envelope_id") or session.current_envelope_id
    envelopes = sheets.get_envelopes()

    # Try the target envelope first; if not found, search ALL envelopes
    # (handles cases where old transactions have a different format or were added
    #  before the current session's envelope was set)
    matched_envelope = next((e for e in envelopes if e.get("ID") == envelope_id), None)

    deleted = False
    found_in_envelope = None

    if matched_envelope:
        try:
            deleted = sheets.hard_delete_transaction(matched_envelope["file_id"], tx_id)
            if deleted:
                found_in_envelope = envelope_id
        except Exception as e:
            return {"error": f"DELETION FAILED — Sheets error in envelope '{envelope_id}': {e}"}

    if not deleted:
        # Fallback: try every other envelope
        for env in envelopes:
            if env.get("ID") == envelope_id:
                continue  # already tried
            try:
                if sheets.hard_delete_transaction(env["file_id"], tx_id):
                    deleted = True
                    found_in_envelope = env["ID"]
                    break
            except Exception:
                pass  # continue trying other envelopes

    if not deleted:
        searched = [e.get("ID", "?") for e in envelopes]
        return {
            "error": f"DELETION FAILED — transaction '{tx_id}' not found in any envelope "
                     f"({', '.join(searched)}). Row was NOT removed. "
                     f"Check that the tx_id is correct.",
        }

    # Clean up parsed_data in PostgreSQL
    if _db.is_ready():
        try:
            pool = await _db.get_pool()
            if pool:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "DELETE FROM parsed_data WHERE transaction_id = $1", tx_id
                    )
        except Exception as e:
            logger.warning(f"delete_transaction: parsed_data cleanup failed: {e}")

    return {
        "status": "ok",
        "deleted": True,
        "tx_id": tx_id,
        "envelope_id": found_in_envelope,
        "message": f"Transaction {tx_id} permanently deleted from envelope {found_in_envelope}.",
    }


async def tool_delete_transaction_rows(params: dict, session: SessionContext,
                                        sheets: SheetsClient, auth: AuthManager) -> Any:
    """Physically delete a range of rows from the Transactions sheet by row number.
    Two-step: first call (confirmed=False) returns a preview; second (confirmed=True) executes."""
    if not auth.can_write(session.user_id):
        return {"error": "Permission denied."}

    start_row = params.get("start_row")
    end_row = params.get("end_row")

    if start_row is None or end_row is None:
        return {"error": "start_row и end_row обязательны."}
    start_row = int(start_row)
    end_row = int(end_row)

    if start_row < 2:
        return {"error": "Строка 1 — заголовок, удалять нельзя. Строки данных начинаются с 2."}
    if end_row < start_row:
        return {"error": "end_row должен быть >= start_row."}
    if end_row - start_row > 99:
        return {"error": "Нельзя удалять больше 100 строк за раз."}

    envelope = _resolve_envelope(params, session, sheets)
    if not auth.can_access_envelope(session.user_id, envelope["ID"]):
        return {"error": "You don't have access to this envelope."}

    count = end_row - start_row + 1

    # ── Step 1: preview (no confirmed flag) ──────────────────────────────────
    if not params.get("confirmed"):
        try:
            raw_rows = sheets.get_transaction_rows_preview(
                envelope["file_id"], start_row, end_row
            )
        except Exception as e:
            raw_rows = []

        lines = []
        for i, row in enumerate(raw_rows):
            sheet_row = start_row + i
            try:
                date     = row[0] if len(row) > 0 else "?"
                amount   = row[1] if len(row) > 1 else "?"
                currency = row[2] if len(row) > 2 else ""
                category = row[3] if len(row) > 3 else ""
                tx_type  = row[8] if len(row) > 8 else ""
                note     = row[5] if len(row) > 5 else ""
                desc = f"{date} · {amount} {currency} · {category}"
                if note:
                    desc += f" · {note}"
                lines.append(f"  {sheet_row}: {desc}")
            except Exception:
                lines.append(f"  {sheet_row}: [данные]")

        preview = "\n".join(lines) if lines else "  (нет данных)"

        # Store pending action in session for inline-button confirmation
        session.pending_delete = {
            "start_row": start_row,
            "end_row": end_row,
            "file_id": envelope["file_id"],
            "count": count,
        }

        return {
            "status": "confirm_required",
            "message": (
                f"⚠️ ВНИМАНИЕ — безвозвратное удаление {count} {_row_word(count)} "
                f"({start_row}–{end_row}):\n\n"
                f"{preview}\n\n"
                "Это действие нельзя отменить. Нажмите кнопку ниже для подтверждения."
            ),
        }

    # ── Step 2: execute (confirmed=True) ─────────────────────────────────────
    try:
        deleted = sheets.delete_transaction_rows(envelope["file_id"], start_row, end_row)
    except Exception as e:
        return {"error": f"Ошибка удаления: {e}"}

    return {
        "status": "ok",
        "message": f"✓ Удалено {deleted} {_row_word(deleted)} ({start_row}–{end_row})",
    }


def _row_word(n: int) -> str:
    if n % 100 in (11, 12, 13, 14):
        return "строк"
    r = n % 10
    if r == 1:
        return "строка"
    if r in (2, 3, 4):
        return "строки"
    return "строк"


async def tool_sort_transactions(params: dict, session: SessionContext,
                                  sheets: SheetsClient, auth: AuthManager) -> Any:
    """Sort Transactions sheet by date (ascending = oldest first, descending = newest first)."""
    if not auth.can_write(session.user_id):
        return {"error": "Permission denied."}

    order = params.get("order", "asc").lower()
    if order not in ("asc", "desc"):
        order = "asc"

    envelope = _resolve_envelope(params, session, sheets)
    if not auth.can_access_envelope(session.user_id, envelope["ID"]):
        return {"error": "You don't have access to this envelope."}

    try:
        count = sheets.sort_transactions_by_date(envelope["file_id"], order)
    except Exception as e:
        return {"error": f"Ошибка сортировки: {e}"}

    direction = "старые → новые" if order == "asc" else "новые → старые"
    return {
        "status": "ok",
        "message": f"✓ Отсортировано {count} {_row_word(count)} по дате ({direction})",
    }


async def tool_find_transactions(params: dict, session: SessionContext,
                                  sheets: SheetsClient, auth: AuthManager) -> Any:
    envelope_id = params.get("envelope_id") or session.current_envelope_id
    if not auth.can_access_envelope(session.user_id, envelope_id):
        return {"error": "Permission denied."}

    envelopes = sheets.get_envelopes()
    file_id = None
    for e in envelopes:
        if e.get("ID") == envelope_id:
            file_id = e["file_id"]
            break

    if not file_id:
        return {"error": "Envelope not found."}

    records = sheets.get_transactions(file_id)
    limit = params.get("limit", 10)

    # Apply filters
    if params.get("date_from"):
        records = [r for r in records if r.get("Date", "") >= params["date_from"]]
    if params.get("date_to"):
        records = [r for r in records if r.get("Date", "") <= params["date_to"]]
    if params.get("category"):
        records = [r for r in records
                   if params["category"].lower() in r.get("Category", "").lower()]
    if params.get("who"):
        records = [r for r in records if r.get("Who") == params["who"]]
    if params.get("note_contains"):
        records = [r for r in records
                   if params["note_contains"].lower() in r.get("Note", "").lower()]

    records = records[-limit:]
    return {"status": "ok", "count": len(records), "transactions": records}
