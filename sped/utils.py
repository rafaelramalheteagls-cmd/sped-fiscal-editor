"""
Módulo de funções utilitárias do SPED Fiscal.
Contém validação, sanitização e conversão de dados.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Validação de registro SPED (proteção SQL Injection)
# Padrão: primeiro caractere alfanumérico (bloco), seguido de 3 dígitos
REG_TYPE_PATTERN = re.compile(r'^[A-Z0-9]\d{3}$')


def validate_reg_type(reg_type: str) -> bool:
    """
    Valida se o tipo de registro é seguro para uso em SQL.
    
    Args:
        reg_type: Tipo de registro SPED (ex: "C100", "D190")
    
    Returns:
        True se válido, False caso contrário
    
    Examples:
        >>> validate_reg_type("C100")
        True
        >>> validate_reg_type("C1X0")
        False
    """
    return bool(REG_TYPE_PATTERN.match(reg_type))


def sanitize_reg_type(reg_type: str) -> str:
    """
    Sanitiza o tipo de registro, removendo caracteres inválidos e validando formato.
    
    Args:
        reg_type: Tipo de registro SPED para sanitizar
    
    Returns:
        Tipo de registro sanitizado em maiúsculas
    
    Raises:
        ValueError: Se o resultado não for um registro válido
    
    Examples:
        >>> sanitize_reg_type("c100")
        'C100'
        >>> sanitize_reg_type("  D190  ")
        'D190'
    """
    cleaned = re.sub(r'[^A-Z0-9]', '', reg_type.upper())
    if not validate_reg_type(cleaned):
        raise ValueError(f"Tipo de registro inválido: {reg_type} (resultado: {cleaned})")
    return cleaned


def parse_float(value: Optional[str]) -> float:
    """
    Converte string para float, tratando formato brasileiro.
    
    Aceita formatos:
    - "1234.56" (ponto decimal)
    - "1.234,56" (separador de milhar + vírgula decimal)
    - "1234,56" (vírgula decimal)
    - "" ou None → 0.0
    
    Args:
        value: String com valor numérico
    
    Returns:
        Valor numérico convertido para float
    
    Examples:
        >>> parse_float("1.234,56")
        1234.56
        >>> parse_float("1234.56")
        1234.56
        >>> parse_float("")
        0.0
    """
    if not value or not isinstance(value, str):
        return 0.0
    try:
        cleaned = value.strip()
        if not cleaned:
            return 0.0
        # Formato brasileiro: 1.234,56 -> remover separador de milhar, depois trocar vírgula por ponto
        if ',' in cleaned and '.' in cleaned:
            cleaned = cleaned.replace('.', '').replace(',', '.')
        elif ',' in cleaned:
            cleaned = cleaned.replace(',', '.')
        return float(cleaned)
    except (ValueError, TypeError) as e:
        logger.warning(f"Erro ao converter '{value}' para float: {e}")
        return 0.0
