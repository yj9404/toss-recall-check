"""카테고리 코드와 출처 기관 라벨."""

CATEGORIES: dict[str, str] = {
    "food": "식품",
    "cosmetic": "화장품",
    "consumer_product": "공산품",
    "overseas": "해외",
    "medicine": "의약품",
    "medical_device": "의료기기",
    "drinking_water": "먹는물",
    "vehicle": "자동차",
}

# vehicle은 노출 정책 확인 전이라 기본값에서 뺀다.
DEFAULT_ENABLED_CATEGORIES = tuple(c for c in CATEGORIES if c != "vehicle")

# 공정위 리콜정보에서 인스턴스화할 카테고리 (ftc_<category>).
FTC_CATEGORIES = ("medicine", "medical_device", "drinking_water", "vehicle")

SOURCE_LABELS: dict[str, str] = {
    "foodsafety_i0490": "식품의약품안전처 식품안전나라",
    # TODO: 아래 라벨은 명세 확정 시 기관 표기를 다시 확인한다.
    "kats": "국가기술표준원",
    "mfds_cosmetic": "식품의약품안전처",
    **{f"ftc_{c}": "공정거래위원회" for c in FTC_CATEGORIES},
}


def category_label(code: str) -> str:
    return CATEGORIES.get(code, code)


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)
