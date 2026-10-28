"""Index d'adresses local : fautes de frappe, numéros, noms usuels, arabe, saisie partielle."""
import json

import pytest

import geocoder
from places_fixture import PLACES


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    path = tmp_path_factory.mktemp("places") / "places.json"
    path.write_text(json.dumps(PLACES, ensure_ascii=False), encoding="utf-8")
    return geocoder.load(str(path))


def names(index, query, **kw):
    return [(h.name, h.detail) for h in geocoder.search(query, index=index, **kw)]


def test_typo_number_and_quartier_alias(index):
    # « hyppocrate » (faute), « cité Avicenne » (= Ibn Sina), numéro et ville en plus.
    assert names(index, "62 rue hyppocrate cité avicenne tunis")[0] == (
        "62 Rue Hippocrate", "Ibn Sina 1 · numéro non localisé, position de la rue")
    assert names(index, "hyppocrate 62")[0][0] == "62 Rue Hippocrate"


def test_numbers_in_names_are_not_house_numbers(index):
    assert names(index, "lac 2")[0] == ("Les Berges du Lac II", "Quartier")
    assert names(index, "menzah 6") == [("El Menzah 6", "Quartier")]


def test_autocomplete_prefix(index):
    assert names(index, "hippo", autocomplete=True)[0][0] == "Rue Hippocrate"
    assert names(index, "hippo") == []  # sans auto-complétion, un mot incomplet ne suffit pas


def test_arabic_and_typos(index):
    assert names(index, "نهج مارسيليا")[0][0] == "Rue de Marseille"
    assert names(index, "rue de marseile")[0][0] == "Rue de Marseille"
    assert names(index, "hopital charles nicole")[0][0] == "Hôpital Charles Nicolle"


def test_unknown_words_reject(index):
    assert names(index, "rue hippocrate sfax") == []
    assert names(index, "zzzz") == []


def test_normalize():
    assert geocoder.normalize("Les Berges du Lac II") == "les berges du lac 2"
    assert geocoder.normalize("Hôpital d'Enfants") == "hopital d enfants"
    assert geocoder.tokens("Cité Ibn Sina 1") == ["ibn", "sina", "1", "avicenne"]
