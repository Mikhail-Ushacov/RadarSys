"""
backend/app/core/ci_selector.py

Алгоритм виявлення та відбору НАЙВАЖЛИВІШИХ об'єктів критичної інфраструктури (ОКІ)
із сирих джерел даних (data/ci.json) відповідно до Закону України «Про критичну інфраструктуру».

Покриває 11 обов'язкових функціональних секторів:
1.  Паливно-енергетичний сектор (Power & Fuel)
2.  Забезпечення життєдіяльності та комунальне господарство (Life Support & Utilities)
3.  Продовольче забезпечення та агропромисловий комплекс (Food & Agro)
4.  Охорона здоров’я та фармацевтична промисловість (Healthcare & Pharma)
5.  Транспорт та логістичні вузли (Transport & Bridges)
6.  Електронні комунікації та інформаційні технології (Telecom & IT)
7.  Фінансовий сектор і ринки капіталу (Finance & Banking)
8.  Державне управління та надання публічних послуг (Government & State Registries)
9.  Хімічна промисловість (Chemical Industry & Hazardous Storage)
10. Цивільний захист та служби порятунку (Civil Defense & Emergency Services)
11. Державний матеріальний резерв та космічна діяльність (Strategic Reserves & Space)
"""

from __future__ import annotations
import math
import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

@dataclass
class CriticalityRule:
    sector_id: str
    sector_name: str
    keywords_tier1: List[str]   # Найвищий пріоритет (стратегічне значення, +50-60 балів)
    keywords_tier2: List[str]   # Високий пріоритет (+25-35 балів)
    keywords_generic: List[str] # Базові секторні ознаки (+10-15 балів)
    default_protect_radius: float

# Словник критеріїв для 11 стратегічних секторів
SECTOR_RULES: Dict[str, CriticalityRule] = {
    "energy": CriticalityRule(
        sector_id="energy",
        sector_name="Паливно-енергетичний сектор",
        keywords_tier1=[
            "гес", "гаес", "тец-5", "тец-6", "тец", "аес", "дамба", "турбін",
            "750 кв", "750кв", "330 кв", "330кв", "укренерго", "північна",
            "нафтобаз", "газорозподіл", "грс", "магістральн"
        ],
        keywords_tier2=[
            "підстанція", "пс ", "трансформатор", "дизель", "палив",
            "газопровід", "енергоблок", "електростанція", "нафтопровод"
        ],
        keywords_generic=["енерго", "електр", "паливо", "котельн"],
        default_protect_radius=2500.0
    ),
    "lifesupport": CriticalityRule(
        sector_id="lifesupport",
        sector_name="Забезпечення життєдіяльності та комунальне господарство",
        keywords_tier1=[
            "водопровідна станція", "київводоканал", "деснянська водопровідна",
            "дніпровська водопровідна", "бортницька станція аерації", "бса",
            "завод «енергія»", "завод енергія", "водозабір"
        ],
        keywords_tier2=[
            "водоканал", "очисні споруди", "насосна станція", "колектор",
            "сміттєспалювальн", "водопостачання", "водовідведення"
        ],
        keywords_generic=["вода", "комунальн", "очисн", "скважин"],
        default_protect_radius=2200.0
    ),
    "food_agro": CriticalityRule(
        sector_id="food_agro",
        sector_name="Продовольче забезпечення та АПК",
        keywords_tier1=[
            "хлібокомбінат", "київхліб", "хлібозавод", "зерносховище",
            "стратегічний елеватор", "агрологістичний"
        ],
        keywords_tier2=["елеватор", "млин", "холодокомбінат", "харчов", "склад продукт"],
        keywords_generic=["хліб", "зерно", "продоволь", "агро"],
        default_protect_radius=1800.0
    ),
    "healthcare": CriticalityRule(
        sector_id="healthcare",
        sector_name="Охорона здоров’я та фармацевтика",
        keywords_tier1=[
            "охматдит", "шалімов", "інститут серця", "інститут хірургії",
            "дарниця фарм", "фармак", "центр екстреної медичної", "банк кров"
        ],
        keywords_tier2=[
            "клінічна лікарня", "госпіталь", "фармацевтичн", "реанімація",
            "онкоцентр", "травматолог", "швидка допомога"
        ],
        keywords_generic=["лікарня", "медичн", "фарм", "поліклініка"],
        default_protect_radius=1900.0
    ),
    "transport": CriticalityRule(
        sector_id="transport",
        sector_name="Транспортна інфраструктура та логістика",
        keywords_tier1=[
            "київ-пасажирський", "дарниця вузол", "жуляни", "бориспіль",
            "південний міст", "північний міст", "петрівський міст", "дарницький міст",
            "міст патона", "міст метро", "річковий порт", "шлюз"
        ],
        keywords_tier2=[
            "вокзал", "аеродром", "сортувальна", "укрзалізниця",
            "депо метро", "тягова підстанція", "шляхопровід"
        ],
        keywords_generic=["міст", "залізниц", "аеропорт", "станція", "термінал"],
        default_protect_radius=2200.0
    ),
    "telecom_it": CriticalityRule(
        sector_id="telecom_it",
        sector_name="Електронні комунікації та ІТ",
        keywords_tier1=[
            "телевежа", "радіотелецентр", "сирець телевежа", "парковий",
            "ua-ix", "gigacenter", "спецзв'язок", "держспецзв'язок"
        ],
        keywords_tier2=[
            "дата-центр", "цод", "точка обміну", "вузол зв'язку",
            "магістральний інтернет", "релейн"
        ],
        keywords_generic=["телекомунікаці", "зв'язок", "сервер", "провайдер"],
        default_protect_radius=1700.0
    ),
    "finance": CriticalityRule(
        sector_id="finance",
        sector_name="Фінансовий сектор та ринки капіталу",
        keywords_tier1=[
            "національний банк", "нбу", "центральне сховище нбу",
            "банкнотно-монетний", "сеп нбу", "державна скарбниця"
        ],
        keywords_tier2=["казначейство", "розрахунковий центр", "монетарн", "процесинг"],
        keywords_generic=["банк", "скарбниц", "платіжн"],
        default_protect_radius=1600.0
    ),
    "government": CriticalityRule(
        sector_id="government",
        sector_name="Державне управління та публічні послуги",
        keywords_tier1=[
            "урядовий квартал", "кабінет міністрів", "верховна рада", "офіс президента",
            "генштаб", "ситуаційний центр", "головний обчислювальний центр", "державні реєстри"
        ],
        keywords_tier2=[
            "міністерство", "міськрада", "крда", "ситуаційн",
            "державний реєстр", "відомств"
        ],
        keywords_generic=["управління", "адміністрація", "державн"],
        default_protect_radius=2000.0
    ),
    "chemical": CriticalityRule(
        sector_id="chemical",
        sector_name="Хімічна промисловість",
        keywords_tier1=[
            "рідкий хлор", "хлорне сховище", "склад хлору", "аміакопровід",
            "небезпечна хімія", "інститут хімічних"
        ],
        keywords_tier2=[
            "хімічний завод", "склад кислот", "аміак", "отруйні речовини",
            "промислові реагенти"
        ],
        keywords_generic=["хімічн", "хлор", "реагент", "добрив"],
        default_protect_radius=2000.0
    ),
    "civil_defense": CriticalityRule(
        sector_id="civil_defense",
        sector_name="Цивільний захист та служби порятунку",
        keywords_tier1=[
            "гу дснс", "оперативно-координаційний центр", "мобільний рятувальний центр",
            "мрц шр", "центр управління в надзвичайних"
        ],
        keywords_tier2=[
            "дснс", "пожежно-рятувальна частина", "рятувальна станція",
            "аварійно-рятувальний", "цивільний захист"
        ],
        keywords_generic=["пожежн", "рятувальн", "дснс", "безпека"],
        default_protect_radius=1800.0
    ),
    "space_reserve": CriticalityRule(
        sector_id="space_reserve",
        sector_name="Держрезерв та космічна діяльність",
        keywords_tier1=[
            "держрезерв", "комбінат «рекорд»", "комбінат рекорд",
            "нцувкз", "центр космічних засобів", "управління космічними"
        ],
        keywords_tier2=[
            "матеріальний резерв", "стратегічний склад", "космічний зв'язок",
            "супутниковий моніторинг"
        ],
        keywords_generic=["резерв", "космос", "супутник"],
        default_protect_radius=2100.0
    )
}


class CriticalInfrastructureSelector:
    """
    Алгоритм багатофакторного оцінювання та відбору найбільш пріоритетних об'єктів
    критичної інфраструктури:
    1. Нормалізація джерел (GeoJSON, Flat JSON, OSM-експорти).
    2. Семантична категоризація за 11 державними секторами.
    3. Розрахунок Score критичності (0 - 100).
    4. Просторове дедуплікування (Spatial NMS) для уникнення нагромадження однакових точок.
    5. Гарантоване секторне квотування (топ-об'єкти для кожного сектору).
    """

    @staticmethod
    def extract_raw_items(raw_data: Any) -> List[Dict[str, Any]]:
        """Конвертує будь-яку структуру JSON у стандартизований список записів."""
        if not raw_data:
            return []

        # Випадок 1: GeoJSON FeatureCollection
        if isinstance(raw_data, dict) and raw_data.get("type") == "FeatureCollection":
            features = raw_data.get("features", [])
            items = []
            for f in features:
                geom = f.get("geometry", {})
                props = f.get("properties", {})
                coords = geom.get("coordinates")
                if not coords or len(coords) < 2:
                    continue
                # GeoJSON coordinates: [lon, lat, (alt)]
                lon, lat = float(coords[0]), float(coords[1])
                alt = float(coords[2]) if len(coords) > 2 else 0.0
                name = props.get("name") or props.get("title") or props.get("description") or "Безіменний об'єкт"
                items.append({
                    "name": str(name),
                    "lat": lat,
                    "lon": lon,
                    "alt": alt,
                    "radius": props.get("radius") or props.get("detection_radius"),
                    "description": props.get("description") or props.get("sector") or "",
                    "tags": props
                })
            return items

        # Випадок 2: Обгорнутий список (items / objects / elements)
        if isinstance(raw_data, dict):
            for key in ["items", "objects", "elements", "data"]:
                if key in raw_data and isinstance(raw_data[key], list):
                    raw_data = raw_data[key]
                    break

        if isinstance(raw_data, list):
            items = []
            for entry in raw_data:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name") or entry.get("title") or entry.get("label")
                lat = entry.get("lat") or entry.get("latitude")
                lon = entry.get("lon") or entry.get("lng") or entry.get("longitude")
                if lat is None or lon is None or not name:
                    continue
                items.append({
                    "name": str(name).strip(),
                    "lat": float(lat),
                    "lon": float(lon),
                    "alt": float(entry.get("alt", 0.0)),
                    "radius": entry.get("radius") or entry.get("detection_radius"),
                    "description": str(entry.get("description") or entry.get("sector") or entry.get("type") or ""),
                    "tags": entry
                })
            return items

        return []

    @classmethod
    def evaluate_entry(cls, entry: Dict[str, Any]) -> Tuple[str, str, float, float]:
        """
        Аналізує об'єкт та повертає:
        (sector_id, sector_name, criticality_score, recommended_protect_radius)
        """
        text_corpus = f"{entry['name']} {entry.get('description', '')}".lower()

        best_sector = "other"
        best_sector_name = "Загальна інфраструктура"
        best_score = 5.0
        best_radius = 1800.0

        for s_id, rule in SECTOR_RULES.items():
            score = 0.0

            # Перевірка Tier 1 (стратегічні об'єкти вищого рангу)
            for kw in rule.keywords_tier1:
                if kw in text_corpus:
                    score += 55.0
                    break

            # Перевірка Tier 2
            for kw in rule.keywords_tier2:
                if kw in text_corpus:
                    score += 25.0
                    break

            # Перевірка загальних слів
            for kw in rule.keywords_generic:
                if kw in text_corpus:
                    score += 10.0
                    break

            # Додаткові критерії напруги для енергомереж (750кВ / 330кВ мають пріоритет)
            if s_id == "energy":
                if "750" in text_corpus: score += 20.0
                elif "330" in text_corpus: score += 12.0
                elif "тец" in text_corpus or "гес" in text_corpus: score += 15.0

            # Мости через річку Дніпро — стратегічні транспортні артерії
            if s_id == "transport" and ("міст" in text_corpus or "шлюз" in text_corpus):
                score += 18.0

            if score > best_score:
                best_score = score
                best_sector = s_id
                best_sector_name = rule.sector_name
                best_radius = rule.default_protect_radius

        final_score = min(100.0, max(5.0, best_score))
        return best_sector, best_sector_name, final_score, best_radius

    @classmethod
    def select_top_critical_assets(
        cls,
        raw_data: Any,
        target_total_count: int = 35,
        min_distance_between_same_sector_m: float = 600.0
    ) -> List[Dict[str, Any]]:
        """
        Головна функція відбору НАЙВАЖЛИВІШИХ об'єктів:
        - Класифікує всі об'єкти за 11 секторами.
        - Відсіює низькопріоритетні та дублікати.
        - Гарантує збалансовану присутність кожного сектору.
        """
        items = cls.extract_raw_items(raw_data)
        if not items:
            return []

        sector_buckets: Dict[str, List[Dict[str, Any]]] = {s: [] for s in SECTOR_RULES}
        sector_buckets["other"] = []

        for item in items:
            s_id, s_name, score, rec_radius = cls.evaluate_entry(item)
            item_radius = float(item.get("radius") or rec_radius)

            desc = item.get("description", "").strip()
            sector_tag = f"Сектор: {s_name}."
            if sector_tag not in desc:
                desc = f"{sector_tag} {desc}".strip()

            processed = {
                "name": item["name"],
                "lat": item["lat"],
                "lon": item["lon"],
                "alt": item.get("alt", 0.0),
                "radius": item_radius,
                "description": desc,
                "sector_id": s_id,
                "sector_name": s_name,
                "criticality_score": score
            }
            if s_id in sector_buckets:
                sector_buckets[s_id].append(processed)
            else:
                sector_buckets["other"].append(processed)

        # Сортуємо об'єкти всередині кожного сектору за спаданням критичності
        for s_id in sector_buckets:
            sector_buckets[s_id].sort(key=lambda x: x["criticality_score"], reverse=True)

        selected: List[Dict[str, Any]] = []

        def is_too_close(candidate: Dict[str, Any], existing_list: List[Dict[str, Any]]) -> bool:
            """Просторова фільтрація для уникнення точок в радіусі min_dist."""
            c_lat, c_lon = candidate["lat"], candidate["lon"]
            for ex in existing_list:
                # Швидка перевірка декартової відстані в метрах
                d_lat = (c_lat - ex["lat"]) * 111132.954
                d_lon = (c_lon - ex["lon"]) * 111412.84 * math.cos(math.radians(c_lat))
                dist = math.hypot(d_lat, d_lon)
                if dist < min_distance_between_same_sector_m and candidate["sector_id"] == ex["sector_id"]:
                    return True
            return False

        # Фаза 1: Гарантоване секторне квотування (топ 2-3 об'єкти з кожного з 11 секторів)
        for s_id in SECTOR_RULES:
            bucket = sector_buckets[s_id]
            added_for_sector = 0
            for cand in bucket:
                if not is_too_close(cand, selected):
                    selected.append(cand)
                    added_for_sector += 1
                    if added_for_sector >= 2:
                        break

        # Фаза 2: Добирання найвищих балів серед усіх секторів до target_total_count
        remaining_pool = []
        for s_id in sector_buckets:
            for item in sector_buckets[s_id]:
                if item not in selected:
                    remaining_pool.append(item)

        remaining_pool.sort(key=lambda x: x["criticality_score"], reverse=True)

        for cand in remaining_pool:
            if len(selected) >= target_total_count:
                break
            if not is_too_close(cand, selected):
                selected.append(cand)

        return selected