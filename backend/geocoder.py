"""Recherche d'adresses et de lieux dans l'index local du Grand Tunis (data/places.json, OpenStreetMap).

Pensée pour la façon dont on écrit une adresse en Tunisie :
- fautes de frappe : une lettre de différence par mot (« hyppocrate » → Hippocrate) ;
- suggestions pendant la frappe : le dernier mot peut être incomplet (« hippo ») ;
- mots sans importance ignorés (rue, avenue, cité, el, de…) et numéro gardé pour l'affichage ;
- noms usuels : « Avicenne » = Ibn Sina, « Lac 2 » = Les Berges du Lac II, chiffres romains ;
- quartier ou ville facultatifs : « rue Hippocrate cité Avicenne Tunis » trouve la rue d'Ibn Sina ;
- noms arabes cherchables.
"""
import bisect
import json
import logging
import os
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("tuntransport.geocoder")
DEFAULT_FILE = Path(__file__).parent / "data" / "places.json"

# Mots qui ne distinguent pas un lieu d'un autre.
STOPWORDS = {
    "rue", "r", "nahj", "avenue", "av", "ave", "boulevard", "bd", "blvd", "impasse", "imp", "route", "rte",
    "place", "pl", "passage", "allee", "chemin", "rond", "point", "cite", "residence", "res", "hay", "quartier",
    "el", "al", "les", "le", "la", "l", "de", "du", "des", "d", "et", "a", "au", "aux", "en", "n", "no", "numero",
    "نهج", "شارع", "زنقة", "حي", "ال",
}
STREET_WORDS = {"rue", "r", "nahj", "avenue", "av", "ave", "boulevard", "bd", "blvd", "impasse", "imp", "route",
                "rte", "passage", "allee", "chemin", "نهج", "شارع", "زنقة"}
ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9"}
# Noms français usuels des personnages qui donnent leur nom aux cités et aux rues.
EXONYMS = {"ibn sina": "avicenne", "ibn rochd": "averroes", "ibn rushd": "averroes"}
ARABIC_MARKS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")


def normalize(text: str) -> str:
    text = ARABIC_MARKS.sub("", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[’'`´\-_/.,;:()\[\]\"«»&]+", " ", text)
    return " ".join(ROMAN.get(t, t) for t in text.split())


def tokens(text: str) -> List[str]:
    norm = normalize(text)
    for name, exonym in EXONYMS.items():
        if name in norm:
            norm += " " + exonym
    return [t for t in norm.split() if t not in STOPWORDS]


def _deletes(word: str) -> Set[str]:
    return {word[:i] + word[i + 1:] for i in range(len(word))}


@dataclass
class Entry:
    name: str
    kind: str          # area, street ou poi
    type: str
    lat: float
    lon: float
    area: Optional[str]
    name_tokens: Set[str]
    area_tokens: Set[str]


@dataclass
class Index:
    entries: List[Entry] = field(default_factory=list)
    postings: Dict[str, List[int]] = field(default_factory=lambda: defaultdict(list))
    vocab: List[str] = field(default_factory=list)
    deletes: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    area_words: Set[str] = field(default_factory=set)
    generated: Optional[str] = None

    def candidates(self, token: str, prefix: bool) -> Dict[str, float]:
        """Mots du vocabulaire proches de `token`, avec une qualité de 0 à 1."""
        out: Dict[str, float] = {}
        if token in self.postings:
            out[token] = 1.0
        if prefix and len(token) >= 2:
            i = bisect.bisect_left(self.vocab, token)
            while i < len(self.vocab) and self.vocab[i].startswith(token) and len(out) < 400:
                out.setdefault(self.vocab[i], 0.85)
                i += 1
        if len(token) >= 4 and not token.isdigit():
            for variant in _deletes(token) | {token}:
                for word in self.deletes.get(variant, ()):
                    if word != token and abs(len(word) - len(token)) <= 1:
                        out.setdefault(word, 0.75)
        return out


_index = Index()


def load(path: Optional[str] = None) -> Index:
    global _index
    path = Path(path or os.environ.get("PLACES_FILE") or DEFAULT_FILE)
    index = Index()
    if not path.exists():
        logger.warning("Places file %s missing: run tools/import_places.py", path)
        _index = index
        return index
    raw = json.loads(path.read_text(encoding="utf-8"))
    index.generated = raw.get("generated")
    for i, p in enumerate(raw["places"]):
        name_tokens = set(tokens(p["n"]))
        for alt in p.get("a", []):
            name_tokens |= set(tokens(alt))
        area_tokens = set()
        for area in [p.get("area")] + p.get("area_alts", []):
            if area:
                area_tokens |= set(tokens(area))
        if not name_tokens:
            continue
        index.entries.append(Entry(p["n"], p["k"], p.get("t", ""), p["lat"], p["lon"], p.get("area"), name_tokens, area_tokens))
        n = len(index.entries) - 1
        for t in name_tokens | area_tokens:
            index.postings[t].append(n)
        if p["k"] == "area":
            index.area_words |= name_tokens
    index.vocab = sorted(index.postings)
    for word in index.vocab:
        if len(word) >= 3 and not word.isdigit():
            for variant in _deletes(word) | {word}:
                index.deletes[variant].add(word)
    logger.info("Places loaded: %d entries from %s", len(index.entries), path)
    _index = index
    return index


def current() -> Index:
    return _index


@dataclass
class Hit:
    name: str
    detail: str
    lat: float
    lon: float
    kind: str
    score: float


KIND_LABEL = {"area": "Quartier", "street": "Rue"}


def search(query: str, limit: int = 8, autocomplete: bool = False, index: Optional[Index] = None) -> List[Hit]:
    index = index or _index
    norm = normalize(query)
    words = norm.split()
    # Numéro de rue : un nombre juste avant « rue », « avenue »… (« 62 rue X »). Ailleurs, un nombre fait
    # partie du nom (« Menzah 6 », « Lac 2 »).
    number = next((w for w, nxt in zip(words, words[1:]) if w.isdigit() and len(w) <= 4 and nxt in STREET_WORDS), None)
    street_query = any(w in STREET_WORDS for w in words)
    qtokens = tokens(query)
    if number:
        qtokens.remove(number)
    if not qtokens or not index.entries:
        return []
    last = qtokens[-1]

    # Pour chaque mot de la requête : mots proches du vocabulaire et leur qualité.
    matches: List[Dict[str, float]] = [index.candidates(t, prefix=autocomplete and t == last) for t in qtokens]
    pool: Dict[int, None] = {}
    for m in matches:
        for word in m:
            for n in index.postings[word]:
                pool[n] = None
    hits: List[Hit] = []
    for n in pool:
        e = index.entries[n]
        total, name_hits, matched_name_tokens = 0.0, 0, set()
        rejected, loose_number = False, None
        for t, m in zip(qtokens, matches):
            on_name = max((q for w, q in m.items() if w in e.name_tokens), default=0.0)
            on_area = max((q for w, q in m.items() if w in e.area_tokens), default=0.0)
            if on_name >= on_area and on_name > 0:
                total += on_name
                name_hits += 1
                matched_name_tokens |= {w for w in m if w in e.name_tokens}
            elif on_area > 0:
                total += 0.6 * on_area
            elif not t.isdigit() and (t in index.area_words or t in {"tunis", "tunisie", "tunisia", "تونس"}):
                total += 0.2  # quartier ou ville mentionné, mais pas celui de ce lieu : toléré
            elif t.isdigit() and len(t) <= 4 and e.kind == "street":
                total += 0.1  # nombre qui n'est pas dans le nom d'une rue : son numéro (« Hippocrate 62 »)
                loose_number = t
            else:
                rejected = True
                break
        if rejected or name_hits == 0:
            continue
        coverage = len(matched_name_tokens & e.name_tokens) / len(e.name_tokens)
        score = total / len(qtokens) + 0.25 * coverage
        if street_query and e.kind == "street":
            score += 0.15
        if e.kind == "area" and not street_query:
            score += 0.05
        detail = e.area if e.area and normalize(e.area) != normalize(e.name) else ""
        hit_number = number or (loose_number if e.kind == "street" else None)
        hits.append(Hit(f"{hit_number} {e.name}" if hit_number and e.kind == "street" else e.name,
                        detail, e.lat, e.lon, e.kind, round(score, 4)))

    hits.sort(key=lambda h: -h.score)
    out, seen = [], set()
    for h in hits:
        key = (h.name, h.detail)
        if key in seen:
            continue
        seen.add(key)
        if h.kind == "street" and h.name[:1].isdigit():
            h = Hit(h.name, f"{h.detail} · numéro non localisé, position de la rue".lstrip(" ·"), h.lat, h.lon, h.kind, h.score)
        elif h.kind in KIND_LABEL and not h.detail:
            h = Hit(h.name, KIND_LABEL[h.kind], h.lat, h.lon, h.kind, h.score)
        out.append(h)
        if len(out) >= limit:
            break
    return out
