"""
Módulo de modelos de dados do SPED Fiscal.
Contém estruturas de dados, constantes e metadados.
"""

from typing import Dict, List, DefaultDict, Tuple
from collections import defaultdict
from dataclasses import dataclass, field

# ============================================================================
# CONSTANTES
# ============================================================================
ENCODINGS: List[str] = ['utf-8', 'latin-1', 'iso-8859-1']
VALID_RECORD_TYPES: Tuple[str, ...] = ('C190', 'C590', 'D190', 'D590')
ENTRADA_CFOPS_PREFIX: Tuple[str, ...] = ('1', '2', '3')
PDF_FONT_SIZE: int = 10

# Índices dos campos SPED para análise de CFOPs
C100_NUM_DOC_IDX: int = 8
C500_NUM_DOC_IDX: int = 10  # NUM_DOC no C500 (campo 10)
D100_NUM_DOC_IDX: int = 9
D500_NUM_DOC_IDX: int = 9  # NUM_DOC no D500 (campo 8 = índice 9, após SUB)
C190_CFOP_IDX: int = 3
C190_ALIQ_ICMS_IDX: int = 4
C190_VL_OPR_IDX: int = 5
C190_VL_BC_ICMS_IDX: int = 6
C190_VL_ICMS_IDX: int = 7
# Índices para C590 e D590 (mesma estrutura do C190)
C590_CFOP_IDX: int = 3  # Campo 2 (índice 3, após |vazio|REG|CST|)
C590_VL_OPR_IDX: int = 5  # Campo 4 (índice 5)
D590_CFOP_IDX: int = 3  # Campo 2 (índice 3)
D590_VL_OPR_IDX: int = 5  # Campo 4 (índice 5)

# ============================================================================
# MAPEAMENTO DE CAMPOS SPED (METADADOS)
# ============================================================================
SPED_LAYOUT: Dict[str, List[str]] = {
    '0000': ['COD_VER', 'COD_FIN', 'DT_INI', 'DT_FIN', 'NOME', 'CNPJ', 'CPF', 'UF', 'IE', 'COD_MUN', 'IM', 'SUFRAMA', 'IND_PERFIL', 'IND_ATIV'],
    '0001': ['IND_MOV'],
    '0005': ['FANTASIA', 'CEP', 'END', 'NUM', 'COMPL', 'BAIRRO', 'FONE', 'FAX', 'EMAIL'],
    '0100': ['NOME', 'CPF', 'CRC', 'CNPJ', 'CEP', 'END', 'NUM', 'COMPL', 'BAIRRO', 'FONE', 'FAX', 'EMAIL', 'COD_MUN'],
    '0150': ['COD_PART', 'NOME', 'COD_PAIS', 'CNPJ', 'CPF', 'IE', 'COD_MUN', 'SUFRAMA', 'END', 'NUM', 'COMPL', 'BAIRRO'],
    '0175': ['DT_ALT', 'NR_CAMPO', 'CONT_ANT'],
    '0190': ['UNID', 'DESCR'],
    '0200': ['COD_ITEM', 'DESCR_ITEM', 'COD_BARRA', 'COD_ANT_ITEM', 'UNID_INV', 'TIPO_ITEM', 'COD_NCM', 'EX_IPI', 'COD_GEN', 'COD_LST', 'ALIQ_ICMS', 'CEST'],
    '0205': ['DESCR_ANT_ITEM', 'DT_INI', 'DT_FIN', 'COD_ANT_ITEM'],
    '0206': ['COD_COMB'],
    '0220': ['UNID_CONV', 'FAT_CONV'],
    '0400': ['COD_NAT', 'DESCR_NAT'],
    '0450': ['COD_INF', 'TXT'],
    '0460': ['COD_OBS', 'TXT'],
    'C001': ['IND_MOV'],
    'C100': ['IND_OPER', 'IND_EMIT', 'COD_PART', 'COD_MOD', 'COD_SIT', 'SER', 'NUM_DOC', 'CHV_NFE', 'DT_DOC', 'DT_E_S', 'VL_DOC', 'IND_PGTO', 'VL_DESC', 'VL_ABAT_NT', 'VL_MERC', 'IND_FRT', 'VL_FRT', 'VL_SEG', 'VL_OUT_DA', 'VL_BC_ICMS', 'VL_ICMS', 'VL_BC_ICMS_ST', 'VL_ICMS_ST', 'VL_IPI', 'VL_PIS', 'VL_COFINS', 'VL_PIS_ST', 'VL_COFINS_ST'],
    'C101': ['VL_FCP_UF_DEST', 'VL_ICMS_UF_DEST', 'VL_ICMS_UF_REM'],
    'C110': ['COD_INF', 'TXT_COMPL'],
    'C113': ['IND_OPER', 'IND_EMIT', 'COD_PART', 'COD_MOD', 'SER', 'SUB', 'NUM_DOC', 'DT_DOC', 'CHV_DOCe'],
    'C120': ['COD_DOC_IMP', 'NUM_DOC_IMP', 'PIS_IMP', 'COFINS_IMP', 'NUM_ACDRAW'],
    'C170': ['NUM_ITEM', 'COD_ITEM', 'DESCR_COMPL', 'QTD', 'UNID', 'VL_ITEM', 'VL_DESC', 'IND_MOV', 'CST_ICMS', 'CFOP', 'COD_NAT', 'VL_BC_ICMS', 'ALIQ_ICMS', 'VL_ICMS', 'VL_BC_ICMS_ST', 'ALIQ_ST', 'VL_ICMS_ST', 'IND_APUR', 'CST_IPI', 'COD_ENQ', 'VL_BC_IPI', 'ALIQ_IPI', 'VL_IPI', 'CST_PIS', 'VL_BC_PIS', 'ALIQ_PIS', 'QUANT_BC_PIS', 'ALIQ_PIS_REAIS', 'VL_PIS', 'CST_COFINS', 'VL_BC_COFINS', 'ALIQ_COFINS', 'QUANT_BC_COFINS', 'ALIQ_COFINS_REAIS', 'VL_COFINS', 'COD_CTA'],
    'C190': ['CST_ICMS', 'CFOP', 'ALIQ_ICMS', 'VL_OPR', 'VL_BC_ICMS', 'VL_ICMS', 'VL_BC_ICMS_ST', 'VL_ICMS_ST', 'VL_RED_BC', 'VL_IPI', 'COD_OBS'],
    'C195': ['COD_OBS', 'TXT_COMPL'],
    'C197': ['COD_AJ', 'DESCR_COMPL_AJ', 'COD_ITEM', 'VL_BC_ICMS', 'ALIQ_ICMS', 'VL_ICMS', 'VL_OUTROS'],
    'C500': ['IND_OPER', 'IND_EMIT', 'COD_PART', 'COD_MOD', 'COD_SIT', 'SER', 'SUB', 'COD_CONS', 'NUM_DOC', 'DT_DOC', 'DT_E_S', 'VL_DOC', 'VL_DESC', 'VL_FORN', 'VL_SERV_NT', 'VL_TERC', 'VL_DA', 'VL_BC_ICMS', 'VL_ICMS', 'VL_BC_ICMS_ST', 'VL_ICMS_ST', 'COD_GRP_TEN', 'VL_PIS', 'VL_COFINS', 'TP_LIGACAO', 'COD_GRUPO_TENSAO'],
    'C510': ['NUM_ITEM', 'COD_ITEM', 'COD_CLASS', 'QTD', 'UNID', 'VL_ITEM', 'VL_DESC', 'CST_ICMS', 'CFOP', 'VL_BC_ICMS', 'ALIQ_ICMS', 'VL_ICMS', 'VL_BC_ICMS_ST', 'ALIQ_ICMS_ST', 'VL_ICMS_ST', 'VL_PIS', 'VL_COFINS', 'COD_CTA'],
    'C590': ['CST_ICMS', 'CFOP', 'ALIQ_ICMS', 'VL_OPR', 'VL_BC_ICMS', 'VL_ICMS', 'VL_BC_ICMS_ST', 'VL_ICMS_ST', 'VL_RED_BC', 'COD_OBS'],
    'D001': ['IND_MOV'],
    'D100': ['IND_OPER', 'IND_EMIT', 'COD_PART', 'COD_MOD', 'COD_SIT', 'SER', 'SUB', 'NUM_DOC', 'CHV_CTE', 'DT_DOC', 'DT_A_P', 'TP_CT_E', 'CHV_CTE_REF', 'VL_DOC', 'VL_DESC', 'IND_FRT', 'VL_SERV', 'VL_BC_ICMS', 'VL_ICMS', 'VL_NT', 'COD_INF', 'COD_CTA', 'COD_MUN_ORIG', 'COD_MUN_DEST'],
    'D110': ['NUM_ITEM', 'COD_ITEM', 'VL_SERV', 'VL_OUT'],
    'D190': ['CST_ICMS', 'CFOP', 'ALIQ_ICMS', 'VL_OPR', 'VL_BC_ICMS', 'VL_ICMS', 'VL_RED_BC', 'COD_OBS'],
    'D500': ['IND_OPER', 'IND_EMIT', 'COD_PART', 'COD_MOD', 'COD_SIT', 'SER', 'SUB', 'NUM_DOC', 'DT_DOC', 'DT_A_P', 'VL_DOC', 'VL_DESC', 'VL_SERV', 'VL_SERV_NT', 'VL_TERC', 'VL_DA', 'VL_BC_ICMS', 'VL_ICMS', 'COD_INF', 'VL_PIS', 'VL_COFINS', 'COD_DA', 'TP_ASSINANTE'],
    'D510': ['NUM_ITEM', 'COD_ITEM', 'COD_CLASS', 'QTD', 'UNID', 'VL_ITEM', 'VL_DESC', 'CST_ICMS', 'CFOP', 'VL_BC_ICMS', 'ALIQ_ICMS', 'VL_ICMS', 'VL_BC_ICMS_ST', 'ALIQ_ICMS_ST', 'VL_ICMS_ST', 'VL_PIS', 'VL_COFINS', 'COD_CTA'],
    'D590': ['CST_ICMS', 'CFOP', 'ALIQ_ICMS', 'VL_OPR', 'VL_BC_ICMS', 'VL_ICMS', 'VL_RED_BC', 'COD_OBS'],
    'E001': ['IND_MOV'],
    'E100': ['DT_INI', 'DT_FIN'],
    'E110': ['VL_TOT_DEBITOS', 'VL_AJ_DEBITOS', 'VL_TOT_AJ_DEBITOS', 'VL_ESTORNOS_CRED', 'VL_TOT_CREDITOS', 'VL_AJ_CREDITOS', 'VL_TOT_AJ_CREDITOS', 'VL_ESTORNOS_DEB', 'VL_SLD_CREDOR_ANT', 'VL_SLD_APURADO', 'VL_TOT_DED', 'VL_ICMS_RECOLHER', 'VL_SLD_CREDOR_TRANSPORTAR', 'DEB_ESP'],
    'E111': ['COD_AJ_APUR', 'DESCR_COMPL_AJ', 'VL_AJ_APUR'],
    'E200': ['UF', 'DT_INI', 'DT_FIN'],
    'E210': ['IND_MOV_ST', 'VL_SLD_CRED_ANT_ST', 'VL_DEVOL_ST', 'VL_RESSARC_ST', 'VL_OUT_CRED_ST', 'VL_AJ_CREDITOS_ST', 'VL_RETENÇAO_ST', 'VL_OUT_DEB_ST', 'VL_AJ_DEBITOS_ST', 'VL_SLD_DEV_ANT_ST', 'VL_DEDUÇÕES_ST', 'VL_ICMS_RECOL_ST', 'VL_SLD_CRED_ST_TRANSPORTAR', 'DEB_ESP_ST'],
    'H001': ['IND_MOV'],
    'H005': ['DT_INV', 'VL_INV', 'MOT_INV'],
    'H010': ['COD_ITEM', 'UNID', 'QTD', 'VL_UNIT', 'VL_ITEM', 'IND_PROP', 'COD_PART', 'TXT_COMPL', 'COD_CTA', 'VL_ITEM_IR'],
    'K001': ['IND_MOV'],
    'K010': ['DT_INI_APUR', 'DT_FIN_APUR'],
    'K200': ['DT_EST', 'COD_ITEM', 'QTD', 'IND_EST', 'COD_PART'],
    'K220': ['DT_MOV', 'COD_ITEM_ORI', 'COD_ITEM_DEST', 'QTD', 'QTD_DEST'],
    'K230': ['DT_INI_OS', 'DT_FIN_OS', 'COD_DOC_OS', 'COD_ITEM_ORI', 'QTD_ENC_OS'],
    'K235': ['DT_SAIDA', 'COD_ITEM', 'QTD', 'COD_INS_SUBST'],
    'K250': ['DT_PROD', 'COD_ITEM', 'QTD'],
    'K255': ['DT_CONS', 'COD_ITEM', 'QTD', 'COD_INS_SUBST'],
    'K260': ['COD_OP_OS', 'COD_ITEM', 'DT_SAIDA', 'QTD_SAIDA', 'DT_RET', 'QTD_RET'],
    'K265': ['COD_ITEM', 'QTD_CONS', 'QTD_RET'],
    'K270': ['DT_INI_AP', 'DT_FIN_AP', 'COD_OP_OS', 'COD_ITEM', 'QTD_COR_POS', 'QTD_COR_NEG', 'ORIGEM'],
    'K275': ['COD_ITEM', 'QTD_COR_POS', 'QTD_COR_NEG', 'ORIGEM'],
    'K280': ['DT_EST', 'COD_ITEM', 'QTD_COR_POS', 'QTD_COR_NEG', 'IND_EST', 'COD_PART'],
    '2001': ['IND_MOV'],
    '2010': ['IND_ATIV', 'VL_REC', 'CST_PIS', 'VL_DESC_PIS', 'ALIQ_PIS', 'VL_CONT_APUR', 'VL_AJ_ACRES', 'VL_AJ_REDUC', 'VL_CONT_DEV', 'VL_OUT_DED', 'VL_CONT_EXT', 'VL_MUL', 'VL_JUR', 'DT_RECOL'],
    '1001': ['IND_MOV'],
    '1010': ['IND_EXP', 'IND_CCRF', 'IND_COMB', 'IND_USINA', 'IND_VA', 'IND_EE', 'IND_CART', 'IND_FORM', 'IND_AER', 'IND_GIAF1', 'IND_GIAF3', 'IND_GIAF4']
}

# Mapeamento de registros pais para filhos (para hierarquia)
CHILD_RECORDS_MAP: Dict[str, List[str]] = {
    'C100': ['C170', 'C190', 'C110', 'C113', 'C120', 'C195', 'C197'],
    'C500': ['C590', 'C510'],
    'D100': ['D190', 'D110'],
    'D500': ['D590', 'D510'],
    'E110': ['E111', 'E112', 'E113', 'E116'],
    'E210': ['E220', 'E230', 'E240', 'E250'],
    'H005': ['H010', 'H020'],
    'K010': ['K200', 'K220', 'K230', 'K235', 'K250', 'K255', 'K260', 'K265', 'K270', 'K275', 'K280']
}

# ============================================================================
# ESTRUTURAS DE DADOS
# ============================================================================
@dataclass
class SpedSummaryData:
    """Dados de resumo do SPED por CFOP"""
    cfop_entrada: DefaultDict[str, float] = field(default_factory=lambda: defaultdict(float))
    cfop_saida: DefaultDict[str, float] = field(default_factory=lambda: defaultdict(float))
    icms_base_entrada: DefaultDict[str, float] = field(default_factory=lambda: defaultdict(float))
    icms_base_saida: DefaultDict[str, float] = field(default_factory=lambda: defaultdict(float))
    icms_value_entrada: DefaultDict[str, float] = field(default_factory=lambda: defaultdict(float))
    icms_value_saida: DefaultDict[str, float] = field(default_factory=lambda: defaultdict(float))
    total_entrada: float = 0.0
    total_saida: float = 0.0
    total_icms_base_entrada: float = 0.0
    total_icms_base_saida: float = 0.0
    total_icms_value_entrada: float = 0.0
    total_icms_value_saida: float = 0.0


@dataclass
class SpedRecord:
    """Registro SPED individual para análises"""
    line_number: int
    tipo_registro_pai: str
    numero_doc: str
    cfop: str
    valor_operacao: float
    base_icms: float
    aliquota: float
    valor_icms: float
