"""Validações de documentos e endereços brasileiros.

CNPJ: aceita o formato numérico e o alfanumérico (emitido pela Receita Federal
desde julho de 2026: 12 posições com letras ou números e 2 dígitos
verificadores numéricos). O cálculo é o mesmo módulo 11, com cada caractere
valendo ``código ASCII - 48`` (``0``-``9`` = 0-9, ``A`` = 17 ... ``Z`` = 42).
"""

import re

UFS = [
    "AC",
    "AL",
    "AP",
    "AM",
    "BA",
    "CE",
    "DF",
    "ES",
    "GO",
    "MA",
    "MT",
    "MS",
    "MG",
    "PA",
    "PB",
    "PR",
    "PE",
    "PI",
    "RJ",
    "RN",
    "RS",
    "RO",
    "RR",
    "SC",
    "SP",
    "SE",
    "TO",
]


def only_alnum(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", value).upper()


def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _check_digit(values: list[int], weights: list[int]) -> int:
    remainder = sum(v * w for v, w in zip(values, weights, strict=True)) % 11
    return 0 if remainder < 2 else 11 - remainder


def valid_cpf(value: str) -> bool:
    digits = only_digits(value)
    if len(digits) != 11 or digits == digits[0] * 11:
        return False
    numbers = [int(d) for d in digits]
    first = _check_digit(numbers[:9], list(range(10, 1, -1)))
    second = _check_digit(numbers[:10], list(range(11, 1, -1)))
    return numbers[9] == first and numbers[10] == second


def valid_cnpj(value: str) -> bool:
    raw = only_alnum(value)
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", raw) or raw == raw[0] * 14:
        return False
    values = [ord(char) - 48 for char in raw]
    first = _check_digit(values[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = _check_digit(values[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return values[12] == first and values[13] == second


def format_document(person_type: str, document: str) -> str:
    raw = only_alnum(document)
    if person_type == "pf":
        return f"{raw[:3]}.{raw[3:6]}.{raw[6:9]}-{raw[9:]}"
    return f"{raw[:2]}.{raw[2:5]}.{raw[5:8]}/{raw[8:12]}-{raw[12:]}"
