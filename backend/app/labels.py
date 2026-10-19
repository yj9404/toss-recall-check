"""카테고리 코드와 출처 기관 라벨."""

# 정의 순서가 /categories 응답(프런트엔드 탭) 순서다.
CATEGORIES: dict[str, str] = {
    "food": "식품",
    "cosmetic": "화장품",
    "consumer_product": "공산품",
    "overseas": "해외",
    "medicine": "의약품",
    "medical_device": "의료기기",
    "drinking_water": "먹는물",
    "vehicle": "자동차",
    "quasi_drug": "의약외품",
    "household_chemical": "생활화학제품",
    "hygiene_product": "위생용품",
    "radiation_product": "생활방사선제품",
}

DEFAULT_ENABLED_CATEGORIES = tuple(CATEGORIES)

# 레코드에 source_label이 없을 때 쓰는 출처별 기본 라벨.
SOURCE_LABELS: dict[str, str] = {
    "foodsafety_i0490": "식품의약품안전처 식품안전나라",
}


def category_label(code: str) -> str:
    return CATEGORIES.get(code, code)


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)
