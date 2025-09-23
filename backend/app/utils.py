# backend/app/utils.py

import re

def validate_gtin(gtin: str) -> bool:
    """
    Valida um código GTIN usando o algoritmo de dígito verificador.
    Função movida para cá para evitar dependências circulares.
    """
    if not gtin or not isinstance(gtin, str) or not gtin.isdigit():
        return False
    
    if len(gtin) not in [8, 12, 13, 14]:
        return False
    
    # Converte a string de dígitos para uma lista de inteiros
    digits = [int(d) for d in gtin]
    
    # Pega o dígito verificador e o corpo do código
    check_digit = digits[-1]
    body = digits[:-1]
    
    # Soma ponderada dos dígitos (da direita para a esquerda)
    weighted_sum = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    
    # Calcula o dígito verificador esperado
    expected_check_digit = (10 - (weighted_sum % 10)) % 10
    
    return check_digit == expected_check_digit