"""
Módulo de Dashboard do SPED Fiscal.
Fornece dados processados para a aba de visão geral.
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

import pandas as pd

from .models import SpedSummaryData, VALID_RECORD_TYPES, ENTRADA_CFOPS_PREFIX
from .utils import parse_float

logger = logging.getLogger(__name__)


@dataclass
class DashboardData:
    """Dados processados para o Dashboard"""
    # Resumo geral
    total_registros: int = 0
    tipos_registro: int = 0
    periodo_inicio: str = ""
    periodo_fim: str = ""
    razao_social: str = ""
    cnpj: str = ""
    
    # Totais financeiros
    total_entradas: float = 0.0
    total_saidas: float = 0.0
    total_icms_entradas: float = 0.0
    total_icms_saidas: float = 0.0
    total_pis_entradas: float = 0.0
    total_pis_saidas: float = 0.0
    total_cofins_entradas: float = 0.0
    total_cofins_saidas: float = 0.0
    
    # Top CFOPs
    top_cfops_entrada: List[Tuple[str, float]] = None
    top_cfops_saida: List[Tuple[str, float]] = None
    
    # Distribuição por bloco
    registros_por_bloco: Dict[str, int] = None
    
    # Consistência
    erros_validacao: List[str] = None
    
    def __post_init__(self):
        if self.top_cfops_entrada is None:
            self.top_cfops_entrada = []
        if self.top_cfops_saida is None:
            self.top_cfops_saida = []
        if self.registros_por_bloco is None:
            self.registros_por_bloco = {}
        if self.erros_validacao is None:
            self.erros_validacao = []


def extract_header_info(file_path: str) -> Dict[str, str]:
    """
    Extrai informações do cabeçalho SPED (registro 0000).
    
    Args:
        file_path: Caminho do arquivo SPED
    
    Returns:
        Dicionário com informações do cabeçalho
    """
    info = {
        'razao_social': '',
        'cnpj': '',
        'periodo_inicio': '',
        'periodo_fim': '',
        'uf': '',
        'cod_ver': ''
    }
    
    try:
        for enc in ['utf-8', 'latin-1']:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    for line in f:
                        fields = line.strip().split('|')
                        if len(fields) > 6 and fields[1] == '0000':
                            info['cod_ver'] = fields[2] if len(fields) > 2 else ''
                            info['periodo_inicio'] = fields[4] if len(fields) > 4 else ''
                            info['periodo_fim'] = fields[5] if len(fields) > 5 else ''
                            info['razao_social'] = fields[6] if len(fields) > 6 else ''
                            info['cnpj'] = fields[7] if len(fields) > 7 else ''
                            info['uf'] = fields[9] if len(fields) > 9 else ''
                            return info
                break
            except UnicodeDecodeError:
                continue
    except Exception as e:
        logger.warning(f"Erro ao extrair cabeçalho: {e}")
    
    return info


def count_records_by_block(file_path: str) -> Dict[str, int]:
    """
    Conta registros por bloco (0, C, D, E, H, 1, 9).
    
    Args:
        file_path: Caminho do arquivo SPED
    
    Returns:
        Dicionário com contagem por bloco
    """
    counts: Dict[str, int] = defaultdict(int)
    
    try:
        for enc in ['utf-8', 'latin-1']:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    for line in f:
                        fields = line.strip().split('|')
                        if len(fields) > 1:
                            reg_type = fields[1]
                            if reg_type:
                                block = reg_type[0]
                                counts[block] += 1
                break
            except UnicodeDecodeError:
                continue
    except Exception as e:
        logger.warning(f"Erro ao contar registros: {e}")
    
    return dict(counts)


def get_top_cfops(file_path: str, limit: int = 10) -> Tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
    """
    Retorna os top CFOPs por valor de operação.
    
    Args:
        file_path: Caminho do arquivo SPED
        limit: Número de CFOPs a retornar
    
    Returns:
        Tuple com (top_entrada, top_saida)
    """
    cfop_entradas: Dict[str, float] = defaultdict(float)
    cfop_saidas: Dict[str, float] = defaultdict(float)
    
    try:
        for enc in ['utf-8', 'latin-1']:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    for line in f:
                        fields = line.strip().split('|')
                        if len(fields) > 7 and fields[1] in VALID_RECORD_TYPES:
                            cfop = fields[3]
                            valor = parse_float(fields[5])
                            if cfop.startswith(ENTRADA_CFOPS_PREFIX):
                                cfop_entradas[cfop] += valor
                            else:
                                cfop_saidas[cfop] += valor
                break
            except UnicodeDecodeError:
                continue
    except Exception as e:
        logger.warning(f"Erro ao extrair top CFOPs: {e}")
    
    top_entrada = sorted(cfop_entradas.items(), key=lambda x: x[1], reverse=True)[:limit]
    top_saida = sorted(cfop_saidas.items(), key=lambda x: x[1], reverse=True)[:limit]
    
    return top_entrada, top_saida


def calculate_financial_summary(file_path: str) -> Dict[str, float]:
    """
    Calcula resumo financeiro do SPED.
    
    Args:
        file_path: Caminho do arquivo SPED
    
    Returns:
        Dicionário com totais financeiros
    """
    summary = {
        'total_entradas': 0.0,
        'total_saidas': 0.0,
        'total_icms_entradas': 0.0,
        'total_icms_saidas': 0.0,
        'qtd_notas_entradas': 0,
        'qtd_notas_saidas': 0,
    }
    
    try:
        for enc in ['utf-8', 'latin-1']:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    for line in f:
                        fields = line.strip().split('|')
                        if len(fields) < 3:
                            continue
                        
                        reg_type = fields[1]
                        
                        # Registros C100/D100 (totais de documentos)
                        if reg_type in ('C100', 'D100'):
                            ind_oper = fields[2] if len(fields) > 2 else ''
                            vl_doc = parse_float(fields[11]) if len(fields) > 11 else 0.0
                            vl_icms = parse_float(fields[20]) if len(fields) > 20 else 0.0
                            
                            if ind_oper == '0':  # Entrada
                                summary['total_entradas'] += vl_doc
                                summary['total_icms_entradas'] += vl_icms
                                summary['qtd_notas_entradas'] += 1
                            else:  # Saída
                                summary['total_saidas'] += vl_doc
                                summary['total_icms_saidas'] += vl_icms
                                summary['qtd_notas_saidas'] += 1
                break
            except UnicodeDecodeError:
                continue
    except Exception as e:
        logger.warning(f"Erro ao calcular resumo financeiro: {e}")
    
    return summary


def generate_dashboard_data(file_path: str) -> DashboardData:
    """
    Gera dados completos para o Dashboard.
    
    Args:
        file_path: Caminho do arquivo SPED
    
    Returns:
        DashboardData com todas as métricas
    """
    data = DashboardData()
    
    # Extrair informações do cabeçalho
    header = extract_header_info(file_path)
    data.razao_social = header.get('razao_social', '')
    data.cnpj = header.get('cnpj', '')
    data.periodo_inicio = header.get('periodo_inicio', '')
    data.periodo_fim = header.get('periodo_fim', '')
    
    # Contar registros
    data.registros_por_bloco = count_records_by_block(file_path)
    data.total_registros = sum(data.registros_por_bloco.values())
    data.tipos_registro = len(data.registros_por_bloco)
    
    # Top CFOPs
    data.top_cfops_entrada, data.top_cfops_saida = get_top_cfops(file_path)
    
    # Resumo financeiro
    financial = calculate_financial_summary(file_path)
    data.total_entradas = financial['total_entradas']
    data.total_saidas = financial['total_saidas']
    data.total_icms_entradas = financial['total_icms_entradas']
    data.total_icms_saidas = financial['total_icms_saidas']
    
    # Validações básicas
    data.erros_validacao = _run_basic_validations(file_path)
    
    logger.info(f"Dashboard gerado: {data.total_registros} registros, {data.tipos_registro} tipos")
    return data


def _run_basic_validations(file_path: str) -> List[str]:
    """
    Executa validações básicas no arquivo SPED.
    
    Args:
        file_path: Caminho do arquivo SPED
    
    Returns:
        Lista de erros encontrados
    """
    errors = []
    
    try:
        has_0000 = False
        has_9999 = False
        has_c100 = False
        
        for enc in ['utf-8', 'latin-1']:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    for line in f:
                        fields = line.strip().split('|')
                        if len(fields) > 1:
                            reg = fields[1]
                            if reg == '0000':
                                has_0000 = True
                            elif reg == '9999':
                                has_9999 = True
                            elif reg == 'C100':
                                has_c100 = True
                break
            except UnicodeDecodeError:
                continue
        
        if not has_0000:
            errors.append("Registro 0000 (Cabeçalho) não encontrado")
        if not has_9999:
            errors.append("Registro 9999 (Rodapé) não encontrado")
        if not has_c100:
            errors.append("Nenhum registro C100 (Documento Fiscal) encontrado")
            
    except Exception as e:
        errors.append(f"Erro ao validar arquivo: {str(e)}")
    
    return errors
